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

import json
import logging
from typing import Any

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

__all__ = [
    "ChannelModel",
    "DeviceModel",
    "SonarBridge",
    "StreamModel",
    "channel_rows",
    "device_rows",
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
    rows = []
    for channel in sorted(config.get("channels", []), key=lambda c: (c["order"], c["id"])):
        rows.append(
            {
                "id": channel["id"],
                "name": channel["name"],
                "color": channel["color"],
                "icon": channel.get("icon", "speaker"),
                "builtin": bool(channel.get("builtin")),
                "activeProfile": channel.get("active_profile", "Default"),
                "profiles": profiles.get(channel["id"], []),
                "personalVolume": channel["personal"]["volume"],
                "personalMuted": channel["personal"]["muted"],
                "streamVolume": channel["stream"]["volume"],
                "streamMuted": channel["stream"]["muted"],
                "kind": "channel",
            }
        )
    for mic in config.get("mic_chains", []):
        if mic["id"] != "mic":
            continue  # yayın mikrofonu ayrı bir şerit değil; FX sayfasında yönetiliyor
        rows.append(
            {
                "id": mic["id"],
                "name": mic["name"],
                "color": "#F2A73B",
                "icon": "mic",
                "builtin": True,
                "activeProfile": mic.get("active_profile", "Default"),
                "profiles": profiles.get(mic["id"], []),
                "personalVolume": mic["monitor_volume"],
                "personalMuted": not mic.get("monitor_enabled", False),
                "streamVolume": mic["volume"],
                "streamMuted": mic["muted"],
                "kind": "mic",
            }
        )
    return rows


def stream_rows(state: dict) -> list[dict]:
    """Çalan uygulamalar. `channel` alanı hangi şeridin altında görüneceğini söyler.

    Kanal bilgisi daemon'dan hazır geliyor (`api.get_streams`); `target_node` yalnızca
    uygulamanın kendi seçtiği hedefi gösterdiği için yedek olarak kullanılıyor.
    """
    config = state.get("config") or {}
    by_node = {f"sonar_{c['id']}": c["id"] for c in config.get("channels", [])}
    rows = []
    for stream in state.get("streams", []):
        if stream.get("is_capture"):
            continue
        rows.append(
            {
                "id": stream["id"],
                "label": stream.get("app_name")
                or stream.get("app_binary")
                or stream.get("media_name")
                or f"#{stream['id']}",
                "binary": stream.get("app_binary", ""),
                "channel": stream.get("channel") or by_node.get(stream.get("target_node", ""), ""),
            }
        )
    return rows


def device_rows(state: dict, *, sources: bool) -> list[dict]:
    """Cihaz seçicilerinin içeriği. İlk satır her zaman 'sistem varsayılanı'."""
    rows = [{"name": "", "label": "Sistem varsayılanı", "isSource": sources}]
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
        "personalVolume", "personalMuted", "streamVolume", "streamMuted", "kind",
        "personalPeak", "streamPeak", "personalHold", "streamHold", "clipped",
    )  # fmt: skip


