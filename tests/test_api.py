from __future__ import annotations

import pytest

from sonar.core.model import BusId, FilterStage
from sonar.daemon.api import ApiError, SonarApi
from sonar.engine import confgen
from sonar.engine.pwstate import GraphState


class FakeSupervisor:
    """Süpervizörün API'ye bakan yüzü. Ne yapıldığını kaydeder, PipeWire'a dokunmaz."""

    def __init__(self) -> None:
        self.state = GraphState()
        self.control = FakeControl()
        self.load_profile = None
        self.calls: list[tuple[str, object]] = []
        self.monitor = FakeMonitor()

    def apply_volumes(self, cfg, *, flush=True):
        self.calls.append(("volumes", None))

    def apply_target(self, cfg, target):
        self.calls.append(("target", target))
        return True

    def reconcile(self, cfg):
        self.calls.append(("reconcile", None))

    def start_monitor(self):
        self.calls.append(("monitor", None))

    def take_over_default_sink(self, cfg):
        self.calls.append(("takeover", None))

    def stop(self, **_kwargs):
        self.calls.append(("stop", None))

    @property
    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]


class FakeControl:
    def __init__(self) -> None:
        self.moved: list[tuple[int, str]] = []
        self.move_ok = True

    def move_stream(self, stream_id, node):
        self.moved.append((stream_id, node))
        return self.move_ok


class FakeMonitor:
    def wait_ready(self, timeout=5.0):
        return True


@pytest.fixture
def api(config_store):
    supervisor = FakeSupervisor()
    return SonarApi(config_store, supervisor, save_delay=0)  # gecikmesiz: her çağrı diske yazar


# --------------------------------------------------------------------------- okuma


def test_get_state_carries_everything_the_ui_needs(api):
    state = api.get_state()
    assert {"config", "profiles", "profile_names", "streams", "devices", "graph_ready"} <= set(
        state
    )
    assert [c["id"] for c in state["config"]["channels"]] == ["game", "chat", "media", "aux"]
    assert set(state["profiles"]) == set(api.config.profile_targets())
    # Gömülü presetler önce, kullanıcının kendi profilleri sonra.
    assert state["profile_names"]["game"][0] == "Flat"
    assert state["profile_names"]["game"][-1] == "Default"
    assert "Flat" in state["builtin_profiles"]["game"]


def test_get_devices_hides_our_own_virtual_nodes(api):
    api.supervisor.state.apply(
        [
            _node(1, "alsa_output.pci", "Audio/Sink", 2000),
            _node(2, "sonar_game_fx", "Audio/Source", 0),
        ]
    )
    names = [d["name"] for d in api.get_devices()]
    assert names == ["alsa_output.pci"]


def test_devices_are_sorted_by_priority(api):
    api.supervisor.state.apply(
        [
            _node(1, "alsa_output.hdmi", "Audio/Sink", 100),
            _node(2, "alsa_output.usb", "Audio/Sink", 2100),
        ]
    )
    assert [d["name"] for d in api.get_devices()] == ["alsa_output.usb", "alsa_output.hdmi"]


def _node(node_id, name, media_class, priority):
    return {
        "id": node_id,
        "type": "PipeWire:Interface:Node",
        "info": {
            "props": {
                "node.name": name,
                "media.class": media_class,
                "priority.session": priority,
            }
        },
    }


