import QtQuick

/*
 * Sürüklenen uygulama kutucuğunun imleci izleyen kopyası.
 *
 * Neden gerekiyor: asıl kutucuk `ListView` içinde ve o liste `clip: true`. Sürüklenirken
 * kendi listesinin dışına çıkamıyor, üstelik QML'de `z` yalnızca **kardeşler arasında**
 * geçerli — kutucuk komşu kanal sütunlarının altında kalıyordu.
 *
 * Çözüm asıl kutucuğu taşımak değil: `DropArea` hedefi asıl öğenin konumundan buluyor,
 * yani o hareket etmeye devam etmeli. Bunun yerine asıl kutucuk soluklaşıyor ve
 * mikserin en üst katmanındaki bu vekil çizilir.
 *
 * `moveTo()` her çağrıda görünürlüğü de açıyor: ilk sürümde `show()` yalnızca sürükleme
 * başlarken bir kez çağrılıyordu ve o çağrı herhangi bir sebeple kaçırıldığında kutucuk
 * hiç görünmüyordu — kullanıcı "sürüklerken kutucuk kayboluyor" dedi.
 */
Item {
    id: root
    property string label: ""
    property color accent: Theme.master
    readonly property bool active: chip.visible

    anchors.fill: parent
    z: 900
    visible: chip.visible
    // Vekil yalnızca çizim: fare olaylarını asıl kutucuk alıyor.
    enabled: false

    function show(text, color) {
        root.label = text
        root.accent = color
        chip.visible = true
    }

    /* `point` bu öğenin koordinat sisteminde. Konum gelmemişse çizmiyoruz: kutucuğun
       sol üst köşede takılı kalması sürüklemeden daha kafa karıştırıcı olurdu. */
    function moveTo(x, y) {
        chip.x = x - chip.width / 2
        chip.y = y - chip.height / 2
        chip.visible = true
    }

    function hide() {
        chip.visible = false
    }

    Rectangle {
        id: chip
        visible: false
        width: 150
        height: 22
        color: Qt.lighter(Theme.raised, 1.5)
        border.width: 1
        border.color: root.accent
        opacity: 0.92

        Text {
            anchors.fill: parent
            anchors.leftMargin: Theme.s1
            anchors.rightMargin: Theme.s1
            verticalAlignment: Text.AlignVCenter
            text: root.label
            color: Theme.text
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSmall
            renderType: Text.NativeRendering
        }
    }
}
