import QtQuick
import QtQuick.Layouts
import "ui"

/* Sol taraftaki master şeridi: cihaz seçicileri ve iki master fader.
 *
 * `masters` `bridge.mastersChanged` sinyaline bağlı bir `Property`, yani buradaki
 * okumalar canlı. Cihaz listeleri ise fonksiyon çağrısı olduğu için `bridge.revision`
 * okuyarak tazeleniyor — QML fonksiyon çağrısına bağlama kurmuyor.
 */
Item {
    id: root
    property var bridge
    implicitWidth: 240

    readonly property var masters: bridge ? bridge.masters : ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            color: Theme.raised
            Row {
                anchors.centerIn: parent
                spacing: Theme.s2
                SonarIcon { name: "speaker"; color: Theme.master; anchors.verticalCenter: parent.verticalCenter }
                Text {
                    text: "MASTER"
                    color: Theme.master
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                    font.letterSpacing: 0.6
                    renderType: Text.NativeRendering
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }

        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: devices.implicitHeight + Theme.s3 * 2

            Column {
                id: devices
                anchors.fill: parent
                anchors.margins: Theme.s3
                spacing: Theme.s3

                SonarSectionLabel { text: "Cihazlar" }

                Repeater {
                    model: [
                        { key: "personal", label: "Kişisel Miks", source: false },
                        { key: "mic",      label: "Mikrofon",     source: true }
                    ]
                    Column {
                        required property var modelData
                        width: parent.width
                        spacing: 2
                        SonarSectionLabel {
                            text: modelData.label
                            color: Theme.textFaint
                        }
                        Row {
                            spacing: Theme.s1
                            width: parent.width
                            SonarComboBox {
                                width: parent.width - percent.width - Theme.s1
                                accent: Theme.master
                                model: root.deviceList(modelData.source)
                                currentValue: (root.masters, root.deviceOf(modelData.key))
                                onActivated: (value) => root.setDevice(modelData.key, value)
                            }
                            Rectangle {
                                id: percent
                                width: 46; height: 26
                                color: Theme.sunken
                                border.width: 1
                                border.color: Theme.border
                                Text {
                                    anchors.centerIn: parent
                                    text: Theme.volumeText((root.masters, root.volumeOf(modelData.key)))
                                    color: Theme.textDim
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSmall
                                    renderType: Text.NativeRendering
                                }
                            }
                        }
                    }
                }

                /* Yayın Miksi'nin fiziksel bir cihazı yok: çıkışı sanal bir kaynak.
                   Burada eskiden bir fiziksel cihaz açılırı vardı ve hiçbir şey
                   yapmıyordu (`bus.device` stream bus'ta confgen'de hiç kullanılmıyor).
                   Yerine OBS'e ne ekleneceğini söyleyen bilgi satırı. */
                Column {
                    width: parent.width
                    spacing: 2
                    SonarSectionLabel { text: "Yayın Miksi"; color: Theme.textFaint }
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
                        text: "OBS'te bu aygıtı ekleyin; yayın fader'ları buraya karışır."
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                }
            }
        }

        SonarPanel {
            id: faders
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160
            Row {
                anchors.centerIn: parent
                spacing: Theme.s6
                Repeater {
                    model: [
                        { key: "personal", icon: "headset" },
                        { key: "stream",   icon: "cast" }
                    ]
                    Column {
                        required property var modelData
                        spacing: Theme.s1
                        SonarIcon {
                            name: modelData.icon
                            color: (root.masters, root.mutedOf(modelData.key)) ? Theme.textFaint : Theme.master
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: Theme.volumeText((root.masters, root.volumeOf(modelData.key)))
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        SonarFader {
                            height: Math.max(80, faders.height - 100)
                            value: (root.masters, root.volumeOf(modelData.key))
                            muted: (root.masters, root.mutedOf(modelData.key))
                            accent: Theme.master
                            onMoved: (v) => root.bridge.setMasterVolume(modelData.key, v)
                        }
                        SonarIconButton {
                            icon: "mute"
                            active: (root.masters, root.mutedOf(modelData.key))
                            accent: Theme.danger
                            anchors.horizontalCenter: parent.horizontalCenter
                            onClicked: root.bridge.setMasterMute(modelData.key,
                                                                 !root.mutedOf(modelData.key))
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

    function setDevice(key, value) {
        if (key === "mic") bridge.setMicDevice(value)
        else bridge.setBusDevice(key, value)
    }
}
