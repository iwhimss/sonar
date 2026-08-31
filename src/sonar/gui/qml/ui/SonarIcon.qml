import QtQuick

/*
 * Metin tabanlı ikon. Harici SVG varlığı taşımamak için Unicode semboller kullanılıyor;
 * hepsi tek renk ve köşesiz görünüme uyuyor.
 */
Text {
    property string name: ""
    readonly property var glyphs: ({
        "gamepad":  "⌘",
        "chat":     "✉",
        "play":     "▶",
        "speaker":  "■",
        "mic":      "●",
        "headset":  "∩",
        "cast":     "◎",
        "gear":     "⚙",
        "mute":     "✕",
        "plus":     "＋",
        "close":    "✕",
        "warn":     "⚠"
    })
    text: glyphs[name] !== undefined ? glyphs[name] : "■"
    color: Theme.textDim
    font.pixelSize: Theme.fontBody
    renderType: Text.NativeRendering
}
