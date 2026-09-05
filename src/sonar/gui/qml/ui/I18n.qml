pragma Singleton
import QtQuick

/*
 * Çeviri singleton'ı. Arayüzdeki her metin buradan geçer: `I18n.t(anahtar)`.
 *
 * `language` özelliği neden var: QML bir binding'i yalnızca okuduğu **özellikler**
 * değişince tazeler. `i18nBackend.tr(key)` çağrısının içinde Python tarafında ne
 * okunduğunu QML görmez. Bu yüzden `t()` önce kendi `language` özelliğini okuyor —
 * o okuma binding'e bağımlılık olarak yazılıyor ve dil değişince metin kendiliğinden
 * güncelleniyor. Uygulamayı yeniden başlatmak gerekmiyor.
 */
QtObject {
    id: root

    readonly property string language: i18nBackend.language
    readonly property var languages: i18nBackend.languages

    function t(key) {
        void root.language          // binding'i dile bağlar — silmeyin
        return i18nBackend.tr(key)
    }

    function tf(key, args) {
        void root.language
        return i18nBackend.trf(key, args)
    }
}
