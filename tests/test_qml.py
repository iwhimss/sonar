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
        from sonar.gui.i18n import QmlI18n

        app = QGuiApplication([])
        bridge = SonarBridge(parent=app)
        engine = QQmlApplicationEngine()
        engine.addImportPath(str(qml_dir()))
        engine.rootContext().setContextProperty("bridge", bridge)
        # `ui/I18n.qml` singleton'ı bu context property'yi okuyor; verilmezse her metin
        # "ReferenceError" olur ve arayüz sessizce boş çizilir.
        engine.rootContext().setContextProperty("i18nBackend", QmlI18n(app))
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

        from PySide6.QtCore import QObject

        seen = []
        field.edited.connect(seen.append)
        field.setProperty("maximum", 3.0)

        # Metin `value`'yu **aynı turda** izlemeli. Eskiden handler ayrı bir
        # `display` binding'ini okuyordu ve metin tam bir adım geride kalıyordu:
        # 0.5 → "50%", 1.0 → "50%", 0.25 → "100%" (test turu 5'te ölçüldü).
        entry = [c for c in field.findChildren(QObject)
                 if c.metaObject().className().startswith("QQuickTextInput")][0]
        texts = []
        for value in (0.5, 1.0, 0.25):
            field.setProperty("value", value)
            texts.append(entry.property("text"))
        print("TEXTS", texts)

        field.setProperty("value", 1.0)
        for text in ("250", "%150", "150,5", "", "abc", "999"):
            field.commit(text)

        print("EMITTED", [round(v, 4) for v in seen])
        print("VALUE", round(field.property("value"), 4))
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
    # Metin değeri gecikmeden izliyor.
    assert "TEXTS ['50%', '100%', '25%']" in out, out


#: Kullanıcıya görünen metin taşıyan QML özellikleri.
TEXT_PROPERTIES = ("text", "title", "label", "hint", "note", "placeholder")

#: Çeviri gerektirmeyen metinler: ürün adı, simgeler, birimler, komutlar, biçim ekleri.
ALLOWED_LITERALS = frozenset(
    {
        "", "Sonar", "Q", "MASTER", "ChatMix", "AutoEQ", "OBS",
        "—", "·", "→", "←", "★", "✓", "▴", "▾", "■", "⚠", "＋", "%",
        "dB", "ms", "Hz", ": 1", "IN", "OUT", "monospace",
        "systemctl --user start sonar-daemon",
        "±6 dB", "±15 dB", "±24 dB", "±36 dB",
        "AutoEQ / EqualizerAPO (*.txt)", "EasyEffects (*.json)", "AutoEQ (*.txt)",
    }
)

#: `text: "..."` biçiminde **tek** bir düz metin ataması. Birleştirme (`"a" + b`) veya
#: `I18n.t(...)` içeren satırlar burada eşleşmiyor; onları ayrıca eliyoruz.
LITERAL_ASSIGN = re.compile(
    r"^\s*(?:readonly\s+)?(?:property\s+string\s+)?(" + "|".join(TEXT_PROPERTIES) + r")\s*:\s*"
    r'"([^"]*)"\s*$'
)


@pytest.mark.parametrize("path", QML_FILES, ids=lambda p: p.name)
def test_user_visible_text_goes_through_the_catalog(path):
    """Kullanıcıya görünen çıplak metin kalmasın — "yuvarlatılmış köşe yok"un kardeşi.

    Kullanıcının şikâyeti "yarısı İngilizce yarısı Türkçe"ydi; kural kendiliğinden
    korunmazsa bir sonraki eklemede aynı yere geri dönülür.
    """
    offenders = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = LITERAL_ASSIGN.match(line)
        if match is None:
            continue
        value = match.group(2)
        if value in ALLOWED_LITERALS:
            continue
        offenders.append(f"{number}: {line.strip()}")
    assert offenders == [], (
        f"{path.name} içinde katalogdan geçmeyen kullanıcı metni var: {offenders}"
    )


#: `bridge: bridge` gibi kendine referans veren atama. Sağdaki ad QML'de **nesnenin
#: kendi** özelliğine çözülüyor, dıştaki context property'ye değil; sonuç sessiz bir
#: `undefined` oluyor.
SELF_REFERENCE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*$")


@pytest.mark.parametrize("path", QML_FILES, ids=lambda p: p.name)
def test_no_self_referencing_property_assignment(path):
    """`x: x` yazmayın.

    Test turu 5'te `SettingsDialog { bridge: bridge }` üç hataya birden yol açtı: dil
    değişmiyor, ayar kutucukları tıklanmıyor, kaldırma hiçbir şey yapmıyordu. QML hata
    vermiyor, yalnızca `undefined` bir nesneyle devam ediyor — bu yüzden kural burada.
    Doğrusu değeri açıkça nitelemek: `bridge: window.bridgeRef()`.
    """
    offenders = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = SELF_REFERENCE.match(line)
        if match is not None and match.group(1) == match.group(2):
            offenders.append(f"{number}: {line.strip()}")
    assert offenders == [], f"{path.name} içinde kendine referans veren atama: {offenders}"
