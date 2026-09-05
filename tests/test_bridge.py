from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6.QtCore")

from PySide6.QtCore import QCoreApplication

from sonar.core.model import default_config
from sonar.core.serde import to_jsonable
from sonar.gui.bridge import (
    ChannelModel,
    SonarBridge,
    channel_rows,
    device_rows,
    stream_rows,
)


@pytest.fixture(scope="session")
def qt_app():
    """Qt nesneleri bir uygulama örneği olmadan kurulamıyor."""
    return QCoreApplication.instance() or QCoreApplication([])


def make_state(**overrides) -> dict:
    state = {
        "config": to_jsonable(default_config()),
        "profile_names": {"game": ["Default", "CS2"]},
        "streams": [],
        "devices": [],
        "conflicts": [],
        "graph_ready": True,
    }
    state.update(overrides)
    return state


# --------------------------------------------------------------------------- saf dönüşümler


def test_channel_rows_are_in_mixer_order():
    rows = channel_rows(make_state())
    assert [r["id"] for r in rows] == ["game", "chat", "media", "aux", "mic", "stream_mic"]


def test_mic_row_carries_monitor_as_the_personal_side():
    """Mikrofonun 'kulaklık' fader'ı yan tondur; kapalıyken susturulmuş görünür."""
    row = next(r for r in channel_rows(make_state()) if r["kind"] == "mic")
    assert row["personalMuted"] is True  # varsayılan: yan ton kapalı
    assert row["streamMuted"] is False


def test_a_shared_mic_chain_is_not_a_strip():
    """Kendi DSP'si olmayan bir giriş kanalı başka bir zincirin kopyası; ayrı şerit değil."""
    state = make_state()
    for mic in state["config"]["mic_chains"]:
        if mic["id"] == "stream_mic":
            mic["share_chain_with_mic"] = True
    assert "stream_mic" not in [r["id"] for r in channel_rows(state)]


def test_profiles_reach_the_row():
    """Gömülü presetler `builtin` bayrağıyla geliyor; arayüz kilit işareti koyuyor."""
    state = make_state(builtin_profiles={"game": ["Default"]})
    row = channel_rows(state)[0]
    assert row["profiles"] == [
        {"name": "Default", "builtin": True},
        {"name": "CS2", "builtin": False},
    ]


def test_channel_without_profiles_gets_an_empty_list():
    row = channel_rows(make_state())[1]
    assert row["profiles"] == []


def test_stream_rows_use_the_channel_from_the_daemon():
    state = make_state(
        streams=[
            {"id": 1, "app_name": "Firefox", "app_binary": "firefox", "channel": "media"},
        ]
    )
    assert stream_rows(state) == [
        {
            "id": 1,
            "label": "Firefox",
            "binary": "firefox",
            "channel": "media",
            "direction": "out",
            "capturesSink": False,
        }
    ]


def test_stream_rows_fall_back_to_the_target_node():
    """Daemon kanalı bilmiyorsa uygulamanın kendi hedefine bakılır."""
    state = make_state(
        streams=[{"id": 2, "app_name": "OBS", "target_node": "sonar_game", "channel": ""}]
    )
    assert stream_rows(state)[0]["channel"] == "game"


def test_capture_streams_are_shown_with_their_direction():
    """Faz 21: aynı uygulama hem çıkış hem giriş şeridinde görünebilmeli.

    Eskiden yakalama akışları buradan atılıyordu ve mikrofon kullanan uygulamalar
    arayüzde hiç görünmüyordu.
    """
    state = make_state(
        streams=[
            {"id": 3, "app_name": "OBS", "is_capture": True, "channel": "mic"},
            {"id": 4, "app_name": "OBS", "is_capture": False, "channel": "media"},
        ]
    )
    rows = stream_rows(state)
    assert [(r["id"], r["direction"], r["channel"]) for r in rows] == [
        (3, "in", "mic"),
        (4, "out", "media"),
    ]


