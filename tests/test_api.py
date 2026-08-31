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
    assert state["profile_names"]["game"] == ["Default"]


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
