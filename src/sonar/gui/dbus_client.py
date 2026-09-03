"""Köprünün kullandığı D-Bus istemcisi.

`SonarBridge` yalnızca `call(method, *args)` ve sinyal bağlama bekler; bu modül onu
QtDBus üzerine oturtur. Ayrı durmasının sebebi, köprünün testlerde sahte bir istemciyle
sürülebilmesi.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusInterface

from sonar.daemon.dbus_iface import BUS_NAME, INTERFACE, OBJECT_PATH

__all__ = ["DBusClient", "DaemonUnavailableError"]

log = logging.getLogger(__name__)


class DaemonUnavailableError(RuntimeError):
    """Daemon'a ulaşılamıyor. Köprü bunu 'bağlı değil' olarak yorumlar."""


class DBusClient(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = QDBusConnection.sessionBus()
        self.iface = QDBusInterface(BUS_NAME, OBJECT_PATH, INTERFACE, self.bus)

    @property
    def available(self) -> bool:
        return self.bus.isConnected() and self.iface.isValid()

    def call(self, method: str, *args: Any) -> Any:
        """Metodu çağırır ve JSON zarfını çözer. Hata durumunda yükseltir."""
        if not self.available:
            raise DaemonUnavailableError("daemon D-Bus'ta yok")
        # `iface.call(method, *args)` PySide6'da en fazla 4 argüman alıyor; beşincisinde
        # `TypeError` veriyor (ölçüldü: 5 argümanlı `SetRule`). `callWithArgumentList`
        # sınırsız ve aynı işi yapıyor.
        message = self.iface.callWithArgumentList(QDBus.CallMode.Block, method, list(args))
        arguments = message.arguments()
        if not arguments:
            raise DaemonUnavailableError(f"'{method}' yanıtsız kaldı")
        try:
            payload = json.loads(arguments[0])
        except (TypeError, json.JSONDecodeError) as error:
            raise DaemonUnavailableError(f"'{method}' geçersiz yanıt verdi") from error
        if not payload.get("ok"):
            # Beklenen bir API hatası: bağlantı sağlam, çağrı reddedildi.
            log.warning("%s reddedildi: %s", method, payload.get("message"))
            return None
        return payload.get("result")

    def connect_signals(self, bridge: QObject) -> bool:
        """Daemon sinyallerini köprünün yuvalarına bağlar."""
        # Yuva adı Qt'nin `SLOT()` kodu olan **"1" önekiyle** ve tam imzayla verilmeli.
        # Öneksiz form sessizce başarısız oluyor (denendi: üç farklı yazım, yalnızca bu
        # tuttu) — arayüz hiçbir güncelleme almadan çalışmaya devam ederdi.
        pairs = (
            ("StateChanged", "1onStateChanged(QString)"),
            ("StreamsChanged", "1onStreamsChanged(QString)"),
            ("LevelsUpdated", "1onLevelsUpdated(QString)"),
            ("GraphRebuilt", "1onGraphRebuilt()"),
            ("Error", "1onError(QString,QString)"),
        )
        ok = True
        for signal, slot in pairs:
            if not self.bus.connect(BUS_NAME, OBJECT_PATH, INTERFACE, signal, bridge, slot):
                log.warning("sinyal bağlanamadı: %s", signal)
                ok = False
        return ok
