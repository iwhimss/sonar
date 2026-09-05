import QtQuick

/*
 * Sayısal giriş. Enter veya odak kaybında değeri gönderir; geçersiz metin geri alınır.
 *
 * ## Enter odağı bırakır
 *
 * Eskiden Enter yalnızca `commit()` çağırıyordu ve alan **yazma kipinde kalıyordu**.
 * Odak alandayken `onValueChanged` metni tazelemiyor (kullanıcının yazdığını silmemek
 * için); başka bir bandı seçince değer değişiyor, metin eski banda ait kalıyordu.
 * Test turu 7'de kullanıcının gördüğü buydu: *"grafikte doğru yerde ama Hz kısmında
 * hâlâ 7000 yazıyor"*. Daha kötüsü, sonraki odak kaybında o eski metin **yeni** banda
 * yazılıyordu.
 *
 * Artık Enter odağı bırakıyor ve gönderme tek noktadan (odak kaybı) geçiyor.
 *
 * ## Düzenlerken yuvarlanmış değer gösterilmez
 *
 * `decimals` yalnızca **gösterim** içindir. Alan düzenlemeye açıldığında yuvarlanmış
 * metin yazsaydık (Q için 0.707 → "0.71"), kullanıcı Enter'a bastığında gerçekten 0.71
 * yazılırdı — sırf kutuya bakmış olmak değeri bozardı.
 */
Rectangle {
    id: root
    property real value: 0
    property int decimals: 1
    property string unit: ""
    property color accent: Theme.master
    //: `false` iken gönderim yapılmaz. Ekolayzerde seçili band yokken alan bir şeye
    //: bağlı değil; o hâlde yazmak yanlış banda değer yazmak olurdu.
    property bool committable: true
    signal committed(real value)

    implicitWidth: 78
    implicitHeight: 22
    color: Theme.sunken
    border.width: 1
    border.color: input.activeFocus ? accent : Theme.border

    function display() {
        return root.value.toFixed(root.decimals) + (root.unit ? " " + root.unit : "")
    }

    /* Düzenleme metni: tam değer, gereksiz sıfırlar olmadan. `String(0.707)` → "0.707",
       `String(7000)` → "7000". */
    function editText() {
        return String(Number(root.value.toFixed(6)))
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
        //: Yalnızca sayı: işaret, rakam ve ondalık ayracı. Türkçe klavyede ayraç virgül.
        validator: RegularExpressionValidator {
            regularExpression: /^-?\d{0,7}([.,]\d{0,4})?$/
        }

        onActiveFocusChanged: {
            if (activeFocus) {
                text = root.editText()
                selectAll()
            } else {
                root.commit()
            }
        }
        // Enter odağı bırakıyor; gönderim `onActiveFocusChanged` üzerinden tek noktadan.
        Keys.onReturnPressed: focus = false
        Keys.onEnterPressed: focus = false
        Keys.onEscapePressed: { text = root.display(); focus = false }
    }

    function commit() {
        const cleaned = String(input.text).replace(",", ".").trim()
        const parsed = parseFloat(cleaned)
        if (isNaN(parsed) || !root.committable) { input.text = display(); return }
        // Değer gerçekten değişmediyse yazma: gereksiz bir D-Bus çağrısı ve gereksiz
        // bir "değişti" olayı üretirdi.
        if (Math.abs(parsed - root.value) > 1e-9) root.committed(parsed)
        input.text = display()
    }
}