class StreamModel(_DictModel):
    keys = ("id", "label", "binary", "channel")


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
    errorRaised = Signal(str, str)
    graphRebuilt = Signal()

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
        self._state: dict = {}
        self._hold_ms = hold_ms
        self._held: dict[str, float] = {}

        # Modeller QML'e **özellik** olarak açılıyor; düz Python özniteliği olarak
        # bırakıldıklarında QML tarafından hiç görülmüyorlar (sessizce `undefined`).
        self._channels = ChannelModel(self)
        self._streams = StreamModel(self)
        self._sinks = DeviceModel(self)
        self._sources = DeviceModel(self)

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
        self._state = state
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
            # Metre değerleri durumun parçası değil; korunmalı.
            for key in ("personalPeak", "streamPeak", "personalHold", "streamHold", "clipped"):
                if key in previous:
                    row[key] = previous[key]
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
        del payload
        state = self._call("GetState")
        if state is not None:
            self.apply_state(state)

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
        for index, row in enumerate(self._channels.rows()):
            level = levels.get(f"sonar_{row['id']}")
            if level is None:
                continue
            self._channels.update_row(
                index,
                {
                    "personalPeak": level["peak_db"],
                    "streamPeak": level["peak_db"],
                    "personalHold": level["hold_db"],
                    "streamHold": level["hold_db"],
                    "clipped": level["clipped"],
                },
            )

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
        config = self._state.get("config") or {}
        buses = {b["id"]: b for b in config.get("buses", [])}
        mic = next((m for m in config.get("mic_chains", []) if m["id"] == "mic"), {})
        return {
            "personal": buses.get("personal", {}),
            "stream": buses.get("stream", {}),
            "mic": mic,
        }

    masters = Property("QVariant", _get_masters, notify=mastersChanged)

    def _get_conflicts(self) -> list:
        return self._state.get("conflicts", [])

    conflicts = Property("QVariant", _get_conflicts, notify=stateChanged)

    # ------------------------------------------------------------------ eylemler

    @Slot(str, str, float)
    def setChannelVolume(self, channel: str, bus: str, value: float) -> None:
        field = "personalVolume" if bus == "personal" else "streamVolume"
        self._optimistic(channel, field, value)
        self._call("SetChannelVolume", channel, bus, value)

    @Slot(str, str, bool)
    def setChannelMute(self, channel: str, bus: str, muted: bool) -> None:
        field = "personalMuted" if bus == "personal" else "streamMuted"
        self._optimistic(channel, field, muted)
        self._call("SetChannelMute", channel, bus, muted)

    @Slot(str, float)
    def setMasterVolume(self, bus: str, value: float) -> None:
        self._call("SetMasterVolume", bus, value)

    @Slot(str, bool)
    def setMasterMute(self, bus: str, muted: bool) -> None:
        self._call("SetMasterMute", bus, muted)

    @Slot(float)
    def setMicVolume(self, value: float) -> None:
        self._optimistic("mic", "streamVolume", value)
        self._call("SetMicVolume", "mic", value)

    @Slot(bool)
    def setMicMute(self, muted: bool) -> None:
        self._optimistic("mic", "streamMuted", muted)
        self._call("SetMicMute", "mic", muted)

    @Slot(bool)
    def setMicMonitor(self, enabled: bool) -> None:
        self._call("SetMicMonitor", "mic", enabled)

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
    def filterOf(self, target: str, stage: str) -> dict:
        """Tek bir aşamanın durumu; tanımsızsa boş sözlük."""
        filters = (self.profileOf(target).get("filters")) or {}
        return filters.get(stage) or {}

    @Slot(str, result="QVariant")
    def profileNames(self, target: str) -> list:
        """Profil listesi; gömülü presetler `builtin: true` ile işaretli."""
        builtin = set((self._state.get("builtin_profiles") or {}).get(target) or [])
        return [
            {"name": name, "builtin": name in builtin}
            for name in (self._state.get("profile_names") or {}).get(target) or []
        ]

    @Slot(str, result=float)
    def chatmixGain(self, channel: str) -> float:
        """Kanalın ChatMix çarpanı. 1.0 = dokunulmamış."""
        return float((self._state.get("chatmix_gains") or {}).get(channel, 1.0))

    @Slot(str, str)
    def importProfile(self, target: str, path: str) -> None:
        from pathlib import Path

        try:
            text = Path(path.removeprefix("file://")).read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            log.warning("dosya okunamadı: %s", error)
            return
        self._call("ImportProfile", target, text, "")
        self.refresh()

    @Slot(str, str, bool)
    def exportProfile(self, target: str, path: str, autoeq: bool) -> None:
        from pathlib import Path

        text = self._call("ExportProfile", target, "", autoeq)
        if text is None:
            return
        try:
            Path(path.removeprefix("file://")).write_text(text, encoding="utf-8")
        except OSError as error:
            log.warning("dosya yazılamadı: %s", error)

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

    @Slot(str, int)
    def setBandCount(self, target: str, count: int) -> None:
        self._call("SetBandCount", target, count)

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

    @Slot(str, str, int)
    def setProfileFavorite(self, target: str, name: str, slot: int) -> None:
        self._call("SetProfileFavorite", target, name, slot)
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

    def _patch_filter(self, target: str, stage: str, values: dict | None) -> dict | None:
        profile = self._profile_dict(target)
        if profile is None:
            return None
        state = profile.setdefault("filters", {}).setdefault(
            stage, {"enabled": False, "params": {}}
        )
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

    @Slot(str)
    def setMicDevice(self, device: str) -> None:
        self._call("SetMicDevice", "mic", device)

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

    @Slot(str, str, result=str)
    def addChannel(self, name: str, color: str) -> str:
        return self._call("AddChannel", name, color) or ""

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