# --------------------------------------------------------------------------- canlı mı, yapısal mı
#
# Faz 4'ün en önemli ayrımı: hangi çağrı sesi keser, hangisi kesmez.


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("set_channel_volume", ("game", "personal", 0.5)),
        ("set_channel_mute", ("game", "stream", True)),
        ("set_master_volume", ("personal", 0.8)),
        ("set_mic_volume", ("mic", 0.6)),
        ("set_chatmix", (70.0,)),
    ],
)
def test_level_changes_are_live(api, call, args):
    getattr(api, call)(*args)
    assert api.supervisor.kinds == ["volumes"], "seviye değişimi asla yeniden inşa tetiklememeli"


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("set_filter_enabled", ("game", "eq", True)),
        ("set_filter_param", ("game", "gate", "threshold_db", -30.0)),
        ("set_eq_band", ("game", 2, "gain_db", 5.0)),
        ("set_eq_preamp", ("game", -3.0)),
        ("load_profile", ("game", "Default")),
    ],
)
def test_dsp_changes_are_live(api, call, args):
    getattr(api, call)(*args)
    assert api.supervisor.kinds == ["target"]
    assert api.supervisor.calls[0][1] == "game"


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("set_bus_device", ("personal", "alsa_output.usb")),
        ("set_mic_device", ("mic", "alsa_input.usb")),
        ("set_mic_monitor", ("mic", True)),
        ("set_mic_stream_send", ("mic", True)),
        ("set_band_count", ("game", 32)),
        ("add_channel", ("Music",)),
    ],
)
def test_structural_changes_rebuild(api, call, args):
    getattr(api, call)(*args)
    assert api.supervisor.kinds == ["reconcile"]


def test_mic_monitor_is_structural_because_it_adds_a_loopback(api):
    """Conf'a `sonar_mic_monitor` modülü ekleniyor; canlı yazımla halledilemez."""
    before = confgen.generate(api.config)
    api.set_mic_monitor("mic", True)
    assert confgen.generate(api.config) != before
    assert "sonar_mic_monitor" in confgen.generate(api.config)


# --------------------------------------------------------------------------- doğrulama
#
# Her geçersiz argüman `ApiError` olmalı: daemon çökmemeli, istemci sebebi anlamalı.


@pytest.mark.parametrize(
    ("call", "args", "code"),
    [
        ("set_channel_volume", ("yok", "personal", 0.5), "unknown_channel"),
        ("set_channel_volume", ("game", "hayali", 0.5), "unknown_bus"),
        ("set_channel_volume", ("game", "personal", 99.0), "invalid_value"),
        ("set_channel_volume", ("game", "personal", -1.0), "invalid_value"),
        ("set_mic_volume", ("yok", 0.5), "unknown_mic"),
        ("set_filter_enabled", ("game", "hayali", True), "unknown_stage"),
        ("set_filter_param", ("game", "gate", "yok", 1.0), "unknown_param"),
        ("set_eq_band", ("game", 99, "gain_db", 1.0), "unknown_band"),
        ("set_eq_band", ("game", 0, "yok", 1.0), "unknown_field"),
        ("set_eq_band", ("game", 0, "band_type", "hayali"), "unknown_field"),
        ("set_band_count", ("game", 7), "unsupported_band_count"),
        ("list_profiles", ("yok",), "unknown_target"),
        ("add_channel", ("",), "invalid_name"),
        ("add_channel", ("Game",), "duplicate_channel"),
        ("remove_channel", ("game",), "channel_protected"),
        ("remove_channel", ("yok",), "unknown_channel"),
        ("set_rule", ("hayali", "x", "game"), "unknown_match_key"),
        ("set_rule", ("binary", "  ", "game"), "invalid_pattern"),
        ("set_rule", ("binary", "x", "yok"), "unknown_channel"),
        ("remove_rule", ("binary", "yok-boyle-kural"), "unknown_rule"),
        ("delete_profile", ("game", "Default"), "profile_protected"),
        ("rename_profile", ("game", "YokBoyle", "Yeni"), "profile_not_renamed"),
        ("set_chatmix_config", (True, "yok", "chat"), "unknown_channel"),
        ("set_default_channel", ("yok",), "unknown_channel"),
    ],
)
def test_invalid_arguments_raise_api_errors(api, call, args, code):
    with pytest.raises(ApiError) as excinfo:
        getattr(api, call)(*args)
    assert excinfo.value.code == code
    assert excinfo.value.message


def test_deepfilter_is_refused_on_playback_channels(api):
    """Oynatma zincirinde gürültü engelleme yok; sessizce yok saymak yerine söylüyoruz."""
    with pytest.raises(ApiError) as excinfo:
        api.set_filter_enabled("game", "df", True)
    assert excinfo.value.code == "stage_not_in_chain"
    api.set_filter_enabled("mic", "df", True)  # mikrofonda sorun yok
    assert api.profile("mic").filter(FilterStage.DEEPFILTER).enabled is True


