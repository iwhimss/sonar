import QtQuick
import "ui"

/* Mikser görünümü: master şeridi + kanal şeritleri + ChatMix. */
Item {
    id: root
    property var bridge
    signal openFx(string channelId)

    Row {
        id: strips
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: chatmix.top
        anchors.bottomMargin: Theme.s2
        spacing: Theme.s1

        MasterStrip {
            bridge: root.bridge
            height: parent.height
        }

        Repeater {
            model: root.bridge ? root.bridge.channels : null
            ChannelStrip {
                required property int index
                height: strips.height
                channel: root.bridge.channels.get(index)
                bridge: root.bridge
                streamModel: root.bridge.streams
                onOpenFx: (id) => root.openFx(id)
                onStreamMenuRequested: (streamId, label) => menu.open(streamId, label)
                onRemoveRequested: (id, name) => removeDialog.open(id, name)
            }
        }

        // + Kanal ekle
        SonarPanel {
            width: 150
            height: strips.height
            color: Theme.bg
            SonarButton {
                anchors.centerIn: parent
                text: "＋  Kanal ekle"
                onClicked: addDialog.visible = true
            }
        }
    }

    // --- ChatMix -----------------------------------------------------------
    SonarPanel {
        id: chatmix
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 54

        Column {
            anchors.centerIn: parent
            spacing: 2
            SonarSectionLabel {
                text: "ChatMix"
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Row {
                spacing: Theme.s2
                SonarIcon { name: "gamepad"; color: Theme.ok; anchors.verticalCenter: parent.verticalCenter }
                SonarSlider {
                    width: 320
                    accent: Theme.master
                    value: root.bridge ? root.bridge.chatmix / 100.0 : 0.5
                    onMoved: (v) => root.bridge.setChatMix(v * 100)
                    anchors.verticalCenter: parent.verticalCenter
                }
                SonarIcon { name: "chat"; color: "#3B9EFF"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }

    // --- akış bağlam menüsü ------------------------------------------------
    Rectangle {
        id: menu
        visible: false
        z: 200
        width: 240
        color: Theme.raised
        border.width: 1
        border.color: Theme.borderStrong
        height: menuColumn.implicitHeight + 2
        property int streamId: -1
        property string label: ""

        function open(id, text) {
            streamId = id
            label = text
            x = Math.min(root.width - width, 40)
            y = Math.min(root.height - height, 80)
            visible = true
        }

        Column {
            id: menuColumn
            anchors.fill: parent
            anchors.margins: 1

            SonarSectionLabel {
                text: menu.label
                leftPadding: Theme.s2
                topPadding: Theme.s2
                bottomPadding: Theme.s1
            }
            Repeater {
                model: root.bridge ? root.bridge.channels : null
                Column {
                    required property int index
                    width: menuColumn.width
                    SonarButton {
                        width: parent.width
                        variant: "ghost"
                        text: "→ " + root.bridge.channels.get(index).name
                        onClicked: {
                            root.bridge.moveStream(menu.streamId,
                                                   root.bridge.channels.get(index).id, false)
                            menu.visible = false
                        }
                    }
                    SonarButton {
                        width: parent.width
                        variant: "ghost"
                        text: "★ Hep " + root.bridge.channels.get(index).name + "'e gönder"
                        visible: root.bridge.channels.get(index).kind === "channel"
                        height: visible ? 28 : 0
                        onClicked: {
                            root.bridge.moveStream(menu.streamId,
                                                   root.bridge.channels.get(index).id, true)
                            menu.visible = false
                        }
                    }
                }
            }
        }
    }
    MouseArea {
        anchors.fill: parent
        z: 199
        visible: menu.visible
        onClicked: menu.visible = false
    }

    // --- kanal silme onayı ---------------------------------------------------
    Rectangle {
        id: removeDialog
        visible: false
        z: 300
        anchors.centerIn: parent
        width: 340
        height: 150
        color: Theme.raised
        border.width: 1
        border.color: Theme.danger
        property string channelId: ""
        property string channelName: ""

        function open(id, name) { channelId = id; channelName = name; visible = true }

        Column {
            anchors.fill: parent
            anchors.margins: Theme.s4
            spacing: Theme.s3
            SonarSectionLabel { text: "Kanalı sil" }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "\"" + removeDialog.channelName + "\" silinecek. Bu kanala yönlenen "
                    + "uygulamalar varsayılan kanala düşer ve ses grafı yeniden kurulur "
                    + "(yaklaşık 200 ms sessizlik)."
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Row {
                spacing: Theme.s2
                SonarButton {
                    text: "Sil"
                    variant: "danger"
                    onClicked: {
                        root.bridge.removeChannel(removeDialog.channelId)
                        removeDialog.visible = false
                    }
                }
                SonarButton { text: "Vazgeç"; onClicked: removeDialog.visible = false }
            }
        }
    }

    // --- kanal ekleme --------------------------------------------------------
    Rectangle {
        id: addDialog
        visible: false
        z: 300
        anchors.centerIn: parent
        width: 320
        height: 170
        color: Theme.raised
        border.width: 1
        border.color: Theme.borderStrong

        Column {
            anchors.fill: parent
            anchors.margins: Theme.s4
            spacing: Theme.s3

            SonarSectionLabel { text: "Yeni kanal" }
            Rectangle {
                width: parent.width
                height: 28
                color: Theme.sunken
                border.width: 1
                border.color: nameInput.activeFocus ? Theme.master : Theme.border
                TextInput {
                    id: nameInput
                    anchors.fill: parent
                    anchors.leftMargin: Theme.s2
                    verticalAlignment: Text.AlignVCenter
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    selectByMouse: true
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Kanal eklemek ses grafını yeniden kurar; yaklaşık 200 ms sessizlik olur."
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Row {
                spacing: Theme.s2
                SonarButton {
                    text: "Ekle"
                    variant: "accent"
                    onClicked: {
                        if (nameInput.text.trim().length > 0)
                            root.bridge.addChannel(nameInput.text.trim(), "#8B95A5")
                        nameInput.text = ""
                        addDialog.visible = false
                    }
                }
                SonarButton {
                    text: "Vazgeç"
                    onClicked: { nameInput.text = ""; addDialog.visible = false }
                }
            }
        }
    }
}
