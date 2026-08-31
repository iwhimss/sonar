# Faz 7 — GUI tasarım sistemi ve Mixer görünümü

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 4 (API), Faz 6 (metreler)
**Çıktı:** `src/sonar/gui/{bridge,dbus_client,app}.py`, `src/sonar/gui/qml/` (14 QML dosyası),
`tests/test_bridge.py`, `tests/test_qml.py` — 67 yeni test (toplam 542)
Ekran görüntüsü: `docs/reference/sonar-mixer.png`

Referans: `docs/reference/steelseries-gg/01-mixer-overview.png`, `02-mixer-master-devices.png`

---

## Tasarım dili

> **Kullanıcı isteği: sade ve modern; yuvarlatılmış köşelerden kaçınılacak.**

- **Köşe yarıçapı her yerde `0`.** Yuvarlatma, yumuşak gölge, gradyan yok
- Ayrım **1 px kenarlıklar** ve **yüzey tonlarıyla** yapılır
- Aksan renkleri dolu dikdörtgen bloklar ve ince çizgiler olarak kullanılır
- Boşluk 4 px ızgarasına oturur (4 / 8 / 12 / 16 / 24)

### Palet (`qml/ui/Theme.qml` — tek kaynak)

| Rol | Değer |
|---|---|
| Zemin | `#0E1116` |
| Yüzey | `#151A21` |
| Yükseltilmiş yüzey | `#1C222B` |
| Kenarlık | `#262E39` |
| Kenarlık (vurgulu) | `#37414F` |
| Metin | `#E4E9F0` |
| İkincil metin | `#8B95A5` |
| Sönük metin | `#5A6472` |

| Kanal | Aksan |
|---|---|
| Master | `#7C6CF0` |
| Game | `#22C58B` |
| Chat | `#3B9EFF` |
| Media | `#F0479A` |
| Mic | `#F2A73B` |
| Aux | `#8B95A5` |

Metre renkleri: normal `#22C58B`, uyarı (-6 dB) `#F2A73B`, clip `#E5484D`

### Tipografi
- Sistem sans (Inter varsa tercih edilir)
- Bölüm başlıkları: büyük harf, 11 px, harf aralığı `+0.08em`, ikincil metin rengi
- Sayısal alanlar: tabular figürler (hizalı rakamlar)

### Bileşen kütüphanesi (`qml/ui/`)
- [x] `Theme.qml` — singleton: renkler, boşluklar, tipografi
- [x] `SonarPanel.qml` — 1 px kenarlıklı, köşesiz kutu; opsiyonel başlık şeridi
- [x] `SonarButton.qml` — düz, köşesiz; normal / vurgulu / tehlikeli varyantları
- [~] `SonarToggle.qml` — gerekmedi; `SonarIconButton`'ın `active` durumu aynı işi görüyor
- [x] `SonarSlider.qml` — yatay; dikdörtgen oluk + dikdörtgen tutamak
- [x] `SonarFader.qml` — dikey; **Shift = hassas mod**, **çift tık = sıfırla**, tekerlek,
      ok tuşları. Üstündeki yüzde **salt okunur**; doğrudan yazma Faz 8'e ertelendi
- [x] `SonarLevelMeter.qml` — dikey segmentli metre, peak-hold çizgisi, clip göstergesi
- [x] `SonarComboBox.qml` — köşesiz açılır liste
- [ ] `SonarNumberField.qml` — Faz 8'e ertelendi (FX sayfasının sayısal alanlarıyla birlikte)
- [x] `SonarTabBar.qml` — üst sekme şeridi (Mixer / Game / Chat / Media / Mic)
- [x] `SonarIcon.qml` — SVG yerine Unicode sembol seti (harici varlık taşımamak için)
- [ ] `SonarTooltip.qml` — Faz 8'e ertelendi

---

## `gui/bridge.py` — D-Bus köprüsü

- [x] `QtDBus` istemcisi; `GetState` ile açılış durumu, sinyallere abone
- [x] Durumu QML'e `QObject` property + `QAbstractListModel` olarak sunar
      (`ChannelModel`, `StreamModel`, `DeviceModel`, `ProfileModel`)
- [x] **İyimser güncelleme:** kullanıcı fader'ı çekince UI anında tepki verir;
      daemon onayı gelince değer düzeltilir (çakışmada daemon kazanır)
- [~] Giden çağrı debounce'u **eklenmedi**: daemon zaten 40 ms'lik pencerede topluyor ve
      D-Bus çağrısı yerel; ölçülebilir bir fayda görülmedi. Gerekirse eklenebilir
