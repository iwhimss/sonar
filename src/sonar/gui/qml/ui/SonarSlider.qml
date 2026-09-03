import QtQuick

/*
 * Yatay slider — ChatMix ve benzeri kontroller için. Köşesiz.
 *
 * `value` **dışarıdan sürülür**; slider ona asla yazmaz, yalnızca `moved()` yayınlar.
 * Eskiden sürükleme `root.value = v` yapıyordu ve bu `value: bridge.chatmix / 100`
 * bağlamasını kalıcı olarak koparıyordu: bir kez sürükledikten sonra "Sıfırla"
 * modeli 50'ye çekiyor ama slider olduğu yerde kalıyordu (test turu 3).
 * `SonarFader` da aynı deseni kullanıyor.
 */
Item {
    id: root
    property real value: 0.5
    property color accent: Theme.master
    signal moved(real value)
    signal released()

    implicitWidth: 200
    implicitHeight: 22

    readonly property int trackHeight: 4
    readonly property int handleWidth: 10
    readonly property real usable: width - handleWidth

    Rectangle {
        y: (root.height - root.trackHeight) / 2
        x: root.handleWidth / 2
        width: root.usable
        height: root.trackHeight
        color: Theme.sunken
        border.width: 1
        border.color: Theme.border
    }

    // orta çizgi (nötr konum işareti)
    Rectangle {
        x: root.width / 2 - 1
        y: (root.height - 12) / 2
        width: 1
        height: 12
        color: Theme.borderStrong
    }

    Rectangle {
        id: knob
        width: root.handleWidth
        height: root.height
        x: root.value * root.usable
        color: drag.pressed ? Qt.lighter(Theme.raised, 1.4) : Theme.raised
        border.width: 1
        border.color: root.accent
    }

    MouseArea {
        id: drag
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        function apply(x) {
            const v = Math.max(0, Math.min(1, (x - root.handleWidth / 2) / root.usable))
            if (v !== root.value) root.moved(v)
        }
        onPressed: (mouse) => apply(mouse.x)
        onPositionChanged: (mouse) => { if (pressed) apply(mouse.x) }
        onReleased: root.released()
        onDoubleClicked: { root.moved(0.5); root.released() }
    }
}
