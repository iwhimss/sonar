import QtQuick
import QtQuick.Controls as C

/*
 * Köşesiz kip penceresi.
 *
 * Neden `QtQuick.Controls`'un `Popup`'ı: eskiden her diyalog sıradan bir `Rectangle`
 * çocuğuydu ve `anchors.centerIn: parent` ile ortalanıyordu. İki şey birden bozuluyordu:
 *
 * 1. Ebeveyn bir `Row` ise `anchors` yasak — QML uyarı basıp yerleşimi bozuyordu
 *    ("Cannot specify ... anchors for items inside Row"). "Çıkış ekle" penceresi bu
 *    yüzden ekranın soluna yarım taşıyordu.
 * 2. Yükseklik sabit veriliyordu; sarılan metin kutunun dışına sarkıyordu.
 *
 * `Popup` sahnenin `Overlay` katmanında açılır, ebeveynin yerleşiminden bağımsızdır ve
 * yüksekliğini içeriğinden alır. Controls'un **stili kullanılmıyor**: `background` ve
 * `contentItem` bizim, radius 0 kuralı geçerli.
 */
C.Popup {
    id: root
    property string title: ""
    property color accent: Theme.master
    default property alias body: holder.data

    //: Pencereye göre en fazla bu kadar geniş; dar ekranda kenarlara yapışmasın.
    property int preferredWidth: 380
    //: İçeriğin kullanabileceği genişlik — `Repeater` içindeki `Text`'ler `parent.width`
    //: göremiyor (ebeveyn `Repeater`), bu yüzden dışarıdan okunabilir olmalı.
    readonly property real bodyWidth: holder.width
    //: İçeriğe kalan en fazla yükseklik. **`root.height` üzerinden hesaplanamaz**:
    //: yükseklik içerikten geliyor, içerik de bundan — bağlama döngüsü kuruluyor ve Qt
    //: onu sessizce 0'da kesiyordu (diyalog gövdesi tamamen boş çiziliyordu).
    readonly property real maxBodyHeight:
        (overlay ? overlay.height : 600) - Theme.s6 * 2 - padding * 2

    /* Boyut sahneye göre, **`parent`e göre değil**. `Popup`un `parent`ı bildirildiği
       yerdeki öğe olarak kalıyor (görsel olarak `Overlay`e taşınsa bile); master şeridi
       240 px olduğu için diyalog 192 px'e sıkışıyordu. */
    readonly property Item overlay: C.Overlay.overlay

    anchors.centerIn: C.Overlay.overlay
    width: Math.min(preferredWidth, (overlay ? overlay.width : 800) - Theme.s6 * 2)
    // Yükseklik **içerikten**: sabit vermek metni taşırıyordu. Pencereden uzun olamaz;
    // uzunsa içerik kayar (küçük pencerede diyalogun altı ekranın dışında kalıyordu).
    implicitHeight: Math.min(column.implicitHeight + padding * 2,
                             (overlay ? overlay.height : 600) - Theme.s6 * 2)
    padding: Theme.s4
    modal: true
    closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside

    background: Rectangle {
        color: Theme.raised
        border.width: 1
        border.color: root.accent
    }

    C.Overlay.modal: Rectangle {
        color: Qt.rgba(0, 0, 0, 0.5)
    }

    contentItem: Column {
        id: column
        spacing: Theme.s3

        SonarSectionLabel {
            id: heading
            text: root.title
            color: root.accent
            visible: root.title.length > 0
        }
        Flickable {
            width: column.width
            // Sığdığı kadarı; sığmıyorsa kayar.
            height: Math.min(holder.height,
                             root.maxBodyHeight
                                 - (heading.visible ? heading.height + column.spacing : 0))
            contentWidth: width
            contentHeight: holder.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            C.ScrollBar.vertical: C.ScrollBar { policy: C.ScrollBar.AsNeeded }

            Item {
                id: holder
                width: parent.width
                implicitHeight: childrenRect.height
                height: childrenRect.height
            }
        }
    }
}
