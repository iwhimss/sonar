import QtQuick
import QtQuick.Layouts
import "ui"

/*
 * Sol taraftaki master şeridi: cihaz seçicileri ve iki master fader.
 *
 * Cihaz bölümü başlıktaki dişliyle katlanıyor. Dişli eskiden her kanal şeridinde vardı
 * ve FX sayfasını açıyordu — ama üstteki sekmeler zaten onu yapıyor, yani gereksizdi.
 * Kullanıcı isteğiyle buraya, işe yarayan tek yere taşındı (Faz 28).
 *
 * `masters` `bridge.mastersChanged` sinyaline bağlı bir `Property`, yani buradaki
 * okumalar canlı. Cihaz listeleri fonksiyon çağrısı olduğu için `bridge.revision`
 * okuyarak tazeleniyor — QML fonksiyon çağrısına bağlama kurmuyor.
 */
Item {
    id: root
    property var bridge
    implicitWidth: 240

    readonly property var masters: bridge ? bridge.masters : ({})
    readonly property string outputId: {
        const list = bridge ? bridge.outputBusId : ""
        return list || "personal"
    }
    /* Katlanma durumu bilinçli olarak kalıcı değil: bir arayüz tercihi için D-Bus
       gidiş-dönüşü ve şema alanı eklemeye değmiyor. */
    property bool devicesOpen: true

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            color: Theme.raised

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.s3
                anchors.rightMargin: Theme.s1
                spacing: Theme.s2

                SonarIcon { name: "speaker"; color: Theme.master; Layout.alignment: Qt.AlignVCenter }
                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    text: "MASTER"
                    color: Theme.master
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                    font.letterSpacing: 0.6
                    renderType: Text.NativeRendering
                }
                SonarIconButton {
                    icon: "gear"
                    accent: Theme.master
                    active: root.devicesOpen
                    Layout.alignment: Qt.AlignVCenter
                    onClicked: root.devicesOpen = !root.devicesOpen
                }
            }
        }

        // --- cihazlar (dişliyle katlanır) -----------------------------------
        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: root.devicesOpen ? devices.implicitHeight + Theme.s3 * 2 : 0
            visible: root.devicesOpen
            clip: true

            Column {
                id: devices
                anchors.fill: parent
                anchors.margins: Theme.s3
                spacing: Theme.s3

                SonarSectionLabel { text: "Kişisel Miks" }
                SonarComboBox {
                    width: parent.width
                    accent: Theme.master
                    model: root.deviceList(false)
                    currentValue: (root.masters, root.deviceOf(root.outputId))
                    onActivated: (value) => root.bridge.setBusDevice(root.outputId, value)
                }

                SonarSectionLabel { text: "Mikrofon" }
                SonarComboBox {
                    width: parent.width
                    accent: Theme.master
                    model: root.deviceList(true)
                    currentValue: (root.masters, root.deviceOf("mic"))
                    onActivated: (value) => root.bridge.setMicDevice("mic", value)
                }

                /* Yayın Miksi'nin fiziksel bir cihazı yok: çıkışı sanal bir kaynak.
                   Burada eskiden bir cihaz açılırı vardı ve hiçbir şey yapmıyordu. */
                SonarSectionLabel { text: "Yayın Miksi" }
                Rectangle {
                    width: parent.width
                    height: 26
                    color: Theme.sunken
                    border.width: 1
                    border.color: Theme.border
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.s2
                        anchors.rightMargin: Theme.s2
                        verticalAlignment: Text.AlignVCenter
                        text: "Sonar Stream Mix — Virtual Input"
                        color: Theme.textDim
                        elide: Text.ElideRight
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "OBS'e **yalnızca** bu aygıtı ekleyin. Aynı miksi bir de "
                        + "\"Ses Çıkışı Yakalama\" ile almak sesi iki kez verir."
                    color: Theme.textFaint
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                }
            }
        }

        SonarPanel {
            id: faders
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 200
            Row {
                anchors.centerIn: parent
                spacing: Theme.s6
                Repeater {
                    model: [
                        { key: root.outputId, icon: "headset", label: "Kulaklık" },
                        { key: "stream", icon: "cast", label: "Yayın" }
                    ]
                    Column {
                        id: busColumn
                        required property var modelData
                        spacing: Theme.s1

                        readonly property real vol: (root.masters, root.volumeOf(modelData.key))
                        readonly property bool mute: (root.masters, root.mutedOf(modelData.key))

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: busColumn.modelData.label
                            color: Theme.textFaint
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        SonarIcon {
                            name: busColumn.modelData.icon
                            color: busColumn.mute ? Theme.textFaint : Theme.master
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: Theme.volumeText(busColumn.vol)
                            color: busColumn.vol > 1.001 ? Theme.warn : Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        SonarFader {
                            height: Math.max(80, faders.height - 130)
                            value: busColumn.vol
                            muted: busColumn.mute
                            accent: Theme.master
                            onMoved: (v) => root.bridge.setMasterVolume(busColumn.modelData.key, v)
                        }
                        SonarIconButton {
                            icon: "mute"
                            active: busColumn.mute
                            accent: Theme.danger
                            anchors.horizontalCenter: parent.horizontalCenter
                            onClicked: root.bridge.setMasterMute(busColumn.modelData.key,
                                                                 !busColumn.mute)
                        }
                    }
                }
            }
        }
    }

    function deviceList(source) {
        if (!bridge) return []
        const _ = bridge.revision   // modeller değişince listeyi tazele
        const model = source ? bridge.sources : bridge.sinks
        const out = []
        for (let i = 0; i < model.rowCount(); ++i) {
            const row = model.get(i)
            out.push({ value: row.name, label: row.label })
        }
        return out
    }

    function deviceOf(key) {
        const m = masters ? masters[key] : null
        if (!m) return ""
        return key === "mic" ? (m.source_device || "") : (m.device || "")
    }

    function volumeOf(key) {
        const m = masters ? masters[key] : null
        return m && m.volume !== undefined ? m.volume : 1.0
    }

    function mutedOf(key) {
        const m = masters ? masters[key] : null
        return m ? m.muted === true : false
    }
}
