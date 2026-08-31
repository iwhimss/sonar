import QtQuick

/* Bölüm başlığı: büyük harf, açık harf aralığı, sönük renk. */
Text {
    color: Theme.textDim
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSmall
    font.letterSpacing: 0.9
    font.capitalization: Font.AllUppercase
    renderType: Text.NativeRendering
}
