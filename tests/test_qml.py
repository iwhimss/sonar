"""QML kaynaklarının gerçekten yüklendiğini ve tasarım kuralına uyduğunu doğrular.

Görsel testler yapmıyoruz; ama "yükleniyor mu" ve "köşe yuvarlatma sızmış mı" soruları
ucuz ve değerli. İkincisi kullanıcının açık isteği (`radius` yok).
"""

from __future__ import annotations

import os
import re

import pytest

pytest.importorskip("PySide6.QtQuick")

from sonar.gui.app import qml_dir

QML_FILES = sorted(qml_dir().rglob("*.qml"))


def test_qml_files_exist():
    assert len(QML_FILES) >= 10
    assert (qml_dir() / "Main.qml").exists()
    assert (qml_dir() / "ui" / "Theme.qml").exists()


@pytest.mark.parametrize("path", QML_FILES, ids=lambda p: p.name)
def test_no_rounded_corners_anywhere(path):
    """Kullanıcının açık isteği: yuvarlatılmış köşe yok."""
    text = path.read_text(encoding="utf-8")
    offenders = [line.strip() for line in text.splitlines() if re.search(r"^\s*radius\s*:", line)]
    assert offenders == [], f"{path.name} içinde köşe yuvarlatma var: {offenders}"


@pytest.mark.parametrize("path", QML_FILES, ids=lambda p: p.name)
def test_no_gradients_or_drop_shadows(path):
    text = path.read_text(encoding="utf-8")
    assert "Gradient" not in text, f"{path.name}: gradyan tasarım dilinde yok"
    assert "DropShadow" not in text, f"{path.name}: gölge tasarım dilinde yok"


def test_qmldir_lists_every_component():
    qmldir = (qml_dir() / "ui" / "qmldir").read_text(encoding="utf-8")
    for path in (qml_dir() / "ui").glob("Sonar*.qml"):
        assert path.stem in qmldir, f"{path.stem} qmldir'de kayıtlı değil"


def test_main_window_loads_offscreen():
    """Yükleme hatası QML'de sessizdir; kök nesne sayısıyla yakalıyoruz.

    Ayrı süreçte çalışıyor: aynı süreçte önce bir `QCoreApplication` kurulmuşsa (diğer
    testler kuruyor) `QGuiApplication` yaratmak Qt'yi abort ettiriyor.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        """
        import sys
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from sonar.gui.app import qml_dir
        from sonar.gui.bridge import SonarBridge

        app = QGuiApplication([])
        bridge = SonarBridge(parent=app)
        engine = QQmlApplicationEngine()
        engine.addImportPath(str(qml_dir()))
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
        print("ROOTS", len(engine.rootObjects()))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=False,
    )
    assert "ROOTS 1" in result.stdout, result.stdout + result.stderr
    # QML hataları stderr'e "TypeError"/"is not defined" olarak düşer.
    assert "TypeError" not in result.stderr, result.stderr
    assert "is not defined" not in result.stderr, result.stderr
