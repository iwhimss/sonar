import QtQuick

/*
 * Bir DSP aşamasının kutusu: başlık + açma anahtarı + içerik.
 * Kapalı panel soluk ama okunabilir kalır (SteelSeries davranışı).
 */
SonarPanel {
    id: root
    property string title: ""
    property bool active: false
    property color accent: Theme.master
    property string note: ""             // "AI aktifken devre dışı" gibi
    default property alias body: holder.data
    signal toggled(bool value)

    Column {
        anchors.fill: parent
        anchors.margins: Theme.s3
        spacing: Theme.s2

        Row {
            spacing: Theme.s2
            width: parent.width

            // Dikdörtgen anahtar — yuvarlak "pill" değil.
            Rectangle {
                width: 30; height: 16
                anchors.verticalCenter: parent.verticalCenter
                color: root.active ? root.accent : Theme.sunken
                border.width: 1
                border.color: root.active ? root.accent : Theme.border
                Rectangle {
                    width: 12; height: 12
                    x: root.active ? 16 : 2
                    y: 2
                    color: root.active ? "#0E1116" : Theme.textFaint
                    Behavior on x { NumberAnimation { duration: 90 } }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggled(!root.active)
                }
            }

            SonarSectionLabel {
                text: root.title
                color: root.active ? root.accent : Theme.textDim
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                visible: root.note.length > 0
                text: root.note
                color: Theme.warn
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Item {
            id: holder
            width: parent.width
            height: parent.height - 26
            opacity: root.active ? 1.0 : 0.45
        }
    }
}
