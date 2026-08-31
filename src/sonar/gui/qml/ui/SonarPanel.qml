import QtQuick

/* 1 px kenarlıklı, köşesiz kutu. Tüm panellerin temeli. */
Rectangle {
    property alias content: inner.data
    property color borderColor: Theme.border
    color: Theme.surface
    border.width: 1
    border.color: borderColor
    // radius bilinçli olarak yok — bkz. Theme.qml
    Item { id: inner; anchors.fill: parent; anchors.margins: 1 }
}
