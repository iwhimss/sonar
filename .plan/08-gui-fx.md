# Faz 8 — Kanal FX sayfası (EQ ve filtreler)

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 7
**Çıktı:** `src/sonar/core/dsp/response.py`, `src/sonar/gui/eqcurve.py`,
`qml/{ChannelFx,EqPanel}.qml`, `qml/ui/{SonarParamRow,SonarFilterPanel,SonarNumberField}.qml`
— 58 yeni test (toplam 600)
Ekran görüntüleri: `docs/reference/sonar-fx-game.png`, `sonar-fx-mic.png`

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

## Ölçüm: eğri gerçeği gösteriyor mu?

Planın en önemli iddiası buydu — çizilen eğrinin **tahmini bir görsel değil**, gerçek DSP
yanıtı olması. Faz 1'de LSP filtre modeli bilinçli olarak `fm_N = 6` ("APO DR") seçilmişti
çünkü RBJ cookbook biquad'larıyla örtüşüyor. Artık ölçüldü.

Üç bandlı belirgin bir eğri kuruldu, her frekansta sinüs basılıp `sonar_game_fx`'ten
kaydedildi ve EQ kapalı hâle göre farkı alındı:

| Hz | çizilen | ölçülen | fark |
|---|---|---|---|
| 63 | +1.57 | +1.55 | -0.01 |
| 125 | +7.90 | +7.90 | -0.00 |
| 250 | +1.15 | +1.15 | 0.00 |
| 500 | -1.69 | -1.69 | 0.00 |
| 1000 | -9.89 | -9.89 | -0.00 |
| 2000 | -1.83 | -1.83 | 0.00 |
| 4000 | +0.38 | +0.38 | 0.00 |
| 8000 | +4.92 | +4.92 | 0.00 |

**Ortalama sapma 0.00 dB, en büyük 0.01 dB.** Kullanıcı ekranda ne görüyorsa kulağında o var.

Arayüz köprüsü üzerinden de doğrulandı (band 6, 2 kHz):

| istenen | ölçülen | çizilen | fark |
|---|---|---|---|
| +9 dB | +9.00 | +9.00 | 0.00 |
| -9 dB | -8.97 | -9.00 | +0.03 |
| 0 dB | +0.00 | -0.00 | 0.00 |

---

## Görevler

### `core/dsp/response.py` — eğrinin matematiği
- [x] RBJ cookbook biquad katsayıları: peak, low/high shelf, low/high pass, notch,
      allpass, bandpass
- [x] `slope` (LSP `s_N`) kaskatlama: 0 → ×1 … 3 → ×4
- [x] Bandların çarpımından bileşik magnitude yanıtı (512 nokta, log ızgara)
- [x] Preamp eğriyi topluca kaydırır
- [x] EQ kapalıyken düz çizgi — kullanıcı bypass'ta ne duyduğunu görüyor
- [x] Nyquist'e dayanan band, sıfır Q gibi uç durumlar patlamıyor

