import QtQuick
import QtQuick.Controls as C
import QtQuick.Layouts
import "ui"

/*
 * Sol taraftaki master şeridi: cihaz seçicileri ve iki master fader.
 *
 * Cihaz bölümü başlıktaki dişliyle katlanıyor. Dişli eskiden her kanal şeridinde vardı
 * ve FX sayfasını açıyordu — ama üstteki sekmeler zaten onu yapıyor, yani gereksizdi.
 * Kullanıcı isteğiyle buraya, işe yarayan tek yere taşındı (Faz 28).
 *
 * `masters` `bridge.mastersChanged` sinyaline bağlı bir `Property`, yani buradaki
 * okumalar canlı. Cihaz listeleri fonksiyon çağrısı olduğu için `bridge.revision`
 * okuyarak tazeleniyor — QML fonksiyon çağrısına bağlama kurmuyor.
 */
Item {
    id: root
    property var bridge
    implicitWidth: 240

    readonly property var masters: bridge ? bridge.masters : ({})
    readonly property string outputId: {
        const list = bridge ? bridge.outputBusId : ""
        return list || "personal"
    }
    /* Katlanma durumu bilinçli olarak kalıcı değil: bir arayüz tercihi için D-Bus
       gidiş-dönüşü ve şema alanı eklemeye değmiyor. */
    property bool devicesOpen: true

    /* Yayın kurulumunun canlı tanısı. `bridge.revision` okunuyor ki graf değişince
       yeniden değerlendirilsin — fonksiyon çağrısı tek başına bağlama kurmaz. Köprü
       çağrıyı yarım saniye önbellekliyor, yani bu okuma serbest. */
    readonly property var setup: bridge ? (bridge.revision, bridge.streamSetup()) : ({})
    readonly property var setupProblems: setup.problems || []
    readonly property var setupListeners: setup.listeners || []
    readonly property bool setupOk: setupProblems.length === 0
    readonly property string setupSummary: {
        if (setupProblems.length > 0) return "⚠ " + setupProblems[0].message
        if (setupListeners.length === 0) return I18n.t("stream.nobody_listening")
        return setupListeners.length === 1
            ? I18n.tf("stream.one_listener", { name: setupListeners[0].label })
            : I18n.tf("stream.many_listeners", { count: setupListeners.length })
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            color: Theme.raised

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.s3
                anchors.rightMargin: Theme.s1
                spacing: Theme.s2

                SonarIcon { name: "speaker"; color: Theme.master; Layout.alignment: Qt.AlignVCenter }
                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    text: I18n.t("master.title")
                    color: Theme.master
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                    font.letterSpacing: 0.6
                    renderType: Text.NativeRendering
                }
                SonarIconButton {
                    icon: "gear"
                    accent: Theme.master
                    active: root.devicesOpen
                    Layout.alignment: Qt.AlignVCenter
                    onClicked: root.devicesOpen = !root.devicesOpen
                }
            }
        }

        // --- cihazlar (dişliyle katlanır) -----------------------------------
        //
        // Kendi içinde kaydırılıyor: kısa bir pencerede bu bölüm fader'ları eziyordu.
        // Artık fader panelinin payı garanti, cihaz listesi gerekirse kayıyor.
        SonarPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: root.devicesOpen
                ? Math.min(devices.implicitHeight + Theme.s3 * 2, root.height - 34 - 240)
                : 0
            visible: root.devicesOpen && Layout.preferredHeight > 40
            clip: true

            C.ScrollView {
                anchors.fill: parent
                anchors.margins: Theme.s3
                clip: true
                contentWidth: availableWidth
                C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff

            Column {
                id: devices
                width: parent.width
                spacing: Theme.s3

                /* Yayın Miksi'nin fiziksel bir cihazı yok: çıkışı sanal bir kaynak.
                   Burada eskiden sabit bir metin vardı ve kullanıcının makinesinde
                   karşılığı olmayan bir cihaz adı yazıyordu. Artık tanı canlı: adı
                   yapılandırmadan, dinleyicileri graftan okuyoruz. */
                SonarSectionLabel { text: I18n.t("master.stream_mix") }
                /* Şeritte yalnızca **özet** duruyor: 240 px'lik bir kolona kurulum
                   yönergesi, dinleyici listesi ve uyarılar sığmıyordu — bölüm kendi
                   içinde kayıyordu ama kullanıcı kaydırılabildiğini görmüyordu.
                   Ayrıntı `streamDialog`'da. */
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: root.setupSummary
                    color: root.setupOk ? Theme.textDim : Theme.warn
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                }
                SonarButton {
                    width: parent.width
                    text: I18n.t("stream.setup.open")
                    onClicked: streamDialog.open()
                }

                SonarSectionLabel { text: I18n.t("bus.personal") }
                SonarComboBox {
                    width: parent.width
                    accent: Theme.master
                    model: root.deviceList(false)
                    currentValue: (root.masters, root.deviceOf(root.outputId))
                    onActivated: (value) => root.bridge.setBusDevice(root.outputId, value)
                }

                SonarSectionLabel { text: I18n.t("master.microphone") }
                SonarComboBox {
                    width: parent.width
                    accent: Theme.master
                    model: root.deviceList(true)
                    currentValue: (root.masters, root.deviceOf("mic"))
                    onActivated: (value) => root.bridge.setMicDevice("mic", value)
                }

            }
            }
        }

        SonarPanel {
            id: faders
            Layout.fillWidth: true
            Layout.fillHeight: true
            //: Kanal şeritleriyle aynı sıkışma davranışı; daha da darsa dişliyle
            //: cihaz bölümü katlanabiliyor.
            Layout.minimumHeight: 140
            Row {
                anchors.centerIn: parent
                spacing: Theme.s6
                Repeater {
                    model: [
                        { key: root.outputId, icon: "headset", label: I18n.t("master.headphones") },
                        { key: "stream", icon: "cast", label: I18n.t("master.stream") }
                    ]
                    Column {
                        id: busColumn
                        required property var modelData
                        spacing: Theme.s1

                        readonly property real vol: (root.masters, root.volumeOf(modelData.key))
                        readonly property bool mute: (root.masters, root.mutedOf(modelData.key))

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: busColumn.modelData.label
                            color: Theme.textFaint
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                        SonarIcon {
                            name: busColumn.modelData.icon
                            color: busColumn.mute ? Theme.textFaint : Theme.master
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        SonarValueField {
                            anchors.horizontalCenter: parent.horizontalCenter
                            value: busColumn.vol
                            maximum: Theme.maxVolume
                            accent: Theme.master
                            onEdited: (v) => root.bridge.setMasterVolume(busColumn.modelData.key, v)
                        }
                        SonarFader {
                            // Sütunun genişliğini `SonarValueField` (58 px) belirliyor;
                            // ortalanmazsa fader sola yaslanıyor ve altındaki mute
                            // düğmesiyle hizasız kalıyordu (kanal şeridindeki hatanın
                            // aynısı, test turu 5).
                            anchors.horizontalCenter: parent.horizontalCenter
                            height: Math.max(60, faders.height - 130)
                            maximum: Theme.maxVolume
                            value: busColumn.vol
                            muted: busColumn.mute
                            accent: Theme.master
                            onMoved: (v) => root.bridge.setMasterVolume(busColumn.modelData.key, v)
                        }
                        SonarIconButton {
                            icon: "mute"
                            active: busColumn.mute
                            accent: Theme.danger
                            anchors.horizontalCenter: parent.horizontalCenter
                            onClicked: root.bridge.setMasterMute(busColumn.modelData.key,
                                                                 !busColumn.mute)
                        }
                    }
                }
            }
        }

        /* --- miksi yakalayan uygulamalar ---------------------------------
         *
         * OBS'in "Masaüstü Sesi", `cava` gibi görselleştiriciler ve ekran kaydediciler
         * bir kanalda değil bir **bus**'ta duruyorlar: yayın ya da kişisel miksin
         * monitörünü dinliyorlar. Köprü satırları baştan beri üretiyordu
         * (`bridge.stream_rows`, bus kimliğine eşleyerek) ama çizen kimse yoktu; ekranda
         * hiçbir yere düşmüyorlardı ve kullanıcı dört tur boyunca "OBS görünmüyor" dedi.
         *
         * Kanal kutucuklarının aksine bunlar **sürüklenemez**: bir bus'ı dinliyorlar,
         * bir kanala taşınmalarının anlamı yok.
         */
        SonarPanel {
            Layout.fillWidth: true
            // `fillHeight` **değil**: fader paneli de doluyor ve ikisi alanı paylaşınca
            // bu panel sıfır yüksekliğe düşüp görünmez kalıyordu.
            Layout.preferredHeight: Math.min(24 + root.captures.length * 24, 96)
            visible: root.captures.length > 0

            Column {
                anchors.fill: parent
                anchors.margins: Theme.s2
                spacing: Theme.s1

                SonarSectionLabel {
                    width: parent.width
                    elide: Text.ElideRight
                    text: I18n.t("master.captures") + "  (" + root.captures.length + ")"
                }

                ListView {
                    id: captureList
                    width: parent.width
                    height: Math.max(0, parent.height - 16)
                    clip: true
                    spacing: 2
                    model: root.captures
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: Rectangle {
                        required property var modelData
                        width: captureList.width
                        height: 22
                        color: Theme.raised
                        border.width: 1
                        border.color: Theme.border

                        SonarIcon {
                            id: captureIcon
                            anchors.left: parent.left
                            anchors.leftMargin: Theme.s1
                            anchors.verticalCenter: parent.verticalCenter
                            name: "record"
                            color: Theme.master
                            font.pixelSize: Theme.fontSmall
                        }
                        Text {
                            anchors.left: captureIcon.right
                            anchors.leftMargin: Theme.s1
                            anchors.right: parent.right
                            anchors.rightMargin: Theme.s1
                            anchors.verticalCenter: parent.verticalCenter
                            // Hangi miksi dinlediği yazıyor: OBS'in yanlış olanı
                            // dinlemesi kullanıcının en sık düştüğü hata.
                            text: modelData.label + " — " + root.busLabel(modelData.channel)
                            color: Theme.textDim
                            elide: Text.ElideRight
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                    }
                }
            }
        }
    }

    /* Yayın kurulumu, tam hâli. Şeritte yalnızca özeti duruyor; buradaki her satır
       graftan okunuyor, sabit metin yok. */
    SonarDialog {
        id: streamDialog
        objectName: "streamDialog"
        title: I18n.t("stream.setup.title")
        preferredWidth: 460

        Column {
            width: parent.width
            spacing: Theme.s3

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("stream.setup.step1")
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Row {
                width: parent.width
                spacing: Theme.s1
                Rectangle {
                    width: parent.width - 26 - Theme.s1
                    height: 28
                    color: Theme.sunken
                    border.width: 1
                    border.color: Theme.border
                    TextInput {
                        id: deviceName
                        anchors.fill: parent
                        anchors.leftMargin: Theme.s2
                        anchors.rightMargin: Theme.s2
                        verticalAlignment: Text.AlignVCenter
                        // Salt okunur ama seçilebilir: kullanıcı adı elle de kopyalayabilsin.
                        readOnly: true
                        selectByMouse: true
                        text: root.setup.device || "Sonar Stream Mix"
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        renderType: Text.NativeRendering
                    }
                }
                SonarIconButton {
                    icon: "copy"
                    accent: Theme.master
                    onClicked: { deviceName.selectAll(); deviceName.copy(); deviceName.deselect() }
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("stream.setup.step2")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            SonarSectionLabel { width: parent.width; text: I18n.t("stream.setup.listeners") }
            Repeater {
                model: root.setupListeners
                Text {
                    required property var modelData
                    width: streamDialog.bodyWidth
                    wrapMode: Text.WordWrap
                    text: "· " + modelData.label + " — "
                        + (modelData.via === "monitor" ? "Masaüstü Sesi" : "alternatif giriş")
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                }
            }
            Text {
                width: parent.width
                visible: root.setupListeners.length === 0
                text: "· " + I18n.t("stream.nobody_listening")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            /* Mikrofonun yayın gönderisi. Bu anahtar modelde baştan beri vardı ama
               hiçbir arayüzü yoktu; kullanıcı "yayında mikrofonum duyulmuyor" ve
               "mikrofonun yayın fader'ı hiçbir şey yapmıyor" diye bildirdi. */
            SonarSectionLabel { width: parent.width; text: I18n.t("stream.setup.mic_section") }
            Repeater {
                model: root.setup.mics || []
                Row {
                    required property var modelData
                    width: streamDialog.bodyWidth
                    spacing: Theme.s2
                    SonarIconButton {
                        icon: "cast"
                        accent: Theme.master
                        active: modelData.in_stream === true
                        onClicked: root.bridge.setMicStreamSend(modelData.id,
                                                                modelData.in_stream !== true)
                    }
                    Text {
                        width: parent.width - 26 - Theme.s2
                        anchors.verticalCenter: parent.verticalCenter
                        wrapMode: Text.WordWrap
                        text: modelData.name + " — " + (modelData.in_stream
                            ? I18n.t("stream.setup.mic_on") : I18n.t("stream.setup.mic_off"))
                        color: modelData.in_stream ? Theme.textDim : Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("stream.setup.mic_note")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }

            Repeater {
                model: root.setupProblems
                Text {
                    required property var modelData
                    width: streamDialog.bodyWidth
                    wrapMode: Text.WordWrap
                    text: "⚠ " + modelData.message
                    color: Theme.warn
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                }
            }
        }
    }

    /* Bus'ları dinleyen akışlar. `bridge.revision` okunuyor ki liste canlı kalsın. */
    readonly property var captures: {
        if (!bridge) return []
        const _ = bridge.revision
        return bridge.streamsFor("stream").concat(bridge.streamsFor(root.outputId))
    }

    function busLabel(id) {
        // Gömülü adların çevirisi tek yerde: köprü, kullanıcı yeniden adlandırmışsa
        // onun adını döndürüyor.
        return root.bridge ? root.bridge.busLabel(id) : id
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
}
