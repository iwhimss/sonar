"""Arayüz ile daemon arasındaki köprü.

QML tarafı buradaki `QObject` özelliklerine ve modellere bağlanır; D-Bus'ın adını bile
görmez. Böylece arayüz, daemon çalışmadan da (testlerde sahte bir istemciyle) sürülebilir.

## İyimser güncelleme

Fader sürüklerken daemon'ın yanıtını beklemek arayüzü hantal gösterirdi. Kullanıcı bir değer
değiştirdiğinde model **anında** güncellenir ve çağrı yola çıkar; daemon'dan gelen
`StateChanged` sinyali değeri düzeltir. Çakışmada daemon kazanır.

Bunun bir tuzağı var: kullanıcı fader'ı sürüklerken daemon'dan gelen eski değerler onu geri
zıplatabilir. Bu yüzden `hold()` ile "şu an bu alanı kullanıcı sürüklüyor" işaretlenir ve o
alan için gelen güncellemeler kısa süre yok sayılır.

## Daemon yokken

`connected` özelliği `false` olur ve arayüz bağlantı ekranını gösterir. Köprü arka planda
yoklamaya devam eder; daemon gelince kendiliğinden bağlanır.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any, ClassVar

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from sonar.core import i18n
from sonar.core.names import (
    BUILTIN_NAMES,
    display_name,
    preset_label,
)

__all__ = [
    "BUILTIN_NAMES",
    "ChannelModel",
    "DeviceModel",
    "SonarBridge",
    "StreamModel",
    "channel_rows",
    "device_rows",
    "display_name",
    "stream_rows",
]

log = logging.getLogger(__name__)

#: Kullanıcının sürüklediği alanın daemon güncellemelerine kapalı kalma süresi.
HOLD_MS = 400

#: Daemon yoksa yeniden deneme aralığı.
RECONNECT_MS = 2000


# --------------------------------------------------------------------------- saf dönüşümler
#
# Bu üç fonksiyon daemon'ın JSON durumunu modellerin satırlarına çevirir. Saf oldukları için
# Qt olmadan test edilebiliyorlar.


def channel_rows(state: dict) -> list[dict]:
    """Kanal şeritlerinin satırları — mikserde soldan sağa görünecek sırayla."""
    config = state.get("config") or {}
    builtins = state.get("builtin_profiles") or {}
    profiles = {
        target: [
            {"name": name, "builtin": name in set(builtins.get(target) or [])} for name in names
        ]
        for target, names in (state.get("profile_names") or {}).items()
    }
    # Tek çıkış bus'ı var (Faz 27); kanalların kulaklık gönderisi hep ona gider.
    output_bus = output_bus_id(config)

    rows = []
    for channel in sorted(config.get("channels", []), key=lambda c: (c["order"], c["id"])):
        sends = channel.get("sends") or {}
        rows.append(
            {
                "id": channel["id"],
                "name": display_name("channel", channel["id"], channel["name"]),
                "color": channel["color"],
                "icon": channel.get("icon", "speaker"),
                "builtin": bool(channel.get("builtin")),
                "activeProfile": channel.get("active_profile", "Default"),
                "profiles": profiles.get(channel["id"], []),
                "personalVolume": _send(sends, output_bus)["volume"],
                "personalMuted": _send(sends, output_bus)["muted"],
                "streamVolume": _send(sends, "stream")["volume"],
                "streamMuted": _send(sends, "stream")["muted"],
                # Çıkış kanalları her zaman yayın miksinde; alan yalnızca giriş
                # kanallarında anlamlı ama model rolü her satırda tanımlı olmalı.
                "inStream": True,
                "kind": "channel",
            }
        )
    for mic in sorted(config.get("mic_chains", []), key=lambda m: (m.get("order", 0), m["id"])):
        if mic.get("share_chain_with_mic"):
            continue  # kendi DSP'si yok; başka bir zincirin kopyası, ayrı şerit değil
        rows.append(
            {
                "id": mic["id"],
                "name": display_name("mic", mic["id"], mic["name"]),
                "color": mic.get("color", "#F2A73B"),
                "icon": mic.get("icon", "mic"),
                "builtin": bool(mic.get("builtin")),
                "activeProfile": mic.get("active_profile", "Default"),
                "profiles": profiles.get(mic["id"], []),
                "personalVolume": mic["monitor_volume"],
                "personalMuted": not mic.get("monitor_enabled", False),
                "streamVolume": mic["volume"],
                "streamMuted": mic["muted"],
                # Mikrofon yayın miksine katılıyor mu. Katılmıyorsa şeritteki 📡 fader'ı
                # yayına hiçbir şey yapmıyor demektir ve bunu şeritte söylüyoruz —
                # kullanıcı üçüncü turda tam bu yüzden "fader ölü" dedi.
                "inStream": bool(mic.get("send_to_stream_bus", True)),
                "kind": "mic",
            }
        )
    return rows


def output_bus_id(config: dict) -> str:
    """Tek çıkış bus'ının kimliği. Faz 27'den beri her zaman bir tane var."""
    for bus in sorted(config.get("buses", []), key=lambda b: (b.get("order", 0), b["id"])):
        if bus.get("kind") != "stream":
            return str(bus["id"])
    return "personal"


def _send(sends: dict, bus_id: str) -> dict:
    """Bir gönderi; yoksa nötr. Yeni eklenen bir bus'ın gönderisi henüz diskte yok."""
    value = sends.get(bus_id)
    return value if isinstance(value, dict) else {"volume": 1.0, "muted": False}