### `gui/eqcurve.py` — çizim
- [x] `QQuickPaintedItem` alt sınıfı (QML `Canvas` her karede JavaScript'e dönerdi)
- [x] Logaritmik frekans ızgarası + dB çizgileri + üst bant etiketleri
      (SUB BASS / BASS / LOW MIDS / MID RANGE / UPPER MIDS / HIGHS)
- [x] Eğri altı gradyan dolgu, aksan renginde çizgi
- [x] Band düğümleri **kare** (köşesiz tasarım dili), band başına ayrı renk
- [x] Koordinat çevirimi QML'e açık: `xForFreq`, `freqForX`, `yForGain`, `gainForY`, `bandAt`
- [x] Ölçek seçimi ±6 / ±15 / ±24 / ±36 dB

### EQ paneli
- [x] Sürüklenebilir band düğümleri: Y = kazanç, X = frekans
- [x] **Fare tekerleği = Q** (seçili band)
- [x] Çift tık = bandı aç/kapa, sağ tık = 0 dB'ye sıfırla
- [x] Seçili bandın detayı: tip, frekans, kazanç, Q — sayısal girilebilir
- [x] Filtre tipleri: peak, low/high shelf, low/high pass, notch, kapalı
- [x] Band sayısı 5 / 10 / 16 / 32
- [x] Hızlı slider'lar: Bass (20–250) / Voice (250–4k) / Treble (4k–20k)
- [x] Preamp kontrolü
- [x] EQ toggle → `enabled` portu, canlı bypass

### Dinamik filtre panelleri
- [x] **Noise Gate**: eşik, atak, bırakma, azaltma
- [x] **Compressor**: eşik, oran, atak, bırakma, makyaj
- [x] **Limiter**: tavan, ileri bakış, bırakma
- [x] Kapalı paneller soluk ama okunabilir
- [ ] "Eşiği otomatik hesapla" — **yapılmadı** (5 sn taban gürültü ölçümü gerekiyor)
- [ ] Panel başına `⋮` menüsü (sıfırla / preset / kopyala-yapıştır) — **yapılmadı**

### Mikrofon sayfasına özel
- [x] **AI Gürültü Engelleme** paneli: aç/kapa, azaltma sınırı, post filtre
- [x] Noise Gate, AI açıkken soluklaşıyor ve **"AI aktifken devre dışı"** notu çıkıyor
- [ ] Dalga formu görseli — **yapılmadı**
- [ ] Eklenti kurulu değilse özel mesaj — **yapılmadı** (aşama zincirden sessizce düşüyor)
- [ ] `mic` ↔ `stream_mic` sekmesi ve "zinciri paylaş" — **yapılmadı**

### Profil şeridi
- [x] Aktif profil açılır menüsü, hızlı geçiş
- [x] **Favori slotları (9 adet)** — tıklayınca atanır/kaldırılır
- [x] "Farklı kaydet" ve "Sil"
- [ ] Arama kutulu gözat paneli, dışa/içe aktarma, kopyalama — **Faz 9'a**
- [ ] Kaydedilmemiş değişiklik göstergesi — **gereksiz**: düzenlemeler aktif profile
      otomatik kalıcı (Faz 4 kararı)

### Etkileşim
- [x] Her kontrol değişikliği canlı duyuluyor (ölçüldü)
- [x] İyimser güncelleme: eğri daemon'ı beklemeden tazeleniyor
- [ ] Ctrl+Z / Ctrl+Y — **yapılmadı**
- [ ] A/B karşılaştırma — **yapılmadı**
- [ ] Global bypass düğmesi — **yapılmadı** (aşama başına toggle var)

---

## Doğrulama — ✅

| Test | Sonuç |
|---|---|
| Eğri ↔ gerçek DSP | 8 frekansta **ortalama 0.00 dB**, en büyük 0.01 dB sapma |
| Arayüzden EQ değişimi | ±9 dB istendi, **±9.00 / -8.97 dB** ölçüldü |
| Profil geçişi | anında ve sessiz (Faz 4'te ölçüldü) |
| QML yükleme | kök nesne 1, uyarı yok |
| Köşe yuvarlatma | 17 QML dosyasının hiçbirinde yok (test ediyor) |

Ekran görüntüleri: `docs/reference/sonar-fx-game.png` (yeşil aksan, gate + compressor açık),
`docs/reference/sonar-fx-mic.png` (turuncu aksan, AI paneli açık, gate soluk ve uyarılı).

---

## Yol boyunca yakalananlar

1. **Sayaç JSON'a eklenince eğri hiç çizilmedi.** Binding'i tazelemek için `revision`
   sayacını `eqJson()` çıktısının sonuna eklemiştim; JSON bozuluyor ve `eq_from_json()`
   sessizce boş bir EQ döndürüyordu. Izgara çiziliyor ama eğri yok — belirti yanıltıcıydı.
   Sayaç artık yalnızca bağımlılık kurmak için okunup atılıyor.
2. **`id` referansları binding kurulurken `null` olabiliyor.** Ölçek açılır listesi eğriden
   önce tanımlıydı ve `curve.rangeDb` okurken patlıyordu; korumalı hâle getirildi.
3. **`SonarParamRow` `enabled`'ı gölgeliyordu** — `SonarButton`'da yaşanan hatanın aynısı.
4. **Ölçüm kirlendi, DSP değil.** Arayüzden +9 dB verildiğinde ölçülen +8.43 çıktı; sebep
   önceki testlerin `Default` profiline **kompresörü açık bırakmış** olmasıydı (düzenlemeler
   aktif profile otomatik kalıcı — Faz 4 kararı). Zincir temizlenince fark 0.00 dB'ye indi.
   Bu, Faz 9'daki "gömülü preset'ler salt okunur olmalı" notunu doğruluyor.

---

## Tamamlanma kriteri — ✅ karşılandı

Kullanıcı bir kanal için EQ ve filtreleri ayarlayıp profil olarak kaydedebiliyor, profiller
arasında anında geçiş yapabiliyor; mikrofon zinciri AI gürültü engelleme dâhil çalışıyor.
Çizilen eğri gerçek DSP yanıtıyla 0.01 dB içinde örtüşüyor.

**Eksik bırakılanlar** yukarıda `- [ ]` ile işaretli: otomatik gate eşiği, panel `⋮`
menüleri, mikrofon dalga formu, `mic`/`stream_mic` sekmesi, Ctrl+Z, A/B karşılaştırma,
global bypass. Hiçbiri temel işlevi engellemiyor.

```bash
ruff check src/ tests/ && pytest -q          # 600 test geçti, lint temiz
```
