"""Çeviri katalogunun QML tarafındaki yüzü.

`sonar.core.i18n` süreç genelinde etkin dili tutuyor; bu sınıf onu QML'e açıyor ve dil
değiştiğinde arayüzün kendiliğinden tazelenmesini sağlıyor.

## Binding tazeleme — dikkat

QML bir binding'i **yalnızca okuduğu özellikler** değiştiğinde yeniden değerlendirir.
`I18n.t("x")` çağrısının içinde Python tarafında bir Python **özniteliği** okumak
hiçbir bağımlılık kurmaz: QML'in yakalayıcısı yalnızca QML/QObject özellik okumalarını
görür. Bu yüzden çeviri iki katmanlı:

* burada `language` bir `Property(str, notify=...)` — QML'den okununca yakalanır,
* `qml/ui/I18n.qml` singleton'ı `t()` içinde **kendi** `language` özelliğini okur.

Böylece `text: I18n.t(anahtar)` yazan her binding dolaylı olarak dile bağlanır ve
dil değişince metin anında güncellenir. Uygulamayı yeniden başlatmak gerekmiyor.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from sonar.core import i18n as core_i18n

__all__ = ["QmlI18n"]


class QmlI18n(QObject):
    """QML'e `i18nBackend` adıyla verilen çeviri nesnesi."""

    languageChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._language = core_i18n.language()

    # ------------------------------------------------------------------ özellikler

    def _get_language(self) -> str:
        return self._language

    def _set_language(self, code: str) -> None:
        normalized = core_i18n.set_language(code)
        if normalized == self._language:
            return
        self._language = normalized
        self.languageChanged.emit()

    language = Property(str, _get_language, _set_language, notify=languageChanged)

    @Property("QVariantList", constant=True)
    def languages(self) -> list:
        """Dil seçicisinin modeli: `[{"code", "label"}, ...]`."""
        return core_i18n.available()

    # ------------------------------------------------------------------ çeviri

    @Slot(str, result=str)
    def tr(self, key: str) -> str:
        return core_i18n.t(key)

    @Slot(str, "QVariantMap", result=str)
    def trf(self, key: str, args: dict) -> str:
        """Yer tutuculu metin: `I18n.tf("x", {name: "Oyun"})`."""
        return core_i18n.t(key, **{str(k): v for k, v in (args or {}).items()})
