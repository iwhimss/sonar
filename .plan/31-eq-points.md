# Faz 31 — EQ: nokta ekleme ve silme

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 26

---

Kullanıcı: *"Bandlar kısmından sayı seçmek yerine EQ ayarında bir yere sağ tık ile ekle
diyip nokta ekleyebilmek veya olan noktayı silebilmek istiyorum."*

- [x] "BANDLAR" açılır menüsü kaldırılsın. `EqState.band_count` alanı kalsın ama artık
      `len(bands)` ile senkron tutulsun (şema göçü gerekmez).
- [x] `EqPanel` eğri alanında **sağ tık → o frekansta yeni band**, band düğümünde
      **sağ tık → sil**. Yeni bandın frekansı tıklanan x, kazancı tıklanan y, `Q` 1.41.
- [x] Yeni API: `AddEqBand(target, freq, gain_db)` → yeni bandın indeksi;
      `RemoveEqBand(target, index)`. İkisi de **canlı** olmalı.
- [x] **Bunun için EQ eklentisi kapasitesi sabitlenecek.** Bugün band sayısı
      `para_equalizer_x8/16/32` arasında seçim yapıyor ve değişimi **yapısal**.
      İlk uygulama adımı: x32'nin boştaki ve ses akarkenki CPU maliyetini ölçmek.
      Kabul edilebilirse zincir her zaman x32 kursun ve band ekleme/silme tamamen canlı
      olsun. Değilse kapasite basamağı aşıldığında yeniden inşa olacağı arayüzde söylensin.
- [x] Üst sınır kapasiteye eşit (32); sınırda "ekle" pasifleşsin.
- [x] `core/importers.py` içe aktarımı band sayısını artık kırpmasın, gelen kadar band
      oluştursun (kapasiteye kadar).

**Ölçüm:** 10 banddan 20'ye çıkarken ses kesilmiyor; çizilen eğri ile ölçülen yanıt
arasındaki sapma Faz 8'deki gibi ≤0.01 dB kalıyor.


---

## Uygulanan hâli

**EQ kapasitesi sabitlendi: her zaman `para_equalizer_x32`.** Bunun ölçümü fazın ilk
adımıydı — altı zincirde, ses akarken: x16 **%11.6**, x32 **%12.0**. Kullanılmayan
bandlar `ft = 0` ile kapalı ve analizörler zaten kapalı olduğu için fark neredeyse yok.
Karşılığında band eklemek/silmek tamamen canlı oldu.

"BANDLAR" açılırı kalktı; yerinde yalnızca "N band" yazıyor. Eğride:

* **boşluğa sağ tık** → o frekansa yeni nokta
* **düğüme sağ tık** → o noktayı sil (son band silinemez)

Yeni API: `AddEqBand(target, freq, gain_db)` → indeks, `RemoveEqBand(target, index)`.
`SetBandCount` kalktı. Bandlar frekansa göre sıralı tutuluyor: kullanıcı eğriye
baktığında soldan sağa gitmesi bekleniyor.

## Ölçümler (canlı graf, 2026-09-04)

| Ölçüm | Sonuç |
|---|---|
| Band eklemek grafı kuruyor mu | `sonar_game` id 112 → 112 — **hayır** |
| Sıralama | 3 kHz ve 7 kHz eklendi, liste 31…16000 sıralı kaldı |
| Eklenen bandın gerçek yanıtı | 3 kHz'de -18 dB çentik: **-26.03 → -44.03 dBFS** (tam -18.00) |
| Silince | **-26.03 dBFS** — birebir eski hâline döndü |

## Yol boyunca yakalananlar

**CPU ölçümü baştan yanlıştı.** `pgrep -f "pipewire -c <conf>"` `timeout` sarmalayıcısını
yakalıyordu ve her şey %0.0 okunuyordu. Bu oturumda tek başına conf ile yapılan tüm
ölçümleri etkiledi; `pipewire` sürecinin kendi PID'iyle yeniden ölçüldü ve
`.plan/30-dsp.md` içindeki crossfeed sayıları düzeltildi.
