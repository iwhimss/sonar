import QtQuick

/*
 * Sürüklenen uygulama kutucuğunun imleci izleyen kopyası.
 *
 * Neden gerekiyor: asıl kutucuk `ListView` içinde ve o liste `clip: true`. Sürüklenirken
 * kutucuk kendi listesinin dışına çıkamıyor, üstelik QML'de `z` yalnızca **kardeşler
 * arasında** geçerli — kutucuk komşu kanal sütunlarının altında kalıyordu.
 *
 * Çözüm asıl kutucuğu taşımak değil: `DropArea` hedefi asıl öğenin konumundan buluyor,
 * yani o hareket etmeye devam etmeli. Bunun yerine asıl kutucuk görünmez olur ve
 * mikserin en üst katmanındaki bu vekil çizilir.
 */
Item {
    id: root
    property string label: ""
    property color accent: Theme.master
    readonly property bool active: chip.visible

    anchors.fill: parent
    z: 900
    visible: chip.visible

    /* Sürükleme başladı: kutucuğu göster. */
    function show(text, color) {
        root.label = text
        root.accent = color
        chip.visible = true
    }

    /* `point` bu öğenin koordinat sisteminde olmalı. */
    function moveTo(x, y) {
        chip.x = x - chip.width / 2
        chip.y = y - chip.height / 2
    }

    function hide() {
        chip.visible = false
    }

    Rectangle {
        id: chip
        visible: false
        width: 140
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
