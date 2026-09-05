import QtQuick

/* Kare, köşesiz ikon düğmesi. `active` durumu aksan rengiyle gösterilir.
 *
 * `tooltip` bir süre bildirilip hiç çizilmiyordu. Efekt panelinin başlığında üç küçük
 * düğme yan yana geldiğinde (tutamak, sıfırla, sil) hangisinin ne yaptığı ikondan
 * anlaşılmıyor; ipucu o yüzden gerçekten çiziliyor artık. Yuvarlatma yok, gölge yok. */
Rectangle {
    id: root
    property string icon: "speaker"
    property bool active: false
    property color accent: Theme.master
    property string tooltip: ""
    signal clicked()

    implicitWidth: 26
    implicitHeight: 26
    color: active ? Qt.rgba(accent.r, accent.g, accent.b, 0.18)
                  : (mouse.containsMouse ? Theme.raised : "transparent")
    border.width: 1
    border.color: active ? accent : (mouse.containsMouse ? Theme.borderStrong : Theme.border)

    SonarIcon {
        anchors.centerIn: parent
        name: root.icon
        color: root.active ? root.accent : Theme.textDim
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }

    /* İpucu düğmenin **altında**: panel başlıklarında düğmeler üst kenara yakın ve
       yukarı açılan bir kutu pencerenin dışına taşardı. */
    Rectangle {
        visible: root.tooltip.length > 0 && mouse.containsMouse
        anchors.top: parent.bottom
        anchors.topMargin: 2
        anchors.horizontalCenter: parent.horizontalCenter
        width: hint.implicitWidth + Theme.s3
        height: hint.implicitHeight + Theme.s2
        color: Theme.raised
        border.width: 1
        border.color: Theme.borderStrong
        z: 10

        Text {
            id: hint
            anchors.centerIn: parent
            text: root.tooltip
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSmall
            renderType: Text.NativeRendering
        }
    }
}
