import QtQuick
import QtQuick.Controls as C
import "ui"

/* Mikser görünümü: master şeridi + kanal şeritleri + ChatMix. */
Item {
    id: root
    property var bridge
    signal openFx(string channelId)

    /* Kulaklığın fiziksel tekeri ChatMix'i sürüyorsa slider salt okunur olur. */
    readonly property bool chatmixByWheel:
        bridge ? (bridge.revision, bridge.chatmixIsHardware()) : false

    /* Şeritler yatay kaydırılabilir: kanal sayısı arttıkça pencereye sığmıyordu ve
       "＋ Kanal ekle" paneli ekrandan yarım taşıyordu.

       Ölçüldü (test turu 5): kaydırma **çalışıyordu** — 900 px pencerede
       `contentWidth = 1002`, `width = 852`. Eksik olan görünür bir tutamaktı:
       `AsNeeded` politikası Basic stilinde duran ekranda hiçbir işaret bırakmıyor ve
       tekerlek `SonarFader.onWheel` tarafından yeniyor, yani şeridin üstünde tekerlek
       kaydırmıyor. Kullanıcı bu yüzden "kaydıramıyorum" dedi.

       Artık içerik taştığında kendi çubuğumuz **her zaman** duruyor (aşağıda), ve
       `Shift`+tekerlek yatay kaydırıyor — düz tekerlek fader'ın kalıyor. */
    C.ScrollView {
        id: scroller
        objectName: "mixerScroller"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: scrollbar.top
        clip: true
        // Controls'un kendi çubukları kapalı; yatayı kendimiz çiziyoruz.
        C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff
        C.ScrollBar.vertical.policy: C.ScrollBar.AlwaysOff

        readonly property real overflow: Math.max(0, contentWidth - availableWidth)

        /* Shift + tekerlek yatay kaydırır. Düz tekerlek bilinçli olarak fader'ın:
           şeridin üstünde tekerlek çevirmek ses seviyesini değiştiriyor ve bu
           davranış üç turdur kullanımda. */
        WheelHandler {
            acceptedModifiers: Qt.ShiftModifier
            onWheel: (event) => {
                const step = event.angleDelta.y > 0 ? -60 : 60
                scroller.contentItem.contentX = Math.max(
                    0, Math.min(scroller.overflow, scroller.contentItem.contentX + step))
            }
        }

        Row {
            id: strips
            height: scroller.availableHeight
            spacing: Theme.s1

            MasterStrip {
                bridge: root.bridge
                height: strips.height
            }

            /* Şerit satırı **sözlük kopyası değil**, model rolleri olarak geçiyor.
               `channels.get(index)` bir fonksiyon çağrısıydı ve hiç yeniden
               değerlenmiyordu: mute düğmesi tepkisiz, fader donuk kalıyordu. */
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

            SonarPanel {
                width: 150
                height: strips.height
                color: Theme.bg
                SonarButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: Theme.s3
                    text: "＋  " + I18n.t("mixer.add_channel")
                    onClicked: addDialog.open()
                }
            }
        }
    }

    /* Yatay kaydırma tutamağı. Yalnızca içerik taştığında görünüyor; genişliği
       görünen oranı, konumu kaydırma konumunu gösteriyor. Yuvarlatma yok. */
    Item {
        id: scrollbar
        objectName: "mixerScrollbar"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: chatmix.top
        anchors.bottomMargin: Theme.s2
        height: visible ? 10 : 0
        visible: scroller.overflow > 0.5

        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 2
            anchors.bottomMargin: 2
            color: Theme.sunken
            border.width: 1
            border.color: Theme.border
        }

        Rectangle {
            id: handle
            objectName: "mixerScrollHandle"
            y: 2
            height: parent.height - 4
            width: Math.max(40, scrollbar.width * scroller.availableWidth
                                / Math.max(1, scroller.contentWidth))
            x: scroller.overflow > 0
               ? (scrollbar.width - width) * scroller.contentItem.contentX / scroller.overflow
               : 0
            // Tutamak oluğun içinde kaybolmamalı: `borderStrong` denendi, ekran
            // görüntüsünde oluktan ayırt edilemiyordu.
            color: barMouse.containsMouse || barMouse.pressed
                   ? Qt.lighter(Theme.master, 1.2) : Theme.master
        }

        MouseArea {
            id: barMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            /* Tutamağın kendisini sürüklemek yerine **tıklanan yere** git: dar bir
               tutamağı yakalamak zorunda kalmadan da kaydırılabiliyor. */
            function seek(mouseX) {
                const span = Math.max(1, scrollbar.width - handle.width)
                const ratio = Math.max(0, Math.min(1, (mouseX - handle.width / 2) / span))
                scroller.contentItem.contentX = ratio * scroller.overflow
            }
            onPressed: (mouse) => seek(mouse.x)
            onPositionChanged: (mouse) => { if (pressed) seek(mouse.x) }
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
                text: root.chatmixByWheel ? I18n.t("mixer.chatmix.by_wheel") : I18n.t("mixer.chatmix")
                color: root.chatmixByWheel ? Theme.warn : Theme.textFaint
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Row {
                spacing: Theme.s2
                SonarIcon {
                    name: "gamepad"; color: Theme.ok
                    anchors.verticalCenter: parent.verticalCenter
                }
                SonarSlider {
                    width: 320
                    accent: Theme.master
                    value: root.bridge ? root.bridge.chatmix / 100.0 : 0.5
                    onMoved: (v) => root.bridge.setChatMix(v * 100)
                    // Teker yönetiyorken elle kaydırmak iki kaynağı çakıştırırdı.
                    enabled: !root.chatmixByWheel
                    opacity: root.chatmixByWheel ? 0.6 : 1.0
                    anchors.verticalCenter: parent.verticalCenter
                }
                SonarIcon {
                    name: "chat"; color: "#3B9EFF"
                    anchors.verticalCenter: parent.verticalCenter
                }
                SonarButton {
                    text: I18n.t("common.reset")
                    variant: "ghost"
                    enabled: !root.chatmixByWheel
                             && (root.bridge ? Math.abs(root.bridge.chatmix - 50) > 0.5 : false)
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.bridge.setChatMix(50)
                }
            }
        }
    }

    // --- akış bağlam menüsü ------------------------------------------------
    SonarDialog {
        id: menu
        title: menu.label
        preferredWidth: 260
        property int streamId: -1
        property string label: ""

        function open(id, text) { streamId = id; label = text; visible = true }

        Column {
            width: parent.width
            Repeater {
                model: root.bridge ? root.bridge.channels : null
                Column {
                    required property int index
                    width: parent.width
                    readonly property var row: root.bridge.channels.get(index)
                    SonarButton {
                        width: parent.width
                        variant: "ghost"
                        text: "→ " + parent.row.name
                        onClicked: {
                            root.bridge.moveStream(menu.streamId, parent.parent.row.id, false)
                            menu.close()
                        }
                    }
                    SonarButton {
                        width: parent.width
                        variant: "ghost"
                        text: I18n.tf("mixer.stream.always", { name: parent.row.name })
                        visible: parent.row.kind === "channel"
                        height: visible ? 28 : 0
                        onClicked: {
                            root.bridge.moveStream(menu.streamId, parent.parent.row.id, true)
                            menu.close()
                        }
                    }
                }
            }
        }
    }

    // --- kanal silme onayı ---------------------------------------------------
    SonarDialog {
        id: removeDialog
        title: I18n.t("channel.remove.title")
        accent: Theme.danger
        preferredWidth: 380
        property string channelId: ""
        property string channelName: ""

        function open(id, name) { channelId = id; channelName = name; visible = true }

        Column {
            width: parent.width
            spacing: Theme.s3
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.tf("channel.remove.body", { name: removeDialog.channelName })
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Row {
                spacing: Theme.s2
                SonarButton {
                    text: I18n.t("common.delete")
                    variant: "danger"
                    onClicked: {
                        root.bridge.removeChannel(removeDialog.channelId)
                        removeDialog.close()
                    }
                }
                SonarButton { text: I18n.t("common.cancel"); onClicked: removeDialog.close() }
            }
        }
    }

    // --- kanal ekleme --------------------------------------------------------
    SonarDialog {
        id: addDialog
        objectName: "addDialog"
        title: I18n.t("channel.add.title")
        preferredWidth: 420

        // "output" = uygulamaların çaldığı sanal çıkış, "input" = işlenmiş mikrofon.
        property string direction: "output"

        function open() {
            direction = "output"
            nameInput.text = ""
            visible = true
            nameInput.forceActiveFocus()
        }

        Column {
            width: parent.width
            spacing: Theme.s3

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

            SonarSectionLabel { text: I18n.t("channel.add.kind") }
            Row {
                spacing: Theme.s2
                width: parent.width
                Repeater {
                    model: [
                        { value: "output", label: I18n.t("channel.add.output"),
                          hint: I18n.t("channel.add.output.hint") },
                        { value: "input", label: I18n.t("channel.add.input"),
                          hint: I18n.t("channel.add.input.hint") }
                    ]
                    Rectangle {
                        id: kindCard
                        required property var modelData
                        width: (addDialog.availableWidth - Theme.s2) / 2
                        // Yükseklik içerikten: sabit vermek metni kartın dışına
                        // taşırıyordu.
                        height: kindBody.implicitHeight + Theme.s2 * 2
                        readonly property bool picked: addDialog.direction === modelData.value
                        color: picked ? Qt.rgba(0.49, 0.42, 0.94, 0.15)
                             : (kindMouse.containsMouse ? Theme.surface : Theme.sunken)
                        border.width: 1
                        border.color: picked ? Theme.master : Theme.border

                        Column {
                            id: kindBody
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.s2
                            spacing: 2
                            Text {
                                text: kindCard.modelData.label
                                color: kindCard.picked ? Theme.master : Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                                font.bold: true
                                renderType: Text.NativeRendering
                            }
                            Text {
                                width: kindBody.width
                                text: kindCard.modelData.hint
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
                            onClicked: addDialog.direction = kindCard.modelData.value
                        }
                    }
                }
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("channel.add.note")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            Row {
                spacing: Theme.s2
                SonarButton { text: I18n.t("common.add"); variant: "accent"; onClicked: addDialog.commit() }
                SonarButton { text: I18n.t("common.cancel"); onClicked: addDialog.close() }
            }
        }

        function commit() {
            const name = nameInput.text.trim()
            if (name.length > 0)
                root.bridge.addChannel(name, direction, "#8B95A5")
            nameInput.text = ""
            close()
        }
    }

    /* Sürüklenen uygulama kutucuğunun imleci izleyen kopyası. En üstte durmalı:
       asıl kutucuk `ListView`'ün `clip`i içinde ve kardeş sütunların altında kalıyordu. */
    SonarDragProxy {
        id: dragLayer
    }
}
