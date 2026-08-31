from __future__ import annotations

import json

import pytest

from sonar.daemon.api import ApiError, SonarApi
from sonar.daemon.dbus_iface import SonarDBusInterface, reply
from tests.test_api import FakeSupervisor

pytest.importorskip("PySide6.QtDBus")


@pytest.fixture
def iface(config_store):
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0)
    return SonarDBusInterface(api)


def _call(iface, method, *args):
    return json.loads(getattr(iface, method)(*args))


# --------------------------------------------------------------------------- zarf
#
# `QDBusContext.sendErrorReply()` PySide6 6.11.2'de segfault ediyor (ölçüldü: çıkış 139),
# ayrıca slot içindeki istisnalar sessizce boş string'e dönüyor. Bu yüzden her metot bir
# JSON zarfı döndürüyor ve zarfın doğruluğu burada test ediliyor.


def test_success_envelope_without_a_result():
    assert json.loads(reply(lambda: None)) == {"ok": True}


def test_success_envelope_with_a_result():
    assert json.loads(reply(lambda: [1, 2])) == {"ok": True, "result": [1, 2]}


def test_api_error_becomes_a_failure_envelope():
    def boom():
        raise ApiError("unknown_channel", "böyle bir kanal yok: xyz")

    payload = json.loads(reply(boom))
    assert payload == {
        "ok": False,
        "code": "unknown_channel",
        "message": "böyle bir kanal yok: xyz",
    }


def test_unexpected_exception_is_contained():
    """Beklenmeyen bir hata bile daemon'ı düşürmemeli."""
    payload = json.loads(reply(lambda: (_ for _ in ()).throw(RuntimeError("beklenmedik"))))
    assert payload["ok"] is False
    assert payload["code"] == "internal"


def test_turkish_characters_survive_the_envelope():
    payload = reply(lambda: "ğüşiöç")
    assert "ğüşiöç" in payload  # ensure_ascii=False


# --------------------------------------------------------------------------- metotlar


def test_ping(iface):
    assert _call(iface, "Ping") == {"ok": True, "result": "pong"}


def test_get_state_round_trips(iface):
    payload = _call(iface, "GetState")
    assert payload["ok"] is True
    assert [c["id"] for c in payload["result"]["config"]["channels"]] == [
        "game",
        "chat",
        "media",
        "aux",
    ]


def test_set_channel_volume(iface):
    assert _call(iface, "SetChannelVolume", "game", "personal", 0.5)["ok"] is True
    assert iface.api.config.channel("game").personal.volume == 0.5


def test_unknown_channel_returns_a_code_not_a_crash(iface):
    payload = _call(iface, "SetChannelVolume", "yok", "personal", 0.5)
    assert payload["ok"] is False
    assert payload["code"] == "unknown_channel"


def test_eq_band_value_is_coerced_from_string(iface):
    """D-Bus imzasını basit tutmak için değer string taşınıyor."""
    assert _call(iface, "SetEqBand", "game", 0, "gain_db", "6.0")["ok"] is True
    assert iface.api.profile("game").eq.bands[0].gain_db == 6.0


def test_eq_band_type_is_passed_through_as_text(iface):
    assert _call(iface, "SetEqBand", "game", 0, "band_type", "low_shelf")["ok"] is True
    assert iface.api.profile("game").eq.bands[0].band_type == "low_shelf"


def test_eq_band_enabled_accepts_truthy_text(iface):
    _call(iface, "SetEqBand", "game", 0, "enabled", "false")
    assert iface.api.profile("game").eq.bands[0].enabled is False
    _call(iface, "SetEqBand", "game", 0, "enabled", "true")
    assert iface.api.profile("game").eq.bands[0].enabled is True


def test_eq_band_rejects_garbage_numbers(iface):
    payload = _call(iface, "SetEqBand", "game", 0, "gain_db", "çok yüksek")
    assert payload["ok"] is False
    assert payload["code"] == "invalid_value"


def test_add_channel_returns_the_new_id(iface):
    payload = _call(iface, "AddChannel", "Voice Chat", "")
    assert payload["result"] == "voice_chat"


