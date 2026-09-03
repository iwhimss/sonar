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
 * `value` lineer ses seviyesi (1.0 = birim kazanç). **Dışarıdan sürülür**: fader ona
 * asla yazmaz, yalnızca `moved()` yayınlar. Köprü zaten iyimser güncelleme yapıyor
 * (`_optimistic` + `_hold`), yani tutamak yine anında hareket ediyor.
 *
 * Eskiden `root.value = v` yazıyordu; bu, modelden gelen bağlamayı **kalıcı olarak**
 * koparıyordu. Bir kez sürükledikten sonra fader daemon'daki değeri bir daha takip
 * etmiyordu — profil değiştirmek, mute etmek, "Sıfırla" demek tutamağı oynatmıyordu.
 */
Item {
    id: root
    property real value: 1.0
    property color accent: Theme.master
    property bool muted: false
    //: Üst sınır (lineer). 1.0 = birim kazanç. Mikser 3.0 veriyor: %100'ün üstü
    //: dijital kazanç, yani kaynak zaten yüksekse kırpabilir. Ses zincirine koruma
    //: eklenmiyor (kullanıcı kararı); yalnızca tutamak ve yüzde uyarı rengine dönüyor.
    property real maximum: 1.0
    signal moved(real value)
    signal released()

    implicitWidth: 22
    implicitHeight: 160

    readonly property int trackWidth: 4
    readonly property int handleHeight: 10
    readonly property real usable: height - handleHeight
    readonly property bool boosted: value > 1.001 && maximum > 1.001

    function fractionToValue(f) { return Math.max(0, Math.min(1, f)) * maximum }
    function valueToY(v) {
        return (1 - Math.max(0, Math.min(1, v / maximum))) * usable
    }

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
        color: root.muted ? Theme.textFaint : (root.boosted ? Theme.warn : root.accent)
        opacity: root.muted ? 0.4 : 1.0
    }

    /* Birim kazanç işareti — %300'lük bir fader'da %100'ün nerede olduğu görünmeli. */
    Rectangle {
        visible: root.maximum > 1.001
        x: (root.width - 10) / 2
        y: root.valueToY(1.0) + root.handleHeight / 2
        width: 10
        height: 1
        color: Theme.borderStrong
    }

    // tutamak
    Rectangle {
        id: handle
        width: root.width
        height: root.handleHeight
        y: root.valueToY(root.value)
        color: drag.pressed ? Qt.lighter(Theme.raised, 1.4) : Theme.raised
        border.width: 1
        border.color: root.muted ? Theme.border : (root.boosted ? Theme.warn : root.accent)
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
                root.moved(v)
                pressValue = v
                pressY = mouse.y
            }
        }
        onPositionChanged: (mouse) => {
            if (!pressed) return
            const scale = (mouse.modifiers & Qt.ShiftModifier) ? 0.2 : 1.0
            const delta = -(mouse.y - pressY) / root.usable * scale
            const v = root.fractionToValue(pressValue / root.maximum + delta)
            if (v !== root.value) root.moved(v)
        }
        onReleased: root.released()
        onDoubleClicked: { root.moved(1.0); root.released() }
        onWheel: (wheel) => {
            const step = (wheel.modifiers & Qt.ShiftModifier) ? 0.005 : 0.02
            const v = root.fractionToValue(
                root.value / root.maximum + (wheel.angleDelta.y > 0 ? step : -step))
            if (v !== root.value) { root.moved(v); root.released() }
        }
    }

    Keys.onUpPressed: { moved(fractionToValue(value / maximum + 0.02)); released() }
    Keys.onDownPressed: { moved(fractionToValue(value / maximum - 0.02)); released() }
}
