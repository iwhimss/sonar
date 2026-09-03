# Faz 21 — Mikrofon yönlendirme

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 19 (canlı arayüz)
**Çıktı:** `src/sonar/engine/router.py`, `core/model.py`, `daemon/api.py`,
`gui/bridge.py`, `gui/qml/ChannelStrip.qml`, `Mixer.qml`

---

## Amaç

Kullanıcının isteği: *"Uygulamaları çıkış cihazları arasında taşıyabiliyoruz fakat
mikrofonlarda taşıyamıyoruz. Discord hem çıkış kanallarında hem giriş kanallarında
görünmeli; hangi uygulamanın hangi mikrofonu kullanacağını seçebilmeliyim."*

Altyapı zaten var: `pwstate` yakalama akışlarını `is_capture` ile envanterde tutuyor.
Eksik olan yalnızca yönlendirme kararı ve arayüz.

---

## Görevler

- [x] `bridge.stream_rows` `is_capture` akışlarını atmayı bırakır; her satır
      `direction: "in" | "out"` taşır. Arayüzde `IN` / `OUT` rozeti.
- [x] Bir yakalama akışının "kanalı" hangi Sonar giriş zincirini dinlediğidir
      (`target.object` → `sonar_<mic>`). `api.get_streams` bunu hazır verir.
- [x] Giriş kanalı şeritleri kendi Apps kutusunu kazanır (bugün `visible: !isMic` ile gizli).
- [x] `RoutingRule` yeni `direction: "out" | "in"` alanı (varsayılan `out`); mevcut
      kurallar göçte `out` olur. Bir uygulamanın hem çıkış hem giriş kuralı olabilir.
- [x] `Router._is_routable` giriş akışlarını da kabul eder; `choose_channel` yöne göre
      kanal ya da mikrofon zinciri seçer. Varsayılan giriş zinciri
      `settings.default_mic_chain`.
- [x] Taşıma mekanizması aynı: `pw-metadata <id> target.object sonar_<mic>`.
      `api.move_stream` hedefin kanal mı mikrofon zinciri mi olduğunu ayırır —
      ayrı bir API'ye gerek yok.
- [x] Sürükle-bırak: çıkış kutucuğu giriş şeridine bırakılamaz. `DropArea` yön
      uyuşmazlığında vurgu vermez ve bırakmayı reddeder.
- [x] `sonar-cli apps` çıktısı yönü gösterir; `sonar-cli move` giriş akışlarını kabul eder.

---

## Kabul ölçütü

- [x] Discord çıkış şeridinde `OUT`, giriş şeridinde `IN` olarak aynı anda görünüyor
- [x] `pw-cat --record` akışı iki giriş zinciri arasında taşınıyor ve her seferinde
      hedef zincirin DSP'sinden geçiyor (dar bantlı EQ çentiği ile ölçülür)
- [x] Uygulama kapanınca her iki listeden de düşüyor (Faz 14 düzeltmesi giriş için de geçerli)


---

## Uygulanan hâli

`RoutingRule` yeni bir `direction` alanı kazandı (`out` = uygulamanın çaldığı ses,
`in` = dinlediği mikrofon; varsayılan `out`, eski kurallar olduğu gibi okunuyor —
şema değişikliği gerekmedi). `choose_channel` akışın yönüne göre yalnızca o yöndeki
kurallara bakıyor; eşleşme yoksa `settings.default_channel` ya da yeni
`settings.default_mic_chain` devreye giriyor.

Taşıma tek yol: `Router.target_node_for` hedefin kanal mı mikrofon zinciri mi olduğunu
çözüyor, `pw-metadata target.object` ikisinde de aynı şekilde çalışıyor. Ayrı bir
`move_capture_stream` API'sine gerek kalmadı.

## Ölçümler (canlı graf, 2026-09-03)

| Ölçüm | Sonuç |
|---|---|
| Yakalama akışı yönlendiriliyor | `pw-cat --record` açılır açılmaz `sonar_mic`'e gitti |
| Zincirler arası taşıma | `sonar-cli move 117 stream_mic` → `pw-link` bağlantısı `sonar_stream_mic:capture_FL → pw-cat:input_FL` oldu |
| Yön ayrımı | `Discord` için hem `→ SES chat` hem `← MİK stream_mic` kuralı yan yana duruyor, birbirini ezmiyor |
| Masaüstü yakalaması korunuyor | cava `(yönlendirilmedi)` kalıyor |

## Yol boyunca yakalananlar

**cava sessizce mikrofona çekildi.** Yakalama akışları yönlendirilmeye başlayınca
`cava` (masaüstü ses görselleştiricisi) `sonar_mic`'e taşındı ve kullanıcının
görselleştiricisi bozuldu. Ayırt edici bayrak `stream.capture.sink` — ölçülerek bulundu.
`StreamInfo.captures_sink` eklendi; bu akışlar ne yönlendiriliyor ne de mikrofon
şeridinde gösteriliyor. OBS'in "Masaüstü Sesi" kaynağı da aynı kapsamda.

**PySide6'da `QDBusInterface.call(method, *args)` en fazla 4 argüman alıyor**;
5 argümanlı `SetRule` çağrısı `TypeError` verdi. Hem CLI hem GUI istemcisi
`callWithArgumentList(QDBus.CallMode.Block, ...)` kullanacak şekilde değiştirildi —
bu sınır bir sonraki metotta yine karşımıza çıkardı.
