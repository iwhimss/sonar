import QtQuick

/*
 * Bir efektin kutusu: tutamak + açma anahtarı + başlık + sil + içerik.
 * Kapalı panel soluk ama okunabilir kalır (SteelSeries davranışı).
 *
 * `movable` ve `removable` şema 7'de geldi: zincir artık sabit değil, kullanıcı efekt
 * ekliyor, siliyor ve sürükleyerek sıralıyor (test turu 6).
 */
SonarPanel {
    id: root
    property string title: ""
    property bool active: false
    property color accent: Theme.master
    property string note: ""             // "AI aktifken devre dışı" gibi
    //: Sürükleme tutamağı gösterilsin mi. Tutamağın kendisi `grip` ile dışarı açılıyor;
    //: sürükleme mantığı listeye ait, panele değil.
    property bool movable: false
    property bool removable: false
    //: Ayarları varsayılana döndüren ↺ düğmesi. Mikserdeki fader sıfırlamasıyla aynı
    //: ikon ve aynı davranış.
    property bool resettable: false
    readonly property alias grip: gripArea
    default property alias body: holder.data
    signal toggled(bool value)
    signal removeRequested()
    signal resetRequested()

    Column {
        anchors.fill: parent
        anchors.margins: Theme.s3
        spacing: Theme.s2

        Item {
            width: parent.width
            height: 18

            Row {
                id: headerRow
                anchors.left: parent.left
                anchors.right: resetButton.left
                anchors.rightMargin: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.s2

                /* Sürükleme tutamağı. Panelin tamamını sürüklemek yerine küçük bir
                   tutamak: içindeki kaydırıcılar da sürükleniyor ve ikisi çakışırdı. */
                Item {
                    width: root.movable ? 10 : 0
                    height: 16
                    visible: root.movable
                    anchors.verticalCenter: parent.verticalCenter

                    Column {
                        anchors.centerIn: parent
                        spacing: 2
                        Repeater {
                            model: 3
                            Rectangle {
                                width: 10
                                height: 2
                                color: gripArea.containsMouse ? root.accent : Theme.borderStrong
                            }
                        }
                    }
                    MouseArea {
                        id: gripArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.SizeVerCursor
                    }
                }

                // Dikdörtgen anahtar — yuvarlak "pill" değil.
                Rectangle {
                    width: 30
                    height: 16
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.active ? root.accent : Theme.sunken
                    border.width: 1
                    border.color: root.active ? root.accent : Theme.border
                    Rectangle {
                        width: 12
                        height: 12
                        x: root.active ? 16 : 2
                        y: 2
                        color: root.active ? "#0E1116" : Theme.textFaint
                        Behavior on x { NumberAnimation { duration: 90 } }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.toggled(!root.active)
                    }
                }

                SonarSectionLabel {
                    text: root.title
                    color: root.active ? root.accent : Theme.textDim
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    visible: root.note.length > 0
                    text: root.note
                    color: Theme.warn
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            SonarIconButton {
                id: resetButton
                visible: root.resettable
                width: visible ? 20 : 0
                icon: "reset"
                tooltip: I18n.t("fx.reset_effect")
                accent: root.accent
                implicitWidth: 20
                implicitHeight: 18
                anchors.right: removeButton.left
                anchors.rightMargin: root.removable ? Theme.s1 : 0
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.resetRequested()
            }

            SonarIconButton {
                id: removeButton
                visible: root.removable
                width: visible ? 20 : 0
                icon: "close"
                tooltip: I18n.t("fx.remove_effect")
                accent: Theme.danger
                implicitWidth: 20
                implicitHeight: 18
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.removeRequested()
            }
        }

        Item {
            id: holder
            width: parent.width
            height: parent.height - 26
            opacity: root.active ? 1.0 : 0.45
        }
    }
}
