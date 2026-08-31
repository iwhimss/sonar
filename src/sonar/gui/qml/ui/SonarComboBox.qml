import QtQuick

/*
 * Köşesiz açılır liste. QtQuick.Controls'un ComboBox'ı stil olarak yuvarlatma ve gölge
 * getirdiği için elle yazıldı — tasarım kuralı (radius 0) burada da geçerli.
 */
Item {
    id: root
    property var model: []           // [{ value, label }]
    property string currentValue: ""
    property string placeholder: "—"
    property color accent: Theme.master
    signal activated(string value)

    implicitWidth: 160
    implicitHeight: 26

    function labelFor(value) {
        if (!model) return placeholder
        for (let i = 0; i < model.length; ++i)
            if (model[i].value === value) return model[i].label
        return placeholder
    }

    Rectangle {
        anchors.fill: parent
        color: mouse.containsMouse || popup.visible ? Theme.raised : Theme.surface
        border.width: 1
        border.color: popup.visible ? root.accent
                     : (mouse.containsMouse ? Theme.borderStrong : Theme.border)

        Text {
            anchors.left: parent.left
            anchors.leftMargin: Theme.s2
            anchors.right: arrow.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.labelFor(root.currentValue)
            color: Theme.text
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            renderType: Text.NativeRendering
        }
        Text {
            id: arrow
            anchors.right: parent.right
            anchors.rightMargin: Theme.s2
            anchors.verticalCenter: parent.verticalCenter
            text: "▾"
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: popup.visible = !popup.visible
    }

    Rectangle {
        id: popup
        visible: false
        z: 100
        y: root.height
        width: Math.max(root.width, 220)
        height: Math.min(list.contentHeight + 2, 260)
        color: Theme.raised
        border.width: 1
        border.color: Theme.borderStrong

        ListView {
            id: list
            anchors.fill: parent
            anchors.margins: 1
            clip: true
            model: root.model
            delegate: Rectangle {
                width: list.width
                height: 26
                required property var modelData
                color: itemMouse.containsMouse ? Theme.surface
                     : (modelData.value === root.currentValue
                        ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.15)
                        : "transparent")
                Text {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.s2
                    anchors.rightMargin: Theme.s2
                    verticalAlignment: Text.AlignVCenter
                    text: parent.modelData.label
                    color: Theme.text
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    renderType: Text.NativeRendering
                }
                MouseArea {
                    id: itemMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.currentValue = parent.modelData.value
                        root.activated(parent.modelData.value)
                        popup.visible = false
                    }
                }
            }
        }
    }
}
