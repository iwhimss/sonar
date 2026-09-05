import QtQuick
import "ui"

/*
 * Kaldırıcı. Kullanıcının isteği: *"uygulama sanki hiç kurulmamış gibi kanalları
 * temizlesin."*
 *
 * Varsayılan olarak yalnızca **kanallar** gidiyor; ayarlar ve profiller diskte kalıyor
 * ki geri dönmek tek tık olsun. Silmek isteyene kutucuk var ve kapalı geliyor —
 * geri alınamayan bir işlem kendiliğinden seçili olmamalı.
 *
 * udev kuralı, systemd unit'i ve paketin kendisi root'a ait; daemon onlara dokunmuyor,
 * kaldırma bitince komutları **yazıyor**.
 */
SonarDialog {
    id: root
    objectName: "uninstallDialog"
    title: I18n.t("uninstall.title")
    accent: Theme.danger
    preferredWidth: 480

    property var bridge
    property bool purge: false
    property bool done: false

    function open() { purge = false; done = false; visible = true }

    Column {
        width: parent.width
        spacing: Theme.s3

        // --- onay ------------------------------------------------------------
        Column {
            width: parent.width
            spacing: Theme.s3
            visible: !root.done

            Repeater {
                model: [I18n.t("uninstall.effect.channels"),
                        I18n.t("uninstall.effect.default_device"),
                        I18n.t("uninstall.effect.apps")]
                Text {
                    required property var modelData
                    width: root.bodyWidth
                    wrapMode: Text.WordWrap
                    text: "· " + modelData
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                }
            }

            SonarCheck {
                width: parent.width
                checked: root.purge
                text: I18n.t("uninstall.purge")
                hint: I18n.t("uninstall.purge.hint")
                accent: Theme.danger
                onToggled: (value) => root.purge = value
            }

            Row {
                spacing: Theme.s2
                SonarButton { text: I18n.t("common.cancel"); onClicked: root.close() }
                SonarButton {
                    text: root.bridge && root.bridge.busy
                          ? I18n.t("uninstall.working") : I18n.t("uninstall.confirm")
                    variant: "danger"
                    enabled: !(root.bridge && root.bridge.busy)
                    onClicked: { root.done = true; root.bridge.deprovision(root.purge) }
                }
            }
        }

        // --- kalan işler -----------------------------------------------------
        Column {
            width: parent.width
            spacing: Theme.s2
            visible: root.done

            Text {
                width: root.bodyWidth
                wrapMode: Text.WordWrap
                text: I18n.t("uninstall.manual")
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
            }
            Repeater {
                model: root.bridge ? root.bridge.manualSteps() : []
                Column {
                    required property var modelData
                    width: root.bodyWidth
                    spacing: 1
                    Text {
                        text: modelData.note
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                        renderType: Text.NativeRendering
                    }
                    Rectangle {
                        width: parent.width
                        height: 24
                        color: Theme.sunken
                        border.width: 1
                        border.color: Theme.border
                        TextInput {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.s2
                            verticalAlignment: Text.AlignVCenter
                            readOnly: true
                            selectByMouse: true
                            text: modelData.command
                            color: Theme.text
                            font.family: "monospace"
                            font.pixelSize: Theme.fontSmall
                            renderType: Text.NativeRendering
                        }
                    }
                }
            }
            SonarButton { text: I18n.t("common.close"); onClicked: root.close() }
        }
    }
}