def stream_rows(state: dict) -> list[dict]:
    """Çalan uygulamalar. `channel` alanı hangi şeridin altında görüneceğini söyler.

    Kanal bilgisi daemon'dan hazır geliyor (`api.get_streams`); `target_node` yalnızca
    uygulamanın kendi seçtiği hedefi gösterdiği için yedek olarak kullanılıyor.
    """
    config = state.get("config") or {}
    by_node = {f"sonar_{c['id']}": c["id"] for c in config.get("channels", [])}
    by_node.update({f"sonar_{m['id']}": m["id"] for m in config.get("mic_chains", [])})
    # Bus'ı dinleyen akışlar (OBS'in yayın miksini yakalaması gibi) master şeridine
    # düşsün; eskiden hiçbir yere düşmüyor ve kullanıcı "OBS görünmüyor" diyordu.
    by_node.update({f"sonar_{b['id']}": b["id"] for b in config.get("buses", [])})
    by_node.update({f"sonar_{b['id']}_out": b["id"] for b in config.get("buses", [])})

    rows = []
    for stream in state.get("streams", []):
        # Yakalama akışları artık atılmıyor: aynı uygulama hem çıkış hem giriş
        # şeridinde görünüyor (Discord örneği). Ayrım `direction` alanında.
        #
        # Masaüstü sesini yakalayanlar da **gösteriliyor** (OBS'in "Masaüstü Sesi"
        # kaynağı gibi); yalnızca otomatik yönlendirilmiyorlar — o eleme `Router`'da.
        # Eskiden buradan da eleniyorlardı ve OBS arayüzde hiç görünmüyordu.
        capture = bool(stream.get("is_capture"))
        rows.append(
            {
                "id": stream["id"],
                "label": stream.get("app_name")
                or stream.get("app_binary")
                or stream.get("media_name")
                or f"#{stream['id']}",
                "binary": stream.get("app_binary", ""),
                "channel": stream.get("channel") or by_node.get(stream.get("target_node", ""), ""),
                "direction": stream.get("direction") or ("in" if capture else "out"),
                # Masaüstü sesi yakalayan akış: kural motoru ona dokunmuyor.
                "capturesSink": bool(stream.get("captures_sink")),
            }
        )
    return rows


def device_rows(state: dict, *, sources: bool) -> list[dict]:
    """Cihaz seçicilerinin içeriği. İlk satır her zaman 'sistem varsayılanı'."""
    rows = [{"name": "", "label": i18n.t("device.system_default"), "isSource": sources}]
    for device in state.get("devices", []):
        if bool(device.get("is_source")) is not sources:
            continue
        rows.append(
            {
                "name": device["name"],
                "label": device.get("description") or device["name"],
                "isSource": sources,
            }
        )
    return rows


# --------------------------------------------------------------------------- modeller


class _DictModel(QAbstractListModel):
    """Sözlük satırlarını QML'e sunan basit model.

    Roller satırların anahtarlarından türetilir; `Qt.UserRole + n`. QML tarafında
    `model.<anahtar>` olarak erişilir.
    """

    keys: tuple[str, ...] = ()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._roles = {
            Qt.ItemDataRole.UserRole + index: QByteArray(key.encode())
            for index, key in enumerate(self.keys)
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self) -> dict:
        return self._roles

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        key = self._roles.get(role)
        if key is None:
            return None
        return self._rows[index.row()].get(bytes(key).decode())

    @Slot(int, result="QVariant")
    def get(self, row: int) -> dict:
        """QML'den tek bir satırı sözlük olarak almak için."""
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    def rows(self) -> list[dict]:
        return list(self._rows)

    def replace(self, rows: list[dict]) -> None:
        """Satırları değiştirir. Uzunluk aynıysa yalnızca değişen hücreler bildirilir —
        aksi hâlde her güncellemede tüm delegeler yeniden kurulur ve sürükleme takılır."""
        if len(rows) == len(self._rows):
            changed = [
                i for i, (old, new) in enumerate(zip(self._rows, rows, strict=True)) if old != new
            ]
            self._rows = rows
            for index in changed:
                model_index = self.index(index, 0)
                self.dataChanged.emit(model_index, model_index, list(self._roles))
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def update_row(self, row: int, values: dict) -> None:
        if not 0 <= row < len(self._rows):
            return
        self._rows[row] = {**self._rows[row], **values}
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, list(self._roles))

    def index_of(self, key: str, value: Any) -> int:
        for index, row in enumerate(self._rows):
            if row.get(key) == value:
                return index
        return -1


class ChannelModel(_DictModel):
    keys = (
        "id", "name", "color", "icon", "builtin", "activeProfile", "profiles",
        "personalVolume", "personalMuted", "streamVolume", "streamMuted",
        "inStream", "kind",
    )  # fmt: skip


class StreamModel(_DictModel):
    keys = ("id", "label", "binary", "channel", "direction", "capturesSink")


class DeviceModel(_DictModel):
    keys = ("name", "label", "isSource")


# --------------------------------------------------------------------------- köprü