def test_a_capture_stream_falls_back_to_its_mic_chain_node():
    state = make_state(
        streams=[{"id": 3, "app_name": "OBS", "is_capture": True, "target_node": "sonar_mic"}]
    )
    assert stream_rows(state)[0]["channel"] == "mic"


def test_stream_label_falls_back():
    state = make_state(streams=[{"id": 4, "media_name": "Bir şey"}])
    assert stream_rows(state)[0]["label"] == "Bir şey"
    state = make_state(streams=[{"id": 5}])
    assert stream_rows(state)[0]["label"] == "#5"


def test_device_rows_start_with_the_system_default():
    state = make_state(
        devices=[
            {"name": "alsa_output.usb", "description": "Arctis 7", "is_source": False},
            {"name": "alsa_input.usb", "description": "Fifine", "is_source": True},
        ]
    )
    sinks = device_rows(state, sources=False)
    assert sinks[0] == {"name": "", "label": "Sistem varsayılanı", "isSource": False}
    assert [d["label"] for d in sinks[1:]] == ["Arctis 7"]
    assert [d["label"] for d in device_rows(state, sources=True)[1:]] == ["Fifine"]


def test_device_without_description_falls_back_to_its_name():
    state = make_state(devices=[{"name": "alsa_output.hdmi", "is_source": False}])
    assert device_rows(state, sources=False)[1]["label"] == "alsa_output.hdmi"


# --------------------------------------------------------------------------- model


def test_model_exposes_keys_as_roles(qt_app):
    model = ChannelModel()
    model.replace(channel_rows(make_state()))
    roles = {bytes(v).decode() for v in model.roleNames().values()}
    assert {"id", "name", "color", "personalVolume"} <= roles
    assert model.rowCount() == 6
    assert model.get(0)["id"] == "game"


def test_same_length_update_does_not_reset_the_model(qt_app):
    """Sıfırlamak tüm delegeleri yeniden kurar ve sürükleme takılır."""
    model = ChannelModel()
    model.replace(channel_rows(make_state()))
    resets = []
    model.modelAboutToBeReset.connect(lambda: resets.append(1))
    rows = channel_rows(make_state())
    rows[0]["personalVolume"] = 0.5
    model.replace(rows)
    assert resets == []
    assert model.get(0)["personalVolume"] == 0.5


def test_length_change_resets_the_model(qt_app):
    model = ChannelModel()
    model.replace(channel_rows(make_state()))
    resets = []
    model.modelAboutToBeReset.connect(lambda: resets.append(1))
    model.replace(channel_rows(make_state())[:2])
    assert resets == [1]


def test_index_of(qt_app):
    model = ChannelModel()
    model.replace(channel_rows(make_state()))
    assert model.index_of("id", "media") == 2
    assert model.index_of("id", "yok") == -1


def test_get_out_of_range_is_empty(qt_app):
    assert ChannelModel().get(5) == {}


# --------------------------------------------------------------------------- köprü


class FakeClient:
    def __init__(self, state: dict) -> None:
        self.state = state
        self.calls: list[tuple] = []
        self.fail = False

    def call(self, method, *args):
        if self.fail:
            raise RuntimeError("daemon gitti")
        self.calls.append((method, args))
        return self.state if method == "GetState" else None


@pytest.fixture
def bridge(qt_app):
    client = FakeClient(make_state())
    obj = SonarBridge(client)
    obj.apply_state(client.state)
    return obj


def test_bridge_fills_its_models(bridge):
    assert bridge.channels.rowCount() == 6
    assert bridge.sinks.rowCount() == 1  # yalnızca "sistem varsayılanı"
    assert bridge.chatmix == 50.0


def test_revision_bumps_so_qml_bindings_refresh(bridge):
    """QML'de `rowCount()` bir özellik değil; binding'ler bu sayaca bakıyor."""
    before = bridge.revision
    bridge.apply_state(make_state())
    assert bridge.revision > before


