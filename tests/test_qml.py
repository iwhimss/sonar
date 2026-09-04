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


def test_value_field_parses_and_never_writes_its_own_value():
    """Fader yüzdesi artık elle girilebiliyor (test turu 4).

    İki şey doğrulanıyor:

    * Ayrıştırma: "%150", "150,5", boş metin, sınır aşımı. Türkçe klavyede ondalık ayracı
      virgül ve `parseFloat` onu tanımıyor — sessizce 150 okunurdu.
    * Bileşen `value`'ya **yazmıyor**. Yazmak modelden gelen bağlamayı kalıcı olarak
      koparıyor; test turu 3'te fader'lar tam bu yüzden daemon'ı takip etmeyi bırakmıştı.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        """
        import sys
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlComponent, QQmlEngine
        from sonar.gui.app import qml_dir

        app = QGuiApplication([])
        engine = QQmlEngine()
        engine.addImportPath(str(qml_dir()))
        component = QQmlComponent(
            engine, QUrl.fromLocalFile(str(qml_dir() / "ui" / "SonarValueField.qml"))
        )
        field = component.create()
        if field is None:
            print("ERRORS", component.errorString())
            sys.exit(1)

        seen = []
        field.edited.connect(seen.append)
        field.setProperty("value", 1.0)
        field.setProperty("maximum", 3.0)

        for text in ("250", "%150", "150,5", "", "abc", "999"):
            field.commit(text)

        print("EMITTED", [round(v, 4) for v in seen])
        print("VALUE", round(field.property("value"), 4))
        print("DISPLAY", field.property("display"))
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
    out = result.stdout + result.stderr
    # %250 → 2.5, %150 → 1.5, "150,5" → 1.505, geçersizler yutuluyor, %999 → maximum
    assert "EMITTED [2.5, 1.5, 1.505, 3.0]" in out, out
    # Bileşen kendi değerine dokunmadı: bağlama sağlam.
    assert "VALUE 1.0" in out, out
    assert "DISPLAY 100%" in out, out
