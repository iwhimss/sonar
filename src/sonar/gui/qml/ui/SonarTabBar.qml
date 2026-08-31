import QtQuick

/* Üst sekme şeridi. Aktif sekme dolu blok, diğerleri düz metin. */
Row {
    id: root
    property var tabs: []            // [{ key, label, color }]
    property string current: ""
    signal selected(string key)
    spacing: Theme.s1

    Repeater {
        model: root.tabs
        Rectangle {
            required property var modelData
            readonly property bool active: modelData.key === root.current
            width: text.implicitWidth + Theme.s4 * 2
            height: 30
            color: active ? (modelData.color !== undefined ? modelData.color : Theme.master)
                          : (tabMouse.containsMouse ? Theme.raised : "transparent")
            Text {
                id: text
                anchors.centerIn: parent
                text: parent.modelData.label
                color: parent.active ? "#0E1116" : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.bold: parent.active
                renderType: Text.NativeRendering
            }
            MouseArea {
                id: tabMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.selected(parent.modelData.key)
            }
        }
    }
}
