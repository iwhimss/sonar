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
        """Tüm durum: yapılandırma, profiller, akışlar, cihazlar, çakışmalar."""
        return reply(self.api.get_state)

    @Slot(result=str)
    def GetDevices(self) -> str:
        """Fiziksel ses cihazları (Sonar'ın kendi sanal node'ları hariç)."""
        return reply(self.api.get_devices)

    @Slot(str, result=str)
    def ListProfiles(self, target: str) -> str:
        """Hedefin profilleri; gömülü presetler önce."""
        return reply(lambda: self.api.list_profiles(target))

    @Slot(result=str)
    def ListHeadsets(self) -> str:
        """Donanım ChatMix tekeri olduğu bilinen kulaklıklar."""
        return reply(self.api.headsets)

    @Slot(str, str, result=str)
    def SetDucking(self, target: str, fields_json: str) -> str:
        """Bir kanalın **profilindeki** Smart Volume ayarları (şema 4).

        Alan sayısı D-Bus imzasında sabitlenemeyecek kadar çok ve ileride büyüyebilir;
        tek bir JSON argümanı imzayı sabit tutuyor.
        """
        import json as _json

        def apply() -> dict:
            try:
                fields = _json.loads(fields_json or "{}")
            except _json.JSONDecodeError as error:
                raise ApiError("invalid_json", f"geçersiz JSON: {error}") from error
            if not isinstance(fields, dict):
                raise ApiError("invalid_json", "Smart Volume ayarları bir sözlük olmalı")
            return self.api.set_ducking(target, **fields)

        return reply(apply)

    @Slot(result=str)
    def Diagnose(self) -> str:
        """Ses yolu teşhisi: eksik bağlantılar, doğmayan node'lar, çakışmalar."""
        return reply(self.api.diagnose)

    @Slot(result=str)
    def ListRules(self) -> str:
        """Uygulama → kanal yönlendirme kuralları."""
        return reply(self.api.list_rules)

    # ------------------------------------------------------------------ seviye

    @Slot(str, str, float, result=str)
    def SetChannelVolume(self, channel: str, bus: str, value: float) -> str:
        """Kanalın bir miks yolundaki seviyesi (lineer, 1.0 = birim kazanç)."""
        return reply(lambda: self.api.set_channel_volume(channel, bus, value))

    @Slot(str, str, bool, result=str)
    def SetChannelMute(self, channel: str, bus: str, muted: bool) -> str:
        """Kanalın bir miks yolunu susturur."""
        return reply(lambda: self.api.set_channel_mute(channel, bus, muted))

    @Slot(str, float, result=str)
    def SetMasterVolume(self, bus: str, value: float) -> str:
        """Personal/Stream bus'ının master seviyesi."""
        return reply(lambda: self.api.set_master_volume(bus, value))

    @Slot(str, bool, result=str)
    def SetMasterMute(self, bus: str, muted: bool) -> str:
        """Personal/Stream bus'ını susturur."""
        return reply(lambda: self.api.set_master_mute(bus, muted))

    @Slot(str, float, result=str)
    def SetMicVolume(self, chain: str, value: float) -> str:
        """Mikrofon zincirinin çıkış seviyesi."""
        return reply(lambda: self.api.set_mic_volume(chain, value))

    @Slot(str, bool, result=str)
    def SetMicMute(self, chain: str, muted: bool) -> str:
        """Mikrofonu susturur."""
        return reply(lambda: self.api.set_mic_mute(chain, muted))

    # ------------------------------------------------------------------ filtreler

    @Slot(str, str, bool, result=str)
    def SetFilterEnabled(self, target: str, stage: str, enabled: bool) -> str:
        """Bir DSP aşamasını açar/kapatır (canlı bypass)."""
        return reply(lambda: self.api.set_filter_enabled(target, stage, enabled))

    @Slot(str, str, str, float, result=str)
    def SetFilterParam(self, target: str, stage: str, name: str, value: float) -> str:
        """Aşamanın bir parametresi; insan biriminde (dB, ms, oran)."""
        return reply(lambda: self.api.set_filter_param(target, stage, name, value))

    @Slot(str, int, str, str, result=str)
    def SetEqBand(self, target: str, band: int, field: str, value: str) -> str:
        """`value` string taşınır: `band_type` metin, diğerleri sayı."""
        return reply(lambda: self.api.set_eq_band(target, band, field, _coerce(field, value)))

    @Slot(str, float, result=str)
    def SetEqPreamp(self, target: str, value_db: float) -> str:
        """Ekolayzer öncesi kazanç."""
        return reply(lambda: self.api.set_eq_preamp(target, value_db))

    @Slot(str, float, float, result=str)
    def AddEqBand(self, target: str, freq: float, gain_db: float) -> str:
        """Verilen frekansa yeni bir EQ bandı ekler. Sonuç: bandın indeksi. **Canlı**."""
        return reply(lambda: self.api.add_eq_band(target, freq, gain_db))

    @Slot(str, int, result=str)
    def RemoveEqBand(self, target: str, index: int) -> str:
        """Bir EQ bandını siler. **Canlı**."""
        return reply(lambda: self.api.remove_eq_band(target, index))

    # ------------------------------------------------------------------ profiller

    @Slot(str, str, result=str)
    def LoadProfile(self, target: str, name: str) -> str:
        """Profili veya gömülü preset'i yükler. Anında ve kesintisiz."""
        return reply(lambda: self.api.load_profile(target, name))

    @Slot(str, str, result=str)
    def SaveProfile(self, target: str, name: str) -> str:
        """Çalışılan profili yeni adla kaydeder ('farklı kaydet')."""
        return reply(lambda: self.api.save_profile(target, name))

    @Slot(str, str, result=str)
    def DeleteProfile(self, target: str, name: str) -> str:
        """Kullanıcı profilini siler; gömülü presetler silinemez."""
        return reply(lambda: self.api.delete_profile(target, name))

    @Slot(str, str, str, result=str)
    def RenameProfile(self, target: str, old: str, new: str) -> str:
        """Kullanıcı profilini yeniden adlandırır."""
        return reply(lambda: self.api.rename_profile(target, old, new))

    @Slot(str, str, str, result=str)
    def ImportProfile(self, target: str, text: str, name: str) -> str:
        """Dış EQ dosyasını içe aktarır. Biçim içerikten bulunur."""
        return reply(lambda: self.api.import_profile(target, text, name))

    @Slot(str, str, bool, result=str)
    def ExportProfile(self, target: str, name: str, autoeq: bool) -> str:
        """Profili metin olarak verir; `autoeq` ise AutoEQ/APO biçiminde."""
        return reply(lambda: self.api.export_profile(target, name, autoeq))

    @Slot(str, str, result=str)
    def CopyProfile(self, target: str, name: str) -> str:
        """Aktif profili yeni bir adla çoğaltır ve ona geçer."""
        return reply(lambda: self.api.copy_profile(target, name))

    @Slot(str, result=str)
    def ResetProfile(self, target: str) -> str:
        """Aktif profili düz hâle döndürür (EQ sıfır, filtreler kapalı)."""
        return reply(lambda: self.api.reset_profile(target))

    @Slot(str, result=str)
    def ListBuiltinProfiles(self, target: str) -> str:
        """Hedefin gömülü (salt okunur) preset adları."""
        return reply(lambda: self.api.builtin_names(target))

    @Slot(str, str, bool, result=str)
    def SetProfileFavorite(self, target: str, name: str, favorite: bool) -> str:
        """Profili favorilere ekler veya çıkarır. Sayı sınırı yok."""
        return reply(lambda: self.api.set_profile_favorite(target, name, favorite))

    @Slot(str, result=str)
    def ListFavorites(self, target: str) -> str:
        """Hedefin sıralı favori profilleri."""
        return reply(lambda: self.api.list_favorites(target))

    @Slot(str, "QStringList", result=str)
    def ReorderFavorites(self, target: str, names: list) -> str:
        """Favori sırasını yeniden yazar."""
        return reply(lambda: self.api.reorder_favorites(target, [str(n) for n in names]))

    @Slot(str, str, result=str)
    def NewProfile(self, target: str, name: str) -> str:
        """Sıfırdan düz bir profil oluşturur ve ona geçer."""
        return reply(lambda: self.api.new_profile(target, name))

    @Slot(str, str, result=str)
    def SetBusDevice(self, bus: str, device: str) -> str:
        """Bus'ın çıkış cihazı. **Yapısal** — graf yeniden kurulur."""
        return reply(lambda: self.api.set_bus_device(bus, device))

    @Slot(str, str, result=str)
    def SetMicDevice(self, chain: str, device: str) -> str:
        """Mikrofon zincirinin giriş cihazı. **Yapısal**."""
        return reply(lambda: self.api.set_mic_device(chain, device))

    @Slot(str, float, result=str)
    def SetMicMonitorVolume(self, chain: str, value: float) -> str:
        """Sidetone seviyesi (0.0–4.0 lineer)."""
        return reply(lambda: self.api.set_mic_monitor_volume(chain, value))

    @Slot(str, bool, result=str)
    def SetMicMonitor(self, chain: str, enabled: bool) -> str:
        """Yan ton (kendi sesini kulaklıktan duyma). **Yapısal**."""
        return reply(lambda: self.api.set_mic_monitor(chain, enabled))

    @Slot(str, bool, result=str)
    def SetMicStreamSend(self, chain: str, enabled: bool) -> str:
        """Mikrofonu yayın miksine de gönderir. **Canlı** (gönderi loopback'i hep kurulu)."""
        return reply(lambda: self.api.set_mic_stream_send(chain, enabled))

    @Slot(bool, result=str)
    def SetChatMixInvert(self, enabled: bool) -> str:
        """Donanım ChatMix tekerinin yönünü ters çevirir."""
        return reply(lambda: self.api.set_chatmix_invert(enabled))

    @Slot(result=str)
    def Provision(self) -> str:
        """Sanal kanalları kurar. **Yapısal**: graf ilk kez ayağa kalkar."""
        return reply(self.api.provision)

    @Slot(bool, result=str)
    def Deprovision(self, purge_settings: bool) -> str:
        """Sanal kanalları söker; sistem Sonar hiç kurulmamış gibi kalır."""
        return reply(lambda: self.api.deprovision(purge_settings))

    @Slot(result=str)
    def SetupSummary(self) -> str:
        """Kurulacak (veya kurulmuş) sanal cihazların listesi."""
        return reply(self.api.setup_summary)

    @Slot(str, result=str)
    def SetLanguage(self, code: str) -> str:
        """Arayüz ve mesaj dili (`tr` / `en`). Grafa dokunmaz."""
        return reply(lambda: self.api.set_language(code))

    @Slot(result=str)
    def StreamSetup(self) -> str:
        """Yayın kurulumunun canlı tanısı — OBS ne dinliyor, mikrofon yayında mı."""
        return reply(self.api.stream_setup)

    @Slot(str, bool, result=str)
    def SetChannelStreamSource(self, channel: str, enabled: bool) -> str:
        """Kanal için OBS'e ayrı bir sanal giriş cihazı yayınla. **Yapısal**."""
        return reply(lambda: self.api.set_channel_stream_source(channel, enabled))

    @Slot(str, str, str, result=str)
    def AddChannel(self, name: str, direction: str, color: str) -> str:
        """Yeni kanal ekler ve id'sini döndürür. **Yapısal**.

        `direction`: `"output"` (uygulamaların çaldığı sanal çıkış) veya `"input"`
        (işlenmiş bir mikrofon kaynağı).
        """
        return reply(
            lambda: self.api.add_channel(
                name, direction or "output", color or "#8B95A5"
            )
        )

    @Slot(str, result=str)
    def RemoveChannel(self, channel: str) -> str:
        """Çıkış veya giriş kanalını siler. **Yapısal**."""
        return reply(lambda: self.api.remove_channel(channel))

    # ------------------------------------------------------------------ yönlendirme

    @Slot(int, str, bool, result=str)
    def MoveStream(self, stream_id: int, channel: str, remember: bool) -> str:
        """`remember` → uygulamayı bundan sonra hep bu kanala gönderen bir kural üretir."""
        return reply(lambda: self.api.move_stream(stream_id, channel, remember))

    @Slot(str, str, str, bool, str, result=str)
    def SetRule(
        self, match_key: str, pattern: str, channel: str, is_regex: bool, direction: str
    ) -> str:
        """Uygulama → hedef kuralı ekler veya günceller.

        `direction` `"out"` (uygulamanın çaldığı ses) veya `"in"` (dinlediği mikrofon).
        """
        return reply(
            lambda: self.api.set_rule(
                match_key, pattern, channel, is_regex, direction or "out"
            )
        )

    @Slot(str, str, str, result=str)
    def RemoveRule(self, match_key: str, pattern: str, direction: str) -> str:
        """Kuralı kaldırır. `direction` boşsa desenin her iki yönü de silinir."""
        return reply(lambda: self.api.remove_rule(match_key, pattern, direction))

    # ------------------------------------------------------------------ ChatMix ve ayarlar

    @Slot(float, result=str)
    def SetChatMix(self, value: float) -> str:
        """ChatMix konumu (0–100, 50 = nötr). Yalnızca kulaklık miksini etkiler."""
        return reply(lambda: self.api.set_chatmix(value))

    @Slot(bool, str, str, result=str)
    def SetChatMixConfig(self, enabled: bool, left: str, right: str) -> str:
        """ChatMix'in hangi kanalları sürdüğü; virgülle çoklu kanal."""
        return reply(lambda: self.api.set_chatmix_config(enabled, left, right))

    @Slot(str, result=str)
    def SetDefaultChannel(self, channel: str) -> str:
        """Kuralla eşleşmeyen uygulamaların düşeceği kanal."""
        return reply(lambda: self.api.set_default_channel(channel))

    @Slot(bool, result=str)
    def SetTakeOverDefaultSink(self, enabled: bool) -> str:
        """Sistem varsayılan çıkışını Sonar'a al (varsayılan kapalı)."""
        return reply(lambda: self.api.set_take_over_default_sink(enabled))

    # ------------------------------------------------------------------ diğer

    @Slot(bool, result=str)
    def SubscribeMeters(self, enabled: bool) -> str:
        """Seviye ölçümünü açar/kapatır. Sonuç: kalan abone sayısı."""
        return reply(lambda: self.api.set_meters_subscribed(enabled))

    @Slot(result=str)
    def GetLevels(self) -> str:
        """Anlık seviyeler. Sürekli akış için `LevelsUpdated` sinyalini dinleyin."""
        return reply(self.api.get_levels)

    @Slot(result=str)
    def Reload(self) -> str:
        """`config.toml`'u diskten yeniden okur (elle düzenleme sonrası)."""
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
