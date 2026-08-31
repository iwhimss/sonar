"""Daemon süreci: olay döngüsü, D-Bus kaydı, sinyaller, temiz kapanış.

Grafı ayakta tutan taraf burasıdır — GUI kapalıyken de ses düzeni bozulmaz.

## Sinyal debounce'u

`pw-dump` saniyede onlarca olay üretebiliyor ve fader sürüklemek arka arkaya delta doğuruyor.
Her birini D-Bus'a yaymak istemciyi boğardı; 50 ms'lik bir pencerede biriktirilip **tek**
`StateChanged` olarak gönderiliyor. Deltalar `kind` alanına göre teklenip listeleniyor,
böylece arayüz neyin değiştiğini bilerek kısmi güncelleme yapabiliyor.

## Tek örnek

D-Bus adı zaten alınmışsa bu bir hata değil: başka bir daemon çalışıyor demektir. Sessizce
ve sıfır çıkış koduyla çıkılır, böylece `systemctl --user start` iki kez çağrıldığında
kırmızı görünmez.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import sys

from PySide6.QtCore import QCoreApplication, QObject, QSocketNotifier, QTimer, Signal
from PySide6.QtDBus import QDBusConnection

from sonar.core import config as config_mod
from sonar.daemon.api import SonarApi
from sonar.daemon.dbus_iface import BUS_NAME, INTERFACE, OBJECT_PATH, SonarDBusInterface
from sonar.engine.pwstate import GraphState
from sonar.engine.supervisor import Supervisor

__all__ = ["SonarDaemon", "main"]

log = logging.getLogger(__name__)

#: Durum sinyallerinin biriktirme penceresi.
SIGNAL_DEBOUNCE_MS = 50


class _ThreadBridge(QObject):
    """`pwstate`'in okuma iş parçacığından Qt olay döngüsüne geçiş köprüsü.

    `QTimer.singleShot(0, ...)` yabancı bir iş parçacığından çağrıldığında **sessizce
    hiçbir şey yapmıyor** — uyarı bile vermiyor. Bu yüzden yönlendirme hiç tetiklenmiyordu.
    Qt sinyalleri ise iş parçacığı güvenli: farklı bir iş parçacığından emit edildiğinde
    otomatik olarak kuyruğa alınıp alıcının iş parçacığında çalıştırılır.
    """

    streams_changed = Signal()
    levels_ready = Signal(str)


class SonarDaemon:
    def __init__(self, paths: config_mod.Paths | None = None) -> None:
        self.app = QCoreApplication(sys.argv)
        self.paths = paths if paths is not None else config_mod.Paths.default()
        self.store = config_mod.ConfigStore(self.paths)
        self.supervisor = Supervisor(self.paths, store=self.store)
        self.api = SonarApi(
            self.store,
            self.supervisor,
            on_change=self._queue_delta,
            on_rebuild=self._graph_rebuilt,
            on_levels=self._queue_levels,
        )
        self.bus = QDBusConnection.sessionBus()
        self.iface = SonarDBusInterface(self.api, self.bus)

        self._pending: dict[str, dict] = {}
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(SIGNAL_DEBOUNCE_MS)
        self._timer.timeout.connect(self._flush_deltas)

        self._streams_timer = QTimer()
        self._streams_timer.setSingleShot(True)
        self._streams_timer.setInterval(SIGNAL_DEBOUNCE_MS)
        self._streams_timer.timeout.connect(self._emit_streams)

        self._bridge = _ThreadBridge()
        self._bridge.streams_changed.connect(self._streams_event)
        self._bridge.levels_ready.connect(self._emit_levels)
        self.supervisor.on_failure.append(self._graph_failed)

    # ------------------------------------------------------------------ açılış

    def register(self) -> bool:
        """D-Bus'a kaydolur. Ad zaten alınmışsa `False` — hata değil."""
        if not self.bus.isConnected():
            log.error("oturum D-Bus'ına bağlanılamadı")
            return False
        if not self.bus.registerService(BUS_NAME):
            log.info("başka bir Sonar daemon'ı zaten çalışıyor; çıkılıyor")
            return False
        options = (
            QDBusConnection.RegisterOption.ExportAllSlots
            | QDBusConnection.RegisterOption.ExportAllSignals
        )
        if not self.bus.registerObject(OBJECT_PATH, INTERFACE, self.iface, options):
            log.error("D-Bus nesnesi kaydedilemedi: %s", OBJECT_PATH)
            return False
        return True

    def run(self) -> int:
        if not self.register():
            return 0
        self._install_signal_handlers()
        self.supervisor.monitor.listen(self._graph_changed)
        try:
            self.api.start()
        except FileNotFoundError:
            log.exception("PipeWire araçları bulunamadı")
            self.iface.emit_signal("Error", "pipewire_missing", "PipeWire araçları bulunamadı")
            return 1
        for conflict in self.api.conflicts():
            log.warning("%s", conflict["message"])
            self.iface.emit_signal("Error", conflict["code"], conflict["message"])
        log.info("Sonar daemon hazır: %s", BUS_NAME)
        try:
            return self.app.exec()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        log.info("kapanıyor")
        try:
            self.api.shutdown()
        finally:
            self.bus.unregisterObject(OBJECT_PATH)
            self.bus.unregisterService(BUS_NAME)

    # ------------------------------------------------------------------ sinyaller

    def _queue_delta(self, delta: dict) -> None:
        """API'den gelen değişiklik. `kind` başına teklenir, 50 ms'de bir yayılır."""
        self._pending[self._delta_key(delta)] = delta
        if not self._timer.isActive():
            self._timer.start()

    @staticmethod
    def _delta_key(delta: dict) -> str:
        """Aynı fader'a gelen 50 değişiklik tek satıra insin diye."""
        parts = [str(delta.get("kind", ""))]
        for field in ("channel", "bus", "target", "stage", "chain", "band", "param"):
            if field in delta:
                parts.append(f"{field}={delta[field]}")
        return "|".join(parts)

    def _flush_deltas(self) -> None:
        if not self._pending:
            return
        changes, self._pending = list(self._pending.values()), {}
        self.iface.emit_signal("StateChanged", json.dumps({"changes": changes}, ensure_ascii=False))

    def _graph_changed(self, changed: frozenset[str]) -> None:
        """`pwstate` iş parçacığından gelir — Qt nesnelerine dokunmadan kuyruğa al."""
        if GraphState.STREAMS in changed or GraphState.DEVICES in changed:
            self._bridge.streams_changed.emit()

    def _streams_event(self) -> None:
        """Yönlendirme kararı Qt iş parçacığında alınır; `pwstate` kendi iş parçacığından
        doğrudan alt süreç çağırmasın diye kuyruğa alınıyor."""
        self.api.sync_routing()
        self._start_streams_timer()

    def _start_streams_timer(self) -> None:
        if not self._streams_timer.isActive():
            self._streams_timer.start()

    def _emit_streams(self) -> None:
        # Bilinçli olarak `get_state()` çağrılmıyor: o tüm yapılandırmayı ve her hedefin
        # profilini serileştiriyor; akış listesi saniyede birkaç kez değişebiliyor.
        from sonar.core import serde

        payload = {
            "streams": [serde.to_jsonable(s) for s in self.supervisor.state.streams.values()],
            "devices": self.api.get_devices(),
        }
        self.iface.emit_signal("StreamsChanged", json.dumps(payload, ensure_ascii=False))

    def _queue_levels(self, levels) -> None:
        """Ölçüm iş parçacığından gelir; D-Bus yayını Qt iş parçacığında yapılır."""
        payload = {
            node: {
                "peak_db": round(level.peak_db, 2),
                "rms_db": round(level.rms_db, 2),
                "hold_db": round(level.hold_db, 2),
                "clipped": level.clipped,
            }
            for node, level in levels.items()
        }
        self._bridge.levels_ready.emit(json.dumps(payload, ensure_ascii=False))

    def _emit_levels(self, payload: str) -> None:
        self.iface.emit_signal("LevelsUpdated", payload)

    def _graph_rebuilt(self) -> None:
        self.iface.emit_signal("GraphRebuilt")

    def _graph_failed(self, message: str) -> None:
        self.iface.emit_signal("Error", "graph_failed", message)

    # ------------------------------------------------------------------ POSIX sinyalleri

    def _install_signal_handlers(self) -> None:
        """SIGTERM/SIGINT'i Qt olay döngüsüne taşır.

        Python'un sinyal işleyicisi olay döngüsü C tarafında beklerken çalışmaz; bir boru
        üzerinden `QSocketNotifier`'a aktarıyoruz. `systemctl --user stop` böylece temiz
        kapanışı tetikliyor — graf süreci öldürülüyor ve varsayılan sink geri veriliyor.
        """
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        os.set_blocking(read_fd, False)
        signal.set_wakeup_fd(write_fd)
        self._notifier = QSocketNotifier(read_fd, QSocketNotifier.Type.Read)
        self._notifier.activated.connect(self._on_posix_signal)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_args: None)

    def _on_posix_signal(self) -> None:
        with contextlib.suppress(BlockingIOError):
            os.read(self._notifier.socket(), 64)
        log.info("kapanma sinyali alındı")
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="sonar-daemon", description="Sonar arka plan servisi")
    parser.add_argument("--log", default=os.environ.get("SONAR_LOG", "info"))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )
    return SonarDaemon().run()


if __name__ == "__main__":
    raise SystemExit(main())
