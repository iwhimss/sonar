# Faz 6 — Seviye ölçümü

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 4
**Çıktı:** `src/sonar/engine/meters.py`

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

- [ ] `MeterSource` — bir node için `pw-cat` alt süreci, ham baytları okuyup numpy dizisine çevirme
- [ ] Peak + RMS hesabı (20 ms pencere), dB dönüşümü (`20*log10`, -60 dB taban)
- [ ] **Peak-hold**: tepe değer 1.5 sn tutulur, sonra 20 dB/s düşer (klasik mikser davranışı)
- [ ] **Clip algılama**: |x| ≥ 0.999 → clip bayrağı, 2 sn yanar
- [ ] `MeterManager` — abonelik sayacı; 0 → tüm süreçleri durdur, >0 → gerekli node'lar için başlat
- [ ] Ölçüm noktaları: her kanalın `_fx` node'u, `sonar_personal`, `sonar_stream`,
      `sonar_mic`, `sonar_stream_mic`
- [ ] `LevelsUpdated` sinyali — tüm noktalar tek JSON'da, 50 ms'de bir (20 Hz, göz için yeterli)
- [ ] Alt süreç ölürse sessizce yeniden başlat (node kaybolduysa yeniden başlatma)
- [ ] Graf yeniden kurulduğunda (`GraphRebuilt`) ölçüm kaynakları yeniden bağlanır
- [ ] CPU ölçümü: 10 kaynak açıkken daemon CPU kullanımı raporlanır (hedef < %2 tek çekirdek)

## Soyutlama notu

`MeterManager` arayüzü `pw-cat`'ten bağımsız tutulur. İleride CPU sorun olursa
libpipewire tabanlı **tek** native yardımcı süreçle (Rust/C, ~200 satır) değiştirilebilir;
D-Bus sinyali ve GUI tarafı aynı kalır.

---

## Doğrulama

```bash
sonar-cli status --json | jq .levels     # abone olunca değerler akmalı
busctl --user monitor io.github.iwhimss.Sonar | grep LevelsUpdated
```

- Sessizlikte tüm değerler -60 dB civarı
- Müzik çalarken ilgili kanal oynuyor, diğerleri sessiz (izolasyon doğru)
- Mikrofona konuşurken `sonar_mic` oynuyor
- `SubscribeMeters(false)` sonrası `pgrep pw-cat` boş dönüyor (süreçler gerçekten durdu)
- Uzun süre açık bırakıldığında bellek sızıntısı yok

---

## Tamamlanma kriteri

GUI abone olduğunda metreler akıcı ve doğru; abone yokken hiçbir ölçüm süreci çalışmıyor.