def test_optimistic_update_is_immediate(bridge):
    bridge.setChannelVolume("game", "personal", 0.25)
    assert bridge.channels.get(0)["personalVolume"] == 0.25
    assert bridge._client.calls[-1] == ("SetChannelVolume", ("game", "personal", 0.25))


def test_mute_change_is_announced_on_the_row(bridge):
    """Şerit artık satırı model rollerinden okuyor; `dataChanged` ona ulaşmalı.

    Eskiden `Mixer.qml` şeride `channels.get(index)` ile donmuş bir sözlük kopyası
    veriyordu ve model ne yayınlarsa yayınlasın arayüz güncellenmiyordu — mute
    düğmesinin "çalışmaması" buydu (test turu 2).
    """
    seen: list[int] = []
    bridge.channels.dataChanged.connect(lambda top, _bottom, _roles: seen.append(top.row()))

    state = make_state()
    state["config"]["channels"][0]["sends"]["stream"]["muted"] = True
    bridge.apply_state(state)

    assert 0 in seen
    assert bridge.channels.get(0)["streamMuted"] is True


def test_row_roles_cover_everything_the_strip_reads(bridge):
    """`ChannelStrip` bu rolleri `required property` olarak istiyor; biri eksikse
    delege hiç kurulmaz ve mikser boş kalır."""
    needed = {
        "id", "name", "color", "icon", "activeProfile", "profiles",
        "personalVolume", "personalMuted", "streamVolume", "streamMuted", "kind",
    }
    assert needed <= set(ChannelModel.keys)
    assert needed <= set(bridge.channels.get(0))


def test_daemon_echo_does_not_undo_a_fresh_drag(bridge):
    """Sürükleme sırasında gelen eski değer fader'ı geri zıplatmamalı."""
    bridge.setChannelVolume("game", "personal", 0.25)
    bridge.apply_state(make_state())  # daemon hâlâ 1.0 diyor
    assert bridge.channels.get(0)["personalVolume"] == 0.25


def test_hold_expires(qt_app):
    client = FakeClient(make_state())
    obj = SonarBridge(client, hold_ms=0)
    obj.apply_state(client.state)
    obj.setChannelVolume("game", "personal", 0.25)
    obj.apply_state(make_state())
    assert obj.channels.get(0)["personalVolume"] == 1.0


def test_meter_values_survive_a_state_refresh(bridge):
    """Seviyeler kanal satırlarında değil ayrı tutuluyor; tam durum yenilemesi silmemeli."""
    bridge.onLevelsUpdated(
        json.dumps(
            {
                "sonar_game": {
                    "peak_db": -12.0,
                    "rms_db": -15.0,
                    "hold_db": -10.0,
                    "clipped": False,
                }
            }
        )
    )
    assert bridge.levelOf("game")["peak_db"] == -12.0
    bridge.apply_state(make_state())
    assert bridge.levelOf("game")["peak_db"] == -12.0, "metre değeri kaybolmamalı"


def test_levels_bump_only_the_levels_counter(bridge):
    """`revision` saniyede 20 kez artsaydı her şeridin tamamı yeniden değerlendirilirdi."""
    before_revision, before_levels = bridge.revision, bridge.levelsRevision
    bridge.onLevelsUpdated(json.dumps({"sonar_game": {"peak_db": -3.0, "hold_db": -3.0}}))
    assert bridge.revision == before_revision
    assert bridge.levelsRevision == before_levels + 1


def test_levels_for_the_mic_use_its_own_node(bridge):
    bridge.onLevelsUpdated(
        json.dumps(
            {"sonar_mic": {"peak_db": -20.0, "rms_db": -22.0, "hold_db": -18.0, "clipped": True}}
        )
    )
    assert bridge.levelOf("mic")["peak_db"] == -20.0
    assert bridge.levelOf("mic")["clipped"] is True


