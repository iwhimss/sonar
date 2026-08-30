# Faz 7 — GUI tasarım sistemi ve Mixer görünümü

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 4 (API), Faz 6 (metreler)
**Çıktı:** `src/sonar/gui/`, `src/sonar/gui/qml/`

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
- [ ] `Theme.qml` — singleton: renkler, boşluklar, tipografi
- [ ] `SonarPanel.qml` — 1 px kenarlıklı, köşesiz kutu; opsiyonel başlık şeridi
- [ ] `SonarButton.qml` — düz, köşesiz; normal / vurgulu / tehlikeli varyantları
- [ ] `SonarToggle.qml` — dikdörtgen anahtar (yuvarlak "pill" değil)
- [ ] `SonarSlider.qml` — yatay; dikdörtgen oluk + dikdörtgen tutamak
- [ ] `SonarFader.qml` — dikey; **Shift = hassas mod**, **çift tık = sıfırla**, tekerlek desteği,
      üstünde sayısal değer alanı (doğrudan yazılabilir)
- [ ] `SonarLevelMeter.qml` — dikey segmentli metre, peak-hold çizgisi, clip göstergesi
- [ ] `SonarComboBox.qml` — köşesiz açılır liste
- [ ] `SonarNumberField.qml` — sayısal giriş, birim etiketi, aralık kırpma
- [ ] `SonarTabBar.qml` — üst sekme şeridi (Mixer / Game / Chat / Media / Mic)
- [ ] `SonarTooltip.qml`, `SonarIcon.qml` (SVG ikon seti)

---

## `gui/bridge.py` — D-Bus köprüsü

- [ ] `QtDBus` istemcisi; `GetState` ile açılış durumu, sinyallere abone
- [ ] Durumu QML'e `QObject` property + `QAbstractListModel` olarak sunar
      (`ChannelModel`, `StreamModel`, `DeviceModel`, `ProfileModel`)
- [ ] **İyimser güncelleme:** kullanıcı fader'ı çekince UI anında tepki verir;
      daemon onayı gelince değer düzeltilir (çakışmada daemon kazanır)
- [ ] Giden çağrılar 20 ms debounce'lu (daemon'daki debounce'a ek, ağ trafiğini azaltır)
- [ ] Daemon yoksa/çökerse: "Daemon çalışmıyor" ekranı + başlatma düğmesi; geri gelince otomatik bağlanır
- [ ] `GraphRebuilt` sinyalinde tam yenileme

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

- [ ] **Master şeridi** (sol): Personal Mix / Stream Mix / Mic Input cihaz seçicileri
      + yanlarında yüzde alanı; master fader'lar ve mute'lar
- [ ] **Kanal şeritleri**: başlık (ikon + aksan renginde ad + dişli → FX sayfası),
      altında profil seçici (hızlı geçiş)
- [ ] **Çift fader**: sol 🎧 = Personal, sağ 📡 = Stream; her birinin üstünde
      aktiflik noktası, altında mute düğmesi, yanında seviye metresi
- [ ] **Apps kutusu**: o kanalda çalan uygulamalar, ikon + ad çipleri
  - [ ] Sürükle-bırak ile başka kanala taşıma
  - [ ] Sağ tık → "Şuraya taşı ▸", "Bu uygulamayı hep buraya gönder"
  - [ ] Çip üstünde uygulamanın kendi seviye metresi (küçük)
- [ ] **ChatMix** slider'ı (Game ↔ Chat), alt şeritte
- [ ] **`+ Kanal ekle`** — yeni aux kanalı (ad + renk seçimi), yapısal değişiklik uyarısıyla
- [ ] Pencere boyutu değişince şeritler orantılı daralır; minimum genişlik altında yatay kaydırma
- [ ] Klavye: `Tab` gezinme, ok tuşlarıyla fader, `M` mute, `1-9` kanal seçimi

---

## `gui/app.py`
- [ ] `QGuiApplication` + `QQmlApplicationEngine`
- [ ] QML kaynakları `importlib.resources` ile paketten yüklenir (kurulu paketten de çalışır)
- [ ] Pencere durumu (boyut/konum/son sekme) `~/.config/sonar/ui.json`
- [ ] Sistem tepsisi ikonu: göster/gizle, hızlı mute, çıkış (daemon çalışmaya devam eder)
- [ ] Kapatma = gizleme (daemon ayakta), gerçek çıkış menüden

---

## Doğrulama

- `sonar` ile açılır, mikser doğru durumu gösterir
- Fader sürüklerken ses **akıcı** değişir, zipper/tık sesi yok
- Metreler akıcı oynar (20 Hz)
- Uygulama sürükleyip başka kanala bırakınca ses anında o kanala geçer
- `sonar-cli volume game personal 30` → GUI anında yansıtır (sinyal akışı çalışıyor)
- GUI kapatılır → ses düzeni bozulmaz
- Ekran görüntüsü alınıp `docs/reference/steelseries-gg/01-mixer-overview.png` ile
  yan yana karşılaştırılır (his olarak yakın mı, ama köşesiz ve sade)

---

## Tamamlanma kriteri

Mikser tam işlevsel: cihaz seçimi, tüm fader'lar, mute'lar, profil geçişi, uygulama
taşıma ve ChatMix GUI'den çalışıyor; tasarım köşesiz ve tutarlı.
