# Faz 8 — Kanal FX sayfası (EQ ve filtreler)

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 7
**Çıktı:** `src/sonar/gui/qml/ChannelFx.qml`, `src/sonar/core/dsp/response.py`

Referans: `docs/reference/steelseries-gg/07-game-eq-spatial.png`, `09-chat-eq-and-filters.png`,
`13-mic-eq-clearcast.png`, `14-mic-clearcast-active.png`

---

## Amaç

Her kanal için ayrı bir FX sayfası: EQ eğrisi, dinamik filtreler ve (mikrofonda) AI gürültü
engelleme. Kullanıcının bir kanal için birden fazla profil kaydedip aralarında hızlı geçiş
yapabildiği yer.

---

## Sayfa düzeni

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Mixer │ [Game] │ Chat │ Media │ Mic                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ PROFİL                        FAVORİLER (2/9)                            │
│ ┌────────────┐ ┌──┐ ┌──┐     ┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐        │
│ │ 🎮 CS2   ▾ │ │☆ │ │🔍│     │CS2││ARC││  ││  ││  ││  ││  ││  ││  │        │
│ └────────────┘ └──┘ └──┘     └──┘└──┘└──┘└──┘└──┘└──┘└──┘└──┘└──┘        │
├──────────────────────────────────────────────────────────────────────────┤
│ [●] EQUALIZER                          Bandlar: [10 ▾]              [⋮]  │
│  +12 ┌────────────────────────────────────────────────────────────────┐  │
│      │        ●                                   ●                   │  │
│   0  │───●─────────●───────●──────────●──────────────────●────●───────│  │
│      │                                                                │  │
│  -12 └────────────────────────────────────────────────────────────────┘  │
│       20Hz   50   100   200   500   1k    2k    5k    10k   20kHz        │
│   Bass ──█──── 0.0 dB   Voice ──█──── 0.0 dB   Treble ──█──── 0.0 dB     │
├───────────────────────────────────┬──────────────────────────────────────┤
│ [○] NOISE GATE               [⋮]  │ [○] COMPRESSOR                  [⋮]  │
│  Threshold ──█────── -60.0 dB     │  Threshold ──█────── -18.0 dB        │
│  Attack    ──█────── 10 ms        │  Ratio     ──█────── 4.0 : 1         │
│  Release   ──█────── 100 ms       │  Attack    ──█────── 5 ms            │
│  ☐ Eşiği otomatik hesapla         │  Release   ──█────── 120 ms          │
│                                   │  Makeup    ──█────── 0.0 dB          │
├───────────────────────────────────┴──────────────────────────────────────┤
│ [○] LIMITER                                                         [⋮]  │
│  Ceiling ────────█── -1.0 dB                                             │
└──────────────────────────────────────────────────────────────────────────┘
```

Mikrofon sayfasında EQ'nun altına ek olarak **AI GÜRÜLTÜ ENGELLEME** paneli girer.

---

## Görevler

### Profil şeridi
- [ ] Aktif profil kartı (kanal ikonu + aksan rengi + ad), açılır menüyle hızlı geçiş
- [ ] **Favori slotları (9 adet)** — tıklayınca anında geçiş, sürükleyerek sıralama
- [ ] `☆` düğmesi: aktif profili favorilere ekle/çıkar
- [ ] `🔍` gözat: tüm profilleri arama kutusuyla listeleyen açılır panel
- [ ] `⋮` menüsü: **Yeni**, **Yeniden adlandır**, **Kopyala**, **Dışa aktar**, **İçe aktar**, **Sil**, **Sıfırla**
- [ ] Kaydedilmemiş değişiklik göstergesi (profil adının yanında `•`) + "Kaydet" / "Geri al"

### EQ paneli
- [ ] **Logaritmik frekans ızgarası** 20 Hz – 20 kHz; dikey eksen ±12 dB (±24 dB'ye genişletilebilir)
- [ ] SteelSeries'teki gibi üst bant etiketleri: SUB BASS / BASS / LOW MIDS / MID RANGE / UPPER MIDS / HIGHS
- [ ] **Sürüklenebilir band düğümleri**: Y = kazanç, X = frekans, **fare tekerleği = Q**
- [ ] Band başına ayrı renk (SteelSeries'teki renkli noktalar gibi)
- [ ] Seçili bandın detay kutusu: tip, frekans, kazanç, Q, slope — sayısal girilebilir
- [ ] Filtre tipleri: peak, low shelf, high shelf, low pass, high pass, notch
- [ ] Band sayısı seçimi: 5 / 10 / 16 / 32 (LSP `para_equalizer_x8/x16/x32` eşlemesi)
- [ ] Band aç/kapa (çift tık) ve sıfırla (sağ tık → 0 dB)
- [ ] **Bileşik eğri çizimi**
  - [ ] `core/dsp/response.py`: her bandın biquad katsayılarını RBJ cookbook ile hesapla,
        `H(e^jw)` çarpımından toplam magnitude yanıtını numpy ile üret (log ölçekte ~512 nokta)
  - [ ] `QQuickPaintedItem` alt sınıfı ile çizim (QML Canvas'tan hızlı)
  - [ ] Eğri altı hafif dolgu, ızgara çizgileri 1 px, köşesiz
- [ ] **Hızlı slider'lar**: Bass / Voice / Treble — ilgili frekans gruplarındaki bandları birlikte sürer
- [ ] Preamp (`g_in`) kontrolü — pozitif kazançta clip'i önlemek için
- [ ] EQ toggle'ı → `enabled` portu (canlı bypass)

### Dinamik filtre panelleri
- [ ] **Noise Gate**: threshold, attack, release, hold, range; "Eşiği otomatik hesapla"
      (5 sn sessizlik ölçüp taban gürültünün +6 dB üstünü ayarlar)
- [ ] **Compressor**: threshold, ratio, attack, release, knee, makeup gain
- [ ] **Limiter**: ceiling, release; gain-reduction göstergesi (varsa)
- [ ] Her panelin `⋮` menüsü: **Sıfırla**, **Preset yükle**, **Bu aşamayı kopyala/yapıştır**
- [ ] Kapalı paneller soluk ama okunabilir (SteelSeries davranışı)

### Mikrofon sayfasına özel
- [ ] **AI GÜRÜLTÜ ENGELLEME (DeepFilterNet)** paneli:
  - [ ] Aç/kapa toggle
  - [ ] "Min ↔ Max" attenuation limit slider'ı (0–100 dB)
  - [ ] Dalga formu görseli (canlı mikrofon sinyali; kapalıyken gri, açıkken aksan renginde)
  - [ ] Eklenti kurulu değilse: panel devre dışı + `sudo pacman -S deepfilter-ladspa` ipucu
- [ ] Noise Gate paneli, AI gürültü engelleme açıkken soluklaştırılır ve üstünde
      **"AI gürültü engelleme aktifken devre dışı"** notu (SteelSeries davranışı)
- [ ] Mikrofon monitörü (sidetone) aç/kapa + seviye — kendi sesini kulaklıktan duyma
- [ ] `sonar_mic` ile `sonar_stream_mic` arasında sekme; "Zinciri Mic ile paylaş" seçeneği

### Etkileşim
- [ ] Her kontrol değişikliği → `SetFilterParam` (20 ms debounce) → **canlı duyulur**
- [ ] Ctrl+Z / Ctrl+Y — sayfa içi geri al/yinele yığını
- [ ] A/B karşılaştırma: iki geçici durum arasında anlık geçiş (`A` / `B` düğmeleri)
- [ ] Tüm zinciri geçici bypass eden global düğme (değişiklikleri karşılaştırmak için)

---

## Doğrulama

- EQ bandını sürüklerken tını **anında** değişiyor, kesinti/tık yok
- Eğri çizimi gerçek DSP yanıtıyla örtüşüyor
  (doğrulama: pembe gürültü çal, `easyeffects` spektrum analizöründe eğri beklendiği gibi görünüyor)
- Profil geçişi anında ve sessiz
- Gate/Compressor gerçekten çalışıyor (mikrofona fısıldayınca gate kesiyor)
- DeepFilterNet açılınca arka plan gürültüsü belirgin azalıyor
- Kurulu olmayan eklenti paneli çökmeye sebep olmuyor, açıklayıcı mesaj gösteriyor

---

## Tamamlanma kriteri

Kullanıcı bir kanal için EQ ve filtreleri ayarlayıp profil olarak kaydedebiliyor,
birden fazla profil arasında anında geçiş yapabiliyor; mikrofon zinciri
AI gürültü engelleme dahil tam çalışıyor.