# --------------------------------------------------------------------------- profiller


def test_edits_persist_to_the_active_profile(api, config_store):
    """ "Kaydet"i unutmak ayarların kaybolması anlamına gelmemeli."""
    api.set_eq_band("game", 1, "gain_db", 7.5)
    assert api.profile("game").eq.bands[1].gain_db == 7.5
    assert config_store.load_profile("game", "Default").eq.bands[1].gain_db == 7.5


def test_save_profile_is_save_as(api, config_store):
    """Yeni adla yazar, aktif profili ona çevirir; eski profil o âna kadarki hâliyle kalır."""
    api.set_eq_band("game", 1, "gain_db", 7.5)
    api.save_profile("game", "CS2")
    assert api.config.channel("game").active_profile == "CS2"
    assert config_store.load_profile("game", "CS2").eq.bands[1].gain_db == 7.5

    api.set_eq_band("game", 1, "gain_db", 2.0)  # artık CS2'ye yazıyor
    assert config_store.load_profile("game", "CS2").eq.bands[1].gain_db == 2.0
    assert config_store.load_profile("game", "Default").eq.bands[1].gain_db == 7.5


def test_switching_profiles_swaps_the_working_copy(api):
    api.set_eq_band("game", 0, "gain_db", 4.0)
    api.save_profile("game", "Bass")
    api.set_eq_band("game", 0, "gain_db", 1.0)  # Bass artık 1.0
    api.load_profile("game", "Default")
    assert api.profile("game").eq.bands[0].gain_db == 4.0  # Default'a yazılmıştı
    api.load_profile("game", "Bass")
    assert api.profile("game").eq.bands[0].gain_db == 1.0


def test_rebuild_uses_the_in_memory_profile_not_the_disk(api, config_store):
    """Grafın yeniden kurulması kullanıcının kaydetmediği düzenlemesini silmemeli."""
    api.set_eq_band("game", 0, "gain_db", 9.0)  # kaydedilmedi
    provider = api.supervisor.load_profile
    assert provider is not None
    restored = provider("game", api.config.channel("game").active_profile)
    assert restored.eq.bands[0].gain_db == 9.0


def test_deleting_the_active_profile_falls_back_to_default(api):
    api.save_profile("game", "Gecici")
    assert api.config.channel("game").active_profile == "Gecici"
    api.delete_profile("game", "Gecici")
    assert api.config.channel("game").active_profile == "Default"


def test_rename_follows_the_active_profile(api):
    api.save_profile("game", "Eski")
    api.rename_profile("game", "Eski", "Yeni")
    assert api.config.channel("game").active_profile == "Yeni"
    assert api.profile("game").name == "Yeni"


def test_favorite_slot_persists(api, config_store):
    api.save_profile("game", "CS2")
    api.set_profile_favorite("game", "CS2", 3)
    assert config_store.load_profile("game", "CS2").favorite_slot == 3


# --------------------------------------------------------------------------- kanallar


def test_added_channel_gets_an_id_and_default_profile(api, config_store):
    channel_id = api.add_channel("Voice Chat", "#ff0000")
    assert channel_id == "voice_chat"
    assert api.config.channel("voice_chat").builtin is False
    assert config_store.paths.profile_file("voice_chat", "Default").exists()


def test_added_channel_can_be_removed(api):
    channel_id = api.add_channel("Music")
    api.remove_channel(channel_id)
    assert api.config.channel(channel_id) is None


# --------------------------------------------------------------------------- kurallar


def test_rule_is_added_then_updated_in_place(api):
    api.set_rule("binary", "cs2", "game")
    assert len(api.list_rules()) == len(api.config.rules)
    count = len(api.config.rules)
    api.set_rule("binary", "cs2", "chat")  # aynı desen → güncelle, kopyalama
    assert len(api.config.rules) == count
    assert next(r for r in api.config.rules if r.pattern == "cs2").channel_id == "chat"


def test_rule_can_be_removed(api):
    api.set_rule("binary", "cs2", "game")
    api.remove_rule("binary", "cs2")
    assert not [r for r in api.config.rules if r.pattern == "cs2"]