def test_a_channel_without_a_measurement_reads_the_floor(bridge):
    assert bridge.levelOf("game") == {"peak_db": -60.0, "hold_db": -60.0, "clipped": False}


def test_malformed_levels_payload_is_ignored(bridge):
    bridge.onLevelsUpdated("bu json değil")  # yükseltmemeli


def test_streams_signal_updates_only_streams_and_devices(bridge):
    payload = json.dumps(
        {
            "streams": [{"id": 9, "app_name": "mpv", "channel": "media"}],
            "devices": [{"name": "alsa_output.usb", "description": "Arctis", "is_source": False}],
        }
    )
    bridge.onStreamsChanged(payload)
    assert bridge.streams.rowCount() == 1
    assert bridge.sinks.rowCount() == 2


def test_connection_lost_when_a_call_fails(bridge):
    bridge._client.fail = True
    bridge.setChannelVolume("game", "personal", 0.5)
    assert bridge.connected is False


def test_start_connects(qt_app):
    client = FakeClient(make_state())
    obj = SonarBridge(client)
    obj.start()
    assert obj.connected is True
    assert obj.channels.rowCount() == 6


def test_start_without_a_daemon_stays_disconnected(qt_app):
    obj = SonarBridge(None)
    obj.start()
    assert obj.connected is False


def test_move_stream_updates_the_model_immediately(bridge):
    bridge.onStreamsChanged(
        json.dumps({"streams": [{"id": 9, "app_name": "mpv", "channel": "media"}], "devices": []})
    )
    bridge.moveStream(9, "game", True)
    assert bridge.streams.get(0)["channel"] == "game"
    assert bridge._client.calls[-1] == ("MoveStream", (9, "game", True))


def test_chatmix_is_optimistic(bridge):
    bridge.setChatMix(80.0)
    assert bridge.chatmix == 80.0


def test_masters_expose_buses_and_mic(bridge):
    masters = bridge.masters
    assert masters["personal"]["name"] == "Personal Mix"
    assert masters["stream"]["name"] == "Stream Mix"
    assert masters["mic"]["id"] == "mic"


# --------------------------------------------------------------------------- FX sayfası


def profile_state() -> dict:
    from sonar.core.model import DEFAULT_FILTER_PARAMS, EffectSlot, FilterStage, default_profile

    profile = default_profile()
    # Şema 7: yeni profilde yalnızca ekolayzer var. Slot testleri için bir gate ekliyoruz.
    profile.effects.append(
        EffectSlot(
            kind=FilterStage.GATE,
            slot="gate",
            enabled=False,
            params=dict(DEFAULT_FILTER_PARAMS[FilterStage.GATE]),
        )
    )
    return make_state(
        profiles={"game": to_jsonable(profile), "mic": to_jsonable(default_profile())}
    )


@pytest.fixture
def fx(qt_app):
    client = FakeClient(profile_state())
    obj = SonarBridge(client)
    obj.apply_state(client.state)
    return obj


def test_eq_json_is_parseable_by_the_curve(fx):
    from sonar.gui.eqcurve import eq_from_json

    eq = eq_from_json(fx.eqJson("game"))
    assert len(eq.bands) == 10
    assert eq.enabled is False


def test_eq_json_for_unknown_target_is_empty(fx):
    assert json.loads(fx.eqJson("yok")) == {}


def test_filter_of_returns_the_slot(fx):
    gate = fx.filterOf("game", "gate")
    assert gate["enabled"] is False
    assert gate["params"]["threshold_db"] == -40.0
    assert fx.filterOf("game", "yok") == {}


def test_effects_of_returns_the_chain_in_signal_order(fx):
    assert [e["slot"] for e in fx.effectsOf("game")] == ["eq", "gate"]
    assert [e["slot"] for e in fx.effectsOf("mic")] == ["eq"]


