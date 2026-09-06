import QtQuick
import "ui"

/*
 * Genel ayarlar. Buraya kadar arayüzde **hiç** genel ayar penceresi yoktu: dil bir yana,
 * `take_over_default_sink` ve `chatmix_invert` yalnızca `sonar-cli`'den erişilebiliyordu
 * (ikincisi Faz 35'te eklenmişti ve hiçbir düğmesi yoktu).
 */
SonarDialog {
    id: root
    objectName: "settingsDialog"
    title: I18n.t("settings.title")
    preferredWidth: 460

    property var bridge

    //: Karşılama akışını yeniden açma isteği — `Main.qml` yakalıyor.
    signal welcomeRequested()
    signal uninstallRequested()

    function open() { visible = true }

    Column {
        width: parent.width
        spacing: Theme.s4

        // --- dil ------------------------------------------------------------
        Column {
            width: parent.width
            spacing: Theme.s1
            SonarSectionLabel { text: I18n.t("settings.language") }
            SonarComboBox {
                width: parent.width
                accent: Theme.master
                model: root.languageOptions()
                currentValue: I18n.language
                onActivated: (value) => root.bridge.setLanguage(value)
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: I18n.t("settings.language.hint")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
        }

        // --- anahtarlar -----------------------------------------------------
        Column {
            width: parent.width
            spacing: Theme.s3
            SonarSectionLabel { text: I18n.t("settings.behaviour") }

            SonarCheck {
                width: parent.width
                checked: root.bridge ? root.bridge.takeOverDefaultSink : false
                text: I18n.t("settings.take_over")
                hint: I18n.t("settings.take_over.hint")
                onToggled: (value) => root.bridge.setTakeOverDefaultSink(value)
            }
            SonarCheck {
                width: parent.width
                checked: root.bridge ? root.bridge.chatmixInvert : false
                text: I18n.t("settings.chatmix_invert")
                hint: I18n.t("settings.chatmix_invert.hint")
                onToggled: (value) => root.bridge.setChatMixInvert(value)
            }
        }

        // --- oturum açılışı -------------------------------------------------
        Column {
            width: parent.width
            spacing: Theme.s3
            SonarSectionLabel { text: I18n.t("settings.autostart") }

            SonarCheck {
                width: parent.width
                enabled: root.bridge ? root.bridge.autostartAvailable : false
                opacity: enabled ? 1.0 : 0.45
                checked: root.bridge ? root.bridge.autostartDaemon : false
                text: I18n.t("settings.autostart.daemon")
                hint: I18n.t("settings.autostart.daemon.hint")
                onToggled: (value) => root.bridge.setAutostart(
                    value, root.bridge.autostartGui)
            }
            SonarCheck {
                width: parent.width
                enabled: root.bridge ? root.bridge.autostartAvailable : false
                opacity: enabled ? 1.0 : 0.45
                checked: root.bridge ? root.bridge.autostartGui : false
                text: I18n.t("settings.autostart.gui")
                hint: I18n.t("settings.autostart.gui.hint")
                onToggled: (value) => root.bridge.setAutostart(
                    root.bridge.autostartDaemon, value)
            }
            Text {
                width: parent.width
                visible: root.bridge ? !root.bridge.autostartAvailable : false
                wrapMode: Text.WordWrap
                text: I18n.t("settings.autostart.unavailable")
                color: Theme.warn
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
        }

        // --- kurulum --------------------------------------------------------
        Column {
            width: parent.width
            spacing: Theme.s2
            SonarSectionLabel { text: I18n.t("settings.setup") }
            Row {
                spacing: Theme.s2
                SonarButton {
                    text: I18n.t("settings.show_welcome")
                    onClicked: { root.close(); root.welcomeRequested() }
                }
                SonarButton {
                    text: I18n.t("settings.uninstall")
                    variant: "ghost"
                    onClicked: { root.close(); root.uninstallRequested() }
                }
            }
        }

        Row {
            spacing: Theme.s2
            SonarButton { text: I18n.t("common.close"); onClicked: root.close() }
        }
    }

    function languageOptions() {
        const out = []
        for (const entry of I18n.languages)
            out.push({ value: entry.code, label: entry.label })
        return out
    }
}
