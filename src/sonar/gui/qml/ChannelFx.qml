import QtQuick
import "ui"

/* Bir kanalın FX sayfası: profil şeridi, EQ ve dinamik filtreler. */
Item {
    id: root
    property var bridge
    property string target: ""

    // Köprüdeki sayaç. Aşağıdaki her bağlama bunu **okuyor** — köprü fonksiyonları
    // property okumadığı için tek başlarına bağlama kurmuyorlar.
    readonly property int tick: bridge ? bridge.revision : 0

    readonly property var channel: bridge ? (tick, bridge.channelOf(target)) : ({})
    readonly property color accent: channel.color !== undefined ? channel.color : Theme.master
    readonly property var profile: bridge ? (tick, bridge.profileOf(target)) : ({})
    readonly property bool isMic: bridge ? (tick, bridge.isInputChannel(target)) : false
    readonly property var names: bridge ? (tick, bridge.profileNames(target)) : []
    readonly property string activeName: channel.activeProfile !== undefined
                                         ? channel.activeProfile : "Default"

    Column {
        anchors.fill: parent
        spacing: Theme.s2

        // --- profil şeridi -------------------------------------------------
        SonarPanel {
            width: parent.width
            height: 56
            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.s3
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.s2

                SonarIcon {
                    name: root.channel.icon !== undefined ? root.channel.icon : "speaker"
                    color: root.accent
                    anchors.verticalCenter: parent.verticalCenter
                }
                SonarComboBox {
                    width: 190
                    accent: root.accent
                    anchors.verticalCenter: parent.verticalCenter
                    model: root.names.map(function (p) {
                        return typeof p === "string"
                            ? { value: p, label: p }
                            : { value: p.name, label: (p.builtin ? "🔒 " : "") + p.name }
                    })
                    currentValue: root.activeName
                    onActivated: (v) => root.bridge.loadProfile(root.target, v)
                }
                SonarButton {
                    text: "Farklı kaydet"
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: saveDialog.open()
                }
                SonarButton {
                    text: "Sıfırla"
                    variant: "ghost"
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.bridge.resetProfile(root.target)
                }
                SonarButton {
                    text: "Sil"
                    variant: "ghost"
                    anchors.verticalCenter: parent.verticalCenter
                    onClicked: root.bridge.deleteProfile(root.target, root.activeName)
                }

                Item { width: Theme.s4; height: 1 }
                SonarSectionLabel {
                    text: "Favoriler"
                    anchors.verticalCenter: parent.verticalCenter
                }
                Row {
                    spacing: 2
                    anchors.verticalCenter: parent.verticalCenter
                    Repeater {
                        model: 9
                        Rectangle {
                            required property int index
                            width: 24; height: 24
                            readonly property bool mine:
                                root.profile.favorite_slot === index + 1
                            color: mine ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.2)
                                        : (favMouse.containsMouse ? Theme.raised : Theme.surface)
                            border.width: 1
                            border.color: mine ? root.accent : Theme.border
                            Text {
                                anchors.centerIn: parent
                                text: String(index + 1)
                                color: parent.mine ? root.accent : Theme.textFaint
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSmall
                                renderType: Text.NativeRendering
                            }
                            MouseArea {
                                id: favMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.bridge.setProfileFavorite(
                                    root.target, root.activeName, parent.mine ? 0 : parent.index + 1)
                            }
                        }
                    }
                }
            }
        }

        // --- EQ ------------------------------------------------------------
        EqPanel {
            width: parent.width
            height: parent.height - 56 - dynamics.height - Theme.s2 * 2
            bridge: root.bridge
            target: root.target
            accent: root.accent
            profile: root.profile
        }

        // --- dinamikler ----------------------------------------------------
        Row {
            id: dynamics
            width: parent.width
            height: 168
            spacing: Theme.s2

            SonarFilterPanel {
                width: (parent.width - Theme.s2 * 2) / 3
                height: parent.height
                title: root.isMic ? "AI Gürültü Engelleme" : "Noise Gate"
                accent: root.accent
                active: root.stageOn(root.isMic ? "df" : "gate")
                onToggled: (v) => root.bridge.setFilterEnabled(root.target,
                                                               root.isMic ? "df" : "gate", v)
                Column {
                    anchors.fill: parent
                    spacing: 2
                    Repeater {
                        model: root.isMic ? root.dfParams : root.gateParams
                        SonarParamRow {
                            required property var modelData
                            width: parent.width
                            label: modelData.label
                            from: modelData.from; to: modelData.to
                            unit: modelData.unit
                            decimals: modelData.digits !== undefined ? modelData.digits : 1
                            accent: root.accent
                            enabled: root.stageOn(modelData.stage)
                            value: root.paramOf(modelData.stage, modelData.key, modelData.fallback)
                            onMoved: (v) => root.bridge.setFilterParam(
                                root.target, modelData.stage, modelData.key, v)
                        }
                    }
                }
            }

            SonarFilterPanel {
                width: (parent.width - Theme.s2 * 2) / 3
                height: parent.height
                title: root.isMic ? "Noise Gate" : "Compressor"
                accent: root.accent
                active: root.stageOn(root.isMic ? "gate" : "comp")
                note: (root.isMic && root.stageOn("df")) ? "AI aktifken devre dışı" : ""
                onToggled: (v) => root.bridge.setFilterEnabled(root.target,
                                                               root.isMic ? "gate" : "comp", v)
                Column {
                    anchors.fill: parent
                    spacing: 2
                    Repeater {
                        model: root.isMic ? root.gateParams : root.compParams
                        SonarParamRow {
                            required property var modelData
                            width: parent.width
                            label: modelData.label
                            from: modelData.from; to: modelData.to
                            unit: modelData.unit
                            decimals: modelData.digits !== undefined ? modelData.digits : 1
                            accent: root.accent
                            enabled: root.stageOn(modelData.stage)
                                     && !(root.isMic && root.stageOn("df"))
                            value: root.paramOf(modelData.stage, modelData.key, modelData.fallback)
                            onMoved: (v) => root.bridge.setFilterParam(
                                root.target, modelData.stage, modelData.key, v)
                        }
                    }
                }
            }

            SonarFilterPanel {
                width: (parent.width - Theme.s2 * 2) / 3
                height: parent.height
                title: root.isMic ? "Compressor + Limiter" : "Limiter"
                accent: root.accent
                active: root.stageOn("lim")
                onToggled: (v) => root.bridge.setFilterEnabled(root.target, "lim", v)
                Column {
                    anchors.fill: parent
                    spacing: 2
                    Repeater {
                        model: root.limParams
                        SonarParamRow {
                            required property var modelData
                            width: parent.width
                            label: modelData.label
                            from: modelData.from; to: modelData.to
                            unit: modelData.unit
                            decimals: modelData.digits !== undefined ? modelData.digits : 1
                            accent: root.accent
                            enabled: root.stageOn(modelData.stage)
                            value: root.paramOf(modelData.stage, modelData.key, modelData.fallback)
                            onMoved: (v) => root.bridge.setFilterParam(
                                root.target, modelData.stage, modelData.key, v)
                        }
                    }
                }
            }
        }
    }

    // --- profil kaydetme -----------------------------------------------------
    Rectangle {
        id: saveDialog
        visible: false
        z: 300
        anchors.centerIn: parent
        width: 320
        height: 140
        color: Theme.raised
        border.width: 1
        border.color: root.accent

        function open() { nameInput.text = root.activeName; visible = true; nameInput.forceActiveFocus() }

        Column {
            anchors.fill: parent
            anchors.margins: Theme.s4
            spacing: Theme.s3
            SonarSectionLabel { text: "Profili farklı kaydet" }
            Rectangle {
                width: parent.width
                height: 28
                color: Theme.sunken
                border.width: 1
                border.color: nameInput.activeFocus ? root.accent : Theme.border
                TextInput {
                    id: nameInput
                    anchors.fill: parent
                    anchors.leftMargin: Theme.s2
                    verticalAlignment: Text.AlignVCenter
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    selectByMouse: true
                    Keys.onReturnPressed: saveDialog.commit()
                }
            }
            Row {
                spacing: Theme.s2
                SonarButton { text: "Kaydet"; variant: "accent"; accent: root.accent
                              onClicked: saveDialog.commit() }
                SonarButton { text: "Vazgeç"; onClicked: saveDialog.visible = false }
            }
        }

        function commit() {
            const name = nameInput.text.trim()
            if (name.length > 0) root.bridge.saveProfile(root.target, name)
            visible = false
        }
    }

    // --- parametre tanımları -------------------------------------------------
    readonly property var gateParams: [
        { stage:"gate", key:"threshold_db", label:"Eşik",    from:-80, to:0,   unit:"dB", fallback:-40 },
        { stage:"gate", key:"attack_ms",    label:"Atak",    from:0,   to:200, unit:"ms", fallback:10 },
        { stage:"gate", key:"release_ms",   label:"Bırakma", from:5,   to:1000,unit:"ms", fallback:100 },
        { stage:"gate", key:"reduction_db", label:"Azaltma", from:-80, to:0,   unit:"dB", fallback:-24 }
    ]
    readonly property var compParams: [
        { stage:"comp", key:"threshold_db", label:"Eşik",    from:-60, to:0,   unit:"dB", fallback:-18 },
        { stage:"comp", key:"ratio",        label:"Oran",    from:1,   to:20,  unit:": 1", fallback:4 },
        { stage:"comp", key:"attack_ms",    label:"Atak",    from:0,   to:200, unit:"ms", fallback:5 },
        { stage:"comp", key:"release_ms",   label:"Bırakma", from:5,   to:1000,unit:"ms", fallback:120 },
        { stage:"comp", key:"makeup_db",    label:"Makyaj",  from:0,   to:24,  unit:"dB", fallback:0 }
    ]
    readonly property var limParams: [
        { stage:"lim", key:"ceiling_db",   label:"Tavan",    from:-24, to:0,  unit:"dB", fallback:-1 },
        { stage:"lim", key:"lookahead_ms", label:"İleri bak",from:0.1, to:20, unit:"ms", fallback:5 },
        { stage:"lim", key:"release_ms",   label:"Bırakma",  from:0.25,to:20, unit:"ms", fallback:5 }
    ]
    readonly property var dfParams: [
        { stage:"df", key:"attenuation_db",   label:"Azaltma", from:0, to:100, unit:"dB",
          fallback:40, digits:0 },
        { stage:"df", key:"post_filter_beta", label:"Post filtre", from:0, to:0.05, unit:"",
          fallback:0.02, digits:3 }
    ]

    /* `tick` (yani `bridge.revision`) bilerek okunuyor.

       QML bir bağlamayı yalnızca içinde okunan **property'ler** değişince yeniden
       değerlendirir. Bu iki fonksiyon hiçbir property okumadığı için `active:
       root.stageOn("gate")` bağlaması `bridge.revision` artınca tazelenmiyordu:
       kullanıcı anahtara basıyor, hiçbir şey olmuyor, başka kanala geçip dönünce
       anahtar açık görünüyordu (çünkü `target` değişince bağlama yeniden kuruluyor).
       `void tick` çağıranın bağlamasına revision'ı bağımlılık olarak ekliyor. */
    function stageOn(stage) {
        void root.tick
        const f = bridge ? bridge.filterOf(target, stage) : ({})
        return f.enabled === true
    }

    function paramOf(stage, key, fallback) {
        void root.tick
        const f = bridge ? bridge.filterOf(target, stage) : ({})
        const params = f.params !== undefined ? f.params : ({})
        return params[key] !== undefined ? params[key] : fallback
    }
}
