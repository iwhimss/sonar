import QtQuick
import "ui"

/* Sol taraftaki master şeridi: cihaz seçicileri ve iki master fader. */
Item {
    id: root
    property var bridge
    implicitWidth: 240

    readonly property var masters: bridge ? bridge.masters : ({})

    Column {
        anchors.fill: parent
        spacing: 0

        SonarPanel {
            width: parent.width
            height: 34
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
            width: parent.width
            height: 200

            Column {
                anchors.fill: parent
                anchors.margins: Theme.s3
                spacing: Theme.s3

                SonarSectionLabel { text: "Cihazlar" }

                Repeater {
                    model: [
                        { key: "personal", label: "Kişisel Miks", source: false },
                        { key: "stream",   label: "Yayın Miksi",  source: false },
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
                                currentValue: root.deviceOf(modelData.key)
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
                                    text: Theme.volumeText(root.volumeOf(modelData.key))
                                    color: Theme.textDim
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSmall
                                    renderType: Text.NativeRendering
                                }
                            }
                        }
                    }
                }
            }
        }

        SonarPanel {
            width: parent.width
            height: 250
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
                            color: root.mutedOf(modelData.key) ? Theme.textFaint : Theme.master
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: Theme.volumeText(root.volumeOf(modelData.key))
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        SonarFader {
                            height: 150
                            value: root.volumeOf(modelData.key)
                            muted: root.mutedOf(modelData.key)
                            accent: Theme.master
                            onMoved: (v) => root.bridge.setMasterVolume(modelData.key, v)
                        }
                        SonarIconButton {
                            icon: "mute"
                            active: root.mutedOf(modelData.key)
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