# --------------------------------------------------------------------------- akış taşıma


def test_move_stream_targets_the_channel_sink(api):
    api.move_stream(77, "chat")
    assert api.supervisor.control.moved == [(77, "sonar_chat")]


def test_failed_move_is_reported(api):
    api.supervisor.control.move_ok = False
    with pytest.raises(ApiError) as excinfo:
        api.move_stream(77, "chat")
    assert excinfo.value.code == "move_failed"


# --------------------------------------------------------------------------- ChatMix


def test_chatmix_is_clamped(api):
    api.set_chatmix(500.0)
    assert api.config.chatmix.value == 100.0
    api.set_chatmix(-5.0)
    assert api.config.chatmix.value == 0.0


# --------------------------------------------------------------------------- kalıcılık


def test_config_is_persisted(api, config_store):
    api.set_channel_volume("game", "personal", 0.25)
    assert config_store.load().channel("game").personal.volume == 0.25


def test_reload_picks_up_hand_edits(api, config_store):
    path = config_store.paths.config_file
    api.flush_save()
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'default_channel = "media"', 'default_channel = "game"'
        ),
        encoding="utf-8",
    )
    api.reload()
    assert api.config.settings.default_channel == "game"
    assert "reconcile" in api.supervisor.kinds


# --------------------------------------------------------------------------- olay yayını


def test_changes_are_announced(config_store):
    seen: list[dict] = []
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0, on_change=seen.append)
    api.set_channel_volume("game", "personal", 0.5)
    api.set_eq_band("game", 0, "gain_db", 3.0)
    assert [d["kind"] for d in seen] == ["channel_volume", "eq_band"]
    assert seen[0]["channel"] == "game" and seen[0]["bus"] == "personal"


def test_a_failing_listener_does_not_break_the_api(config_store):
    def boom(_delta):
        raise RuntimeError("dinleyici patladı")

    api = SonarApi(config_store, FakeSupervisor(), save_delay=0, on_change=boom)
    api.set_channel_volume("game", "personal", 0.5)  # yükseltmemeli
    assert api.config.channel("game").personal.volume == 0.5


def test_bus_enum_round_trips(api):
    api.set_channel_volume("game", BusId.STREAM.value, 0.3)
    assert api.config.channel("game").send(BusId.STREAM).volume == 0.3


def test_internal_loopbacks_are_hidden_from_the_stream_list(api):
    """Kullanıcı Sonar'ın kendi tesisatını değil, gerçek uygulamaları görmeli."""
    api.supervisor.state.apply(
        [
            {
                "id": 1,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "sonar_game_to_personal",
                        "media.class": "Stream/Output/Audio",
                    }
                },
            },
            {
                "id": 2,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "firefox",
                        "media.class": "Stream/Output/Audio",
                        "application.name": "Firefox",
                    }
                },
            },
        ]
    )
    assert [s["app_name"] for s in api.get_streams()] == ["Firefox"]
    assert len(api.supervisor.state.streams) == 2, "envanterin kendisi eksilmemeli"


def test_conflicting_system_processor_is_detected(api):
    """EasyEffects servis kipinde çıkışımızı kendi zincirine çekiyor ve cihaz seçimini
    sessizce yok sayıyor; kullanıcıya söylemeliyiz."""
    assert api.conflicts() == []
    api.supervisor.state.apply(
        [
            {
                "id": 1,
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"node.name": "easyeffects_sink", "media.class": "Audio/Sink"}},
            }
        ]
    )
    conflicts = api.conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["name"] == "EasyEffects"
    assert "EasyEffects" in conflicts[0]["message"]
    assert api.get_state()["conflicts"] == conflicts


# --------------------------------------------------------------------------- yönlendirme


def _stream_obj(api, stream_id, name, **props):
    api.supervisor.state.apply(
        [
            {
                "id": stream_id,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": name,
                        "media.class": "Stream/Output/Audio",
                        **props,
                    }
                },
            }
        ]
    )


