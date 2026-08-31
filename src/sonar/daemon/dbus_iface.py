"""D-Bus arayüzü — `daemon.api.SonarApi` üzerine ince bir sarmalayıcı.

Servis `io.github.iwhimss.Sonar`, yol `/io/github/iwhimss/Sonar`, arayüz aynı ad.

## Her metot JSON zarfı döndürür

`QDBusContext.sendErrorReply()` PySide6 6.11.2'de **segfault ediyor** (ölçüldü: çıkış kodu
139). Native D-Bus hatası kullanılsaydı her geçersiz argüman daemon'ı düşürürdü. Bunun
yerine her metot tek bir `s` döndürür:

```
{"ok": true}                                        # başarı
{"ok": true, "result": ...}                         # değer dönen metotlar
{"ok": false, "code": "unknown_channel", "message": "…"}
```

Bu, PySide6'nın slot içindeki istisnaları sessizce yutup boş string döndürmesi sorununu da
çözüyor: sarmalayıcı her çağrıyı yakalıyor, istemci başarıyı hatadan ayırabiliyor.

## Sinyaller elle gönderilir

PySide6 6.11.2'de Qt'nin **otomatik sinyal relay'i çalışmıyor**: nesne
`ExportAllSignals` ile kaydedilse ve introspection sinyalleri gösterse bile, Python'da
tanımlı bir `Signal` emit edildiğinde otobüse hiçbir mesaj çıkmıyor (ölçüldü:
`dbus-monitor` sıfır mesaj). Sessiz bir başarısızlık — arayüz hiçbir güncelleme almadan
çalışmaya devam ederdi.

Bu yüzden `emit_signal()` her sinyali `QDBusMessage.createSignal()` ile **elle** gönderir.
Qt sinyali de ayrıca emit edilir: aynı süreç içindeki dinleyiciler ve introspection için.

## Neden argümanlar basit tiplerde

Metot imzaları yalnızca `s`, `b`, `d`, `i`, `u` kullanır; karmaşık yapılar JSON string
olarak taşınır. `busctl` ile elle çağırmak kolay kalıyor ve API büyüdüğünde eski istemciler
kırılmıyor.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage

from sonar.daemon.api import ApiError, SonarApi

__all__ = ["BUS_NAME", "INTERFACE", "OBJECT_PATH", "SonarDBusInterface", "reply"]

log = logging.getLogger(__name__)

BUS_NAME = "io.github.iwhimss.Sonar"
OBJECT_PATH = "/io/github/iwhimss/Sonar"
INTERFACE = "io.github.iwhimss.Sonar"


def reply(fn: Callable[[], Any]) -> str:
    """Bir çağrıyı çalıştırıp sonucunu JSON zarfına sarar. Asla yükseltmez."""
    try:
        result = fn()
    except ApiError as error:
        return json.dumps({"ok": False, "code": error.code, "message": error.message})
    except Exception as error:  # pragma: no cover - beklenmeyen; daemon ayakta kalmalı
        log.exception("D-Bus metodu beklenmedik şekilde başarısız oldu")
        return json.dumps({"ok": False, "code": "internal", "message": str(error)})
    payload: dict[str, Any] = {"ok": True}
    if result is not None:
        payload["result"] = result
    return json.dumps(payload, ensure_ascii=False)


class SonarDBusInterface(QObject):
    """D-Bus'a açılan yüzey. Mantık yok — her şey `SonarApi`'de."""

    StateChanged = Signal(str)
    StreamsChanged = Signal(str)
    LevelsUpdated = Signal(str)
    GraphRebuilt = Signal()
    Error = Signal(str, str)

    def __init__(
        self,
        api: SonarApi,
        connection: QDBusConnection | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.connection = connection

    # ------------------------------------------------------------------ sinyal yayını

    def emit_signal(self, name: str, *args: object) -> bool:
        """Sinyali hem Qt tarafına hem D-Bus'a yayar.

        D-Bus mesajı elle üretiliyor: PySide6 6.11.2 Python sinyallerini otobüse relay
        etmiyor (bkz. modül başlığı). Qt sinyali de emit ediliyor ki aynı süreç içindeki
        dinleyiciler çalışsın.
        """
        signal = getattr(self, name, None)
        if signal is not None:
            signal.emit(*args)
        if self.connection is None:
            return False
        message = QDBusMessage.createSignal(OBJECT_PATH, INTERFACE, name)
        message.setArguments(list(args))
        return bool(self.connection.send(message))

    # ------------------------------------------------------------------ okuma

    @Slot(result=str)
    def GetState(self) -> str:
        return reply(self.api.get_state)

    @Slot(result=str)
    def GetDevices(self) -> str:
        return reply(self.api.get_devices)

    @Slot(str, result=str)
    def ListProfiles(self, target: str) -> str:
        return reply(lambda: self.api.list_profiles(target))

    @Slot(result=str)
    def ListRules(self) -> str:
        return reply(self.api.list_rules)

    # ------------------------------------------------------------------ seviye

    @Slot(str, str, float, result=str)
    def SetChannelVolume(self, channel: str, bus: str, value: float) -> str:
        return reply(lambda: self.api.set_channel_volume(channel, bus, value))

    @Slot(str, str, bool, result=str)
    def SetChannelMute(self, channel: str, bus: str, muted: bool) -> str:
        return reply(lambda: self.api.set_channel_mute(channel, bus, muted))

    @Slot(str, float, result=str)
    def SetMasterVolume(self, bus: str, value: float) -> str:
        return reply(lambda: self.api.set_master_volume(bus, value))

    @Slot(str, bool, result=str)
    def SetMasterMute(self, bus: str, muted: bool) -> str:
        return reply(lambda: self.api.set_master_mute(bus, muted))

    @Slot(str, float, result=str)
    def SetMicVolume(self, chain: str, value: float) -> str:
        return reply(lambda: self.api.set_mic_volume(chain, value))

    @Slot(str, bool, result=str)
    def SetMicMute(self, chain: str, muted: bool) -> str:
        return reply(lambda: self.api.set_mic_mute(chain, muted))

    # ------------------------------------------------------------------ filtreler

    @Slot(str, str, bool, result=str)
    def SetFilterEnabled(self, target: str, stage: str, enabled: bool) -> str:
        return reply(lambda: self.api.set_filter_enabled(target, stage, enabled))

    @Slot(str, str, str, float, result=str)
    def SetFilterParam(self, target: str, stage: str, name: str, value: float) -> str:
        return reply(lambda: self.api.set_filter_param(target, stage, name, value))

    @Slot(str, int, str, str, result=str)
    def SetEqBand(self, target: str, band: int, field: str, value: str) -> str:
        """`value` string taşınır: `band_type` metin, diğerleri sayı."""
        return reply(lambda: self.api.set_eq_band(target, band, field, _coerce(field, value)))

    @Slot(str, float, result=str)
    def SetEqPreamp(self, target: str, value_db: float) -> str:
        return reply(lambda: self.api.set_eq_preamp(target, value_db))

    @Slot(str, int, result=str)
    def SetBandCount(self, target: str, count: int) -> str:
        return reply(lambda: self.api.set_band_count(target, count))

    # ------------------------------------------------------------------ profiller

    @Slot(str, str, result=str)
    def LoadProfile(self, target: str, name: str) -> str:
        return reply(lambda: self.api.load_profile(target, name))

    @Slot(str, str, result=str)
    def SaveProfile(self, target: str, name: str) -> str:
        return reply(lambda: self.api.save_profile(target, name))

    @Slot(str, str, result=str)
    def DeleteProfile(self, target: str, name: str) -> str:
        return reply(lambda: self.api.delete_profile(target, name))

    @Slot(str, str, str, result=str)
    def RenameProfile(self, target: str, old: str, new: str) -> str:
        return reply(lambda: self.api.rename_profile(target, old, new))

    @Slot(str, str, int, result=str)
    def SetProfileFavorite(self, target: str, name: str, slot: int) -> str:
        return reply(lambda: self.api.set_profile_favorite(target, name, slot))

    # ------------------------------------------------------------------ yapısal

    @Slot(str, str, result=str)
    def SetBusDevice(self, bus: str, device: str) -> str:
        return reply(lambda: self.api.set_bus_device(bus, device))

    @Slot(str, str, result=str)
    def SetMicDevice(self, chain: str, device: str) -> str:
        return reply(lambda: self.api.set_mic_device(chain, device))

    @Slot(str, bool, result=str)
    def SetMicMonitor(self, chain: str, enabled: bool) -> str:
        return reply(lambda: self.api.set_mic_monitor(chain, enabled))

    @Slot(str, bool, result=str)
    def SetMicStreamSend(self, chain: str, enabled: bool) -> str:
        return reply(lambda: self.api.set_mic_stream_send(chain, enabled))

    @Slot(str, str, result=str)
    def AddChannel(self, name: str, color: str) -> str:
        return reply(lambda: self.api.add_channel(name, color or "#8B95A5"))

    @Slot(str, result=str)
    def RemoveChannel(self, channel: str) -> str:
        return reply(lambda: self.api.remove_channel(channel))

    # ------------------------------------------------------------------ yönlendirme

    @Slot(int, str, result=str)
    def MoveStream(self, stream_id: int, channel: str) -> str:
        return reply(lambda: self.api.move_stream(stream_id, channel))

    @Slot(str, str, str, bool, result=str)
    def SetRule(self, match_key: str, pattern: str, channel: str, is_regex: bool) -> str:
        return reply(lambda: self.api.set_rule(match_key, pattern, channel, is_regex))

    @Slot(str, str, result=str)
    def RemoveRule(self, match_key: str, pattern: str) -> str:
        return reply(lambda: self.api.remove_rule(match_key, pattern))

    # ------------------------------------------------------------------ ChatMix ve ayarlar

    @Slot(float, result=str)
    def SetChatMix(self, value: float) -> str:
        return reply(lambda: self.api.set_chatmix(value))

    @Slot(bool, str, str, result=str)
    def SetChatMixConfig(self, enabled: bool, left: str, right: str) -> str:
        return reply(lambda: self.api.set_chatmix_config(enabled, left, right))

    @Slot(str, result=str)
    def SetDefaultChannel(self, channel: str) -> str:
        return reply(lambda: self.api.set_default_channel(channel))

    @Slot(bool, result=str)
    def SetTakeOverDefaultSink(self, enabled: bool) -> str:
        return reply(lambda: self.api.set_take_over_default_sink(enabled))

    # ------------------------------------------------------------------ diğer

    @Slot(bool, result=str)
    def SubscribeMeters(self, enabled: bool) -> str:
        """Faz 6'da bağlanacak; şimdilik isteği kabul edip sayacı tutuyoruz."""
        return reply(lambda: self.api.set_meters_subscribed(enabled))

    @Slot(result=str)
    def Reload(self) -> str:
        return reply(self.api.reload)

    @Slot(result=str)
    def Ping(self) -> str:
        """İstemcinin daemon'ın ayakta olduğunu ucuzca doğrulaması için."""
        return reply(lambda: "pong")


def _coerce(field: str, value: str) -> float | str | bool:
    if field == "band_type":
        return value
    if field == "enabled":
        return value.strip().lower() in {"1", "true", "yes", "on", "evet"}
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid_value", f"sayı bekleniyordu: {value!r}") from exc
