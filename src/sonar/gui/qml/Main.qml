import QtQuick
import QtQuick.Window
import "ui"

/* Ana pencere: başlık, sekmeler, içerik. Daemon yoksa bağlantı ekranı gösterilir. */
Window {
    id: window
    visible: true
    width: 1180
    height: 720
    minimumWidth: 900
    minimumHeight: 620
    color: Theme.bg
    title: "Sonar"

    property string currentTab: "mixer"

    /* Klavye: 1–9 sekmeler, Esc mikser'e döner. Fader'lar ok tuşlarıyla sürülüyor
       (bkz. SonarFader). */
    Item {
        focus: true
        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Escape) {
                window.currentTab = "mixer"
                event.accepted = true
                return
            }
            const index = event.key - Qt.Key_1
            if (index >= 0 && index < 9) {
                const tabs = window.tabList()
                if (index < tabs.length) {
                    window.currentTab = tabs[index].key
                    event.accepted = true
                }
            }
        }
    }

    // --- üst şerit ---------------------------------------------------------
    Item {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 76

        Text {
            id: brand
            anchors.left: parent.left
            anchors.leftMargin: Theme.s6
            anchors.top: parent.top
            anchors.topMargin: Theme.s3
            text: "Sonar"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitle
            renderType: Text.NativeRendering
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: Theme.s6
            anchors.rightMargin: Theme.s6
            anchors.top: brand.bottom
            anchors.topMargin: Theme.s2
            height: 1
            color: Theme.border
        }

        SonarTabBar {
            anchors.left: parent.left
            anchors.leftMargin: Theme.s6
            anchors.bottom: parent.bottom
            current: window.currentTab
            tabs: window.tabList()
            onSelected: (key) => window.currentTab = key
        }
    }

    // --- uyarı şeridi ------------------------------------------------------
    Rectangle {
        id: warning
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        height: visible ? 30 : 0
        visible: bridge.connected && bridge.conflicts.length > 0
        color: Qt.rgba(0.95, 0.65, 0.23, 0.14)
        border.width: 1
        border.color: Theme.warn
        Row {
            anchors.left: parent.left
            anchors.leftMargin: Theme.s3
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.s2
            SonarIcon { name: "warn"; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter }
            Text {
                text: warning.visible ? bridge.conflicts[0].message : ""
                color: Theme.warn
                elide: Text.ElideRight
                width: window.width - 80
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
                renderType: Text.NativeRendering
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // --- içerik ------------------------------------------------------------
    Item {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: warning.bottom
        anchors.bottom: parent.bottom
        anchors.margins: Theme.s6
        anchors.topMargin: Theme.s3

        Mixer {
            anchors.fill: parent
            visible: bridge.connected && window.currentTab === "mixer"
            bridge: window.bridgeRef()
            onOpenFx: (id) => window.currentTab = id
        }

        // FX sayfaları Faz 8'de geliyor.
        Item {
            anchors.fill: parent
            visible: bridge.connected && window.currentTab !== "mixer"
            SonarPanel {
                anchors.centerIn: parent
                width: 420
                height: 120
                Column {
                    anchors.centerIn: parent
                    spacing: Theme.s2
                    SonarSectionLabel {
                        text: window.currentTab + " — FX"
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    Text {
                        text: "Ekolayzer ve filtre sayfası Faz 8'de geliyor."
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        renderType: Text.NativeRendering
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }
            }
        }

        // --- daemon yok ----------------------------------------------------
        SonarPanel {
            anchors.centerIn: parent
            width: 460
            height: 150
            visible: !bridge.connected
            Column {
                anchors.centerIn: parent
                spacing: Theme.s3
                Text {
                    text: "Sonar servisi çalışmıyor"
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontTitle
                    renderType: Text.NativeRendering
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "systemctl --user start sonar-daemon"
                    color: Theme.textDim
                    font.family: "monospace"
                    font.pixelSize: Theme.fontBody
                    renderType: Text.NativeRendering
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "Bağlantı kurulunca bu ekran kendiliğinden kapanır."
                    color: Theme.textFaint
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                    renderType: Text.NativeRendering
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }

    function bridgeRef() { return bridge }

    function tabList() {
        // `bridge.revision` bilinçli olarak okunuyor: binding'in modeller değişince
        // yeniden değerlendirilmesi buna bağlı (rowCount() bir özellik değil).
        const _ = bridge.revision
        const tabs = [{ key: "mixer", label: "Mikser", color: Theme.master }]
        if (!bridge.connected) return tabs
        for (let i = 0; i < bridge.channels.rowCount(); ++i) {
            const row = bridge.channels.get(i)
            tabs.push({ key: row.id, label: row.name, color: row.color })
        }
        return tabs
    }


}
