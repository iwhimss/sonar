# Faz 9 — Profiller, presetler ve ChatMix

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 8
**Çıktı:** `src/sonar/core/{presets,importers}.py`, `src/sonar/engine/headset.py`,
`packaging/99-sonar-headset.rules` — 112 yeni test (toplam 712)

---

## Amaç

Kullanıcının asıl istediği senaryoyu tamamlamak:

> "Bir kanal için birden fazla EQ ayarı yapıp kaydedebilmeliyim. Örnek olarak oyun kanalı için
> CS2 için ayrı EQ ve filtre, Arc Raiders için ayrı EQ ve filtre ayarlayıp aralarında hızlıca
> geçiş yapabilmeliyim."

Ayrıca ChatMix (oyun ↔ sohbet dengesi) ve hazır preset kütüphanesi.

---

## Faz 8'den devreden

- [x] Profil kopyalama (`CopyProfile`), dışa/içe aktarma (`.sonarprofile`), sıfırlama
- [ ] Gözat paneli (arama kutusu) — **yapılmadı**, profil sayısı azken açılır liste yeterli
- [ ] Panel başına `⋮` menüsü — **yapılmadı**; "Sıfırla" profil şeridine kondu
- [ ] Noise Gate "eşiği otomatik hesapla" — **yapılmadı** (5 sn taban gürültü ölçümü gerekiyor)
- [ ] Mikrofon dalga formu — **yapılmadı**
- [ ] `mic` ↔ `stream_mic` sekmesi — **yapılmadı**
- [ ] Ctrl+Z / Ctrl+Y, A/B karşılaştırma, global bypass — **yapılmadı**

Kalanlar `.plan/99-backlog.md`'ye taşındı.

---

## Görevler

### Preset kütüphanesi (`core/presets.py`)
- [x] Çıkış kanalları: `Flat`, `FPS Footsteps`, `Bass Boost`, `Vocal Clarity`,
      `Night Mode`, `Movie`, `Music`
- [x] Mikrofon: `Flat`, `Broadcast`, `Podcast`, `Aggressive Cleanup`
- [x] **Presetler salt okunur.** Düzenlenmeye başlanınca `"<ad> (özel)"` adıyla kopya
      oluşturulup ona geçiliyor; kopya adları çakışmıyor (`(özel 2)`, `(özel 3)`…)
- [x] Preset formatı kullanıcı profilleriyle birebir aynı
- [x] Her çağrı **taze bir kopya** döndürüyor (ortak nesne paylaşılmıyor)
- [x] Preset üzerine yazma / silme / yeniden adlandırma reddediliyor

**Plandan sapma:** presetler `src/sonar/presets/` altında dosya değil, `core/presets.py`
içinde **Python verisi**. Kod incelemesinden geçiyorlar, paketleme kenar durumu yok ve
"dosya okunamadı" diye bir hata yolu kalmıyor.

### İçe / dışa aktarma (`core/importers.py`)
- [x] `.sonarprofile` — şema sürümlü JSON; daha yeni sürüm reddediliyor
- [x] **AutoEQ `ParametricEQ.txt`** — kulaklık düzeltme eğrilerinin fiili standardı
- [x] **Equalizer APO `config.txt`** — Windows'tan taşıma
- [x] **EasyEffects preset `.json`** — EQ bölümü
- [x] Dışa aktarma: `.sonarprofile` **ve** AutoEQ metin biçimi
- [x] **Biçim içerikten bulunuyor**, uzantıya güvenilmiyor
- [x] Band sayısı desteklenen kapasiteye yuvarlanıyor (3 → 5, 7 → 10, 12 → 16, 20 → 32)
- [x] 32'den fazla band: en **zayıf kazançlılar** düşüyor ve kullanıcı uyarılıyor
- [x] Kullanılmayan bandlar `OFF` yapılıyor — aksi hâlde varsayılan frekanslar eğriye sızıyor
- [x] CLI: `sonar-cli import|export|presets|reset`

### ChatMix
- [x] Tek slider (0–100), 50 = nötr
- [x] **Yalnızca `personal` fader'larını etkiliyor** — ölçüldü, yayın miksi hiç değişmiyor
- [x] Kısma dB tabanlı (algısal), taban `-40 dB`
- [x] **Bir tarafa birden fazla kanal** verilebiliyor (`"chat,media"`). Yeni alan eklemek
      yerine mevcut alan çoğullaştırıldı; eski yapılandırmalar olduğu gibi okunuyor
- [x] Arayüzde kısılan kanalın fader'ının altında `ChatMix %N` rozeti — fader taban
      değeri gösteriyor, duyulan ses taban × çarpan
- [x] Kullanıcı fader'ı elle oynatırsa taban değer güncelleniyor, ChatMix üstüne uygulanıyor

### Donanım ChatMix tekeri (`engine/headset.py`)
- [x] Bilinen kulaklıkların HID düğümleri tespit ediliyor (SteelSeries 5 model)
- [x] Erişilebilirlik kontrolü + kullanıcıya ne yapması gerektiğini söyleyen mesaj
- [x] `packaging/99-sonar-headset.rules` — `uaccess` etiketli udev kuralı
- [ ] **Teker konumunun okunması yapılmadı.** Gerekçe aşağıda

