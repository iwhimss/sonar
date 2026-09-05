import QtQuick

/*
 * Fader'ın üstündeki yüzde göstergesi — tıklayınca düzenlenebilir, yanında sıfırlama.
 *
 * Eskiden salt okunur bir `Text`'ti. Kullanıcı hem bir sayı yazabilmek hem de ChatMix'teki
 * gibi tek düğmeyle birim kazanca dönebilmek istedi (test turu 4).
 *
 * `value` **lineer** ses seviyesi (1.0 = %100 = birim kazanç); alanda yüzde gösteriliyor.
 *
 * `SonarFader` ve `SonarSlider` gibi bu da `value`'ya **asla yazmaz**, yalnızca
 * `edited()` yayınlar. Bir kez yazmak modelden gelen bağlamayı kalıcı olarak koparıyor;
 * test turu 3'te fader'lar tam bu yüzden daemon'ı takip etmeyi bırakmıştı.
 *
 * Metnin kendisi de bağlama değil: `TextInput.text` kullanıcı yazarken değişiyor, yani
 * bağlama zaten ilk tuşta kopardı. `onValueChanged` ile elle tazeleniyor — odak
 * alandayken dokunulmuyor ki kullanıcının yazdığı silinmesin (`SonarNumberField` deseni).
 *
 * Şerit dar (148 px, iki fader yan yana), o yüzden düğme 26 px'lik standart boyunda
 * değil: metin + düğme birlikte ~54 px, kolonun içinde kalıyor.
 */
Item {
    id: root

    property real value: 1.0
    //: Üst sınır (lineer). Alana yazılan yüzde buna göre kırpılır.
    property real maximum: 3.0
    property color accent: Theme.master
    //: Sıfırlamanın gittiği değer. Fader'ın çift tık davranışıyla aynı olmalı.
    readonly property real unity: 1.0

    signal edited(real value)

    implicitWidth: 58
    implicitHeight: 16

    /* Metin **yerinde** hesaplanıyor, `root.display` okunmuyor.
       Ölçüldü (test turu 5): `display` ayrı bir binding ve `onValueChanged` çalıştığında
       henüz tazelenmemiş oluyor — metin tam bir adım geride kalıyordu.
           value 0.5 → "50%" ✓ · value 1.0 → "50%" ✗ · value 0.25 → "100%" ✗
       Fader `value`'ya doğrudan bağlı olduğu için doğru yere gidiyordu; kullanıcının
       gördüğü "slider sıfırlanıyor ama metin sıfırlanmıyor" tam olarak buydu. */
    function percentText(value) { return Math.round(value * 100) + "%" }

    onValueChanged: if (!field.activeFocus) field.text = root.percentText(root.value)
    Component.onCompleted: field.text = root.percentText(root.value)

    /* "150", "%150", " 150,5 " — hepsi kabul. Türkçe klavyede ondalık ayracı virgül;
       `parseFloat` virgülü tanımadığı için sessizce 150 okunurdu. */
    function parsePercent(text) {
        const cleaned = String(text).replace("%", "").replace(",", ".").trim()
        if (cleaned === "") return NaN
        const parsed = parseFloat(cleaned)
        return isNaN(parsed) ? NaN : parsed
    }

    function commit(text) {
        const parsed = root.parsePercent(text)
        if (isNaN(parsed)) return          // geçersiz metin: değer değişmez
        root.edited(Math.max(0, Math.min(root.maximum, parsed / 100)))
    }

    Row {
        anchors.centerIn: parent
        spacing: 2

        Item {
            width: 36
            height: 16
            anchors.verticalCenter: parent.verticalCenter

            Rectangle {
                anchors.fill: parent
                // Düzenleme kipinde çerçeve çıkıyor; normalde salt metin gibi duruyor
                // ki mikser kalabalıklaşmasın.
                visible: field.activeFocus
                color: Theme.sunken
                border.width: 1
                border.color: root.accent
            }

            TextInput {
                id: field
                anchors.fill: parent
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                // %100 üstü dijital kazanç; kırpma riskini renk söylüyor.
                color: field.activeFocus
                    ? Theme.text
                    : (root.value > 1.001 ? Theme.warn : Theme.textDim)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                selectByMouse: true
                renderType: Text.NativeRendering
                // Yalnızca rakam, ondalık ayracı ve yüzde işareti.
                validator: RegularExpressionValidator {
                    regularExpression: /^%?\d{0,3}([.,]\d{0,2})?%?$/
                }

                onActiveFocusChanged: {
                    if (activeFocus) {
                        // Düzenlerken yüzde işareti olmasın; kullanıcı üstüne yazacak.
                        text = String(Math.round(root.value * 100))
                        selectAll()
                    } else {
                        root.commit(text)
                        text = root.percentText(root.value)
                    }
                }
                Keys.onReturnPressed: focus = false
                Keys.onEnterPressed: focus = false
                Keys.onEscapePressed: {
                    text = root.percentText(root.value)
                    focus = false
                }
            }
        }

        SonarIconButton {
            anchors.verticalCenter: parent.verticalCenter
            implicitWidth: 18
            implicitHeight: 16
            icon: "reset"
            accent: root.accent
            // Zaten birim kazançtaysa yapacak bir şey yok.
            enabled: Math.abs(root.value - root.unity) > 0.001
            opacity: enabled ? 1.0 : 0.3
            onClicked: root.edited(root.unity)
        }
    }
}
