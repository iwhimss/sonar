import QtQuick
import "ui"

/*
 * Tek bir kanal şeridi: başlık, profil seçici, çift fader (kulaklık + yayın),
 * mute düğmeleri ve altındaki uygulama kutusu.
 */
Item {
    id: root
    required property var channel      // ChannelModel satırı
    property var bridge
    property var streamModel
    signal openFx(string channelId)

    implicitWidth: 132

    readonly property color accent: channel.color
    readonly property bool isMic: channel.kind === "mic"
    readonly property real chatmixGain:
        bridge ? (bridge.revision, bridge.chatmixGain(channel.id)) : 1.0

    /* Şeridin tamamı bırakma hedefi: kullanıcı çipi şeridin herhangi bir yerine
       bırakabilsin, yalnızca küçük Apps kutusuna nişan almak zorunda kalmasın. */
    DropArea {
        id: drop
        anchors.fill: parent
        z: 10
        onDropped: (event) => {
            const source = event.source
            if (source && source.streamId !== undefined)
                root.bridge.moveStream(source.streamId, root.channel.id, false)
            event.accept()
        }
    }

    // Bırakma sırasında hedef şerit vurgulanır.
    Rectangle {
        anchors.fill: parent
        visible: drop.containsDrag
        color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.10)
        border.width: 2
        border.color: root.accent
        z: 9
    }

    Column {
        anchors.fill: parent
        spacing: 0

        // --- başlık --------------------------------------------------------
        SonarPanel {
            width: parent.width
            height: 34
            color: Theme.raised
            Row {
                anchors.centerIn: parent
                spacing: Theme.s2
                SonarIcon {
                    name: root.channel.icon
                    color: root.accent
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: root.channel.name.toUpperCase()
                    color: root.accent
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                    font.letterSpacing: 0.6
                    renderType: Text.NativeRendering
                    anchors.verticalCenter: parent.verticalCenter
                }
                SonarIconButton {
                    icon: "gear"
                    accent: root.accent
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.openFx(root.channel.id)
                }
                // Her kanal silinebilir — Aux'u kullanmayan kullanıcı onu da atabilmeli.
                // Neyin kaybolacağını onay penceresi anlatıyor.
                SonarIconButton {
                    icon: "close"
                    accent: Theme.danger
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.removeRequested(root.channel.id, root.channel.name)
                }
            }
        }

        // --- profil --------------------------------------------------------
        SonarPanel {
            width: parent.width
            height: 30
            SonarComboBox {
                anchors.fill: parent
                anchors.margins: 2
                accent: root.accent
                model: (root.channel.profiles || []).map(function (p) {
                    // Gömülü presetler kilit işaretiyle ayrılıyor (salt okunurlar).
                    return typeof p === "string"
                        ? { value: p, label: p }
                        : { value: p.name, label: (p.builtin ? "🔒 " : "") + p.name }
                })
                currentValue: root.channel.activeProfile
                onActivated: (value) => root.bridge.loadProfile(root.channel.id, value)
            }
        }

        // --- fader'lar -----------------------------------------------------
        SonarPanel {
            width: parent.width
            height: 250

            Row {
                anchors.centerIn: parent
                spacing: Theme.s4

                Repeater {
                    model: [
                        { bus: "personal", icon: "headset",
                          vol: root.channel.personalVolume, mute: root.channel.personalMuted,
                          peak: root.channel.personalPeak, hold: root.channel.personalHold },
                        { bus: "stream", icon: "cast",
                          vol: root.channel.streamVolume, mute: root.channel.streamMuted,
                          peak: root.channel.streamPeak, hold: root.channel.streamHold }
                    ]

                    Column {
                        required property var modelData
                        spacing: Theme.s1

                        SonarIcon {
                            name: modelData.icon
                            color: modelData.mute ? Theme.textFaint : root.accent
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        // aktiflik noktası
                        Rectangle {
                            width: 6; height: 6
                            anchors.horizontalCenter: parent.horizontalCenter
                            color: modelData.mute ? Theme.textFaint : root.accent
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: Theme.volumeText(modelData.vol)
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        /* ChatMix bu kanalı kısıyorsa söyle: fader taban değeri gösteriyor,
                           duyulan ses taban × ChatMix çarpanı. */
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: modelData.bus === "personal" && root.chatmixGain < 0.99
                            text: "ChatMix " + Math.round(root.chatmixGain * 100) + "%"
                            color: Theme.warn
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        Row {
                            spacing: 3
                            SonarFader {
                                height: 150
                                value: modelData.vol
                                muted: modelData.mute
                                accent: root.accent
                                onMoved: (v) => root.setVolume(modelData.bus, v)
                            }
                            SonarLevelMeter {
                                height: 150
                                db: modelData.peak === undefined ? -60 : modelData.peak
                                holdDb: modelData.hold === undefined ? -60 : modelData.hold
                                clipped: root.channel.clipped === true
                            }
                        }
                        SonarIconButton {
                            icon: "mute"
                            active: modelData.mute
                            accent: Theme.danger
                            anchors.horizontalCenter: parent.horizontalCenter
                            onClicked: root.toggleMute(modelData.bus, !modelData.mute)
                        }
                    }
                }
            }
        }

        // --- uygulamalar ---------------------------------------------------
        SonarPanel {
            width: parent.width
            height: 120
            visible: !root.isMic

            Column {
                anchors.fill: parent
                anchors.margins: Theme.s2
                spacing: Theme.s1

                SonarSectionLabel { text: "Apps" }

                Repeater {
                    model: root.streamModel
                    Rectangle {
                        id: chip
                        required property string label
                        required property string channel
                        required property int id
                        visible: channel === root.channel.id
                        height: visible ? 22 : 0
                        width: parent.width
                        color: chipMouse.drag.active ? Qt.lighter(Theme.raised, 1.5) : Theme.raised
                        border.width: 1
                        border.color: chipMouse.drag.active ? root.accent : Theme.border
                        opacity: chipMouse.drag.active ? 0.85 : 1.0

                        // Sürükleme için: taşınırken üstte kalsın.
                        z: chipMouse.drag.active ? 50 : 0
                        Drag.active: chipMouse.drag.active
                        Drag.source: chip
                        Drag.hotSpot.x: width / 2
                        Drag.hotSpot.y: height / 2
                        property int streamId: id

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.s1
                            verticalAlignment: Text.AlignVCenter
                            text: chip.label
                            color: Theme.text
                            elide: Text.ElideRight
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        MouseArea {
                            id: chipMouse
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            cursorShape: Qt.PointingHandCursor
                            drag.target: chip
                            drag.threshold: 6
                            onClicked: (mouse) => {
                                if (mouse.button === Qt.RightButton)
                                    root.streamMenuRequested(chip.id, chip.label)
                            }
                            onReleased: {
                                if (chip.Drag.active) chip.Drag.drop()
                                chip.x = 0; chip.y = 0
                            }
                        }
                    }
                }
            }
        }
    }

    signal streamMenuRequested(int streamId, string label)
    signal removeRequested(string channelId, string name)

    function setVolume(bus, value) {
        if (root.isMic) {
            if (bus === "stream") root.bridge.setMicVolume(value)
            return
        }
        root.bridge.setChannelVolume(root.channel.id, bus, value)
    }

    function toggleMute(bus, muted) {
        if (root.isMic) {
            if (bus === "stream") root.bridge.setMicMute(muted)
            else root.bridge.setMicMonitor(!muted)
            return
        }
        root.bridge.setChannelMute(root.channel.id, bus, muted)
    }
}
