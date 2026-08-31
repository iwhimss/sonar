"""`sonar` — arayüz uygulaması.

Pencereyi kapatmak uygulamayı **kapatmaz**: ses düzenini daemon taşıyor, arayüz yalnızca
bir istemci. Gerçek çıkış tepsi menüsünden yapılır.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from sonar.core import config as config_mod

# `EqCurve` QML tipi olarak kaydedilmesi için içe aktarılmalı (yan etkili import).
from sonar.gui import eqcurve  # noqa: F401
from sonar.gui.bridge import SonarBridge
from sonar.gui.dbus_client import DBusClient

__all__ = ["main", "qml_dir"]

log = logging.getLogger(__name__)


def qml_dir() -> Path:
    """QML kaynaklarının kökü. Kurulu paketten de çalışır."""
    return Path(__file__).resolve().parent / "qml"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="sonar", description="Sonar mikser arayüzü")
    parser.add_argument("--log", default="warning")
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.WARNING))

    # `QApplication` (QtWidgets) seçildi: sistem tepsisi ikonu QtGui ile gelmiyor.
    app = QApplication(sys.argv)
    app.setApplicationName("Sonar")
    app.setOrganizationName("iwhimss")
    app.setDesktopFileName("io.github.iwhimss.Sonar")

    # Köprü uygulamaya bağlanıyor: aksi hâlde çıkışta Python tarafından toplanıp
    # QML'in altından çekiliyor ve kapanışta 'null' hataları düşüyor.
    bridge = SonarBridge(parent=app)
    client = DBusClient(app)
    bridge.attach(client)
    client.connect_signals(bridge)

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    if not engine.rootObjects():
        log.error("arayüz yüklenemedi")
        return 1

    bridge.start()
    bridge.subscribeMeters(True)
    tray = _install_tray(app, engine)

    paths = config_mod.Paths.default()
    _restore_window(engine, paths)
    exit_code = app.exec()
    del tray
    bridge.subscribeMeters(False)
    _save_window(engine, paths)
    return exit_code


def _install_tray(app: QApplication, engine: QQmlApplicationEngine):
    """Sistem tepsisi ikonu.

    Pencereyi kapatmak uygulamayı kapatmaz — ses düzenini daemon taşıyor, arayüz yalnızca
    bir istemci. Gerçek çıkış buradan yapılır. Tepsi yoksa (bazı masaüstlerinde) sessizce
    atlanır ve pencere kapanışı uygulamayı sonlandırır.
    """
    from PySide6.QtWidgets import QMenu, QSystemTrayIcon

    if not isinstance(app, QApplication) or not QSystemTrayIcon.isSystemTrayAvailable():
        return None

    window = engine.rootObjects()[0]
    app.setQuitOnLastWindowClosed(False)

    menu = QMenu()
    show = menu.addAction("Sonar'ı göster")
    show.triggered.connect(window.show)
    menu.addSeparator()
    quit_action = menu.addAction("Çıkış (daemon çalışmaya devam eder)")
    quit_action.triggered.connect(app.quit)

    tray = QSystemTrayIcon(QIcon.fromTheme("audio-volume-high"), app)
    tray.setToolTip("Sonar")
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.show()
    return tray


def _restore_window(engine: QQmlApplicationEngine, paths: config_mod.Paths) -> None:
    state = config_mod.ConfigStore(paths).load_ui_state()
    window = engine.rootObjects()[0]
    geometry = state.get("window") or {}
    if geometry.get("width") and geometry.get("height"):
        window.setWidth(int(geometry["width"]))
        window.setHeight(int(geometry["height"]))
    if "tab" in state:
        window.setProperty("currentTab", state["tab"])


def _save_window(engine: QQmlApplicationEngine, paths: config_mod.Paths) -> None:
    roots = engine.rootObjects()
    if not roots:
        return
    window = roots[0]
    store = config_mod.ConfigStore(paths)
    state = store.load_ui_state()
    state["window"] = {"width": window.width(), "height": window.height()}
    state["tab"] = window.property("currentTab")
    store.save_ui_state(state)


if __name__ == "__main__":
    raise SystemExit(main())