def test_sync_routing_places_new_streams(api):
    _stream_obj(api, 10, "firefox", **{"application.process.binary": "firefox"})
    decisions = api.sync_routing()
    assert [(d.stream_id, d.channel_id) for d in decisions] == [(10, "media")]
    assert api.supervisor.control.moved == [(10, "sonar_media")]


def test_manual_move_stops_the_router_from_touching_it(api):
    _stream_obj(api, 10, "firefox", **{"application.process.binary": "firefox"})
    api.move_stream(10, "game")
    assert api.sync_routing() == []
    assert api.supervisor.control.moved == [(10, "sonar_game")]


def test_move_with_remember_creates_a_rule_from_the_binary(api):
    _stream_obj(api, 10, "cs2", **{"application.process.binary": "cs2_linux64"})
    api.move_stream(10, "game", remember=True)
    rule = next(r for r in api.config.rules if r.pattern == "cs2_linux64")
    assert (rule.match_key, rule.channel_id) == ("binary", "game")


def test_remember_falls_back_to_the_application_name(api):
    _stream_obj(api, 11, "wine", **{"application.name": "Arc Raiders"})
    api.move_stream(11, "game", remember=True)
    rule = next(r for r in api.config.rules if r.pattern == "Arc Raiders")
    assert rule.match_key == "app_name"


def test_remember_refuses_an_unidentifiable_stream(api):
    _stream_obj(api, 12, "anonim")
    with pytest.raises(ApiError) as excinfo:
        api.move_stream(12, "game", remember=True)
    assert excinfo.value.code == "not_identifiable"


def test_remember_on_a_vanished_stream_is_reported(api):
    _stream_obj(api, 13, "mpv", **{"application.process.binary": "mpv"})
    api.supervisor.state.apply([{"id": 13, "type": "PipeWire:Interface:Node", "info": None}])
    with pytest.raises(ApiError) as excinfo:
        api.move_stream(13, "game", remember=True)
    assert excinfo.value.code == "unknown_stream"


def test_routing_decisions_are_announced(config_store):
    seen: list[dict] = []
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0, on_change=seen.append)
    _stream_obj(api, 10, "firefox", **{"application.process.binary": "firefox"})
    api.sync_routing()
    assert seen[-1]["kind"] == "stream_routed"
    assert seen[-1]["channel"] == "media"


def test_structural_change_resets_the_router(api):
    """Node id'leri değişti; hangi akışın nereye gittiğine dair kayıt geçersiz."""
    _stream_obj(api, 10, "firefox", **{"application.process.binary": "firefox"})
    api.sync_routing()
    assert api.router.decided
    api.set_mic_monitor("mic", True)
    assert api.router.decided == {}


def test_streams_carry_their_channel(api):
    """Arayüz uygulamanın hangi şeritte görüneceğini buradan öğreniyor.

    `target.object`'ten okunamıyor: `pw-metadata` ile taşıdığımızda hedef metadata
    deposunda kalıyor, node'un props'una yazılmıyor.
    """
    _stream_obj(api, 10, "firefox", **{"application.process.binary": "firefox"})
    api.sync_routing()
    row = next(s for s in api.get_streams() if s["app_binary"] == "firefox")
    assert row["channel"] == "media"


def test_untouched_stream_has_no_channel(api):
    _stream_obj(api, 11, "mpv", **{"application.process.binary": "mpv"})
    assert next(s for s in api.get_streams() if s["id"] == 11)["channel"] == ""


# --------------------------------------------------------------------------- presetler
#
# Gömülü presetler salt okunur. Düzenlemeler aktif profile otomatik kalıcı olduğu için,
# kopya alınmasaydı bir preset'i kurcalamak preset'in kendisini bozardı.


def test_builtin_presets_are_listed_first(api):
    names = api.list_profiles("game")
    assert names[:2] == ["Flat", "FPS Footsteps"]
    assert "Default" in names


def test_mic_gets_its_own_catalogue(api):
    assert "Broadcast" in api.list_profiles("mic")
    assert "FPS Footsteps" not in api.list_profiles("mic")


