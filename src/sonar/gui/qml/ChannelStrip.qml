import QtQuick
import QtQuick.Layouts
import "ui"

/*
 * Tek bir kanal şeridi: başlık, profil seçici, çift fader (kulaklık + yayın),
 * mute düğmeleri ve altındaki uygulama kutusu.
 *
 * ## Neden satır alanları tek tek `required property`
 *
 * Eskiden şerit `channel: bridge.channels.get(index)` ile bir **sözlük kopyası**
 * alıyordu. `get()` bir fonksiyon çağrısı ve `bridge.channels` (model nesnesi) hiç
 * değişmiyor; yani o bağlama bir kez değerlenip donuyordu. Model `dataChanged`
 * yayınlasa bile şerit görmüyordu — mute düğmesi tepkisiz, fader donuk, profil adı
 * eski. Test turu 2'deki "gui anlık güncellenmiyor" şikâyeti buydu.
 *
 * `Repeater` delegesi olarak model rollerini doğrudan almak bunu kökten çözüyor:
 * `dataChanged` ilgili özelliği tazeliyor. Rol adları `bridge.ChannelModel.keys`
 * ile birebir aynı olmalı.
 */
Item {
    id: root

    // --- model rolleri (ChannelModel.keys ile birebir) ----------------------
    required property string id
    required property string name
    required property color color
    required property string icon
    required property string activeProfile
    required property var profiles
    required property real personalVolume
    required property bool personalMuted
    required property real streamVolume
    required property bool streamMuted
    required property string kind

    property var bridge
    property var dragProxy
    signal openFx(string channelId)
    signal streamMenuRequested(int streamId, string label)
    signal removeRequested(string channelId, string name)

    implicitWidth: 148

    readonly property color accent: root.color
    readonly property bool isMic: root.kind === "mic"
    readonly property real chatmixGain:
        bridge ? (bridge.revision, bridge.chatmixGain(root.id)) : 1.0

    /* Bu kanalda çalan uygulamalar. `bridge.revision` okunuyor ki akış listesi
       değişince bağlama yeniden değerlendirilsin — fonksiyon çağrısı tek başına
       bağlama kurmaz. */
    readonly property var apps:
        bridge ? (bridge.revision, bridge.streamsFor(root.id)) : []

    readonly property var favorites:
        bridge ? (bridge.revision, bridge.favoritesOf(root.id)) : []

    /* Profil menüsü: önce favoriler, sonra ayraç, sonra tümü. Gömülü presetler
       kilit işaretiyle ayrılıyor (salt okunurlar). */
    readonly property var profileOptions: {
        const all = (root.profiles || []).map(function (p) {
            return typeof p === "string"
                ? { value: p, label: p, builtin: false }
                : { value: p.name, label: p.name, builtin: p.builtin === true }
        })
        const out = []
        if (favorites.length > 0) {
            out.push({ value: "", label: "Favoriler", header: true })
            for (const name of favorites) {
                const hit = all.find(function (o) { return o.value === name })
                if (hit) out.push({ value: hit.value, label: "★ " + hit.label })
            }
            out.push({ value: "", label: "Tüm profiller", header: true })
        }
        for (const option of all)
            out.push({ value: option.value, label: (option.builtin ? "🔒 " : "") + option.label })
        return out
    }

    /* Anlık seviye. Ayrı bir sayaca (`levelsRevision`) bağlı: `revision` saniyede 20
       kez artsaydı şeridin tamamı yeniden değerlendirilirdi. */
    readonly property var level:
        bridge ? (bridge.levelsRevision, bridge.levelOf(root.id))
               : ({ peak_db: -60, hold_db: -60, clipped: false })

    /* Şeridin tamamı bırakma hedefi: kullanıcı çipi şeridin herhangi bir yerine
       bırakabilsin, yalnızca küçük Apps kutusuna nişan almak zorunda kalmasın. */
    /* Şeridin tamamı bırakma hedefi. Yön uyuşmazlığı reddediliyor: bir mikrofon akışı
       çıkış kanalına, bir oynatma akışı giriş zincirine bırakılamaz — PipeWire tarafında
       da anlamsız olurdu. */
    DropArea {
        id: drop
        anchors.fill: parent
        z: 10
        readonly property bool accepts: {
            const source = drag.source
            if (!source || source.streamDirection === undefined) return false
            return (source.streamDirection === "in") === root.isMic
        }
        onDropped: (event) => {
            if (!drop.accepts) { event.accepted = false; return }
            const source = event.source
            if (source && source.streamId !== undefined)
                root.bridge.moveStream(source.streamId, root.id, false)
            event.accept()
        }
    }

    // Bırakma sırasında hedef şerit vurgulanır.
    Rectangle {
        anchors.fill: parent
        visible: drop.containsDrag && drop.accepts
        color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.10)
        border.width: 2
        border.color: root.accent
        z: 9
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // --- başlık --------------------------------------------------------
        //
        // Eskiden ortalanmış bir `Row`'du: ikon + ad + dişli + çarpı, 132 px şeride
        // sığmıyor ve silme düğmesinin yarısı kırpılıyordu. Artık ad esniyor ve
        // düğmeler sağa sabit.
        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            color: Theme.raised

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.s2
                anchors.rightMargin: Theme.s1
                spacing: Theme.s1

                SonarIcon {
                    name: root.icon
                    color: root.accent
                    Layout.alignment: Qt.AlignVCenter
                }
                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    text: root.name.toUpperCase()
                    color: root.accent
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                    font.letterSpacing: 0.6
                    renderType: Text.NativeRendering
                }
                SonarIconButton {
                    icon: "gear"
                    accent: root.accent
                    Layout.alignment: Qt.AlignVCenter
                    onClicked: root.openFx(root.id)
                }
                // Her kanal silinebilir — Aux'u kullanmayan kullanıcı onu da atabilmeli.
                // Neyin kaybolacağını onay penceresi anlatıyor.
                SonarIconButton {
                    icon: "close"
                    accent: Theme.danger
                    Layout.alignment: Qt.AlignVCenter
                    onClicked: root.removeRequested(root.id, root.name)
                }
            }
        }

        // --- profil --------------------------------------------------------
        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            SonarComboBox {
                anchors.fill: parent
                anchors.margins: 2
                accent: root.accent
                // Şerit dar; liste bu yüzden kontrolden geniş açılıyor.
                popupWidth: 240
                model: root.profileOptions
                currentValue: root.activeProfile
                onActivated: (value) => root.bridge.loadProfile(root.id, value)
            }
        }

        // --- fader'lar -----------------------------------------------------
        SonarPanel {
            id: faderPanel
            Layout.fillWidth: true
            // Sabit 250 px'ti; küçük pencerede altındaki Apps kutusunu negatif
            // yüksekliğe düşürüyordu. Artık kalan alanın çoğunu alıyor ama Apps
            // kutusuna her zaman yer bırakıyor.
            Layout.preferredHeight: Math.max(180, Math.min(250, root.height - 150))

            Row {
                anchors.centerIn: parent
                spacing: Theme.s4

                Repeater {
                    model: [
                        // "output" = kanalın seçili çıkış bus'ı; daemon çözüyor.
                        { bus: "output", icon: "headset" },
                        { bus: "stream", icon: "cast" }
                    ]

                    Column {
                        id: busColumn
                        required property var modelData
                        spacing: Theme.s1

                        readonly property string bus: modelData.bus
                        readonly property real vol: bus === "output"
                            ? root.personalVolume : root.streamVolume
                        readonly property bool mute: bus === "output"
                            ? root.personalMuted : root.streamMuted
                        readonly property int barHeight: Math.max(80, faderPanel.height - 100)

                        SonarIcon {
                            name: busColumn.modelData.icon
                            color: busColumn.mute ? Theme.textFaint : root.accent
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        // aktiflik noktası
                        Rectangle {
                            width: 6; height: 6
                            anchors.horizontalCenter: parent.horizontalCenter
                            color: busColumn.mute ? Theme.textFaint : root.accent
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: Theme.volumeText(busColumn.vol)
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        /* ChatMix bu kanalı kısıyorsa söyle: fader taban değeri gösteriyor,
                           duyulan ses taban × ChatMix çarpanı. */
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: busColumn.bus === "output" && root.chatmixGain < 0.99
                            text: "ChatMix " + Math.round(root.chatmixGain * 100) + "%"
                            color: Theme.warn
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        Row {
                            spacing: 3
                            SonarFader {
                                height: busColumn.barHeight
                                value: busColumn.vol
                                muted: busColumn.mute
                                accent: root.accent
                                onMoved: (v) => root.setVolume(busColumn.bus, v)
                            }
                            /* Metre kanal sink monitöründen besleniyor: DSP ve fader
                               öncesi, yani uygulamanın çaldığı seviye. İki bus için de
                               aynı — ayrım fader'ın kendisinde görünüyor. */
                            SonarLevelMeter {
                                height: busColumn.barHeight
                                db: root.level.peak_db
                                holdDb: root.level.hold_db
                                clipped: root.level.clipped === true
                            }
                        }
                        SonarIconButton {
                            icon: "mute"
                            active: busColumn.mute
                            accent: Theme.danger
                            anchors.horizontalCenter: parent.horizontalCenter
                            onClicked: root.toggleMute(busColumn.bus, !busColumn.mute)
                        }
                    }
                }
            }
        }

        // --- uygulamalar ---------------------------------------------------
        SonarPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0

            Column {
                anchors.fill: parent
                anchors.margins: Theme.s2
                spacing: Theme.s1

                SonarSectionLabel {
                    text: (root.isMic ? "Mikrofonu kullananlar  (" : "Apps  (")
                          + root.apps.length + ")"
                }

                ListView {
                    id: appList
                    width: parent.width
                    height: Math.max(0, parent.height - 16)
                    clip: true          // taşma yok; fazlası kaydırılır
                    spacing: 2
                    model: root.apps
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: Rectangle {
                        id: chip
                        required property var modelData
                        required property int index
                        width: appList.width - (appList.contentHeight > appList.height ? 4 : 0)
                        height: 22
                        color: Theme.raised
                        border.width: 1
                        border.color: Theme.border
                        // Sürüklenirken asıl kutucuk görünmez olur; imleci vekil izler.
                        // Kutucuğun kendisi hareket etmeye devam etmeli, çünkü
                        // `DropArea` hedefi onun konumundan buluyor.
                        opacity: chipMouse.drag.active ? 0.0 : 1.0

                        Drag.active: chipMouse.drag.active
                        Drag.source: chip
                        Drag.hotSpot.x: width / 2
                        Drag.hotSpot.y: height / 2
                        property int streamId: modelData.id
                        property string streamDirection: modelData.direction

                        /* Yön rozeti: aynı uygulama hem çıkış hem giriş şeridinde
                           görünebiliyor (Discord). Hangisi olduğu okunabilmeli. */
                        Rectangle {
                            id: badge
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.s1
                            anchors.verticalCenter: parent.verticalCenter
                            width: 22
                            height: 14
                            color: "transparent"
                            border.width: 1
                            border.color: Theme.borderStrong
                            Text {
                                anchors.centerIn: parent
                                text: chip.modelData.direction === "in" ? "IN" : "OUT"
                                color: Theme.textFaint
                                font.family: Theme.fontFamily
                                font.pixelSize: 9
                                font.letterSpacing: 0.4
                                renderType: Text.NativeRendering
                            }
                        }
                        Text {
                            anchors.left: badge.right
                            anchors.leftMargin: Theme.s1
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.s1
                            anchors.verticalCenter: parent.verticalCenter
                            text: chip.modelData.label
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
                            hoverEnabled: true
                            drag.target: chip
                            drag.threshold: 6
                            onClicked: (mouse) => {
                                if (mouse.button === Qt.RightButton)
                                    root.streamMenuRequested(chip.streamId, chip.modelData.label)
                            }
                            onPositionChanged: (mouse) => {
                                if (!chip.Drag.active || !root.dragProxy) return
                                const point = mapToItem(root.dragProxy, mouse.x, mouse.y)
                                root.dragProxy.moveTo(point.x, point.y)
                            }
                            onReleased: {
                                if (chip.Drag.active) chip.Drag.drop()
                                chip.x = 0; chip.y = 0
                            }
                        }

                        /* `drag.active` bir grup özelliği; doğrudan sinyal handler'ı yok.
                           Yerel bir özelliğe bağlayıp onun değişimini dinliyoruz. */
                        property bool dragging: chipMouse.drag.active
                        onDraggingChanged: {
                            if (!root.dragProxy) return
                            if (dragging) root.dragProxy.show(chip.modelData.label, root.accent)
                            else root.dragProxy.hide()
                        }
                    }

                    // İnce kaydırma göstergesi — köşesiz, Controls'a bağımlı değil.
                    Rectangle {
                        width: 3
                        color: Theme.borderStrong
                        anchors.right: parent.right
                        visible: appList.contentHeight > appList.height
                        height: appList.height * (appList.height / Math.max(appList.contentHeight, 1))
                        y: appList.contentY * (appList.height / Math.max(appList.contentHeight, 1))
                    }
                }
            }
        }
    }

    /* Giriş kanalında iki fader başka şeyleri sürüyor: "output" sidetone (kulaklıkta
       kendini duyma), "stream" mikrofonun kendi seviyesi. Zincir kimliği **her zaman**
       şeridin kendi kimliği — eskiden köprü sabit `"mic"` yazdığı için ikinci giriş
       kanalının düğmeleri birincisini sürüyordu (test turu 3). */
    function setVolume(bus, value) {
        if (root.isMic) {
            if (bus === "stream") root.bridge.setMicVolume(root.id, value)
            else root.bridge.setMicMonitorVolume(root.id, value)
            return
        }
        root.bridge.setChannelVolume(root.id, bus, value)
    }

    function toggleMute(bus, muted) {
        if (root.isMic) {
            if (bus === "stream") root.bridge.setMicMute(root.id, muted)
            else root.bridge.setMicMonitor(root.id, !muted)
            return
        }
        root.bridge.setChannelMute(root.id, bus, muted)
    }
}
