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
    assert [r["id"] for r in rows] == ["game", "chat", "media", "aux", "mic"]


def test_mic_row_carries_monitor_as_the_personal_side():
    """Mikrofonun 'kulaklık' fader'ı yan tondur; kapalıyken susturulmuş görünür."""
    row = next(r for r in channel_rows(make_state()) if r["kind"] == "mic")
    assert row["personalMuted"] is True  # varsayılan: yan ton kapalı
    assert row["streamMuted"] is False


def test_stream_mic_is_not_a_strip():
    """`stream_mic` mikserde ayrı bir şerit değil; FX sayfasından yönetiliyor."""
    assert "stream_mic" not in [r["id"] for r in channel_rows(make_state())]


def test_profiles_reach_the_row():
    row = channel_rows(make_state())[0]
    assert row["profiles"] == ["Default", "CS2"]


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
        {"id": 1, "label": "Firefox", "binary": "firefox", "channel": "media"}
    ]


def test_stream_rows_fall_back_to_the_target_node():
    """Daemon kanalı bilmiyorsa uygulamanın kendi hedefine bakılır."""
    state = make_state(
        streams=[{"id": 2, "app_name": "OBS", "target_node": "sonar_game", "channel": ""}]
    )
    assert stream_rows(state)[0]["channel"] == "game"


def test_capture_streams_are_not_shown():
    state = make_state(streams=[{"id": 3, "app_name": "OBS", "is_capture": True}])
    assert stream_rows(state) == []


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
    assert model.rowCount() == 5
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
    assert bridge.channels.rowCount() == 5
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
    bridge.onLevelsUpdated(
        json.dumps(
            {
                "sonar_game_fx": {
                    "peak_db": -12.0,
                    "rms_db": -15.0,
                    "hold_db": -10.0,
                    "clipped": False,
                }
            }
        )
    )
    assert bridge.channels.get(0)["personalPeak"] == -12.0
    bridge.apply_state(make_state())
    assert bridge.channels.get(0)["personalPeak"] == -12.0, "metre değeri kaybolmamalı"


def test_levels_for_the_mic_use_its_own_node(bridge):
    bridge.onLevelsUpdated(
        json.dumps(
            {"sonar_mic": {"peak_db": -20.0, "rms_db": -22.0, "hold_db": -18.0, "clipped": True}}
        )
    )
    mic = bridge.channels.get(bridge.channels.index_of("id", "mic"))
    assert mic["streamPeak"] == -20.0
    assert mic["clipped"] is True


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
    assert obj.channels.rowCount() == 5


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