def test_loading_a_preset_does_not_write_it_to_disk(api, config_store):
    api.load_profile("game", "Bass Boost")
    assert api.profile("game").name == "Bass Boost"
    assert not config_store.paths.profile_file("game", "Bass Boost").exists()


def test_editing_a_preset_creates_a_copy(api, config_store):
    api.load_profile("game", "Bass Boost")
    api.set_eq_band("game", 0, "gain_db", 3.0)

    assert api.config.channel("game").active_profile == "Bass Boost (özel)"
    assert config_store.paths.profile_file("game", "Bass Boost (özel)").exists()
    # Preset'in kendisi bozulmamalı.
    fresh = api.list_profiles("game")
    assert "Bass Boost" in fresh
    api.load_profile("game", "Bass Boost")
    assert api.profile("game").eq.bands[0].gain_db == 0.0


def test_repeated_edits_do_not_pile_up_copies(api):
    api.load_profile("game", "Bass Boost")
    api.set_eq_band("game", 0, "gain_db", 3.0)
    api.set_eq_band("game", 1, "gain_db", 4.0)
    copies = [n for n in api.list_profiles("game") if "özel" in n]
    assert copies == ["Bass Boost (özel)"]


def test_copy_names_do_not_collide(api):
    api.load_profile("game", "Bass Boost")
    api.set_eq_band("game", 0, "gain_db", 3.0)
    api.load_profile("game", "Bass Boost")
    api.set_eq_band("game", 0, "gain_db", 5.0)
    copies = {n for n in api.list_profiles("game") if "özel" in n}
    assert copies == {"Bass Boost (özel)", "Bass Boost (özel 2)"}


def test_editing_a_user_profile_does_not_copy(api):
    api.set_eq_band("game", 0, "gain_db", 3.0)
    assert api.config.channel("game").active_profile == "Default"
    assert not [n for n in api.list_profiles("game") if "özel" in n]


def test_a_copy_is_announced(config_store):
    seen: list[dict] = []
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0, on_change=seen.append)
    api.load_profile("game", "Flat")
    api.set_eq_enabled("game", True)
    assert any(d["kind"] == "profile_copied" for d in seen)


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("save_profile", ("game", "Bass Boost")),
        ("delete_profile", ("game", "Bass Boost")),
        ("rename_profile", ("game", "Bass Boost", "X")),
        ("rename_profile", ("game", "Default", "Bass Boost")),
    ],
)
def test_presets_are_protected(api, call, args):
    with pytest.raises(ApiError) as excinfo:
        getattr(api, call)(*args)
    assert excinfo.value.code == "profile_readonly"


def test_filter_edits_also_trigger_the_copy(api):
    api.load_profile("mic", "Broadcast")
    api.set_filter_param("mic", "comp", "ratio", 6.0)
    assert api.config.mic("mic").active_profile == "Broadcast (özel)"


def test_state_marks_which_profiles_are_builtin(api):
    state = api.get_state()
    assert "Bass Boost" in state["builtin_profiles"]["game"]
    assert "Default" not in state["builtin_profiles"]["game"]


def test_rebuild_uses_the_preset_when_it_is_active(api):
    """Graf yeniden kurulunca aktif preset diskte olmadığı için kaybolmamalı."""
    api.load_profile("game", "FPS Footsteps")
    provider = api.supervisor.load_profile
    restored = provider("game", "FPS Footsteps")
    assert restored.eq.enabled is True
    assert restored.eq.bands[6].gain_db > 4.0


# --------------------------------------------------------------------------- içe/dışa aktarma

AUTOEQ_TEXT = """\
Preamp: -5.0 dB
Filter 1: ON LSC Fc 100 Hz Gain 5.0 dB Q 0.70
Filter 2: ON PK Fc 3000 Hz Gain -4.0 dB Q 2.00
"""


def test_import_creates_and_activates_a_profile(api, config_store):
    result = api.import_profile("game", AUTOEQ_TEXT, "HD650")
    assert result["name"] == "HD650"
    assert result["source"] == "autoeq"
    assert api.config.channel("game").active_profile == "HD650"
    assert config_store.paths.profile_file("game", "HD650").exists()
    assert api.profile("game").eq.preamp_db == -5.0


