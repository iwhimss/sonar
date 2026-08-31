import QtQuick
import Sonar.Dsp
import "ui"

/*
 * Ekolayzer paneli: bileşik eğri, sürüklenebilir band düğümleri, seçili bandın detayı.
 *
 * Eğri gerçek DSP yanıtıdır — ölçüldü, sapma 0.01 dB (bkz. .plan/08-gui-fx.md).
 */
SonarPanel {
    id: root
    property var bridge
    property string target: ""
    property color accent: Theme.master
    property var profile: ({})

    readonly property var eq: profile.eq !== undefined ? profile.eq : ({})
    readonly property int bandCount: eq.band_count !== undefined ? eq.band_count : 10
    readonly property var bands: eq.bands !== undefined ? eq.bands : []

    Column {
        anchors.fill: parent
        anchors.margins: Theme.s3
        spacing: Theme.s2

        // --- başlık --------------------------------------------------------
        Row {
            width: parent.width
            spacing: Theme.s2

            Rectangle {
                width: 30; height: 16
                anchors.verticalCenter: parent.verticalCenter
                color: root.eq.enabled ? root.accent : Theme.sunken
                border.width: 1
                border.color: root.eq.enabled ? root.accent : Theme.border
                Rectangle {
                    width: 12; height: 12; y: 2
                    x: root.eq.enabled ? 16 : 2
                    color: root.eq.enabled ? "#0E1116" : Theme.textFaint
                    Behavior on x { NumberAnimation { duration: 90 } }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.bridge.setEqEnabled(root.target, !root.eq.enabled)
                }
            }
            SonarSectionLabel {
                text: "Equalizer"
                color: root.eq.enabled ? root.accent : Theme.textDim
                anchors.verticalCenter: parent.verticalCenter
            }
            Item { width: Theme.s4; height: 1 }
            SonarSectionLabel { text: "Bandlar"; anchors.verticalCenter: parent.verticalCenter }
            SonarComboBox {
                width: 70
                accent: root.accent
                anchors.verticalCenter: parent.verticalCenter
                model: [{value:"5",label:"5"},{value:"10",label:"10"},
                        {value:"16",label:"16"},{value:"32",label:"32"}]
                currentValue: String(root.bandCount)
                onActivated: (v) => root.bridge.setBandCount(root.target, parseInt(v))
            }
            Item { width: Theme.s4; height: 1 }
            SonarSectionLabel { text: "Ölçek"; anchors.verticalCenter: parent.verticalCenter }
            SonarComboBox {
                width: 84
                accent: root.accent
                anchors.verticalCenter: parent.verticalCenter
                model: [{value:"6",label:"±6 dB"},{value:"15",label:"±15 dB"},
                        {value:"24",label:"±24 dB"},{value:"36",label:"±36 dB"}]
                currentValue: curve ? String(curve.rangeDb) : "15"
                onActivated: (v) => { if (curve) curve.rangeDb = parseFloat(v) }
            }
        }

        // --- eğri ----------------------------------------------------------
        Item {
            width: parent.width
            height: parent.height - 152

            EqCurve {
                id: curve
                anchors.fill: parent
                accent: root.accent
                eq: root.bridge ? root.eqPayload() : ""
                rangeDb: 15

                MouseArea {
                    id: drag
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    property int band: -1

                    onPressed: (mouse) => {
                        band = curve.bandAt(mouse.x, mouse.y)
                        if (band >= 0) curve.selectedBand = band
                        if (mouse.button === Qt.RightButton && band >= 0) {
                            root.bridge.setEqBand(root.target, band, "gain_db", "0")
                            band = -1
                        }
                    }
                    onPositionChanged: (mouse) => {
                        if (!pressed || band < 0) return
                        root.bridge.setEqBand(root.target, band, "gain_db",
                                              String(curve.gainForY(mouse.y).toFixed(2)))
                        root.bridge.setEqBand(root.target, band, "freq",
                                              String(curve.freqForX(mouse.x).toFixed(1)))
                    }
                    onDoubleClicked: (mouse) => {
                        const b = curve.bandAt(mouse.x, mouse.y)
                        if (b < 0) return
                        const on = root.bands[b].enabled
                        root.bridge.setEqBand(root.target, b, "enabled", on ? "false" : "true")
                    }
                    onWheel: (wheel) => {
                        const b = curve.selectedBand
                        if (b < 0 || b >= root.bands.length) return
                        const q = root.bands[b].q * (wheel.angleDelta.y > 0 ? 1.15 : 1 / 1.15)
                        root.bridge.setEqBand(root.target, b, "q",
                                              String(Math.max(0.1, Math.min(30, q)).toFixed(3)))
                    }
                }
            }
        }

        // --- seçili band ---------------------------------------------------
        Row {
            width: parent.width
            height: 26
            spacing: Theme.s2
            visible: curve && curve.selectedBand >= 0 && curve.selectedBand < root.bands.length

            readonly property var band: visible ? root.bands[curve.selectedBand] : ({})

            SonarSectionLabel {
                text: "Band " + ((curve ? curve.selectedBand : -1) + 1)
                anchors.verticalCenter: parent.verticalCenter
            }
            SonarComboBox {
                width: 120
                accent: root.accent
                anchors.verticalCenter: parent.verticalCenter
                model: [{value:"peak",label:"Peak"},{value:"low_shelf",label:"Low shelf"},
                        {value:"high_shelf",label:"High shelf"},{value:"low_pass",label:"Low pass"},
                        {value:"high_pass",label:"High pass"},{value:"notch",label:"Notch"},
                        {value:"off",label:"Kapalı"}]
                currentValue: parent.band.band_type !== undefined ? parent.band.band_type : "peak"
                onActivated: (v) => root.bridge.setEqBand(root.target, curve.selectedBand,
                                                          "band_type", v)
            }
            Repeater {
                model: [
                    { key: "freq",    label: "Frekans", unit: "Hz", digits: 0 },
                    { key: "gain_db", label: "Kazanç",  unit: "dB", digits: 1 },
                    { key: "q",       label: "Q",       unit: "",   digits: 2 }
                ]
                Row {
                    required property var modelData
                    spacing: 4
                    anchors.verticalCenter: parent.verticalCenter
                    SonarSectionLabel {
                        text: modelData.label
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    SonarNumberField {
                        width: 78
                        accent: root.accent
                        decimals: modelData.digits
                        unit: modelData.unit
                        value: parent.parent.band[modelData.key] !== undefined
                               ? parent.parent.band[modelData.key] : 0
                        onCommitted: (v) => root.bridge.setEqBand(
                            root.target, curve.selectedBand, modelData.key, String(v))
                    }
                }
            }
        }

        // --- hızlı slider'lar ----------------------------------------------
        Row {
            width: parent.width
            spacing: Theme.s4
            Repeater {
                model: [
                    { label: "Bass",   low: 20,   high: 250 },
                    { label: "Voice",  low: 250,  high: 4000 },
                    { label: "Treble", low: 4000, high: 20000 }
                ]
                SonarParamRow {
                    required property var modelData
                    width: (root.width - Theme.s3 * 2 - Theme.s4 * 2) / 3
                    label: modelData.label
                    from: -12; to: 12; unit: "dB"
                    accent: root.accent
                    value: root.groupGain(modelData.low, modelData.high)
                    onMoved: (v) => root.setGroupGain(modelData.low, modelData.high, v)
                }
            }
        }

        SonarParamRow {
            width: parent.width
            label: "Preamp"
            from: -24; to: 12; unit: "dB"
            accent: root.accent
            value: root.eq.preamp_db !== undefined ? root.eq.preamp_db : 0
            onMoved: (v) => root.bridge.setEqPreamp(root.target, v)
        }
    }

    /* Köprüdeki `revision` **okunuyor** ki binding band değişince tazelensin.
       Sayacı JSON'a eklemek değeri bozuyordu (eğri hiç çizilmiyordu); yalnızca bağımlılık
       kurmak için okunup atılıyor. */
    function eqPayload() {
        const _ = bridge.revision
        return bridge.eqJson(target)
    }

    function groupGain(low, high) {
        let total = 0, count = 0
        for (let i = 0; i < Math.min(bandCount, bands.length); ++i) {
            if (bands[i].freq >= low && bands[i].freq < high) { total += bands[i].gain_db; ++count }
        }
        return count ? total / count : 0
    }

    function setGroupGain(low, high, value) {
        for (let i = 0; i < Math.min(bandCount, bands.length); ++i) {
            if (bands[i].freq >= low && bands[i].freq < high)
                bridge.setEqBand(target, i, "gain_db", String(value.toFixed(2)))
        }
    }
}