class SonarBridge(QObject):
    """QML'in gördüğü tek nesne."""

    connectedChanged = Signal()
    stateChanged = Signal()
    chatmixChanged = Signal()
    mastersChanged = Signal()
    revisionChanged = Signal()
    levelsChanged = Signal()
    errorRaised = Signal(str, str)
    noticeRaised = Signal(str, bool)  # (metin, hata mı)
    graphRebuilt = Signal()
    #: Dil değişti — `app.py` bunu çeviri nesnesine ve `ui.json`'a bağlıyor.
    languageChanged = Signal(str)
    #: Kurulum bitti: `(başarılı mı, mesaj)`. Karşılama ekranı bunu dinliyor.
    provisionFinished = Signal(bool, str)
    #: Kaldırma bitti: `(başarılı mı, ayarlar da silindi mi)`.
    deprovisionFinished = Signal(bool, bool)
    busyChanged = Signal()

    def __init__(
        self,
        client: Any | None = None,
        parent: QObject | None = None,
        *,
        hold_ms: int = HOLD_MS,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._connected = False
        self._revision = 0
        self._levels_revision = 0
        self._state: dict = {}
        self._hold_ms = hold_ms
        self._held: dict[str, float] = {}

        # Modeller QML'e **özellik** olarak açılıyor; düz Python özniteliği olarak
        # bırakıldıklarında QML tarafından hiç görülmüyorlar (sessizce `undefined`).
        self._channels = ChannelModel(self)
        self._streams = StreamModel(self)
        self._levels: dict[str, dict] = {}
        self._sinks = DeviceModel(self)
        self._sources = DeviceModel(self)
        #: `StreamSetup` tanısının önbelleği. Ayrı bir D-Bus çağrısı ve QML bağlaması her
        #: `revision` artışında yeniden değerlendiriliyor; fader sürüklerken bu saniyede
        #: onlarca çağrı demek olurdu. Yarım saniyelik pencere tanı için fazlasıyla taze.
        self._setup: dict = {}
        self._setup_at = 0.0
        #: Kurulum/kaldırma sürüyor. D-Bus çağrısı bloke ediyor; arayüz önce "kuruluyor…"
        #: yazabilsin diye iş bir sonraki olay döngüsü turuna atılıyor.
        self._busy = False
        #: Kaldırmadan sonra kullanıcıya gösterilecek, root gerektiren adımlar.
        self._manual_steps: list = []

        self._reconnect = QTimer(self)
        self._reconnect.setInterval(RECONNECT_MS)
        self._reconnect.timeout.connect(self._try_connect)

    # ------------------------------------------------------------------ bağlantı

    def attach(self, client: Any) -> None:
        """İstemciyi bağlar. Testler burada sahte bir istemci verir."""
        self._client = client

    @Slot()
    def start(self) -> None:
        self._try_connect()
        if not self._connected:
            self._reconnect.start()

    def _try_connect(self) -> None:
        if self._client is None:
            return
        state = self._call("GetState")
        if state is None:
            self._set_connected(False)
            return
        self._reconnect.stop()
        self._set_connected(True)
        self.apply_state(state)

    def _set_connected(self, value: bool) -> None:
        if self._connected != value:
            self._connected = value
            self.connectedChanged.emit()
            if not value:
                self._reconnect.start()

    # ------------------------------------------------------------------ durum

    def apply_state(self, state: dict) -> None:
        """Tam durumu uygular. Açılışta ve `GraphRebuilt` sonrasında çağrılır."""
        previous = self._settings().get("language")
        self._state = state
        language = self._settings().get("language")
        # Dil `sonar-cli lang` ile de değişebiliyor; arayüz daemon'ı takip etsin.
        if language and language != previous:
            # Dili **burada** kurmuyoruz. `sonar.core.i18n` süreç genelinde tek bir dil
            # tutuyor ve QML'in tazeleme tetiği `QmlI18n.language` özelliği; ikisini ayrı
            # yerlerden yazmak arayüzü karışık dilde bırakıyordu (ölçüldü: yükleme
            # sırasında değerlenen bağlamalar bir dilde, sonradan tazelenenler ötekinde).
            # Tek yol: sinyal → `app._apply_language` → `QmlI18n` → çekirdek.
            self.languageChanged.emit(str(language))
        self._refresh_models()
        self._bump()
        self.stateChanged.emit()
        self.chatmixChanged.emit()
        self.mastersChanged.emit()

    def _bump(self) -> None:
        self._revision += 1
        self.revisionChanged.emit()

    def _refresh_models(self) -> None:
        rows = channel_rows(self._state)
        held = {row["id"]: row for row in self._channels.rows()}
        for row in rows:
            previous = held.get(row["id"])
            if previous is None:
                continue
            for field in ("personalVolume", "streamVolume"):
                if self._is_held(f"{row['id']}.{field}"):
                    row[field] = previous[field]
        self._channels.replace(rows)
        self._streams.replace(stream_rows(self._state))
        self._sinks.replace(device_rows(self._state, sources=False))
        self._sources.replace(device_rows(self._state, sources=True))

    @Slot(str)
    def onStateChanged(self, payload: str) -> None:
        """Daemon delta yolladı. Delta yalnızca *neyin* değiştiğini söylüyor; tam durumu
        yeniden çekmek en basit ve en az hata yapan yol — `GetState` ucuz."""
        self._announce(payload)
        state = self._call("GetState")
        if state is not None:
            self.apply_state(state)

    #: Kullanıcıya söylenmesi gereken deltalar → (metin şablonu, hata mı).
    #: Şablonlar katalog **anahtarı** tutuyor; biçimlendirme delta alanlarıyla burada
    #: yapılıyor. `save_failed` bir istisna: metni daemon üretiyor (dosya sistemi hatası).
    _NOTICES: ClassVar[dict[str, tuple[str, bool]]] = {
        "profile_copied": ("notice.profile_copied", False),
        "save_failed": ("notice.save_failed", True),
        "path_ok": ("notice.path_ok", False),
    }

    def _announce(self, payload: str) -> None:
        """Sessizce olup biten şeyleri kullanıcıya söyler.

        `profile_copied` özellikle önemli: kullanıcı gömülü bir preseti kurcalayınca
        daemon arkada '<ad> (özel)' kopyası açıyor ve aktif profili değiştiriyor.
        Söylenmezse "seçtiğim preset neden değişti?" oluyor.
        """
        try:
            changes = json.loads(payload).get("changes") or []
        except (json.JSONDecodeError, AttributeError):
            return
        for change in changes:
            # Kopan ses yolu şablona sığmıyor: kanal adları listeden geliyor.
            if change.get("kind") == "path_broken":
                names = ", ".join(change.get("channels") or []) or i18n.t("notice.a_channel")
                self.noticeRaised.emit(i18n.t("notice.path_broken", names=names), True)
                continue
            notice = self._NOTICES.get(change.get("kind"))
            if notice is None:
                continue
            key, is_error = notice
            with contextlib.suppress(KeyError, IndexError):
                self.noticeRaised.emit(i18n.t(key, **change), is_error)

    @Slot(str)
    def onStreamsChanged(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        self._state["streams"] = data.get("streams", [])
        self._state["devices"] = data.get("devices", [])
        self._streams.replace(stream_rows(self._state))
        self._sinks.replace(device_rows(self._state, sources=False))
        self._sources.replace(device_rows(self._state, sources=True))
        self._bump()

    @Slot(str)
    def onLevelsUpdated(self, payload: str) -> None:
        try:
            levels = json.loads(payload)
        except json.JSONDecodeError:
            return
        self._levels = levels
        self._levels_revision += 1
        self.levelsChanged.emit()

    @Slot(str, result="QVariant")
    def levelOf(self, channel: str) -> dict:
        """Bir kanalın anlık seviyesi. Ölçüm yoksa taban değerler.

        Eskiden seviyeler `ChannelModel` satırlarına yazılıyordu, ama mikser şeride
        `channels.get(index)` ile **anlık bir sözlük kopyası** veriyor; kopya
        tazelenmediği için metreler hiç oynamıyordu (kullanıcı: "boş görünüyordu").
        """
        level = (self._levels or {}).get(f"sonar_{channel}")
        if level is None:
            return {"peak_db": -60.0, "hold_db": -60.0, "clipped": False}
        return level

    @Slot()
    def onGraphRebuilt(self) -> None:
        self._try_connect()
        self.graphRebuilt.emit()

    @Slot(str, str)
    def onError(self, code: str, message: str) -> None:
        self.errorRaised.emit(code, message)

    # ------------------------------------------------------------------ özellikler

    def _get_revision(self) -> int:
        """Modeller her değiştiğinde artar.

        QML'de `model.rowCount()` gibi **fonksiyon** çağrıları bir özellik değişimine
        bağlı olmadıkları için kendiliğinden yeniden değerlendirilmiyor; sekme listesi ve
        cihaz açılır listeleri boş kalıyordu. Bu sayacı okuyan binding'ler artık tazeleniyor.
        """
        return self._revision

    revision = Property(int, _get_revision, notify=revisionChanged)

    def _get_levels_revision(self) -> int:
        """Yalnızca seviye güncellemelerinde artar.

        Ayrı bir sayaç: `revision` saniyede 20 kez artsaydı her şeridin **tamamı**
        yeniden değerlendirilirdi. Metre bileşenleri yalnızca bunu okuyor.
        """
        return self._levels_revision

    levelsRevision = Property(int, _get_levels_revision, notify=levelsChanged)

    def _get_connected(self) -> bool:
        return self._connected

    connected = Property(bool, _get_connected, notify=connectedChanged)

    def _get_channels(self) -> ChannelModel:
        return self._channels

    channels = Property(QObject, _get_channels, constant=True)

    def _get_streams(self) -> StreamModel:
        return self._streams

    streams = Property(QObject, _get_streams, constant=True)

    def _get_sinks(self) -> DeviceModel:
        return self._sinks

    sinks = Property(QObject, _get_sinks, constant=True)

    def _get_sources(self) -> DeviceModel:
        return self._sources

    sources = Property(QObject, _get_sources, constant=True)

    def _get_chatmix(self) -> float:
        return float(((self._state.get("config") or {}).get("chatmix") or {}).get("value", 50.0))

    chatmix = Property(float, _get_chatmix, notify=chatmixChanged)

    def _get_masters(self) -> dict:
        """Bus id → bus sözlüğü, artı `"mic"` anahtarıyla birincil mikrofon zinciri.

        Çıkış bus'ı sayısı artık sabit değil; `outputs` listesi mikserin master
        şeritlerini soldan sağa sürüyor.
        """
        config = self._state.get("config") or {}
        buses = {b["id"]: b for b in config.get("buses", [])}
        mic = next((m for m in config.get("mic_chains", []) if m["id"] == "mic"), {})
        return {**buses, "mic": mic}

    masters = Property("QVariant", _get_masters, notify=mastersChanged)

    def _get_output_bus_id(self) -> str:
        """Tek çıkış bus'ının kimliği. Arayüz onu ada göre aramak zorunda kalmasın."""
        return output_bus_id(self._state.get("config") or {})

    outputBusId = Property(str, _get_output_bus_id, notify=mastersChanged)

    def _settings(self) -> dict:
        return (self._state.get("config") or {}).get("settings") or {}

    def _get_language(self) -> str:
        return str(self._settings().get("language") or "tr")

    language = Property(str, _get_language, notify=stateChanged)

    @Slot(str)
    def setLanguage(self, code: str) -> None:
        """Dili daemon'a yazar ve arayüzü hemen çevirir.

        Arayüz daemon'ın yanıtını beklemiyor: `languageChanged` burada yayılıyor, çünkü
        daemon kapalıyken de (karşılama ekranı, "servis çalışmıyor" paneli) dil seçici
        çalışmalı. Daemon açıksa `apply_state` aynı değeri geri getirir ve ikinci bir
        yayım olmaz.
        """
        self._call("SetLanguage", code)
        self.languageChanged.emit(code)
        # Yayın tanısının metinlerini **daemon** üretiyor ve önbellekte eski dilde
        # duruyor; süresi dolana kadar master şeridi Türkçe kalıyordu (ölçüldü).
        self._setup_at = 0.0
        # Satırlardaki gömülü adlar (`display_name`) çeviriyle üretiliyor; modeller
        # yeniden kurulmazsa sekme başlıkları eski dilde kalırdı.
        self._refresh_models()
        self._bump()

    @Slot()
    def startDaemon(self) -> None:
        """Daemon'ı başlatmayı dener: önce D-Bus etkinleştirmesi, sonra doğrudan süreç.

        Kullanıcının şikâyeti: *"uygulama açılırken farklı kodlar vs. girmek gerekiyor."*
        Kurulu bir sistemde otobüs daemon'ı kendisi kaldırıyor; depodan çalıştırmada
        (servis dosyası yok) süreci burada başlatıyoruz.
        """
        import subprocess
        import sys

        starter = getattr(self._client, "start_service", None)
        if starter is not None and starter():
            self._try_connect()
            if self._connected:
                return
        command = [sys.executable, "-m", "sonar.daemon.service"]
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            self.noticeRaised.emit(i18n.t("daemon.start_failed", error=error), True)
            return
        # Graf ilk kurulumda birkaç saniye sürüyor; yoklama zamanlayıcısı zaten dönüyor.
        self.noticeRaised.emit(i18n.t("daemon.starting"), False)
        self._reconnect.start()

    def _get_busy(self) -> bool:
        return self._busy

    busy = Property(bool, _get_busy, notify=busyChanged)

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    @Slot(result="QVariant")
    def setupSummary(self) -> dict:
        """Kurulacak (veya kurulmuş) sanal cihazların listesi."""
        return self._call("SetupSummary") or {}

    @Slot()
    def provision(self) -> None:
        """Sanal kanalları kurar.

        Çağrı bloke ediyor (graf ilk kez ayağa kalkıyor, ~1 sn). Arayüzün "kuruluyor…"
        yazabilmesi için iş bir sonraki olay döngüsü turuna atılıyor; aksi hâlde kullanıcı
        düğmeye basıyor ve ekran donuk kalıyor.
        """
        if self._busy:
            return
        self._set_busy(True)
        QTimer.singleShot(50, self._provision_now)

    def _provision_now(self) -> None:
        try:
            result = self._call("Provision")
        finally:
            self._set_busy(False)
        if result is None:
            # Hata zaten `errorRaised`/log ile bildirildi; ekran tekrar denemeye izin verir.
            self.provisionFinished.emit(False, i18n.t("welcome.install_failed"))
            return
        self.refresh()
        self.provisionFinished.emit(True, "")

    @Slot(bool)
    def deprovision(self, purge_settings: bool) -> None:
        """Sanal kanalları söker. Sonuçtaki elle yapılacak adımlar bildirim olarak çıkar."""
        if self._busy:
            return
        self._set_busy(True)
        QTimer.singleShot(50, lambda: self._deprovision_now(bool(purge_settings)))

    def _deprovision_now(self, purge_settings: bool) -> None:
        try:
            result = self._call("Deprovision", purge_settings)
        finally:
            self._set_busy(False)
        self.refresh()
        if result is None:
            # Çağrı reddedildi ya da daemon gitti. Pencere "kaldırıldı" demesin:
            # test turu 5'te kullanıcı "kaldırıldı dedi ama hiçbir şey olmadı" dedi ve
            # haklıydı — köprü `undefined`di, diyalog yine de başarı panelini açıyordu.
            self.noticeRaised.emit(i18n.t("uninstall.failed"), True)
            self.deprovisionFinished.emit(False, False)
            return
        self._manual_steps = result.get("manual_steps") or []
        self.noticeRaised.emit(i18n.t("uninstall.done"), False)
        self.deprovisionFinished.emit(True, bool(result.get("purged")))

    @Slot(result="QVariant")
    def manualSteps(self) -> list:
        """Kaldırmadan sonra elle yapılacaklar. Root'a ait işleri daemon yapmıyor."""
        return self._manual_steps

    def _get_take_over_default_sink(self) -> bool:
        return bool(self._settings().get("take_over_default_sink", False))

    takeOverDefaultSink = Property(bool, _get_take_over_default_sink, notify=stateChanged)

    @Slot(bool)
    def setTakeOverDefaultSink(self, enabled: bool) -> None:
        self._call("SetTakeOverDefaultSink", bool(enabled))
        self.refresh()

    def _get_chatmix_invert(self) -> bool:
        return bool(self._settings().get("chatmix_invert", False))

    chatmixInvert = Property(bool, _get_chatmix_invert, notify=stateChanged)

    @Slot(bool)
    def setChatMixInvert(self, enabled: bool) -> None:
        """Donanım tekerinin yönü. Faz 35'te modele girdi, arayüz karşılığı yoktu."""
        self._call("SetChatMixInvert", bool(enabled))
        self.refresh()

    def _get_provisioned(self) -> bool:
        """Sanal kanallar kuruldu mu. Daemon'a bağlı değilken `True` sayılır —
        bilinmeyen bir durumda karşılama ekranını açmak yanlış olurdu."""
        if not self._connected:
            return True
        return bool(self._settings().get("provisioned", True))

    provisioned = Property(bool, _get_provisioned, notify=stateChanged)

    def _get_conflicts(self) -> list:
        return self._state.get("conflicts", [])

    conflicts = Property("QVariant", _get_conflicts, notify=stateChanged)

    # ------------------------------------------------------------------ eylemler

    @Slot(str, str, float)
    def setChannelVolume(self, channel: str, bus: str, value: float) -> None:
        # Arayüzdeki iki fader "output" (kanalın seçili çıkışı) ve "stream" adını
        # kullanıyor; hangi bus'a yazılacağını daemon çözüyor.
        field = "streamVolume" if bus == "stream" else "personalVolume"
        self._optimistic(channel, field, value)
        self._call("SetChannelVolume", channel, bus, value)

    @Slot(str, str, bool)
    def setChannelMute(self, channel: str, bus: str, muted: bool) -> None:
        field = "streamMuted" if bus == "stream" else "personalMuted"
        self._optimistic(channel, field, muted)
        self._call("SetChannelMute", channel, bus, muted)

    @Slot(str, float)
    def setMasterVolume(self, bus: str, value: float) -> None:
        self._call("SetMasterVolume", bus, value)

    @Slot(str, bool)
    def setMasterMute(self, bus: str, muted: bool) -> None:
        self._call("SetMasterMute", bus, muted)

    @Slot(str, float)
    def setMicVolume(self, chain: str, value: float) -> None:
        self._optimistic(chain, "streamVolume", value)
        self._call("SetMicVolume", chain, value)

    @Slot(str, bool)
    def setMicMute(self, chain: str, muted: bool) -> None:
        self._optimistic(chain, "streamMuted", muted)
        self._call("SetMicMute", chain, muted)

    @Slot(str, bool)
    def setMicStreamSend(self, chain: str, enabled: bool) -> None:
        """Mikrofon yayın miksine katılsın mı — OBS tek kaynak kullanıyorsa açık olmalı."""
        self._setup_at = 0.0  # tanı hemen tazelensin
        self._call("SetMicStreamSend", chain, enabled)

    @Slot(result="QVariant")
    def streamSetup(self) -> dict:
        """Yayın kurulumu tanısı; `api.stream_setup()`in önbelleklenmiş hâli."""
        now = time.monotonic()
        if not self._setup or now - self._setup_at > 0.5:
            result = self._call("StreamSetup")
            if isinstance(result, dict):
                self._setup = result
                self._setup_at = now
        return self._setup

    @Slot(str, bool)
    def setMicMonitor(self, chain: str, enabled: bool) -> None:
        self._optimistic(chain, "personalMuted", not enabled)
        self._call("SetMicMonitor", chain, enabled)

    @Slot(str, float)
    def setMicMonitorVolume(self, chain: str, value: float) -> None:
        """Sidetone seviyesi — giriş şeridindeki kulaklık fader'ı."""
        self._optimistic(chain, "personalVolume", value)
        self._call("SetMicMonitorVolume", chain, value)

    # ------------------------------------------------------------------ FX sayfası

    @Slot(str, result=str)
    def eqJson(self, target: str) -> str:
        """Seçili hedefin EQ durumu — `EqCurve.eq` bunu bekliyor."""
        profile = (self._state.get("profiles") or {}).get(target) or {}
        return json.dumps(profile.get("eq") or {})

    @Slot(str, result="QVariant")
    def profileOf(self, target: str) -> dict:
        """Aktif profilin tamamı: EQ + filtreler + favori slotu."""
        return (self._state.get("profiles") or {}).get(target) or {}

    @Slot(str, str, result="QVariant")
    def filterOf(self, target: str, slot: str) -> dict:
        """Tek bir slotun durumu; zincirde yoksa boş sözlük.

        `stage` yerine artık **slot kimliği** (şema 7): aynı efektten birden fazla
        eklenebiliyor ve her birinin kendi ayarları var.
        """
        for effect in self.profileOf(target).get("effects") or []:
            if effect.get("slot") == slot:
                return effect
        return {}

    @Slot(str, result="QVariant")
    def effectsOf(self, target: str) -> list:
        """Hedefin efekt zinciri, sinyal sırasıyla. FX sayfasının panel listesi bu."""
        return list(self.profileOf(target).get("effects") or [])

    @Slot(str, result="QVariant")
    def effectKinds(self, target: str) -> list:
        """Bu hedefe eklenebilecek efektler — kurulu olmayanlar listede yok."""
        return self._call("ListEffectKinds", target) or []

    @Slot(str, str)
    def addEffect(self, target: str, kind: str) -> None:
        """Zincirin sonuna efekt ekler. **Yapısal**: graf yeniden kurulur (~200 ms)."""
        self._call("AddEffect", target, kind, -1)
        self.refresh()

    @Slot(str, str)
    def removeEffect(self, target: str, slot: str) -> None:
        self._call("RemoveEffect", target, slot)
        self.refresh()

    @Slot(str, str, int)
    def moveEffect(self, target: str, slot: str, index: int) -> None:
        self._call("MoveEffect", target, slot, index)
        self.refresh()

    @Slot(str, result="QVariant")
    def profileNames(self, target: str) -> list:
        """Profil listesi; gömülü presetler `builtin: true` ile işaretli."""
        builtin = set((self._state.get("builtin_profiles") or {}).get(target) or [])
        return [
            {"name": name, "builtin": name in builtin}
            for name in (self._state.get("profile_names") or {}).get(target) or []
        ]

    @Slot(result=bool)
    def chatmixIsHardware(self) -> bool:
        """ChatMix'i kulaklık tekeri sürüyorsa slider salt okunur olur."""
        return bool(self._state.get("chatmix_hardware"))

    @Slot(str, result="QVariant")
    def ducking(self, target: str) -> dict:
        """Bir hedefin **profilindeki** Smart Volume ayarları (şema 4)."""
        profile = self._profile_dict(target) or {}
        return dict(profile.get("ducking") or {})

    @Slot(str, "QVariant")
    def setDucking(self, target: str, fields: Any) -> None:
        """Smart Volume ayarlarını değiştirir. Yalnızca verilen alanlar yazılır.

        QML'den gelen sözlük bir `QJSValue`; `dict()` onu iterable sanıp `TypeError`
        veriyordu ve anahtar hiç çalışmıyordu (test turu 3). `toVariant()` gerçek bir
        Python sözlüğü veriyor.
        """
        import json as _json

        payload = _as_dict(fields)
        self._call("SetDucking", target, _json.dumps(payload))
        self.refresh()

    @Slot(str, result=str)
    def busLabel(self, bus_id: str) -> str:
        """Bir bus'ın arayüzde görünecek adı (kullanıcı adlandırmışsa onunki)."""
        buses = (self._state.get("config") or {}).get("buses") or []
        bus = next((b for b in buses if b.get("id") == bus_id), None)
        if bus is None:
            return bus_id
        return display_name("bus", bus_id, str(bus.get("name", bus_id)))

    @Slot(str, result=str)
    def presetLabel(self, name: str) -> str:
        """Gömülü preset adının çevirisi; kullanıcının kendi profil adları değişmez."""
        return preset_label(name)

    @Slot(str, result=bool)
    def isInputChannel(self, target: str) -> bool:
        """Hedef bir giriş kanalı mı? Sabit `"mic"`/`"stream_mic"` listesi yetmiyor —
        kullanıcı kendi giriş kanalını ekleyebiliyor (Faz 13)."""
        config = self._state.get("config") or {}
        return any(mic["id"] == target for mic in config.get("mic_chains", []))

    @Slot(str, result="QVariant")
    def streamsFor(self, channel: str) -> list:
        """Bir kanalda çalan uygulamalar.

        Süzme burada yapılıyor: şerit tüm akış modelini gezip görünmeyenleri
        `height: 0` ile saklıyordu, bu yüzden liste kutudan taşıyordu.
        """
        return [row for row in self._streams.rows() if row.get("channel") == channel]

    @Slot(str, result=float)
    def chatmixGain(self, channel: str) -> float:
        """Kanalın ChatMix çarpanı. 1.0 = dokunulmamış."""
        return float((self._state.get("chatmix_gains") or {}).get(channel, 1.0))

    @Slot(str, str)
    def importProfile(self, target: str, path: str) -> None:
        """Bir EQ dosyasını profil olarak içe aktarır ve sonucu kullanıcıya söyler."""
        from pathlib import Path

        try:
            text = Path(path.removeprefix("file://")).read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            self.noticeRaised.emit(
                i18n.t("notice.read_failed", error=error.strerror or error), True
            )
            return
        result = self._call("ImportProfile", target, text, "")
        self.refresh()
        if result is None:
            return  # hata zaten `errorRaised` ile bildirildi
        parts = [
            i18n.t("notice.imported", name=result.get("name"), source=result.get("source"))
        ]
        if result.get("dropped"):
            parts.append(i18n.t("notice.bands_dropped", count=result["dropped"]))
        parts.extend(result.get("warnings") or [])
        self.noticeRaised.emit(" — ".join(parts), False)

    @Slot(str, str, bool)
    def exportProfile(self, target: str, path: str, autoeq: bool) -> None:
        from pathlib import Path

        text = self._call("ExportProfile", target, "", autoeq)
        if text is None:
            return
        target_path = Path(path.removeprefix("file://"))
        try:
            target_path.write_text(text, encoding="utf-8")
        except OSError as error:
            self.noticeRaised.emit(
                i18n.t("notice.write_failed", error=error.strerror or error), True
            )
            return
        self.noticeRaised.emit(i18n.t("notice.saved", name=target_path.name), False)

    @Slot(str)
    def resetProfile(self, target: str) -> None:
        self._call("ResetProfile", target)
        self.refresh()

    @Slot(str, result="QVariant")
    def channelOf(self, target: str) -> dict:
        row = self._channels.index_of("id", target)
        return self._channels.get(row) if row >= 0 else {}

    @Slot(str, bool)
    def setEqEnabled(self, target: str, enabled: bool) -> None:
        self._patch_eq(target, {"enabled": enabled})
        self._call("SetFilterEnabled", target, "eq", enabled)

    @Slot(str, int, str, str)
    def setEqBand(self, target: str, band: int, field: str, value: str) -> None:
        self._patch_band(target, band, field, value)
        self._call("SetEqBand", target, band, field, value)

    @Slot(str, float)
    def setEqPreamp(self, target: str, value_db: float) -> None:
        self._patch_eq(target, {"preamp_db": value_db})
        self._call("SetEqPreamp", target, value_db)

    @Slot(str, float, float)
    def addEqBand(self, target: str, freq: float, gain_db: float) -> None:
        """Eğriye sağ tıklamanın karşılığı. Canlı — ses kesilmez."""
        self._call("AddEqBand", target, freq, gain_db)
        self.refresh()

    @Slot(str, int)
    def removeEqBand(self, target: str, index: int) -> None:
        self._call("RemoveEqBand", target, index)
        self.refresh()

    @Slot(str, str, bool)
    def setFilterEnabled(self, target: str, stage: str, enabled: bool) -> None:
        self._patch_filter(target, stage, {"enabled": enabled})
        self._call("SetFilterEnabled", target, stage, enabled)

    @Slot(str, str, str, float)
    def setFilterParam(self, target: str, stage: str, name: str, value: float) -> None:
        state = self._patch_filter(target, stage, None)
        if state is not None:
            state.setdefault("params", {})[name] = value
            self._bump()
        self._call("SetFilterParam", target, stage, name, value)

    @Slot(str, str)
    def saveProfile(self, target: str, name: str) -> None:
        self._call("SaveProfile", target, name)
        self.refresh()

    @Slot(str, str)
    def deleteProfile(self, target: str, name: str) -> None:
        self._call("DeleteProfile", target, name)
        self.refresh()

    @Slot(str, str, str)
    def renameProfile(self, target: str, old: str, new: str) -> None:
        self._call("RenameProfile", target, old, new)
        self.refresh()

    @Slot(str, str, bool)
    def setProfileFavorite(self, target: str, name: str, favorite: bool) -> None:
        self._call("SetProfileFavorite", target, name, favorite)
        self.refresh()

    @Slot(str, result="QVariant")
    def favoritesOf(self, target: str) -> list:
        """Hedefin sıralı favori profilleri."""
        return list((self._state.get("favorites") or {}).get(target) or [])

    @Slot(str, "QVariantList")
    def reorderFavorites(self, target: str, names: list) -> None:
        favorites = self._state.setdefault("favorites", {})
        favorites[target] = [str(name) for name in names]
        self._bump()
        self._call("ReorderFavorites", target, [str(name) for name in names])

    @Slot(str, str)
    def newProfile(self, target: str, name: str) -> None:
        self._call("NewProfile", target, name)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        state = self._call("GetState")
        if state is not None:
            self.apply_state(state)

    # --- iyimser yamalar: değişiklik anında eğriye yansısın ---------------

    def _profile_dict(self, target: str) -> dict | None:
        return (self._state.get("profiles") or {}).get(target)

    def _patch_eq(self, target: str, values: dict) -> None:
        profile = self._profile_dict(target)
        if profile is None:
            return
        profile.setdefault("eq", {}).update(values)
        self._bump()

    def _patch_band(self, target: str, band: int, field: str, value: str) -> None:
        profile = self._profile_dict(target)
        if profile is None:
            return
        bands = (profile.get("eq") or {}).get("bands") or []
        if not 0 <= band < len(bands):
            return
        if field == "band_type":
            bands[band][field] = value
        elif field == "enabled":
            bands[band][field] = str(value).lower() in {"1", "true", "yes", "on"}
        elif field == "slope":
            bands[band][field] = int(float(value))
        else:
            try:
                bands[band][field] = float(value)
            except (TypeError, ValueError):
                return
        self._bump()

    def _patch_filter(self, target: str, slot: str, values: dict | None) -> dict | None:
        """İyimser güncelleme: slotu bellekteki profilde günceller.

        Slot zincirde yoksa `None` döner — daemon çağrısı da reddedilecek, uydurma bir
        slot yaratmak arayüzü daemon'la uyumsuz bırakırdı.
        """
        profile = self._profile_dict(target)
        if profile is None:
            return None
        effects = profile.setdefault("effects", [])
        state = next((e for e in effects if e.get("slot") == slot), None)
        if state is None:
            return None
        if values:
            state.update(values)
            self._bump()
        return state

    # ------------------------------------------------------------------ profiller

    @Slot(str, str)
    def loadProfile(self, target: str, name: str) -> None:
        self._call("LoadProfile", target, name)

    @Slot(str, str)
    def setBusDevice(self, bus: str, device: str) -> None:
        self._call("SetBusDevice", bus, device)

    @Slot(str, str)
    def setMicDevice(self, chain: str, device: str) -> None:
        self._call("SetMicDevice", chain, device)

    @Slot(float)
    def setChatMix(self, value: float) -> None:
        config = self._state.setdefault("config", {}).setdefault("chatmix", {})
        config["value"] = value
        self.chatmixChanged.emit()
        self._call("SetChatMix", value)

    @Slot(int, str, bool)
    def moveStream(self, stream_id: int, channel: str, remember: bool) -> None:
        row = self._streams.index_of("id", stream_id)
        if row >= 0:
            self._streams.update_row(row, {"channel": channel})
        self._call("MoveStream", stream_id, channel, remember)

    @Slot(str, str, str, result=str)
    def addChannel(self, name: str, direction: str, color: str) -> str:
        return self._call("AddChannel", name, direction, color) or ""

    @Slot(str)
    def removeChannel(self, channel: str) -> None:
        self._call("RemoveChannel", channel)

    @Slot(bool)
    def subscribeMeters(self, enabled: bool) -> None:
        self._call("SubscribeMeters", enabled)

    # ------------------------------------------------------------------ iç kısım

    def _optimistic(self, channel_id: str, field: str, value: Any) -> None:
        """Modeli anında güncelle, sonra çağrıyı yolla."""
        row = self._channels.index_of("id", channel_id)
        if row < 0:
            return
        self._channels.update_row(row, {field: value})
        self._hold(f"{channel_id}.{field}")

    def _hold(self, key: str) -> None:
        import time

        self._held[key] = time.monotonic() + self._hold_ms / 1000.0

    def _is_held(self, key: str) -> bool:
        import time

        until = self._held.get(key)
        if until is None:
            return False
        if time.monotonic() >= until:
            del self._held[key]
            return False
        return True

    def _call(self, method: str, *args: Any) -> Any:
        if self._client is None:
            return None
        try:
            return self._client.call(method, *args)
        except Exception as error:  # daemon gitmiş olabilir
            log.debug("D-Bus çağrısı başarısız (%s): %s", method, error)
            self._set_connected(False)
            return None


def _as_dict(value: Any) -> dict:
    """QML'den gelen bir değeri Python sözlüğüne çevirir.

    QML sözlükleri köprüye `QJSValue` olarak geliyor; `dict()` onları iterable sanıyor.
    `toVariant()` PySide6'nın dönüşümünü kullanıyor.
    """
    if value is None:
        return {}
    to_variant = getattr(value, "toVariant", None)
    if to_variant is not None:
        value = to_variant()
    return dict(value) if isinstance(value, dict) else {}


def _as_dict(value: Any) -> dict:
    """QML'den gelen bir değeri Python sözlüğüne çevirir.

    QML sözlükleri köprüye `QJSValue` olarak geliyor; `dict()` onları iterable sanıyor.
    `toVariant()` PySide6'nın kendi dönüşümünü kullanıyor.
    """
    if value is None:
        return {}
    to_variant = getattr(value, "toVariant", None)
    if to_variant is not None:
        value = to_variant()
    return dict(value) if isinstance(value, dict) else {}