- [x] Daemon yoksa/çökerse: "Servis çalışmıyor" ekranı, başlatma komutu yazılı;
      2 sn'de bir yeniden denenip geri gelince kendiliğinden bağlanıyor
- [ ] Ekrandaki başlatma **düğmesi** yok (komut metin olarak gösteriliyor)
- [x] `GraphRebuilt` sinyalinde tam yenileme

---

## Mixer görünümü (`qml/Mixer.qml`)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Sonar                                              [Mixer] Game Chat Media Mic │
├──────────────┬──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ ⚙ MASTER     │ 🎮 GAME ⚙│ 💬 CHAT ⚙│ ▶ MEDIA ⚙│ 🎤 MIC  ⚙│                 │
│              │ [Default]│ [Default]│ [Default]│ [Default]│                 │
│ CİHAZLAR     │  🎧   📡 │  🎧   📡 │  🎧   📡 │  🎧   📡 │                 │
│ Personal ▾ % │  ▓    ▓  │  ▓    ▓  │  ▓    ▓  │  ▓    ▓  │  + Kanal ekle   │
│ Stream   ▾ % │  █    █  │  █    █  │  █    █  │  █    █  │                 │
│ Mic In   ▾ % │  █    █  │  █    █  │  █    █  │  █    █  │                 │
│              │  🔇   🔇 │  🔇   🔇 │  🔇   🔇 │  🔇   🔇 │                 │
│              ├──────────┼──────────┼──────────┼──────────┤                 │
│              │ Apps     │ Apps     │ Apps     │ Apps     │                 │
│              │ ┌──────┐ │ ┌──────┐ │ ┌──────┐ │          │                 │
│              │ │ cs2  │ │ │Discord│ │ │Spotify││          │                 │
│              │ └──────┘ │ └──────┘ │ └──────┘ │          │                 │
│              ├──────────┴──────────┤          │          │                 │
│              │ 🎮 ──────█────── 💬 │  CHATMIX │          │                 │
└──────────────┴─────────────────────┴──────────┴──────────┴─────────────────┘
```

- [x] **Master şeridi** (sol): Personal Mix / Stream Mix / Mic Input cihaz seçicileri
      + yanlarında yüzde alanı; master fader'lar ve mute'lar
- [x] **Kanal şeritleri**: başlık (ikon + aksan renginde ad + dişli → FX sayfası),
      altında profil seçici (hızlı geçiş)
- [x] **Çift fader**: sol 🎧 = Personal, sağ 📡 = Stream; her birinin üstünde
      aktiflik noktası, altında mute düğmesi, yanında seviye metresi
- [x] **Apps kutusu**: o kanalda çalan uygulamalar, ikon + ad çipleri
  - [x] Sürükle-bırak ile başka kanala taşıma
  - [x] Sağ tık → "Şuraya taşı ▸", "Bu uygulamayı hep buraya gönder"
  - [ ] Çip üstünde uygulamanın kendi seviye metresi — **yapılmadı**, akış başına ölçüm
        noktası gerekiyor (şu an kanal başına ölçüyoruz)
- [x] **ChatMix** slider'ı (Game ↔ Chat), alt şeritte
- [x] **`+ Kanal ekle`** — yeni aux kanalı, yapısal değişiklik uyarısıyla; kanal silme
      onay kutusuyla (yerleşik kanallar silinemez)
- [ ] Renk seçimi **yok**; yeni kanallar varsayılan gri aksanla geliyor
- [~] Minimum pencere boyutu tanımlı; orantılı daralma ve yatay kaydırma **yapılmadı**
- [x] Klavye: `1–9` sekme, `Esc` mikser'e dön, ok tuşlarıyla fader
- [ ] `Tab` gezinme ve `M` mute — **yapılmadı** (odak yönetimi gerekiyor)

---

## `gui/app.py`
- [x] `QApplication` + `QQmlApplicationEngine` (tepsi ikonu QtWidgets gerektiriyor)
- [x] QML kaynakları paket dizininden yükleniyor (`Path(__file__).parent / "qml"`);
      `importlib.resources` gerekmedi, kurulu paketten de çalışıyor
- [x] Pencere durumu (boyut + son sekme) `~/.config/sonar/ui.json`; konum **kaydedilmiyor**
- [x] Sistem tepsisi ikonu: göster, çıkış (daemon çalışmaya devam eder)
- [ ] Tepsiden hızlı mute — **yapılmadı**
- [x] Kapatma = gizleme (daemon ayakta), gerçek çıkış menüden

---

## PySide6'nın üç sessiz tuzağı

Üçü de hata vermiyor, yalnızca hiçbir şey olmuyor — arayüz "çalışıyor" görünüp boş kalıyor.

### 1. Python öznitelikleri QML'e görünmüyor
`self.channels = ChannelModel(self)` QML tarafında `undefined`. Modellerin `Property`
olarak açılması şart. Belirti: `Cannot call method 'rowCount' of undefined`.

### 2. Fonksiyon çağrıları binding'i tazelemiyor
`tabs: window.tabList()` bir kez değerlendirilip donuyordu; sekme listesi ve cihaz
açılır listeleri boş kalıyordu. QML yalnızca **özellik** okumalarını izliyor, `rowCount()`
bir özellik değil. Çözüm: köprüde `revision` sayacı; ilgili fonksiyonlar onu okuyor.

### 3. D-Bus sinyal yuvaları `"1"` öneki istiyor
`bus.connect(..., bridge, "onGraphRebuilt()")` sessizce `False` dönüyor. Üç yazım denendi:

| yazım | sonuç |
|---|---|
| `"onGraphRebuilt()"` | ✗ |
| `"onGraphRebuilt"` | ✗ |
| `"1onGraphRebuilt()"` | ✓ |

`"1"` Qt'nin `SLOT()` makro kodu. Tek `QString` argümanlı sinyaller öneksiz de bağlanmış
görünüyordu, bu yüzden sorun ancak `GraphRebuilt` ve `Error`'da fark edildi.

---

## Doğrulama — ✅ gerçek daemon ile

Ekran görüntüsü: `docs/reference/sonar-mixer.png` (offscreen render, canlı daemon).

| Test | Sonuç |
|---|---|
| QML yükleniyor | kök nesne 1, uyarı yok |
| Bağlantı | `connected = true`, 5 kanal, cihazlar listelendi |
| Uygulama dağılımı | Arc Raiders → GAME, Discord → CHAT, Firefox → MEDIA (şeritlerin altında) |
| `sonar-cli volume game personal 30` | arayüz **0.30** gösterdi |
| `sonar-cli mute game personal on` | arayüz `muted = true` gösterdi |
| `sonar-cli chatmix 75` | arayüz **75** gösterdi |
| Seviye metresi | canlı ses çalarken **-20.0 dB** |
| Köşe yuvarlatma | 14 QML dosyasının hiçbirinde `radius` yok (test ediyor) |
| Gradyan / gölge | yok (test ediyor) |

`test_qml.py` tasarım kuralını **test olarak** koruyor: herhangi bir dosyaya `radius`,
`Gradient` veya `DropShadow` sızarsa suite kırılır.

---

## Yol boyunca yakalananlar

1. **`StreamsChanged` sinyali ham envanteri yolluyordu.** Faz 4'te düzeltilmişti ama Faz 6'daki
   bir düzenlemede geri gitmişti; arayüz "çalan uygulamalar" olarak Sonar'ın kendi
   loopback'lerini gösteriyordu. Artık `api.get_streams()` kullanılıyor ve bir test kaynağı
   kontrol ediyor.
2. **Akışın hangi kanalda olduğu `target.object`'ten okunamıyor.** `pw-metadata` ile
   taşıdığımızda hedef metadata deposunda kalıyor, node'un props'una yazılmıyor. Doğru
   kaynak yönlendiricinin kendi kaydı; `get_streams()` artık her akışa `channel` ekliyor.
3. **Köprü uygulamaya bağlanmalı.** Aksi hâlde Python çıkışta topluyor ve QML'in altından
   çekiliyor, kapanışta `Cannot read property of null` yağıyor.
4. **`QCoreApplication` varken `QGuiApplication` kurulamıyor** — Qt abort ediyor. QML
   yükleme testi ayrı süreçte çalışıyor.

---

## Tamamlanma kriteri — ✅ karşılandı

Mikser işlevsel: cihaz seçimi, tüm fader'lar, mute'lar, profil geçişi, uygulama taşıma
(sürükle-bırak + sağ tık menüsü), kanal ekleme/silme ve ChatMix arayüzden çalışıyor.
Tasarım köşesiz ve tutarlı.

**Eksik bırakılanlar** (yukarıda `- [ ]` olarak işaretli): uygulama çipi başına mini metre,
`Tab`/`M` klavye gezinmesi, pencere konumunun kaydedilmesi, şeritlerin orantılı daralması.
Hiçbiri işlevi engellemiyor.

```bash
ruff check src/ tests/ && pytest -q          # 542 test geçti, lint temiz
```
