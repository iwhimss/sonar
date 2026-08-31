import QtQuick

/* Sayısal giriş. Enter veya odak kaybında değeri gönderir; geçersiz metin geri alınır. */
Rectangle {
    id: root
    property real value: 0
    property int decimals: 1
    property string unit: ""
    property color accent: Theme.master
    signal committed(real value)

    implicitWidth: 78
    implicitHeight: 22
    color: Theme.sunken
    border.width: 1
    border.color: input.activeFocus ? accent : Theme.border

    function display() {
        return root.value.toFixed(root.decimals) + (root.unit ? " " + root.unit : "")
    }

    onValueChanged: if (!input.activeFocus) input.text = display()
    Component.onCompleted: input.text = display()

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: Theme.s1
        anchors.rightMargin: Theme.s1
        verticalAlignment: Text.AlignVCenter
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSmall
        selectByMouse: true
        renderType: Text.NativeRendering

        onActiveFocusChanged: {
            if (activeFocus) text = root.value.toFixed(root.decimals)
            else root.commit()
        }
        Keys.onReturnPressed: root.commit()
        Keys.onEnterPressed: root.commit()
        Keys.onEscapePressed: { text = root.display(); focus = false }
    }

    function commit() {
        const parsed = parseFloat(input.text)
        if (isNaN(parsed)) { input.text = display(); return }
        root.committed(parsed)
        input.text = display()
    }
}
