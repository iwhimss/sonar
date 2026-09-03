# Faz 21 — Mikrofon yönlendirme

**Durum:** ⚪ Bekliyor
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

- [ ] `bridge.stream_rows` `is_capture` akışlarını atmayı bırakır; her satır
      `direction: "in" | "out"` taşır. Arayüzde `IN` / `OUT` rozeti.
- [ ] Bir yakalama akışının "kanalı" hangi Sonar giriş zincirini dinlediğidir
      (`target.object` → `sonar_<mic>`). `api.get_streams` bunu hazır verir.
- [ ] Giriş kanalı şeritleri kendi Apps kutusunu kazanır (bugün `visible: !isMic` ile gizli).
- [ ] `RoutingRule` yeni `direction: "out" | "in"` alanı (varsayılan `out`); mevcut
      kurallar göçte `out` olur. Bir uygulamanın hem çıkış hem giriş kuralı olabilir.
- [ ] `Router._is_routable` giriş akışlarını da kabul eder; `choose_channel` yöne göre
      kanal ya da mikrofon zinciri seçer. Varsayılan giriş zinciri
      `settings.default_mic_chain`.
- [ ] Taşıma mekanizması aynı: `pw-metadata <id> target.object sonar_<mic>`.
      `api.move_stream` hedefin kanal mı mikrofon zinciri mi olduğunu ayırır —
      ayrı bir API'ye gerek yok.
- [ ] Sürükle-bırak: çıkış kutucuğu giriş şeridine bırakılamaz. `DropArea` yön
      uyuşmazlığında vurgu vermez ve bırakmayı reddeder.
- [ ] `sonar-cli apps` çıktısı yönü gösterir; `sonar-cli move` giriş akışlarını kabul eder.

---

## Kabul ölçütü

- [ ] Discord çıkış şeridinde `OUT`, giriş şeridinde `IN` olarak aynı anda görünüyor
- [ ] `pw-cat --record` akışı iki giriş zinciri arasında taşınıyor ve her seferinde
      hedef zincirin DSP'sinden geçiyor (dar bantlı EQ çentiği ile ölçülür)
- [ ] Uygulama kapanınca her iki listeden de düşüyor (Faz 14 düzeltmesi giriş için de geçerli)
