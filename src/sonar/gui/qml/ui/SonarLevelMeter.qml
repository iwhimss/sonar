import QtQuick

/*
 * Dikey segmentli seviye metresi. Peak-hold çizgisi ve clip göstergesi taşır.
 * Segmentler köşesiz; renk eşikleri Theme.meterColor()'dan geliyor.
 */
Item {
    id: root
    property real db: -60          // anlık tepe
    property real holdDb: -60      // tutulan tepe
    property bool clipped: false

    implicitWidth: 5
    implicitHeight: 160

    readonly property int segments: 24
    readonly property real fraction: Theme.dbToFraction(db)

    Rectangle {
        anchors.fill: parent
        color: Theme.sunken
        border.width: 1
        border.color: Theme.border
    }

    Column {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 1
        Repeater {
            model: root.segments
            Rectangle {
                width: parent.width
                height: (root.height - 2 - (root.segments - 1)) / root.segments
                // en üst segment index 0 → alttan doldur
                readonly property real segTop: (root.segments - index) / root.segments
                readonly property real segDb: -60 + segTop * 60
                color: root.fraction >= segTop ? Theme.meterColor(segDb)
                                               : Qt.rgba(1, 1, 1, 0.04)
            }
        }
    }

    // peak-hold çizgisi
    Rectangle {
        visible: root.holdDb > -59.5
        width: parent.width
        height: 1
        color: Theme.text
        y: (1 - Theme.dbToFraction(root.holdDb)) * (root.height - 1)
    }

    // clip göstergesi
    Rectangle {
        visible: root.clipped
        width: parent.width
        height: 3
        color: Theme.meterClip
    }
}