**Araştırma sonucu (bu makine, SteelSeries Arctis 7+ `1038:220e`):**
planın öngördüğü "Game ve Chat ayrı iki USB ses cihazı" durumu **geçerli değil** —
PipeWire cihazı tek çıkış + tek giriş olarak görüyor ve teker ALSA'da bir kontrol olarak
görünmüyor. Konum HID üzerinden geliyor ama `/dev/hidraw*` düğümleri `crw------- root root`.

Teker okumak iki şey gerektiriyor: udev kuralı **ve** cihaza özel HID rapor biçiminin
çözülmesi. İkincisi cihazdan okumadan doğrulanamaz; doğrulanmamış bir protokol yazmak HID'e
körlemesine veri göndermek demek. Bu yüzden yalnızca tespit yapıldı — kural kurulduktan
sonra biçimi çözmek küçük bir iş, backlog'da kayıtlı.

---

## Doğrulama — ✅ ölçülerek

### Kullanıcının asıl senaryosu

Game kanalı için iki profil oluşturuldu (CS2: 2 kHz +9 dB, Arc Raiders: 2 kHz -9 dB),
favori slotlarına atandı, aralarında geçiş yapılıp **ses ölçüldü**:

| profil | ölçülen (2 kHz) | D-Bus çağrısı |
|---|---|---|
| CS2 | **+9.00 dB** | 11.4 ms |
| Arc Raiders | **-9.00 dB** | 13.2 ms |
| CS2 | **+9.00 dB** | 9.7 ms |
| Arc Raiders | **-9.00 dB** | 10.5 ms |

**Kesinti testi:** müzik çalarken 3.4 saniyede **12 geçiş** yapıldı —
**0 dropout, 0 tık** (en büyük örnek adımı teorik değerin 1.29 katı, eşik 1.5).

> İlk analizde 3 tık görünmüştü; üçü de kaydın sonunda, yani testin sesi ortadan
> kesmesinden kaynaklanıyordu. Kuyruk atılınca kayıt temiz.

### ChatMix

İki uygulama **farklı frekanslarda** çalındı (oyun 300 Hz, sohbet 900 Hz) ve kayıtlar
spektral olarak ayrıldı — aynı tonu kullanmak faz girişimi yüzünden yanıltıcı sonuç veriyor
(bir kez o tuzağa düşüldü):

| ChatMix | kulaklık oyun | kulaklık sohbet | yayın oyun | yayın sohbet |
|---|---|---|---|---|
| 50 (nötr) | -21.9 | -21.9 | -21.9 | -21.9 |
| 0 (tam oyun) | -21.9 | **-62.0** | -21.9 | -21.9 |
| 100 (tam sohbet) | **-61.9** | -21.9 | -21.9 | -21.9 |
| sağ = chat + media, 100 | **-62.1** | -21.9 | -21.9 | -21.9 |

Kulaklıkta doğru kanal ~40 dB kısılıyor, **yayın miksi hiçbir durumda değişmiyor**.

### Presetler ve içe/dışa aktarma

```
$ sonar-cli presets game
🔒 Flat / FPS Footsteps / Bass Boost / Vocal Clarity / Night Mode / Movie / Music
   Default

$ sonar-cli import game hd650.txt --name HD650
içe aktarıldı: HD650  (biçim: autoeq, 5 band)

$ sonar-cli export game --autoeq        # birebir aynı metin geri geliyor
```

Preset'lerin ses karakteri de test ediliyor: `FPS Footsteps` 3 kHz'i >4 dB yükseltip 40 Hz'i
kısıyor, `Bass Boost` yalnızca altı kaldırıyor, `Broadcast` 30 Hz'i >6 dB kesiyor. Bu testler
eğrinin gerçek DSP yanıtı olduğu ölçüldüğü için (Faz 8, 0.01 dB) anlamlı.

---

## Yol boyunca yakalananlar

1. **Aynı frekansta iki ton ölçümü bozuyor.** ChatMix testinde iki uygulama da 440 Hz
   çalınca faz girişimi sonucu "yayın miksi değişiyor" gibi gösterdi. Farklı frekanslar +
   FFT ile ayrıştırınca gerçek tablo çıktı. Ürün doğruydu, ölçüm yanlıştı.
2. **Profil geçişi tıkı sanılan şey testin kendi kuyruğuydu** — kaydı ortadan kesmek
   süreksizlik yaratıyor. Pencere düzeltilince 0 tık.
3. **Donanım tekeri için varsayım yanlıştı.** Plan "iki ayrı USB cihaz" bekliyordu; Arctis 7+
   tek cihaz olarak görünüyor ve teker HID'de, root'a kapalı.

---

## Tamamlanma kriteri — ✅ karşılandı

Kullanıcı bir kanal için istediği kadar profil kaydedip favori slotlarından **anında ve
kesintisiz** geçiş yapabiliyor (ölçüldü: 12 geçişte 0 dropout, 0 tık); ChatMix kişisel miksi
ayarlarken yayın miksini bozmuyor (ölçüldü); hazır presetler salt okunur ve AutoEQ / APO /
EasyEffects içe aktarma çalışıyor.

```bash
ruff check src/ tests/ && pytest -q          # 712 test geçti, lint temiz
```
