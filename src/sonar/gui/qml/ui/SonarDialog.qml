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

    anchors.centerIn: C.Overlay.overlay
    width: Math.min(preferredWidth, (parent ? parent.width : 800) - Theme.s6 * 2)
    // Yükseklik **içerikten**: sabit vermek metni taşırıyordu.
    implicitHeight: column.implicitHeight + padding * 2
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
            text: root.title
            color: root.accent
            visible: root.title.length > 0
        }
        Item {
            id: holder
            width: column.width
            implicitHeight: childrenRect.height
            height: childrenRect.height
        }
    }
}
