import QtQuick

/*
 * Dikey fader. Dikdörtgen oluk + dikdörtgen tutamak — yuvarlatma yok.
 *
 * Etkileşim:
 *   sürükle          — değer
 *   Shift + sürükle  — hassas mod (1/5 hız)
 *   çift tık         — birim kazanca (1.0) sıfırla
 *   tekerlek         — ±%2 (Shift ile ±%0.5)
 *
 * `value` lineer ses seviyesi (1.0 = birim kazanç). Üst sınır 1.0'da tutuluyor: daemon 4.0'a
 * kadar kabul ediyor ama mikserde yükseltme sürprizi istemiyoruz.
 */
Item {
    id: root
    property real value: 1.0
    property color accent: Theme.master
    property bool muted: false
    signal moved(real value)
    signal released()

    implicitWidth: 22
    implicitHeight: 160

    readonly property int trackWidth: 4
    readonly property int handleHeight: 10
    readonly property real usable: height - handleHeight

    function fractionToValue(f) { return Math.max(0, Math.min(1, f)) }
    function valueToY(v) { return (1 - Math.max(0, Math.min(1, v))) * usable }

    // oluk
    Rectangle {
        x: (root.width - root.trackWidth) / 2
        y: root.handleHeight / 2
        width: root.trackWidth
        height: root.usable
        color: Theme.sunken
        border.width: 1
        border.color: Theme.border
    }

    // dolu kısım
    Rectangle {
        x: (root.width - root.trackWidth) / 2
        width: root.trackWidth
        y: root.valueToY(root.value) + root.handleHeight / 2
        height: root.usable - root.valueToY(root.value)
        color: root.muted ? Theme.textFaint : root.accent
        opacity: root.muted ? 0.4 : 1.0
    }

    // tutamak
    Rectangle {
        id: handle
        width: root.width
        height: root.handleHeight
        y: root.valueToY(root.value)
        color: drag.pressed ? Qt.lighter(Theme.raised, 1.4) : Theme.raised
        border.width: 1
        border.color: root.muted ? Theme.border : root.accent
    }

    MouseArea {
        id: drag
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        property real pressValue: 0
        property real pressY: 0

        onPressed: (mouse) => {
            pressValue = root.value
            pressY = mouse.y
            // Tutamağın dışına tıklandıysa oraya atla.
            if (mouse.y < handle.y || mouse.y > handle.y + handle.height) {
                const v = root.fractionToValue(1 - (mouse.y - root.handleHeight / 2) / root.usable)
                root.value = v
                root.moved(v)
                pressValue = v
                pressY = mouse.y
            }
        }
        onPositionChanged: (mouse) => {
            if (!pressed) return
            const scale = (mouse.modifiers & Qt.ShiftModifier) ? 0.2 : 1.0
            const delta = -(mouse.y - pressY) / root.usable * scale
            const v = root.fractionToValue(pressValue + delta)
            if (v !== root.value) { root.value = v; root.moved(v) }
        }
        onReleased: root.released()
        onDoubleClicked: { root.value = 1.0; root.moved(1.0); root.released() }
        onWheel: (wheel) => {
            const step = (wheel.modifiers & Qt.ShiftModifier) ? 0.005 : 0.02
            const v = root.fractionToValue(root.value + (wheel.angleDelta.y > 0 ? step : -step))
            if (v !== root.value) { root.value = v; root.moved(v); root.released() }
        }
    }

    Keys.onUpPressed: { const v = fractionToValue(value + 0.02); value = v; moved(v); released() }
    Keys.onDownPressed: { const v = fractionToValue(value - 0.02); value = v; moved(v); released() }
}
