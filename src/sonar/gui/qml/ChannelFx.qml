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
                ? { value: p, label: root.bridge.presetLabel(p), builtin: false }
                : { value: p.name, label: root.bridge.presetLabel(p.name),
                    builtin: p.builtin === true }
        })
        const out = []
        if (root.favorites.length > 0) {
            out.push({ value: "", label: I18n.t("profile.favorites"), header: true })
            for (const name of root.favorites) {
                const hit = all.find(function (o) { return o.value === name })
                if (hit) out.push({ value: hit.value, label: "★ " + hit.label })
            }
            out.push({ value: "", label: I18n.t("profile.all"), header: true })
        }
        for (const option of all)
            out.push({ value: option.value, label: (option.builtin ? "🔒 " : "") + option.label })
        return out
    }

    /* Sayfa kendi yüksekliğini bildiriyor; dışarıdaki `ScrollView` gerisini hallediyor.
       Eskiden `anchors.fill: parent` ile pencereye sıkıştırılıyordu ve panel içerikleri
       kutularının dışına taşıyordu (test turu 3). */
    implicitHeight: page.implicitHeight

    Column {
        id: page
        width: parent.width
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
                        text: "＋ " + I18n.t("profile.new")
                        variant: "accent"
                        accent: root.accent
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: newDialog.open()
                    }
                    SonarButton {
                        text: I18n.t("common.reset")
                        variant: "ghost"
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: root.bridge.resetProfile(root.target)
                    }
                    SonarButton {
                        text: I18n.t("common.delete")
                        variant: "ghost"
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: root.bridge.deleteProfile(root.target, root.activeName)
                    }
                    SonarButton {
                        text: I18n.t("profile.import")
                        variant: "ghost"
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: importDialog.open()
                    }
                    SonarButton {
                        text: I18n.t("profile.export")
                        variant: "ghost"
                        anchors.verticalCenter: parent.verticalCenter
                        onClicked: exportDialog.open()
                    }

                    /* Değişiklikler otomatik kaydediliyor; kullanıcı "kaydet" aramasın.
                       Dar pencerede satıra sığmıyorsa tamamen gizleniyor — yarım
                       kırpılmış bir cümle bilgi vermiyor. */
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: x + implicitWidth <= parent.width
                        text: I18n.t("profile.autosave")
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
                        text: I18n.t("profile.no_favorites")
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

        // --- efekt zinciri -------------------------------------------------
        //
        // Paneller **alt alta**, sinyal sırasıyla (kullanıcının isteği, test turu 6).
        // Eskiden `Flow` içinde yan yana sarıyorlardı; zincirin sırası görünmüyordu ve
        // sıra artık kullanıcının kararı olduğu için yanıltıcı olurdu.
        Column {
            id: dynamics
            width: parent.width
            spacing: Theme.s2

            readonly property real panelWidth: width

            Repeater {
                model: root.effects
                Item {
                    id: effectItem
                    required property var modelData
                    required property int index
                    width: dynamics.panelWidth
                    height: eqPanel.visible ? eqPanel.height : panel.height

                    /* Ekolayzer zincirin bir üyesi ama gövdesi eğri editörü. Ayrı bir
                       panelde dursaydı listede ikinci kez görünür ve sırası anlamsız
                       kalırdı — sinyal listedeki sırayla akıyor. */
                    EqPanel {
                        id: eqPanel
                        visible: effectItem.modelData.kind === "eq"
                        width: parent.width
                        //: Eğrinin okunabilir kaldığı en kısa boy.
                        height: visible ? 400 : 0
                        bridge: root.bridge
                        target: root.target
                        accent: root.accent
                        profile: root.profile
                        movable: true
                        removable: true
                        onRemoveRequested: root.bridge.removeEffect(
                            root.target, effectItem.modelData.slot)
                    }

                    SonarFilterPanel {
                        id: panel
                        visible: effectItem.modelData.kind !== "eq"
                        width: parent.width
                        height: visible ? body.implicitHeight + 26 + Theme.s3 * 2 : 0
                        title: I18n.t("effect." + effectItem.modelData.kind)
                        accent: root.accent
                        active: effectItem.modelData.enabled === true
                        movable: true
                        removable: true
                        note: (root.isMic && effectItem.modelData.kind === "gate"
                               && root.stageOn("df")) ? I18n.t("fx.gate.disabled_by_df") : ""
                        onToggled: (v) => root.bridge.setFilterEnabled(
                            root.target, effectItem.modelData.slot, v)
                        onRemoveRequested: root.bridge.removeEffect(
                            root.target, effectItem.modelData.slot)

                        Column {
                            id: body
                            anchors.fill: parent
                            spacing: 2

                            Repeater {
                                model: effectItem.modelData.params
                                SonarParamRow {
                                    required property var modelData
                                    width: parent.width
                                    label: I18n.t(modelData.label)
                                    from: modelData.from
                                    to: modelData.to
                                    unit: modelData.unit
                                    decimals: modelData.digits
                                    accent: root.accent
                                    enabled: effectItem.modelData.enabled === true
                                    value: root.paramOf(effectItem.modelData.slot,
                                                        modelData.name, modelData.fallback)
                                    onMoved: (v) => root.bridge.setFilterParam(
                                        root.target, effectItem.modelData.slot,
                                        modelData.name, v)
                                }
                            }

                            Text {
                                visible: effectItem.modelData.hint !== ""
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: effectItem.modelData.hint !== ""
                                      ? I18n.t(effectItem.modelData.hint) : ""
                                color: Theme.textFaint
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSmall
                                renderType: Text.NativeRendering
                            }
                        }
                    }

                    /* Sıralama: tutamağı sürükle, panel bırakıldığı yere geçsin.
                       Favori şeridindeki desenin aynısı — orada da `DropArea` komşunun
                       indeksini okuyup listeyi yeniden diziyor. */
                    Drag.active: dragArea.drag.active
                    Drag.hotSpot.x: 10
                    Drag.hotSpot.y: 8
                    property int dragIndex: effectItem.index

                    MouseArea {
                        id: dragArea
                        x: 0
                        y: 0
                        width: 24
                        height: 24
                        cursorShape: Qt.SizeVerCursor
                        drag.target: effectItem
                        drag.axis: Drag.YAxis
                        drag.threshold: 6
                        onReleased: { effectItem.Drag.drop(); effectItem.y = 0 }
                    }

                    DropArea {
                        anchors.fill: parent
                        onEntered: (event) => {
                            const from = event.source.dragIndex
                            if (from === effectItem.index) return
                            root.bridge.moveEffect(root.target,
                                                   root.effects[from].slot, effectItem.index)
                        }
                    }
                }
            }

            SonarButton {
                text: "＋ " + I18n.t("fx.add_effect")
                variant: "accent"
                accent: root.accent
                onClicked: addEffectDialog.open()
            }

            Text {
                visible: root.effects.length === 0
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("fx.empty_chain")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            /* Smart Volume bir DSP aşaması değil, daemon tarafında bir zarf takipçisi —
               bu yüzden `SonarFilterPanel`'i elle kuruluyor. Şema 4'ten beri profilin
               içinde: tetikleyici, profili taşıyan kanalın kendisi. */
            SonarFilterPanel {
                width: dynamics.panelWidth
                height: smartBody.implicitHeight + 26 + Theme.s3 * 2
                visible: !root.isMic
                title: I18n.t("fx.stage.smart")
                accent: root.accent
                active: root.duckOn
                onToggled: (v) => root.bridge.setDucking(root.target, { "enabled": v })
                Column {
                    id: smartBody
                    anchors.fill: parent
                    spacing: 2
                    Repeater {
                        model: root.duckParams
                        SonarParamRow {
                            required property var modelData
                            width: parent.width
                            label: modelData.label
                            from: modelData.from; to: modelData.to
                            unit: modelData.unit
                            decimals: modelData.digits !== undefined ? modelData.digits : 1
                            accent: root.accent
                            enabled: root.duckOn
                            value: root.duckValue(modelData.key, modelData.fallback)
                            onMoved: (v) => {
                                const patch = {}
                                patch[modelData.key] = v
                                root.bridge.setDucking(root.target, patch)
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: I18n.tf("fx.smart.hint", { name: root.channelName })
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
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
            SonarSectionLabel { text: I18n.t("profile.new") }
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
                text: I18n.t("profile.new.hint")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Row {
                spacing: Theme.s2
                SonarButton { text: I18n.t("common.create"); variant: "accent"; accent: root.accent
                              onClicked: newDialog.commit() }
                SonarButton { text: I18n.t("common.cancel"); onClicked: newDialog.visible = false }
            }
        }

        /* Pencere yalnızca profil **gerçekten** oluşturulunca kapanıyor. Aynı ad zaten
           varsa daemon reddediyor ve mesaj bildirim şeridine düşüyor; pencere açık
           kalırsa kullanıcı adı düzeltebiliyor. Eskiden her hâlükârda kapanıyor ve
           hiçbir şey olmuyordu — test turu 7'nin şikâyeti buydu. */
        function commit() {
            const name = nameInput.text.trim()
            if (name.length === 0) return
            if (root.bridge.newProfile(root.target, name)) {
                nameInput.text = ""
                visible = false
            } else {
                nameInput.forceActiveFocus()
                nameInput.selectAll()
            }
        }
    }

    /* Efekt ekleme penceresi. Kategorilere ayrılmış; kurulu olmayan eklentiler ve bu
       hedefte anlamsız olanlar (mikrofonda Uzamsal Ses, oynatmada gürültü engelleme)
       listede hiç görünmüyor — kullanıcıya ekleyemeyeceği bir şeyi göstermek onu graf
       kurulamadığında yalnız bırakır. */
    SonarDialog {
        id: addEffectDialog
        objectName: "addEffectDialog"
        title: I18n.t("fx.add_effect")
        accent: root.accent
        preferredWidth: 460

        property var kinds: []

        function open() {
            kinds = root.bridge ? root.bridge.effectKinds(root.target) : []
            visible = true
        }

        Column {
            width: parent.width
            spacing: Theme.s3

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("fx.add_effect.note")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            Repeater {
                model: ["dynamics", "tone", "space", "utility"]
                Column {
                    required property var modelData
                    width: addEffectDialog.bodyWidth
                    spacing: Theme.s1
                    visible: addEffectDialog.inCategory(modelData).length > 0

                    SonarSectionLabel { text: I18n.t("effect.category." + modelData) }

                    Flow {
                        width: parent.width
                        spacing: Theme.s1
                        Repeater {
                            model: addEffectDialog.inCategory(modelData)
                            SonarButton {
                                required property var modelData
                                text: I18n.t("effect." + modelData.kind)
                                onClicked: {
                                    root.bridge.addEffect(root.target, modelData.kind)
                                    addEffectDialog.close()
                                }
                            }
                        }
                    }
                }
            }

            SonarButton { text: I18n.t("common.close"); onClicked: addEffectDialog.close() }
        }

        function inCategory(category) {
            /* Zincirde zaten bir ekolayzer varsa ikincisi eklenemiyor (band modeli ve
               eğri profilde tek); listede göstermek "tıkladım, hata verdi" demekti. */
            const hasEq = root.effects.some(function (e) { return e.kind === "eq" })
            return (kinds || []).filter(function (k) {
                return k.category === category && !(k.kind === "eq" && hasEq)
            })
        }
    }

    // --- içe / dışa aktarma --------------------------------------------------
    /* İki pencere de **aynı** klasörde açılıyor ve son kullanılan klasör hatırlanıyor.
       Eskiden dışa aktarma `currentFile`'a geçersiz bir URL veriyordu
       (`"file://" + ad` — URL kurallarına göre bu bir *host* adı, yol boş), Qt onu yok
       sayıyor ve her pencere kendi varsayılanında açılıyordu: kullanıcı belgelerine
       kaydedip ev dizininde arıyordu (test turu 7). */
    Dialogs.FileDialog {
        id: importDialog
        title: I18n.t("profile.import.title")
        currentFolder: root.bridge ? root.bridge.profileFolder : ""
        nameFilters: [
            I18n.t("profile.filter.sonar") + " (*.sonarprofile)",
            I18n.t("profile.filter.all_supported") + " (*.sonarprofile *.txt *.json)",
            "AutoEQ / EqualizerAPO (*.txt)",
            "EasyEffects (*.json)",
            I18n.t("profile.filter.any") + " (*)"
        ]
        onAccepted: {
            root.bridge.rememberProfileFolder(currentFolder.toString())
            root.bridge.importProfile(root.target, selectedFile.toString())
        }
    }

    Dialogs.FileDialog {
        id: exportDialog
        title: I18n.t("profile.export.title")
        fileMode: Dialogs.FileDialog.SaveFile
        currentFolder: root.bridge ? root.bridge.profileFolder : ""
        //: Yalnızca dosya **adı**; klasörü `currentFolder` veriyor.
        currentFile: root.activeName + ".sonarprofile"
        nameFilters: [I18n.t("profile.filter.sonar") + " (*.sonarprofile)", "AutoEQ (*.txt)"]
        onAccepted: {
            const path = selectedFile.toString()
            root.bridge.rememberProfileFolder(currentFolder.toString())
            root.bridge.exportProfile(root.target, path, path.endsWith(".txt"))
        }
    }

    // --- parametre tanımları -------------------------------------------------
    /* Spatial Audio (crossfeed): kulaklar arası sızıntı. Ölçüldü — kapalıyken çıkış
       girişe bit-eş, açıkken karşı kulakta -6 dB kopya ve 0.40 ms gecikme. */
    readonly property var spatialParams: [
        { stage:"spatial", key:"immersion", label:I18n.t("param.immersion"), from:0, to:100, unit:"", fallback:50, digits:0 },
        { stage:"spatial", key:"distance",  label:I18n.t("param.distance"),         from:0, to:100, unit:"", fallback:40, digits:0 }
    ]
    readonly property var boostParams: [
        { stage:"boost", key:"gain_db", label:I18n.t("param.gain"), from:0, to:12, unit:"dB", fallback:6 }
    ]
    /* Smart Volume ayarları profilde duruyor (şema 4). */
    readonly property var ducking: bridge ? (tick, bridge.ducking(target)) : ({})
    readonly property bool duckOn: ducking.enabled === true
    readonly property string channelName: channel.name !== undefined ? channel.name : target
    readonly property var duckParams: [
        { key:"reduction_db", label:I18n.t("param.reduction"),  from:-40, to:0,    unit:"dB", fallback:-12 },
        { key:"threshold_db", label:I18n.t("param.threshold"), from:-80, to:0,    unit:"dB", fallback:-40 },
        { key:"attack_ms",    label:I18n.t("param.attack"), from:0,   to:500,  unit:"ms", fallback:80 },
        { key:"hold_ms",      label:I18n.t("param.hold"),      from:0,   to:2000, unit:"ms", fallback:400 },
        { key:"release_ms",   label:I18n.t("param.release"), from:20,  to:3000, unit:"ms", fallback:800 }
    ]

    function duckValue(key, fallback) {
        void root.tick
        const value = ducking[key]
        return value !== undefined ? value : fallback
    }

    /* Zincirdeki efektler — **daemon'dan**, sıralarıyla birlikte.
     *
     * Şema 6'ya kadar bu liste burada elle yazılıydı: her panelin başlığı, parametreleri,
     * aralıkları ve birimleri QML'de duruyordu ve yeni bir efekt eklemek QML yazmayı
     * gerektiriyordu. Artık `core/dsp/effects.py` tek kaynak; panel de parametre satırı
     * da o meta veriden çiziliyor.
     */
    readonly property var effects: bridge ? (tick, bridge.effectsOf(target)) : []

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
