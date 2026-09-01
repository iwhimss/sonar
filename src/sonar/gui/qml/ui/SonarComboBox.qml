import QtQuick
import QtQuick.Controls as C
import QtQuick.Window

/*
 * Köşesiz açılır liste.
 *
 * Neden `QtQuick.Controls`'un `Popup`'ı: eskiden açılır liste sıradan bir `Rectangle`
 * çocuğuydu. QML'de `z` yalnızca **kardeşler arasında** geçerli, üstelik üst kapsayıcı
 * `clip` yapıyorsa liste kırpılıyor — pratikte her dropdown başka bir panelin altında
 * kalıyordu. `Popup` sahnenin `Overlay` katmanında açılır, hiçbir şeyin altında kalmaz.
 *
 * Controls'un **stili kullanılmıyor**: `background` ve `contentItem` tamamen bizim,
 * radius 0 kuralı geçerli. `app.py` içinde `QQuickStyle.setStyle("Basic")` çağrılıyor ki
 * platform stili araya girmesin.
 */
Item {
    id: root
    property var model: []           // [{ value, label }] veya [{ value, label, header }]
    property string currentValue: ""
    property string placeholder: "—"
    property color accent: Theme.master
    //: Liste bu yüksekliği aşarsa kaydırılır.
    property int maxPopupHeight: 280
    property int popupWidth: 0       // 0 = en az kontrol kadar, en çok 260
    signal activated(string value)

    implicitWidth: 160
    implicitHeight: 26

    function labelFor(value) {
        if (!model) return placeholder
        for (let i = 0; i < model.length; ++i)
            if (model[i].value === value) return model[i].label
        return placeholder
    }

    function indexOfCurrent() {
        if (!model) return 0
        for (let i = 0; i < model.length; ++i)
            if (model[i].value === root.currentValue) return i
        return 0
    }

    Rectangle {
        anchors.fill: parent
        color: mouse.containsMouse || popup.opened ? Theme.raised : Theme.surface
        border.width: 1
        border.color: popup.opened ? root.accent
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
            text: popup.opened ? "▴" : "▾"
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: popup.opened ? popup.close() : popup.open()
    }

    C.Popup {
        id: popup
        // Kontrolün altına açılır; ekranın altına taşacaksa üstüne.
        readonly property bool above: {
            const window = root.Window.window
            if (!window) return false
            const bottom = root.mapToItem(null, 0, root.height).y
            return bottom + implicitHeight > window.height && bottom > implicitHeight
        }
        x: 0
        y: above ? -implicitHeight : root.height
        width: root.popupWidth > 0 ? root.popupWidth : Math.max(root.width, 220)
        implicitHeight: Math.min(list.contentHeight + 2, root.maxPopupHeight)
        padding: 1
        modal: false
        // Dışarı tıklayınca kapansın — eski elle yazılmış liste bunu yapmıyordu.
        closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutsideParent

        background: Rectangle {
            color: Theme.raised
            border.width: 1
            border.color: Theme.borderStrong
        }

        onOpened: {
            list.currentIndex = root.indexOfCurrent()
            list.positionViewAtIndex(list.currentIndex, ListView.Contain)
            list.forceActiveFocus()
        }

        contentItem: ListView {
            id: list
            clip: true
            model: root.model
            boundsBehavior: Flickable.StopAtBounds
            keyNavigationEnabled: true
            highlightMoveDuration: 0

            Keys.onReturnPressed: root.pick(list.currentIndex)
            Keys.onEnterPressed: root.pick(list.currentIndex)

            delegate: Rectangle {
                id: option
                required property var modelData
                required property int index
                //: Ayraç satırı: seçilemez, yalnızca grup başlığı.
                readonly property bool isHeader: modelData.header === true
                width: list.width
                height: isHeader ? 20 : 26
                color: isHeader ? "transparent"
                     : (optionMouse.containsMouse || list.currentIndex === index
                        ? Theme.surface
                        : (modelData.value === root.currentValue
                           ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.15)
                           : "transparent"))

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.s2
                    anchors.rightMargin: Theme.s2
                    verticalAlignment: Text.AlignVCenter
                    text: option.modelData.label
                    color: option.isHeader ? Theme.textFaint : Theme.text
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: option.isHeader ? Theme.fontSmall : Theme.fontBody
                    font.letterSpacing: option.isHeader ? 0.9 : 0
                    font.capitalization: option.isHeader ? Font.AllUppercase : Font.MixedCase
                    renderType: Text.NativeRendering
                }
                Rectangle {
                    visible: option.isHeader && option.index > 0
                    width: parent.width
                    height: 1
                    color: Theme.border
                }
                MouseArea {
                    id: optionMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: !option.isHeader
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.pick(option.index)
                }
            }

            // İnce kaydırma göstergesi — köşesiz.
            Rectangle {
                width: 3
                color: Theme.borderStrong
                anchors.right: parent.right
                visible: list.contentHeight > list.height
                height: list.height * (list.height / Math.max(list.contentHeight, 1))
                y: list.contentY * (list.height / Math.max(list.contentHeight, 1))
            }
        }
    }

    function pick(index) {
        if (!model || index < 0 || index >= model.length) return
        const option = model[index]
        if (option.header === true) return
        root.currentValue = option.value
        root.activated(option.value)
        popup.close()
    }
}
