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
    //: Zincirdeki diğer paneller gibi sürüklenip silinebilsin diye (şema 7).
    property bool movable: false
    property bool removable: false
    readonly property alias grip: eqGrip
    signal removeRequested()

    readonly property var eq: profile.eq !== undefined ? profile.eq : ({})
    readonly property int bandCount: eq.band_count !== undefined ? eq.band_count : 10
    readonly property var bands: eq.bands !== undefined ? eq.bands : []
    //: LSP `para_equalizer_x32`'nin kapasitesi. Sınırda "ekle" hiçbir şey yapmıyor.
    readonly property int maxBands: 32

    Column {
        anchors.fill: parent
        anchors.margins: Theme.s3
        spacing: Theme.s2

        // --- başlık --------------------------------------------------------
        Row {
            width: parent.width
            spacing: Theme.s2

            Item {
                width: root.movable ? 10 : 0
                height: 16
                visible: root.movable
                anchors.verticalCenter: parent.verticalCenter
                Column {
                    anchors.centerIn: parent
                    spacing: 2
                    Repeater {
                        model: 3
                        Rectangle {
                            width: 10
                            height: 2
                            color: eqGrip.containsMouse ? root.accent : Theme.borderStrong
                        }
                    }
                }
                MouseArea {
                    id: eqGrip
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.SizeVerCursor
                }
            }

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
                text: I18n.t("fx.stage.eq")
                color: root.eq.enabled ? root.accent : Theme.textDim
                anchors.verticalCenter: parent.verticalCenter
            }
            Item { width: Theme.s4; height: 1 }
            /* "Bandlar" açılırı kalktı: band sayısı artık eğriye sağ tıklayarak
               değişiyor. Zincir her zaman 32 bandlık eklentiyle kurulduğu için bu
               tamamen canlı — eskiden kapasite değişimi grafı yeniden kuruyordu. */
            SonarSectionLabel {
                text: I18n.tf("eq.bands", { count: root.bandCount })
                anchors.verticalCenter: parent.verticalCenter
            }
            Item { width: Theme.s4; height: 1 }
            SonarSectionLabel { text: I18n.t("eq.scale"); anchors.verticalCenter: parent.verticalCenter }
            SonarComboBox {
                width: 84
                accent: root.accent
                anchors.verticalCenter: parent.verticalCenter
                model: [{value:"6",label:"±6 dB"},{value:"15",label:"±15 dB"},
                        {value:"24",label:"±24 dB"},{value:"36",label:"±36 dB"}]
                currentValue: curve ? String(curve.rangeDb) : "15"
                onActivated: (v) => { if (curve) curve.rangeDb = parseFloat(v) }
            }

            /* Sil düğmesi sağa yaslı: başlık satırı bir `Row` olduğu için araya esnek
               bir boşluk konuyor. */
            Item {
                width: Math.max(0, parent.width - eqRemove.width - x - Theme.s2)
                height: 1
            }
            SonarIconButton {
                id: eqRemove
                visible: root.removable
                width: visible ? 20 : 0
                icon: "close"
                accent: Theme.danger
                implicitWidth: 20
                implicitHeight: 18
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.removeRequested()
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

                    /* Sağ tık: bir düğümün üstündeyse **sil**, boşluktaysa o frekansa
                       yeni bir nokta **ekle**. İkisi de canlı. Eskiden sağ tık bandın
                       kazancını sıfırlıyordu; kullanıcı nokta ekleyip silmek istedi. */
                    onPressed: (mouse) => {
                        band = curve.bandAt(mouse.x, mouse.y)
                        if (band >= 0) curve.selectedBand = band
                        if (mouse.button !== Qt.RightButton) return
                        if (band >= 0) {
                            if (root.bands.length > 1) root.bridge.removeEqBand(root.target, band)
                            curve.selectedBand = -1
                        } else if (root.bands.length < root.maxBands) {
                            root.bridge.addEqBand(root.target,
                                                  curve.freqForX(mouse.x),
                                                  curve.gainForY(mouse.y))
                        }
                        band = -1
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
                text: I18n.tf("eq.band", { n: (curve ? curve.selectedBand : -1) + 1 })
                anchors.verticalCenter: parent.verticalCenter
            }
            SonarComboBox {
                width: 120
                accent: root.accent
                anchors.verticalCenter: parent.verticalCenter
                model: [{value:"peak",label:I18n.t("eq.type.peak")},
                        {value:"low_shelf",label:I18n.t("eq.type.low_shelf")},
                        {value:"high_shelf",label:I18n.t("eq.type.high_shelf")},
                        {value:"low_pass",label:I18n.t("eq.type.low_pass")},
                        {value:"high_pass",label:I18n.t("eq.type.high_pass")},
                        {value:"notch",label:I18n.t("eq.type.notch")},
                        {value:"off",label:I18n.t("eq.type.off")}]
                currentValue: parent.band.band_type !== undefined ? parent.band.band_type : "peak"
                onActivated: (v) => root.bridge.setEqBand(root.target, curve.selectedBand,
                                                          "band_type", v)
            }
            Repeater {
                model: [
                    { key: "freq",    label: I18n.t("eq.freq"), unit: "Hz", digits: 0 },
                    { key: "gain_db", label: I18n.t("eq.gain"),  unit: "dB", digits: 1 },
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
                    { label: I18n.t("eq.range.bass"),   low: 20,   high: 250 },
                    { label: I18n.t("eq.range.voice"),  low: 250,  high: 4000 },
                    { label: I18n.t("eq.range.treble"), low: 4000, high: 20000 }
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
            label: I18n.t("eq.preamp")
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
