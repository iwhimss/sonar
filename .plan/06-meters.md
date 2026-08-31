# Faz 6 — Seviye ölçümü

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 4
**Çıktı:** `src/sonar/engine/meters.py`, `tests/test_meters.py` — 33 yeni test (toplam 475) — 30'u `test_meters.py`

---

## Amaç

Mikserdeki seviye metrelerini beslemek: her kanalın, bus'ın ve mikrofonun anlık
peak/RMS değerlerini düşük maliyetle ölçüp GUI'ye göndermek.

---

## Yaklaşım

Her ölçüm noktası için düşük örnekleme hızında bir yakalama akışı:

```bash
pw-cat --record --target <node> --rate 8000 --channels 1 --format f32 -
```

8 kHz mono f32 = 32 KB/s. 10 ölçüm noktası için toplam ~320 KB/s — ihmal edilebilir.
Peak ve RMS 20 ms'lik pencerelerde numpy ile hesaplanır.

**Talep üzerine çalışma:** ölçüm yalnızca bir GUI istemcisi `SubscribeMeters(true)` dediğinde
başlar, son istemci gidince durur. Daemon tek başına çalışırken **sıfır maliyet**.

---

## Görevler

- [x] `MeterSource` — bir node için `pw-cat` alt süreci, ham f32 → numpy
- [x] Peak + RMS (50 ms pencere), dB dönüşümü, -60 dB taban
- [x] **Peak-hold**: 1.5 s tutulur, sonra 20 dB/s düşer
- [x] **Clip algılama**: `|x| ≥ 0.999` → 2 sn yanar
- [x] `MeterManager` — abonelik sayacı; 0 → tüm süreçler durur
- [x] Ölçüm noktaları: kanal `_fx`'leri, `sonar_personal`, `sonar_stream`,
      `sonar_mic`, `sonar_stream_mic` (8 nokta)
- [x] `LevelsUpdated` sinyali — tek JSON, 50 ms'de bir (ölçüldü: 3.5 s'de **69 sinyal** ≈ 20 Hz)
- [x] `GetLevels` metodu — anlık okuma
- [x] Alt süreç ölürse yeniden başlatılır
- [x] Graf yeniden kurulduğunda ölçüm noktaları yeniden bağlanır
- [x] `sonar-cli meters` — terminalde canlı metre
- [x] CPU ölçüldü (aşağıya bak)

---

## Ölçümler

### Eklentinin kendi metreleri neden kullanılamadı
LSP `para_equalizer`'ın `iml`/`imr`/`sml`/`smr` ("Input/Output signal meter") çıkış kontrol
portları var ve bedava olurdu. Denendi: PipeWire'ın filter-chain'i **yalnızca giriş**
kontrol portlarını `Props` içinde açığa çıkarıyor, çıkışlar hiç görünmüyor.

### `pw-cat --latency` — bedava üç kat kazanç
Varsayılan 100 ms yerine 500 ms tampon istemek `pw-cat`'in CPU'sunu **%1.00 → %0.33**
düşürüyor. Endişe, metrenin yavaşlaması olurdu; ölçüldü, **değişmiyor**:

| | teslimat aralığı | tepki gecikmesi |
|---|---|---|
| varsayılan (100 ms) | 53.3 ms | 53.3 ms |
| `--latency 500ms` | 53.3 ms | 53.5 ms |
| `--latency 200ms` | 53.3 ms | — |

Sebep: stdout'a akışı pace eden şey `pw-cat`'in tamponu değil, bizim okuma boyumuz
(`WINDOW_S`). Tampon yalnızca `pw-cat`'in kendi uyanma sıklığını belirliyor.

### Analiz penceresi
20 ms'den **50 ms**'ye çıkarıldı — rapor aralığıyla aynı. Daha kısa pencere ekstra bilgi
vermiyor, yalnızca iş parçacığı uyanmalarını artırıyordu (8 kaynakta saniyede 400 → 160).
`analyse()` hızlı yolu da kopyasız hâle getirildi (`isfinite` maskesi her blokta ayırma
yapıyordu; artık yalnızca NaN/inf görülürse ayıklanmış yola düşülüyor).

### CPU — hedef tutturulamadı, dürüst kayıt

| | daemon | graf | `pw-cat` ×8 | net maliyet |
|---|---|---|---|---|
| ilk hâl | %2.62 | +%2.12 | %0.87 | **~%5.6** |
| optimizasyonlardan sonra | %1.87–2.25 | değişken | %0.37–0.87 | **%3.1 – %4.9** |

Plandaki hedef **%2**'ydi; tutturulamadı. Kalan maliyetin çoğu daemon'ın Python tarafında
(saniyede 160 iş parçacığı uyanması + numpy + JSON + D-Bus). Ölçümler arasında sapma
yüksek çünkü graf sürecinin kendi yükü de dalgalanıyor.

**Bağlam:** bu maliyet yalnızca bir istemci abone olduğunda, yani mikser penceresi açıkken
oluşuyor. Abone yokken **sıfır** (doğrulandı: `pgrep pw-cat` → 0). Bir masaüstü uygulaması
için kabul edilebilir; hedefi tutturmak isteyen yol `.plan/99-backlog.md`'de.

---

## Soyutlama notu

`MeterManager` arayüzü `pw-cat`'ten bağımsız tutulur. İleride CPU sorun olursa
libpipewire tabanlı **tek** native yardımcı süreçle (Rust/C, ~200 satır) değiştirilebilir;
D-Bus sinyali ve GUI tarafı aynı kalır.

---

## Doğrulama — ✅ gerçek sistemde

| Test | Sonuç |
|---|---|
| Abone yokken `pgrep pw-cat` | **0** |
| Abone olunca | **8** süreç |
| Sessizlikte 8 nokta | hepsi **-60.00 dB** |
| Oyun sesi çalarken | `game_fx` -20.08, `personal` -20.69, `stream` -20.69, **diğer 5 nokta sessiz** |
| Abonelik bitince | **0** süreç |
| `LevelsUpdated` | 3.5 s'de **69 sinyal** (≈ 20 Hz), peak/rms/hold/clip taşıyor |

### Peak-hold davranışı (canlı ölçüm)

| an | peak | hold |
|---|---|---|
| çalarken | -20.08 | -19.99 |
| ses bitti +0.3 s | -60.00 | **-19.93** (tutuluyor) |
| +1.0 s | -60.00 | **-19.93** |
| +2.0 s | -60.00 | -29.47 |
| +3.0 s | -60.00 | -49.52 |
| +4.5 s | -60.00 | -60.00 |

1.5 s tutup 20 dB/s düşüyor — tam tasarlandığı gibi.

---

## Tamamlanma kriteri — ✅ karşılandı

Abone olunduğunda metreler akıcı ve doğru; abone yokken hiçbir ölçüm süreci çalışmıyor.
CPU hedefi (%2) tutturulamadı — ölçülen %3–5, gerekçesi ve çözüm yolu yukarıda.

```bash
ruff check src/ tests/ && pytest -q          # 475 test geçti, lint temiz
```