def test_patching_an_unknown_slot_does_not_invent_one(fx):
    """Uydurma bir slot arayüzü daemon'la uyumsuz bırakırdı."""
    before = fx.revision
    fx.setFilterEnabled("game", "yok", True)
    assert fx.filterOf("game", "yok") == {}
    assert fx.revision == before


def test_eq_band_change_is_optimistic(fx):
    """Eğri sürüklerken daemon'ın yanıtını beklemeden güncellenmeli."""
    fx.setEqBand("game", 2, "gain_db", "7.5")
    eq = json.loads(fx.eqJson("game"))
    assert eq["bands"][2]["gain_db"] == 7.5
    assert fx._client.calls[-1] == ("SetEqBand", ("game", 2, "gain_db", "7.5"))


def test_eq_band_type_and_enabled_are_typed_correctly(fx):
    fx.setEqBand("game", 0, "band_type", "low_shelf")
    fx.setEqBand("game", 0, "enabled", "false")
    band = json.loads(fx.eqJson("game"))["bands"][0]
    assert band["band_type"] == "low_shelf"
    assert band["enabled"] is False


def test_eq_band_out_of_range_is_ignored(fx):
    fx.setEqBand("game", 99, "gain_db", "5")  # yükseltmemeli


def test_garbage_band_value_does_not_corrupt_the_state(fx):
    before = fx.eqJson("game")
    fx.setEqBand("game", 0, "gain_db", "çok yüksek")
    assert fx.eqJson("game") == before


def test_eq_enabled_is_optimistic(fx):
    fx.setEqEnabled("game", True)
    assert json.loads(fx.eqJson("game"))["enabled"] is True


def test_preamp_is_optimistic(fx):
    fx.setEqPreamp("game", -4.0)
    assert json.loads(fx.eqJson("game"))["preamp_db"] == -4.0


def test_filter_enabled_is_optimistic(fx):
    fx.setFilterEnabled("game", "gate", True)
    assert fx.filterOf("game", "gate")["enabled"] is True


def test_filter_param_is_optimistic(fx):
    fx.setFilterParam("game", "gate", "threshold_db", -12.0)
    assert fx.filterOf("game", "gate")["params"]["threshold_db"] == -12.0
    assert fx._client.calls[-1] == (
        "SetFilterParam",
        ("game", "gate", "threshold_db", -12.0),
    )


def test_every_optimistic_edit_bumps_the_revision(fx):
    """Aksi hâlde eğri binding'i tazelenmez ve ekranda hiçbir şey değişmez."""
    before = fx.revision
    fx.setEqBand("game", 1, "gain_db", "2")
    assert fx.revision > before


def test_profile_actions_reach_the_daemon(fx):
    fx.saveProfile("game", "CS2")
    fx.renameProfile("game", "CS2", "Arc")
    fx.deleteProfile("game", "Arc")
    fx.setProfileFavorite("game", "Default", 3)
    methods = [c[0] for c in fx._client.calls]
    for name in ("SaveProfile", "RenameProfile", "DeleteProfile", "SetProfileFavorite"):
        assert name in methods


def test_channel_of_returns_the_strip_row(fx):
    # Gömülü kanalların **gösterilen** adı çevriliyor; yapılandırmadaki ad (ve dolayısıyla
    # PipeWire cihaz açıklaması) İngilizce ve sabit kalıyor.
    assert fx.channelOf("game")["name"] == "Oyun"
    assert fx.channelOf("yok") == {}


def test_a_renamed_channel_keeps_the_users_name(fx):
    """Çeviri yalnızca ada hiç dokunulmamışsa devreye girer."""
    from sonar.gui.bridge import display_name

    assert display_name("channel", "game", "Game") == "Oyun"
    assert display_name("channel", "game", "Valorant") == "Valorant"
    assert display_name("channel", "kendi_kanalim", "Kendi Kanalım") == "Kendi Kanalım"


def test_profile_names(fx):
    assert fx.profileNames("game") == [
        {"name": "Default", "builtin": False},
        {"name": "CS2", "builtin": False},
    ]
    assert fx.profileNames("yok") == []


