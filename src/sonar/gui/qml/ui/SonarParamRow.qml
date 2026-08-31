import QtQuick

/* Etiket + yatay slider + sayısal değer. Filtre panellerinin tek yapı taşı. */
Item {
    id: root
    property string label: ""
    property real value: 0
    property real from: 0
    property real to: 1
    property string unit: ""
    property int decimals: 1
    property color accent: Theme.master
    // `enabled` Item'dan miras; yeniden tanımlamak temel sınıfı gölgeliyordu.
    signal moved(real value)
    signal released()

    implicitHeight: 26
    opacity: enabled ? 1.0 : 0.45

    Text {
        id: name
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 92
        text: root.label
        color: Theme.textDim
        elide: Text.ElideRight
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSmall
        renderType: Text.NativeRendering
    }

    SonarSlider {
        id: slider
        anchors.left: name.right
        anchors.right: readout.left
        anchors.rightMargin: Theme.s2
        anchors.verticalCenter: parent.verticalCenter
        accent: root.accent
        value: (root.value - root.from) / Math.max(1e-9, root.to - root.from)
        onMoved: (v) => root.moved(root.from + v * (root.to - root.from))
        onReleased: root.released()
    }

    Rectangle {
        id: readout
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 74
        height: 22
        color: Theme.sunken
        border.width: 1
        border.color: Theme.border
        Text {
            anchors.centerIn: parent
            text: root.value.toFixed(root.decimals) + (root.unit ? " " + root.unit : "")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSmall
            renderType: Text.NativeRendering
        }
    }
}
