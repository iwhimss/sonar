import QtQuick
import QtQuick.Dialogs as Dialogs
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
    readonly property var favorites: bridge ? (tick, bridge.favoritesOf(target)) : []
    readonly property bool activeIsFavorite: favorites.indexOf(activeName) >= 0

    /* Profil seçicinin listesi: önce favoriler, sonra ayraç, sonra tümü. */
    readonly property var profileOptions: {
        const all = root.names.map(function (p) {
            return typeof p === "string"
                ? { value: p, label: p, builtin: false }
                : { value: p.name, label: p.name, builtin: p.builtin === true }
        })
        const out = []
        if (root.favorites.length > 0) {
            out.push({ value: "", label: "Favoriler", header: true })
            for (const name of root.favorites) {
                const hit = all.find(function (o) { return o.value === name })
                if (hit) out.push({ value: hit.value, label: "★ " + hit.label })
            }
            out.push({ value: "", label: "Tüm profiller", header: true })
        }
        for (const option of all)
            out.push({ value: option.value, label: (option.builtin ? "🔒 " : "") + option.label })
        return out
    }

    Column {
        anchors.fill: parent
        spacing: Theme.s2

        // --- profil şeridi -------------------------------------------------
        SonarPanel {
            width: parent.width
            height: 86

            Column {
                anchors.fill: parent
                anchors.margins: Theme.s2
                spacing: Theme.s1

                Row {
                    spacing: Theme.s2
                    height: 28

                    SonarIcon {
                        name: root.channel.icon !== undefined ? root.channel.icon : "speaker"
                        color: root.accent
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    SonarComboBox {
                        width: 210
                        accent: root.accent
                        anchors.verticalCenter: parent.verticalCenter
                        model: root.profileOptions
                        currentValue: root.activeName
                        onActivated: (v) => root.bridge.loadProfile(root.target, v)
                    }

                    /* Favori yıldızı. Eskiden 9 numaralı kutu vardı ama favoriye
                       eklemenin bir yolu yoktu — kullanıcının şikâyeti buydu. */
                    SonarIconButton {
                        icon: root.activeIsFavorite ? "star-on" : "star"
                        accent: Theme.warn
                        active: root.activeIsFavorite
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: root.bridge.setProfileFavorite(
                            root.target, root.activeName, !root.activeIsFavorite)
                    }

                    SonarButton {
                        text: "＋ Yeni profil"
                        variant: "accent"
                        accent: root.accent
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: newDialog.open()
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
                    SonarButton {
                        text: "İçe aktar"
                        variant: "ghost"
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: importDialog.open()
                    }
                    SonarButton {
                        text: "Dışa aktar"
                        variant: "ghost"
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: exportDialog.open()
                    }

                    /* Değişiklikler otomatik kaydediliyor; kullanıcı "kaydet" aramasın. */
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "değişiklikler otomatik kaydediliyor"
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                }

                // --- favori şeridi: sınırsız, sürüklenerek sıralanır --------
                Item {
                    width: parent.width
                    height: 26

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: root.favorites.length === 0
                        text: "Favori yok — yıldıza basarak ekleyin, hızlı geçiş için buraya dizilir."
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }

                    ListView {
                        id: favList
                        anchors.fill: parent
                        orientation: ListView.Horizontal
                        spacing: Theme.s1
                        clip: true
                        visible: root.favorites.length > 0
                        model: root.favorites
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: Item {
                            id: favItem
                            required property string modelData
                            required property int index
                            width: chipText.implicitWidth + Theme.s4
                            height: 24

                            Rectangle {
                                id: chip
                                width: parent.width
                                height: parent.height
                                readonly property bool current: favItem.modelData === root.activeName
                                color: chip.current
                                    ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.2)
                                    : (favMouse.containsMouse ? Theme.raised : Theme.surface)
                                border.width: 1
                                border.color: chip.current ? root.accent : Theme.border
                                opacity: favMouse.drag.active ? 0.7 : 1.0
                                z: favMouse.drag.active ? 50 : 0

                                Drag.active: favMouse.drag.active
                                Drag.source: favItem
                                Drag.hotSpot.x: width / 2

                                Text {
                                    id: chipText
                                    anchors.centerIn: parent
                                    text: "★ " + favItem.modelData
                                    color: chip.current ? root.accent : Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSmall
                                    renderType: Text.NativeRendering
                                }
                                MouseArea {
                                    id: favMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    drag.target: chip
                                    drag.axis: Drag.XAxis
                                    drag.threshold: 6
                                    onClicked: root.bridge.loadProfile(root.target, favItem.modelData)
                                    onReleased: { chip.Drag.drop(); chip.x = 0 }
                                }
                            }

                            DropArea {
                                anchors.fill: parent
                                onEntered: (event) => {
                                    const from = event.source.index
                                    const to = favItem.index
                                    if (from === to) return
                                    const order = root.favorites.slice()
                                    order.splice(to, 0, order.splice(from, 1)[0])
                                    root.bridge.reorderFavorites(root.target, order)
                                }
                            }
                        }
                    }
                }
            }
        }

        // --- EQ ------------------------------------------------------------
        EqPanel {
            width: parent.width
            height: parent.height - 86 - dynamics.height - Theme.s2 * 2
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

    // --- yeni profil ---------------------------------------------------------
    Rectangle {
        id: newDialog
        visible: false
        z: 300
        anchors.centerIn: parent
        width: 360
        height: 170
        color: Theme.raised
        border.width: 1
        border.color: root.accent

        function open() { nameInput.text = ""; visible = true; nameInput.forceActiveFocus() }

        Column {
            anchors.fill: parent
            anchors.margins: Theme.s4
            spacing: Theme.s3
            SonarSectionLabel { text: "Yeni profil" }
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
                    Keys.onReturnPressed: newDialog.commit()
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Sıfırdan düz başlar: EQ düz, tüm filtreler kapalı. "
                    + "Şu anki profil olduğu gibi kalır."
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Row {
                spacing: Theme.s2
                SonarButton { text: "Oluştur"; variant: "accent"; accent: root.accent
                              onClicked: newDialog.commit() }
                SonarButton { text: "Vazgeç"; onClicked: newDialog.visible = false }
            }
        }

        function commit() {
            const name = nameInput.text.trim()
            if (name.length > 0) root.bridge.newProfile(root.target, name)
            visible = false
        }
    }

    // --- içe / dışa aktarma --------------------------------------------------
    Dialogs.FileDialog {
        id: importDialog
        title: "Profil içe aktar"
        nameFilters: [
            "Desteklenen tüm biçimler (*.txt *.json *.sonarprofile)",
            "AutoEQ / EqualizerAPO (*.txt)",
            "EasyEffects (*.json)",
            "Sonar profili (*.sonarprofile)",
            "Tüm dosyalar (*)"
        ]
        onAccepted: root.bridge.importProfile(root.target, selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: exportDialog
        title: "Profili dışa aktar"
        fileMode: Dialogs.FileDialog.SaveFile
        currentFile: "file://" + root.activeName + ".sonarprofile"
        nameFilters: ["Sonar profili (*.sonarprofile)", "AutoEQ (*.txt)"]
        onAccepted: {
            const path = selectedFile.toString()
            root.bridge.exportProfile(root.target, path, path.endsWith(".txt"))
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
