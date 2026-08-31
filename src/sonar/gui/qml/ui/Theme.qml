pragma Singleton
import QtQuick

/*
 * Tasarım dilinin tek kaynağı.
 *
 * Kullanıcı isteği: sade ve modern, **yuvarlatılmış köşe yok**. Bu yüzden burada bir
 * `radius` değeri bilinçli olarak tanımlı DEĞİL — bileşenlerin hiçbiri köşe yuvarlatmıyor.
 * Ayrım 1 px kenarlıklar ve yüzey tonlarıyla yapılıyor.
 */
QtObject {
    id: theme

    // --- yüzeyler -----------------------------------------------------------
    readonly property color bg:          "#0E1116"
    readonly property color surface:     "#151A21"
    readonly property color raised:      "#1C222B"
    readonly property color sunken:      "#0B0E12"
    readonly property color border:      "#262E39"
    readonly property color borderStrong:"#37414F"

    // --- metin --------------------------------------------------------------
    readonly property color text:        "#E4E9F0"
    readonly property color textDim:     "#8B95A5"
    readonly property color textFaint:   "#5A6472"

    // --- aksanlar -----------------------------------------------------------
    readonly property color master:      "#7C6CF0"
    readonly property color danger:      "#E5484D"
    readonly property color warn:        "#F2A73B"
    readonly property color ok:          "#22C58B"

    // --- metre --------------------------------------------------------------
    readonly property color meterNormal: "#22C58B"
    readonly property color meterWarn:   "#F2A73B"
    readonly property color meterClip:   "#E5484D"

    // --- boşluk (4 px ızgarası) ---------------------------------------------
    readonly property int s1: 4
    readonly property int s2: 8
    readonly property int s3: 12
    readonly property int s4: 16
    readonly property int s6: 24

    // --- tipografi ----------------------------------------------------------
    readonly property string fontFamily: "Inter"
    readonly property int fontSmall:  11
    readonly property int fontBody:   13
    readonly property int fontTitle:  15

    /* Bölüm başlığı: büyük harf, açık harf aralığı, sönük renk. */
    function sectionFont(target) {
        target.font.family = theme.fontFamily
        target.font.pixelSize = theme.fontSmall
        target.font.letterSpacing = 0.9
        target.font.capitalization = Font.AllUppercase
    }

    /* dB değerini 0..1 aralığına çevirir (-60 dB taban). */
    function dbToFraction(db) {
        return Math.max(0, Math.min(1, (db + 60) / 60))
    }

    /* Lineer ses seviyesini yüzdeye çevirir. */
    function volumeText(v) {
        return Math.round(v * 100) + "%"
    }

    function meterColor(db) {
        if (db >= -1) return theme.meterClip
        if (db >= -6) return theme.meterWarn
        return theme.meterNormal
    }
}