def test_profile_names_mark_builtins(qt_app):
    client = FakeClient(make_state(builtin_profiles={"game": ["CS2"]}))
    obj = SonarBridge(client)
    obj.apply_state(client.state)
    assert obj.profileNames("game")[1] == {"name": "CS2", "builtin": True}


def test_chatmix_gain_defaults_to_unity(fx):
    assert fx.chatmixGain("game") == 1.0


def test_chatmix_gain_is_reported(qt_app):
    client = FakeClient(make_state(chatmix_gains={"game": 0.01, "chat": 1.0}))
    obj = SonarBridge(client)
    obj.apply_state(client.state)
    assert obj.chatmixGain("game") == pytest.approx(0.01)


# --------------------------------------------------------------------------- akış süzme


def test_streams_for_filters_by_channel(qt_app):
    """Şerit tüm listeyi gezip görünmeyenleri saklıyordu; süzme artık köprüde."""
    bridge = SonarBridge()
    bridge.apply_state(
        make_state(
            streams=[
                {"id": 1, "app_name": "Brave", "channel": "media"},
                {"id": 2, "app_name": "Discord", "channel": "chat"},
                {"id": 3, "app_name": "mpv", "channel": "media"},
            ]
        )
    )
    assert [row["label"] for row in bridge.streamsFor("media")] == ["Brave", "mpv"]
    assert [row["label"] for row in bridge.streamsFor("chat")] == ["Discord"]
    assert bridge.streamsFor("game") == []


# --------------------------------------------------------------------------- bildirimler


def test_a_preset_copy_is_announced(bridge):
    """Daemon gömülü preset düzenlenince sessizce kopya açıyor; kullanıcı bunu görmeli."""
    seen = []
    bridge.noticeRaised.connect(lambda text, is_error: seen.append((text, is_error)))
    bridge.onStateChanged(
        json.dumps(
            {
                "changes": [
                    {
                        "kind": "profile_copied",
                        "target": "game",
                        "from": "Flat",
                        "to": "Flat (özel)",
                    }
                ]
            }
        )
    )
    assert len(seen) == 1
    assert "Flat (özel)" in seen[0][0]
    assert seen[0][1] is False


def test_a_failed_save_is_announced_as_an_error(bridge):
    seen = []
    bridge.noticeRaised.connect(lambda text, is_error: seen.append((text, is_error)))
    bridge.onStateChanged(
        json.dumps({"changes": [{"kind": "save_failed", "message": "Disk dolu."}]})
    )
    assert seen == [("Disk dolu.", True)]


def test_uninteresting_deltas_are_not_announced(bridge):
    seen = []
    bridge.noticeRaised.connect(lambda text, is_error: seen.append(text))
    bridge.onStateChanged(json.dumps({"changes": [{"kind": "channel_volume", "channel": "game"}]}))
    assert seen == []


def test_a_malformed_delta_payload_is_ignored(bridge):
    bridge.onStateChanged("bu json değil")  # yükseltmemeli


# --------------------------------------------------------------------------- giriş kanalları
#
# Test turu 3: ikinci bir giriş kanalı eklendiğinde onun fader/mute düğmeleri birincil
# `mic` zincirini sürüyordu — köprü zincir kimliğini sabit yazıyordu.


def test_mic_slots_target_the_chain_they_are_given(bridge):
    bridge.setMicMute("stream_mic", True)
    assert bridge._client.calls[-1] == ("SetMicMute", ("stream_mic", True))

    bridge.setMicVolume("stream_mic", 0.4)
    assert bridge._client.calls[-1] == ("SetMicVolume", ("stream_mic", 0.4))

    bridge.setMicMonitor("stream_mic", False)
    assert bridge._client.calls[-1] == ("SetMicMonitor", ("stream_mic", False))

    bridge.setMicDevice("stream_mic", "alsa_input.usb")
    assert bridge._client.calls[-1] == ("SetMicDevice", ("stream_mic", "alsa_input.usb"))


