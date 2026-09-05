import QtQuick
import QtQuick.Controls as C
import "ui"

/*
 * Karşılama akışı: kısa bir tanıtım ve "Sanal kanalları kur" düğmesi.
 *
 * Kullanıcının isteği (test turu 5): *"uygulama kurulduğunda ilk açıldığında kısa bir
 * tanıtım ekranı gelsin… ardından sanal kanalları kur adında bir buton olsun."*
 *
 * Dört sayfa var ve **ilki dil**: geri kalan her şey ona bağlı. Sayfa 3 sabit metin
 * değil, kurulacakların gerçek listesini `bridge.setupSummary()`'den okuyor — doküman
 * ile makinedeki adların ayrışması (test turu 4'ün OBS karışıklığı) tam bu yüzden oldu.
 */
Item {
    id: root
    objectName: "welcome"
    property var bridge
    //: `true` iken kurulum zaten yapılmış: son sayfa "kur" yerine "kapat" gösterir.
    property bool review: false

    signal finished()

    property int page: 0
    readonly property int pageCount: 4
    property string failure: ""

    onVisibleChanged: if (visible) { page = 0; failure = "" }

    Connections {
        target: root.bridge
        function onProvisionFinished(ok, message) {
            if (ok) { root.failure = ""; root.finished() }
            else root.failure = message
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.s6 * 2, 620)
        height: Math.min(parent.height - Theme.s6 * 2, 460)
        color: Theme.raised
        border.width: 1
        border.color: Theme.border

        Column {
            anchors.fill: parent
            anchors.margins: Theme.s6
            spacing: Theme.s4

            // --- başlık ---------------------------------------------------
            Text {
                text: root.pageTitle()
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitle
                renderType: Text.NativeRendering
            }

            // --- adım göstergesi ------------------------------------------
            Row {
                spacing: Theme.s1
                Repeater {
                    model: root.pageCount
                    Rectangle {
                        required property int index
                        width: 34
                        height: 3
                        color: index <= root.page ? Theme.master : Theme.border
                    }
                }
            }

            // --- gövde ----------------------------------------------------
            Item {
                width: parent.width
                height: parent.height - 34 - 3 - 28 - Theme.s4 * 4

                // 1. dil
                Column {
                    anchors.fill: parent
                    spacing: Theme.s3
                    visible: root.page === 0
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: I18n.t("welcome.language.body")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        renderType: Text.NativeRendering
                    }
                    Repeater {
                        model: I18n.languages
                        SonarButton {
                            required property var modelData
                            width: 220
                            text: modelData.label
                            variant: I18n.language === modelData.code ? "accent" : "normal"
                            onClicked: root.bridge.setLanguage(modelData.code)
                        }
                    }
                }

                // 2. Sonar ne yapar
                Column {
                    anchors.fill: parent
                    spacing: Theme.s3
                    visible: root.page === 1
                    Repeater {
                        model: [
                            { title: I18n.t("welcome.what.channels.title"),
                              body: I18n.t("welcome.what.channels.body") },
                            { title: I18n.t("welcome.what.mixes.title"),
                              body: I18n.t("welcome.what.mixes.body") },
                            { title: I18n.t("welcome.what.profiles.title"),
                              body: I18n.t("welcome.what.profiles.body") }
                        ]
                        Column {
                            required property var modelData
                            width: parent.width
                            spacing: 1
                            SonarSectionLabel { text: modelData.title }
                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: modelData.body
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSmall
                                renderType: Text.NativeRendering
                            }
                        }
                    }
                }

                // 3. ne kurulacak
                Column {
                    anchors.fill: parent
                    spacing: Theme.s2
                    visible: root.page === 2
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: I18n.t("welcome.devices.body")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                    C.ScrollView {
                        width: parent.width
                        height: parent.height - 90
                        clip: true
                        C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff
                        Column {
                            spacing: 1
                            Repeater {
                                model: root.deviceList()
                                Text {
                                    required property var modelData
                                    text: "· " + modelData
                                    color: Theme.textFaint
                                    font.family: "monospace"
                                    font.pixelSize: Theme.fontSmall
                                    renderType: Text.NativeRendering
                                }
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: I18n.t("welcome.devices.obs")
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                }

                // 4. kur
                Column {
                    anchors.fill: parent
                    spacing: Theme.s3
                    visible: root.page === 3
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: root.review ? I18n.t("welcome.install.done")
                                          : I18n.t("welcome.install.body")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        renderType: Text.NativeRendering
                    }
                    SonarButton {
                        width: 260
                        visible: !root.review
                        text: root.bridge && root.bridge.busy
                              ? I18n.t("welcome.install.working")
                              : I18n.t("welcome.install.action")
                        variant: "accent"
                        enabled: !(root.bridge && root.bridge.busy)
                        onClicked: root.bridge.provision()
                    }
                    Text {
                        width: parent.width
                        visible: root.failure.length > 0
                        wrapMode: Text.WordWrap
                        text: "⚠ " + root.failure
                        color: Theme.danger
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                }
            }

            // --- gezinme --------------------------------------------------
            Row {
                width: parent.width
                spacing: Theme.s2
                SonarButton {
                    text: I18n.t("welcome.back")
                    variant: "ghost"
                    enabled: root.page > 0
                    onClicked: root.page -= 1
                }
                SonarButton {
                    text: I18n.t("welcome.next")
                    variant: "accent"
                    visible: root.page < root.pageCount - 1
                    onClicked: root.page += 1
                }
                SonarButton {
                    text: I18n.t("common.close")
                    visible: root.review && root.page === root.pageCount - 1
                    onClicked: root.finished()
                }
            }
        }
    }

    function pageTitle() {
        const titles = [I18n.t("welcome.language.title"), I18n.t("welcome.what.title"),
                        I18n.t("welcome.devices.title"), I18n.t("welcome.install.title")]
        return titles[root.page]
    }

    /* Kurulacakların **gerçek** listesi: sabit metin değil, yapılandırmadan okunuyor.
       Kanal adı değiştirilmişse burada da o ad görünür — kullanıcının OBS'te arayacağı
       ad ile bu liste hep birebir aynı. */
    function deviceList() {
        if (!root.bridge) return []
        const summary = root.bridge.setupSummary()
        const out = []
        for (const bus of summary.buses || []) out.push(bus.device)
        for (const channel of summary.channels || []) out.push(channel.device)
        for (const mic of summary.mics || []) out.push(mic.device)
        return out
    }
}
