import QtQuick

/* Düz, köşesiz düğme. variant: "normal" | "accent" | "danger" | "ghost" */
Rectangle {
    id: root
    property string text: ""
    property string variant: "normal"
    // `enabled` Item'dan miras alınıyor; yeniden tanımlamak temel sınıfı gölgeliyordu.
    property color accent: Theme.master
    signal clicked()

    implicitWidth: label.implicitWidth + Theme.s4 * 2
    implicitHeight: 28
    color: {
        if (!enabled) return Theme.surface
        if (variant === "ghost") return mouse.containsMouse ? Theme.raised : "transparent"
        if (variant === "accent") return mouse.pressed ? Qt.darker(accent, 1.3) : accent
        if (variant === "danger") return mouse.pressed ? Qt.darker(Theme.danger, 1.3) : Theme.danger
        return mouse.containsMouse ? Theme.raised : Theme.surface
    }
    border.width: 1
    border.color: variant === "normal" || variant === "ghost"
                  ? (mouse.containsMouse ? Theme.borderStrong : Theme.border)
                  : "transparent"

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: !root.enabled ? Theme.textFaint
             : (root.variant === "accent" || root.variant === "danger") ? "#0E1116" : Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        renderType: Text.NativeRendering
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
