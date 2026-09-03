# Faz 25 — Kırık kontroller

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** —
**Çıktı:** `src/sonar/engine/meters.py`, `engine/pwstate.py`, `daemon/api.py`,
`gui/bridge.py`, `gui/qml/ChannelStrip.qml`, `gui/qml/ui/SonarSlider.qml`

---

## Amaç

Test turu 3'te ortaya çıkan "hiç çalışmıyor" sınıfı hataları kapatmak. Bunlar durmadan
diğer her şeyin testini engelliyor, bu yüzden turun ilk fazı.

---

## Ölçülmüş kök nedenler

| Belirti | Kök neden |
|---|---|
| Seviye barları graf yeniden kurulunca boşalıyor | `MeterManager.configure()` `_stop_sources()` + `_start_sources()` yapıyor ama **`_schedule()` çağırmıyor**. `_stop_sources()` 20 Hz tick zamanlayıcısını iptal ediyor; bir daha kurulmuyor. |
| İkinci giriş kanalının düğmeleri `mic`'i sürüyor | `bridge.setMicVolume/setMicMute/setMicMonitor/setMicDevice` zincir kimliğini **sabit `"mic"`** yazıyor. |
| Smart Volume açılamıyor | `bridge.setDucking` QML'den gelen `QJSValue`'yu `dict()`'e veriyor → `TypeError`. |
| ChatMix "Sıfırla" slider'ı oynatmıyor | `SonarSlider.apply()` `root.value = v` yaparak `value: bridge.chatmix / 100` bağlamasını koparıyor. |
| Kendi `pw-cat`'lerimiz uygulama listesinde | `StreamInfo.is_internal` yalnızca `node.name` `sonar_` ile başlıyorsa `True`; ölçüm süreçlerinin adı `pw-cat`. |
| OBS uygulama olarak görünmüyor | `captures_sink` süzgeci OBS'in masaüstü yakalamasını **arayüzden de** eliyor; `sonar_stream_out`'u dinleyen ikinci akış hiçbir şeride düşmüyor. |

---

## Görevler

- [x] `MeterManager.configure()` abonelik varken yeniden başlattıktan sonra `_schedule()`
      çağırsın. Regresyon testi: `configure()` sonrası `on_levels` yeniden çağrılıyor.
- [x] Metreler yalnızca `_structural` yolunda değil, **her** yeniden inşadan sonra
      kurulsun: `api` `supervisor.on_rebuild` dinleyicisine `meters.configure(...)` eklesin
      (çökme kurtarması ve PipeWire restart yolları bugün atlanıyor).
- [x] `bridge.setMicVolume/setMicMute/setMicMonitor/setMicDevice` zincir kimliği alsın;
      `ChannelStrip` kendi `root.id`'sini geçsin, `_optimistic` doğru satırı yamalasın.
- [x] `bridge.setDucking` `QJSValue`'yu `toVariant()` ile çözsün.
- [x] `SonarSlider` bağlamayı koparmasın: sürükleme yalnızca `moved()` yayınlasın,
      `value` dışarıdan sürülsün (`SonarFader`'daki desenin aynısı).
- [x] Ölçüm süreçleri kendilerini tanıtsın: `MeterSource` `pw-cat`'e
      `--media-category Manager` yerine ayırt edici bir `node.name` versin
      (`sonar_meter_<hedef>`), `is_internal` böylece ad tahminine dayanmasın.
- [x] `captures_sink` yalnızca `Router`'da eleme sebebi olsun; `bridge.stream_rows`
      masaüstü yakalayıcılarını **göstersin**. Bus'ı dinleyen akışlar (`sonar_stream_out`,
      bus monitörü) master şeridinde listelensin.

---

## Kabul ölçütü

- [x] Kanal eklendikten sonra metreler oynamaya devam ediyor
- [x] İkinci giriş kanalının mute'u yalnızca kendi zincirini susturuyor (`pw-dump`)
- [x] Smart Volume anahtarı `TypeError` vermeden çalışıyor
- [x] ChatMix "Sıfırla" slider'ı gerçekten ortaya getiriyor
- [x] `sonar-cli status` çıktısında `pw-cat` yok, OBS var


---

## Yol boyunca yakalananlar

**`SonarFader` de aynı bağlama hatasını yapıyormuş.** `SonarSlider`'ı düzeltirken fark
edildi: fader da sürüklerken `root.value = v` yazıyordu, yani **bir kez sürüklenen fader
daemon'daki değeri bir daha takip etmiyordu**. Profil değiştirmek, mute etmek, "Sıfırla"
demek tutamağı oynatmıyordu. Köprü zaten iyimser güncelleme yaptığı için (`_optimistic` +
`_hold`) yerel yazıma hiç gerek yokmuş.

**Sidetone fader'ının karşılığı yokmuş.** Giriş şeridindeki kulaklık fader'ı
`setVolume("output", …)` çağırıyor ama `ChannelStrip` mikrofonda yalnızca `"stream"`
dalını ele alıyordu; fader sessizce hiçbir şey yapmıyordu. `SetMicMonitorVolume` D-Bus
metodu ve `api.set_mic_monitor_volume` eklendi.

**Ölçümler (canlı graf, 2026-09-03):**

| Ölçüm | Sonuç |
|---|---|
| Metreler yeniden inşadan sonra | `levelsRevision` 31 → **166** (akıyor) |
| İkinci giriş kanalının mute'u | `sonar_test mute=True`, `sonar_mic mute=False` |
| Uygulama listesi | 7 adet `pw-cat` gitti; OBS'in iki kaynağı göründü |
| Smart Volume anahtarı | `TypeError` yok |
