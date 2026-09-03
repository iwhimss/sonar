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
    readonly property var outputs: bridge ? bridge.outputs : []

    // Smart Volume. `bridge.revision` okunuyor ki ayar değişince tazelensin.
    readonly property var ducking: bridge ? (bridge.revision, bridge.ducking()) : ({})
    // Durum daha gelmemişken `ducking.enabled` tanımsız; `bool`a atanamıyor.
    readonly property bool duckOn: ducking.enabled === true
    readonly property string duckTrigger: {
        const list = ducking.trigger_channels || []
        return list.length > 0 ? list[0] : ""
    }
    readonly property string duckDescription:
        duckTrigger.length > 0
            ? root.nameOf(duckTrigger) + " kanalında ses olunca diğer kanallar kısılır."
            : "Hangi kanalı dinleyeceğini seçin."

    readonly property var channelOptions: {
        const _ = bridge ? bridge.revision : 0
        const out = []
        const model = bridge ? bridge.channels : null
        if (!model) return out
        for (let i = 0; i < model.rowCount(); ++i) {
            const row = model.get(i)
            if (row.kind === "channel") out.push({ value: row.id, label: row.name })
        }
        return out
    }

    function nameOf(channelId) {
        for (const option of channelOptions)
            if (option.value === channelId) return option.label
        return channelId
    }

    /* Master fader'lar: her çıkış bus'ı, sonra yayın. Bus sayısı sabit değil. */
    readonly property var faderKeys: {
        const out = []
        for (const bus of outputs)
            out.push({ key: bus.id, icon: "headset", label: bus.name })
        out.push({ key: "stream", icon: "cast", label: "Yayın" })
        return out
    }

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

                SonarSectionLabel { text: "Çıkışlar" }

                /* Her çıkış bus'ı bir fiziksel cihaz + kendi master fader'ı. Kanal
                   hangisine gideceğini kendi şeridinden seçiyor (Faz 20). */
                Repeater {
                    model: root.outputs
                    Column {
                        id: outputRow
                        required property var modelData
                        width: parent.width
                        spacing: 2

                        SonarSectionLabel {
                            text: outputRow.modelData.name
                            color: Theme.textFaint
                        }
                        Row {
                            spacing: Theme.s1
                            width: parent.width
                            SonarComboBox {
                                width: parent.width - dropBus.width - Theme.s1
                                accent: Theme.master
                                model: root.deviceList(false)
                                currentValue: outputRow.modelData.device || ""
                                onActivated: (value) =>
                                    root.bridge.setBusDevice(outputRow.modelData.id, value)
                            }
                            SonarIconButton {
                                id: dropBus
                                icon: "close"
                                accent: Theme.danger
                                // En az bir çıkış kalmalı; yoksa kanalların sesi
                                // hiçbir yere gitmez.
                                visible: root.outputs.length > 1
                                onClicked: root.bridge.removeOutputBus(outputRow.modelData.id)
                            }
                        }
                    }
                }

                SonarButton {
                    width: parent.width
                    text: "＋  Çıkış ekle"
                    variant: "ghost"
                    onClicked: addOutput.open()
                }

                SonarSectionLabel { text: "Mikrofon"; color: Theme.textFaint }
                SonarComboBox {
                    width: parent.width
                    accent: Theme.master
                    model: root.deviceList(true)
                    currentValue: (root.masters, root.deviceOf("mic"))
                    onActivated: (value) => root.bridge.setMicDevice(value)
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

        /* Smart Volume kanal profilinin değil **ayarların** parçası: bir kanalı
           kısarken başka bir kanalı dinliyor, yani tek bir kanala ait değil. */
        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: smart.implicitHeight + Theme.s3 * 2

            Column {
                id: smart
                anchors.fill: parent
                anchors.margins: Theme.s3
                spacing: Theme.s2

                Row {
                    spacing: Theme.s2
                    width: parent.width
                    Rectangle {
                        width: 30; height: 16
                        anchors.verticalCenter: parent.verticalCenter
                        color: root.duckOn ? Theme.master : Theme.sunken
                        border.width: 1
                        border.color: root.duckOn ? Theme.master : Theme.border
                        Rectangle {
                            width: 12; height: 12
                            x: root.duckOn ? 16 : 2
                            y: 2
                            color: root.duckOn ? "#0E1116" : Theme.textFaint
                            Behavior on x { NumberAnimation { duration: 90 } }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.bridge.setDucking({ "enabled": !root.duckOn })
                        }
                    }
                    SonarSectionLabel {
                        text: "Smart Volume"
                        color: root.duckOn ? Theme.master : Theme.textDim
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: root.duckDescription
                    color: Theme.textFaint
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                }

                SonarComboBox {
                    width: parent.width
                    accent: Theme.master
                    enabled: root.duckOn
                    model: root.channelOptions
                    currentValue: root.duckTrigger
                    onActivated: (value) => root.bridge.setDucking(
                        { "trigger_channels": [value] })
                }

                SonarParamRow {
                    width: parent.width
                    label: "İndirim"
                    from: -40; to: 0; unit: "dB"
                    accent: Theme.master
                    enabled: root.duckOn
                    value: root.ducking.reduction_db !== undefined
                           ? root.ducking.reduction_db : -12
                    onMoved: (v) => root.bridge.setDucking({ "reduction_db": v })
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
                    model: root.faderKeys
                    Column {
                        required property var modelData
                        spacing: Theme.s1
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.label
                            color: Theme.textFaint
                            elide: Text.ElideRight
                            width: 56
                            horizontalAlignment: Text.AlignHCenter
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
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

    /* Yeni çıkış bus'ı: ad + cihaz. Yapısal, yani graf yeniden kurulur. */
    Rectangle {
        id: addOutput
        visible: false
        z: 400
        parent: root.parent ? root.parent : root
        anchors.centerIn: parent
        width: 360
        height: 200
        color: Theme.raised
        border.width: 1
        border.color: Theme.borderStrong

        function open() { nameField.text = ""; device = ""; visible = true
                          nameField.forceActiveFocus() }
        property string device: ""

        Column {
            anchors.fill: parent
            anchors.margins: Theme.s4
            spacing: Theme.s3

            SonarSectionLabel { text: "Yeni çıkış" }

            Rectangle {
                width: parent.width
                height: 28
                color: Theme.sunken
                border.width: 1
                border.color: nameField.activeFocus ? Theme.master : Theme.border
                TextInput {
                    id: nameField
                    anchors.fill: parent
                    anchors.leftMargin: Theme.s2
                    verticalAlignment: Text.AlignVCenter
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    selectByMouse: true
                    Keys.onReturnPressed: addOutput.commit()
                }
            }

            SonarComboBox {
                width: parent.width
                accent: Theme.master
                model: root.deviceList(false)
                currentValue: addOutput.device
                onActivated: (value) => addOutput.device = value
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Yeni çıkış kendi fader'ı, EQ'su ve profilleriyle gelir. "
                    + "Graf yeniden kurulur; yaklaşık 200 ms sessizlik olur."
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            Row {
                spacing: Theme.s2
                SonarButton { text: "Ekle"; variant: "accent"; onClicked: addOutput.commit() }
                SonarButton { text: "Vazgeç"; onClicked: addOutput.visible = false }
            }
        }

        function commit() {
            const name = nameField.text.trim()
            if (name.length > 0) root.bridge.addOutputBus(name, device)
            visible = false
        }
    }
}