def test_subscribe_meters_counts_clients(iface):
    _call(iface, "SubscribeMeters", True)
    _call(iface, "SubscribeMeters", True)
    assert iface.api.meters_subscribed == 2
    _call(iface, "SubscribeMeters", False)
    assert iface.api.meters_subscribed == 1


def test_meters_never_go_negative(iface):
    _call(iface, "SubscribeMeters", False)
    assert iface.api.meters_subscribed == 0


def test_every_slot_returns_a_json_envelope(iface):
    """Sözleşme: istisnasız her metot `{"ok": ...}` döndürür."""
    from PySide6.QtCore import QMetaMethod

    meta = iface.metaObject()
    checked = 0
    for index in range(meta.methodOffset(), meta.methodCount()):
        method = meta.method(index)
        if method.methodType() != QMetaMethod.MethodType.Slot:
            continue
        name = bytes(method.name()).decode()
        if name.startswith("_") or method.parameterCount() > 0:
            continue
        payload = json.loads(getattr(iface, name)())
        assert "ok" in payload, f"{name} zarf döndürmedi"
        checked += 1
    assert checked >= 4


# --------------------------------------------------------------------------- sinyal yayını
#
# PySide6 6.11.2 Python sinyallerini D-Bus'a relay etmiyor (ölçüldü: `dbus-monitor` sıfır
# mesaj görüyor, introspection sinyalleri gösterse bile). Sessiz bir başarısızlık olurdu:
# arayüz hiçbir güncelleme almadan çalışmaya devam ederdi. Bu yüzden elle gönderiyoruz.


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list = []

    def send(self, message) -> bool:
        self.sent.append(message)
        return True


def test_emit_signal_sends_a_dbus_message(config_store):
    from sonar.daemon.dbus_iface import INTERFACE, OBJECT_PATH

    connection = FakeConnection()
    iface = SonarDBusInterface(SonarApi(config_store, FakeSupervisor(), save_delay=0), connection)
    assert iface.emit_signal("StateChanged", '{"changes": []}') is True

    message = connection.sent[0]
    assert message.path() == OBJECT_PATH
    assert message.interface() == INTERFACE
    assert message.member() == "StateChanged"
    assert message.arguments() == ['{"changes": []}']


def test_emit_signal_also_fires_the_qt_signal(config_store):
    seen: list[str] = []
    iface = SonarDBusInterface(
        SonarApi(config_store, FakeSupervisor(), save_delay=0), FakeConnection()
    )
    iface.StateChanged.connect(seen.append)
    iface.emit_signal("StateChanged", "merhaba")
    assert seen == ["merhaba"]


def test_signal_without_arguments(config_store):
    connection = FakeConnection()
    iface = SonarDBusInterface(SonarApi(config_store, FakeSupervisor(), save_delay=0), connection)
    iface.emit_signal("GraphRebuilt")
    assert connection.sent[0].member() == "GraphRebuilt"


def test_emit_without_a_connection_does_not_raise(config_store):
    """Testlerde ve D-Bus'sız kullanımda sessizce False dönmeli."""
    iface = SonarDBusInterface(SonarApi(config_store, FakeSupervisor(), save_delay=0))
    assert iface.emit_signal("StateChanged", "x") is False


def test_every_declared_signal_can_be_emitted(config_store):
    """Sözleşme: bildirilen her sinyalin elle gönderimi çalışmalı."""
    connection = FakeConnection()
    iface = SonarDBusInterface(SonarApi(config_store, FakeSupervisor(), save_delay=0), connection)
    for name, args in (
        ("StateChanged", ("{}",)),
        ("StreamsChanged", ("{}",)),
        ("LevelsUpdated", ("{}",)),
        ("GraphRebuilt", ()),
        ("Error", ("code", "mesaj")),
    ):
        assert iface.emit_signal(name, *args) is True
    assert [m.member() for m in connection.sent] == [
        "StateChanged",
        "StreamsChanged",
        "LevelsUpdated",
        "GraphRebuilt",
        "Error",
    ]
