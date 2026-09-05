import QtQuick

/*
 * Köşesiz onay kutusu. Ayarlar penceresindeki anahtarlar için.
 *
 * `SonarIconButton`ın `active` durumu bir *düğme*yi işaretliyor; burada işaretlenen bir
 * **ayar** ve yanında açıklaması var, o yüzden ayrı bir bileşen. Tasarım dili aynı:
 * yuvarlatma yok, çerçeve + dolgu.
 */
Item {
    id: root
    property bool checked: false
    property string text: ""
    property string hint: ""
    property color accent: Theme.master

    signal toggled(bool value)

    implicitHeight: body.implicitHeight
    implicitWidth: 320

    Rectangle {
        id: box
        width: 14
        height: 14
        y: 2
        color: root.checked ? root.accent : Theme.sunken
        border.width: 1
        border.color: root.checked ? root.accent : Theme.borderStrong

        Text {
            anchors.centerIn: parent
            visible: root.checked
            text: "✓"
            color: "#0E1116"
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSmall
            renderType: Text.NativeRendering
        }
    }

    Column {
        id: body
        anchors.left: box.right
        anchors.leftMargin: Theme.s2
        anchors.right: parent.right
        spacing: 1

        Text {
            width: parent.width
            text: root.text
            wrapMode: Text.WordWrap
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            renderType: Text.NativeRendering
        }
        Text {
            width: parent.width
            // `height: visible ? implicitHeight : 0` yazmayın: sarılan bir `Text`in
            // yüksekliğini kendi `implicitHeight`ine bağlamak Qt'de bağlama döngüsü
            // üretiyor (ölçüldü). `Column` görünmeyen çocuğu zaten atlıyor.
            visible: root.hint.length > 0
            text: root.hint
            wrapMode: Text.WordWrap
            color: Theme.textFaint
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSmall
            renderType: Text.NativeRendering
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