def test_mic_mute_updates_only_its_own_row(bridge):
    mic = bridge.channels.index_of("id", "mic")
    other = bridge.channels.index_of("id", "stream_mic")

    bridge.setMicMute("stream_mic", True)

    assert bridge.channels.get(other)["streamMuted"] is True
    assert bridge.channels.get(mic)["streamMuted"] is False


def test_sidetone_volume_has_an_api(bridge):
    """Giriş şeridindeki kulaklık fader'ının karşılığı yoktu; sessizce hiçbir şey yapıyordu."""
    bridge.setMicMonitorVolume("mic", 0.25)
    assert bridge._client.calls[-1] == ("SetMicMonitorVolume", ("mic", 0.25))
    assert bridge.channels.get(bridge.channels.index_of("id", "mic"))["personalVolume"] == 0.25


# --------------------------------------------------------------------------- QML sözlükleri


def test_qjsvalue_dicts_are_converted():
    """QML'den gelen sözlük `QJSValue`; `dict()` onu iterable sanıp `TypeError` veriyordu."""
    from sonar.gui.bridge import _as_dict

    class FakeJsValue:
        def toVariant(self):  # noqa: N802 - Qt adı
            return {"enabled": True, "reduction_db": -9.0}

    assert _as_dict(FakeJsValue()) == {"enabled": True, "reduction_db": -9.0}
    assert _as_dict({"a": 1}) == {"a": 1}
    assert _as_dict(None) == {}


def test_desktop_capturers_are_listed_but_flagged():
    """OBS'in "Masaüstü Sesi" kaynağı arayüzde görünmeli; yalnızca otomatik
    yönlendirilmemeli. Eskiden köprüden de eleniyor ve OBS hiç görünmüyordu."""
    state = make_state(
        streams=[
            {"id": 9, "app_name": "OBS", "is_capture": True, "captures_sink": True,
             "target_node": "sonar_stream"},
        ]
    )
    rows = stream_rows(state)
    assert [(r["label"], r["capturesSink"], r["channel"]) for r in rows] == [
        ("OBS", True, "stream")
    ]


# --------------------------------------------------------------------------- kurulum


def test_provisioned_defaults_to_true_while_disconnected(qt_app):
    """Daemon'a bağlı değilken karşılama ekranı açılmamalı.

    Bilinmeyen bir durumda "kurulu değil" varsaymak, bağlantı kopan bir kullanıcıya
    kurulum sihirbazı göstermek demekti.
    """
    obj = SonarBridge(FakeClient(make_state()))
    assert obj.provisioned is True


def test_provisioned_follows_the_daemon(bridge):
    bridge._set_connected(True)
    assert bridge.provisioned is False, "varsayılan yapılandırma henüz kurulmamış"

    state = make_state()
    state["config"]["settings"]["provisioned"] = True
    bridge.apply_state(state)

    assert bridge.provisioned is True


def test_provision_is_deferred_so_the_ui_can_paint_first(bridge, qt_app):
    """Çağrı bloke ediyor; düğmeye basınca ekranın donmaması için sonraki tura atılıyor."""
    bridge._client.calls.clear()

    bridge.provision()

    assert bridge.busy is True
    assert not any(call[0] == "Provision" for call in bridge._client.calls)
    qt_app.processEvents()
    import time

    time.sleep(0.1)
    qt_app.processEvents()
    assert any(call[0] == "Provision" for call in bridge._client.calls)
    assert bridge.busy is False


def test_deprovision_passes_the_purge_flag(bridge, qt_app):
    import time

    bridge._client.calls.clear()
    bridge.deprovision(True)
    qt_app.processEvents()
    time.sleep(0.1)
    qt_app.processEvents()

    assert ("Deprovision", (True,)) in bridge._client.calls
