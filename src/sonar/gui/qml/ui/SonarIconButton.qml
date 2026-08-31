import QtQuick

/* Kare, köşesiz ikon düğmesi. `active` durumu aksan rengiyle gösterilir. */
Rectangle {
    id: root
    property string icon: "speaker"
    property bool active: false
    property color accent: Theme.master
    property string tooltip: ""
    signal clicked()

    implicitWidth: 26
    implicitHeight: 26
    color: active ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                  : (mouse.containsMouse ? Theme.raised : "transparent")
    border.width: 1
    border.color: active ? accent : (mouse.containsMouse ? Theme.borderStrong : Theme.border)

    SonarIcon {
        anchors.centerIn: parent
        name: root.icon
        color: root.active ? root.accent : Theme.textDim
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
