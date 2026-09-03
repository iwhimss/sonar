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

        /* Şerit satırı **sözlük kopyası değil**, model rolleri olarak geçiyor.
           `channels.get(index)` bir fonksiyon çağrısıydı ve hiç yeniden değerlenmiyordu:
           mute düğmesi tepkisiz, fader donuk, profil adı eski kalıyordu. */
        Repeater {
            model: root.bridge ? root.bridge.channels : null
            ChannelStrip {
                height: strips.height
                bridge: root.bridge
                dragProxy: dragLayer
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
                onClicked: addDialog.open()
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
                    id: chatmixSlider
                    width: 320
                    accent: Theme.master
                    value: root.bridge ? root.bridge.chatmix / 100.0 : 0.5
                    onMoved: (v) => root.bridge.setChatMix(v * 100)
                    anchors.verticalCenter: parent.verticalCenter
                    // Çift tık zaten 50'ye döndürüyor (SonarSlider), ama keşfedilmiyordu;
                    // yanına görünür bir "Sıfırla" düğmesi kondu.
                }
                SonarIcon { name: "chat"; color: "#3B9EFF"; anchors.verticalCenter: parent.verticalCenter }
                SonarButton {
                    text: "Sıfırla"
                    variant: "ghost"
                    enabled: root.bridge ? Math.abs(root.bridge.chatmix - 50) > 0.5 : false
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.bridge.setChatMix(50)
                }
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
                text: "\"" + removeDialog.channelName + "\" ve tüm profilleri silinecek. "
                    + "Bu kanala yönlenen kurallar kalkar, uygulamaları varsayılan kanala "
                    + "düşer. Ses grafı yeniden kurulur (yaklaşık 200 ms sessizlik)."
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
        width: 380
        height: 250
        color: Theme.raised
        border.width: 1
        border.color: Theme.borderStrong

        // "output" = uygulamaların çaldığı sanal çıkış, "input" = işlenmiş mikrofon.
        property string direction: "output"

        function open() { direction = "output"; nameInput.text = ""; visible = true
                          nameInput.forceActiveFocus() }

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
                    Keys.onReturnPressed: addDialog.commit()
                }
            }

            SonarSectionLabel { text: "Kanal türü" }
            Row {
                spacing: Theme.s2
                width: parent.width
                Repeater {
                    model: [
                        { value: "output", label: "Çıkış",
                          hint: "Uygulamaların ses çaldığı sanal çıkış cihazı" },
                        { value: "input", label: "Giriş",
                          hint: "İşlenmiş bir mikrofon — sanal giriş cihazı" }
                    ]
                    Rectangle {
                        required property var modelData
                        width: (addDialog.width - Theme.s4 * 2 - Theme.s2) / 2
                        height: 52
                        readonly property bool picked: addDialog.direction === modelData.value
                        color: picked ? Qt.rgba(0.49, 0.42, 0.94, 0.15)
                             : (kindMouse.containsMouse ? Theme.surface : Theme.sunken)
                        border.width: 1
                        border.color: picked ? Theme.master : Theme.border
                        Column {
                            anchors.fill: parent
                            anchors.margins: Theme.s2
                            spacing: 2
                            Text {
                                text: parent.parent.modelData.label
                                color: parent.parent.picked ? Theme.master : Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                                font.bold: true
                                renderType: Text.NativeRendering
                            }
                            Text {
                                width: parent.width
                                text: parent.parent.modelData.hint
                                wrapMode: Text.WordWrap
                                color: Theme.textFaint
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSmall
                                renderType: Text.NativeRendering
                            }
                        }
                        MouseArea {
                            id: kindMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: addDialog.direction = parent.modelData.value
                        }
                    }
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
                    onClicked: addDialog.commit()
                }
                SonarButton {
                    text: "Vazgeç"
                    onClicked: { nameInput.text = ""; addDialog.visible = false }
                }
            }
        }

        function commit() {
            const name = nameInput.text.trim()
            if (name.length > 0)
                root.bridge.addChannel(name, direction, "#8B95A5")
            nameInput.text = ""
            visible = false
        }
    }

    /* Sürüklenen uygulama kutucuğunun imleci izleyen kopyası. En üstte durmalı:
       asıl kutucuk `ListView`'ün `clip`i içinde ve kardeş sütunların altında kalıyordu. */
    SonarDragProxy {
        id: dragLayer
    }
}