def test_import_applies_to_the_graph(api):
    api.import_profile("game", AUTOEQ_TEXT, "HD650")
    assert ("target", "game") in api.supervisor.calls


def test_import_never_overwrites_a_preset(api):
    result = api.import_profile("game", AUTOEQ_TEXT, "Bass Boost")
    assert result["name"] == "Bass Boost (özel)"
    assert "Bass Boost" in api.builtin_names("game")


def test_import_reports_dropped_bands(api):
    lines = [f"Filter {i}: ON PK Fc {50 + i * 90} Hz Gain 2 dB Q 1" for i in range(40)]
    result = api.import_profile("game", "\n".join(lines), "Çok")
    assert result["dropped"] == 8
    assert result["warnings"]


def test_import_rejects_garbage(api):
    with pytest.raises(ApiError) as excinfo:
        api.import_profile("game", "bu bir EQ dosyası değil")
    assert excinfo.value.code == "import_failed"


def test_export_round_trips_through_import(api):
    api.set_eq_band("game", 3, "gain_db", 5.0)
    api.set_eq_enabled("game", True)
    text = api.export_profile("game")
    api.import_profile("chat", text, "Kopya")
    assert api.profile("chat").eq.bands[3].gain_db == 5.0


def test_export_autoeq_is_text(api):
    api.set_eq_enabled("game", True)
    text = api.export_profile("game", autoeq=True)
    assert text.startswith("Preamp:")
    assert "Filter 1:" in text


def test_export_of_a_named_profile(api):
    api.save_profile("game", "CS2")
    api.load_profile("game", "Default")
    assert "CS2" in api.export_profile("game", "CS2")


def test_copy_profile(api):
    api.set_eq_band("game", 0, "gain_db", 4.0)
    api.copy_profile("game", "Kopyam")
    assert api.config.channel("game").active_profile == "Kopyam"
    assert api.profile("game").eq.bands[0].gain_db == 4.0


def test_copy_refuses_a_preset_name(api):
    with pytest.raises(ApiError) as excinfo:
        api.copy_profile("game", "Movie")
    assert excinfo.value.code == "profile_readonly"


def test_reset_flattens_the_active_profile(api):
    api.set_eq_enabled("game", True)
    api.set_eq_band("game", 4, "gain_db", 9.0)
    api.set_filter_enabled("game", "gate", True)
    api.reset_profile("game")
    profile = api.profile("game")
    assert profile.eq.enabled is False
    assert profile.eq.bands[4].gain_db == 0.0
    assert profile.filter(FilterStage.GATE).enabled is False
    assert profile.name == "Default", "sıfırlama adı korumalı"


def test_reset_on_a_preset_copies_first(api):
    api.load_profile("game", "Bass Boost")
    api.reset_profile("game")
    assert api.config.channel("game").active_profile == "Bass Boost (özel)"


# --------------------------------------------------------------------------- ChatMix


def test_chatmix_accepts_several_channels_per_side(api):
    api.set_chatmix_config(True, "game", "chat,media")
    from sonar.engine.supervisor import chatmix_gains

    api.set_chatmix(100.0)
    gains = chatmix_gains(api.config)
    assert gains["chat"] == pytest.approx(1.0)
    assert gains["media"] == pytest.approx(1.0)
    assert gains["game"] < 0.05


def test_chatmix_config_rejects_an_unknown_channel_in_a_list(api):
    with pytest.raises(ApiError) as excinfo:
        api.set_chatmix_config(True, "game", "chat,yok")
    assert excinfo.value.code == "unknown_channel"


def test_chatmix_config_rejects_an_empty_side(api):
    with pytest.raises(ApiError) as excinfo:
        api.set_chatmix_config(True, "game", "  ")
    assert excinfo.value.code == "invalid_value"


def test_state_exposes_chatmix_gains(api):
    api.set_chatmix(100.0)
    gains = api.get_state()["chatmix_gains"]
    assert gains["game"] < 0.05
    assert gains["chat"] == pytest.approx(1.0)


def test_state_lists_headsets(api):
    assert isinstance(api.get_state()["headsets"], list)
