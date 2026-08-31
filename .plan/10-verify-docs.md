# Faz 10 — Uçtan uca doğrulama ve dokümantasyon

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 9
**Çıktı:** `README.md`, `ARCHITECTURE.md` (D-Bus API referansı koddan üretiliyor),
`CONTRIBUTING.md`, `docs/{OBS,PERFORMANCE,TROUBLESHOOTING}.md`

---

## Amaç

Gerçek kullanım senaryolarında sistemi baştan sona sınamak ve kullanıcının (ve gelecekteki
katkıcıların) ihtiyaç duyacağı belgeleri yazmak.

---

## Faz 5'ten devreden — ✅ yapıldı

EasyEffects kullanıcının izniyle durdurulup yönlendirmenin duyulabilir doğrulaması
tamamlandı: hedefsiz açılan bir akışta kayıp **21 ms** (tam bir PipeWire kuantumu), kanal
izolasyonu (-240 dBFS) ve kişisel/yayın ayrımı ölçüldü. Ayrıntı `.plan/05-routing.md`.

Bu faz için kalan: aynı senaryoların **gerçek OBS ve gerçek oyunla** tekrarı.

---

## Test senaryoları

### 1. OBS yayın senaryosu
- [x] Sonar'ın OBS'e sunduğu kaynaklar doğrulandı: `Sonar Stream Mix`, `Sonar Stream Mic`,
      kanal başına `_fx` yakalama noktaları — hepsi `Audio/Source` olarak listeleniyor
- [x] **Telifli müziği yayından çıkarma** ölçüldü (asıl amaç, aşağıya bak)
- [x] `docs/OBS.md` yazıldı: kaynak ekleme, çok track'li kayıt, senkron, sık sorunlar
- [ ] **Gerçek OBS ile kayıt alınmadı.** OBS bir masaüstü uygulaması; kaynak ekleyip
      track atamak birkaç tıklama gerektiriyor ve otomatikleştirilemedi. Sonar tarafındaki
      her şey (kaynakların varlığı, izolasyon, fader davranışı) ölçümle doğrulandı;
      kalan yalnızca OBS'in kendi yapılandırması

### 2. Uygulama yönlendirme senaryosu
- [x] Dört uygulama aynı anda: Arc Raiders → game, Discord → chat, Firefox → media,
      Spotify → media. Dördü de doğru kanala düştü (7–23 ms)
- [x] Elle taşıma ve `--remember` ile kalıcılaştırma çalışıyor
- [x] Kural değişimi yalnızca yeni akışları etkiliyor (açık akışlar korunuyor)
- [ ] Tarayıcının iki sekmesi ayrı ayrı — denenmedi (aynı binary, aynı kural)

### 3. Dayanıklılık
- [x] Graf sürecine `kill -9` → süpervizör yeniden başlattı, 32 node geri geldi
- [x] `pw-dump` izleyicisine `kill -9` → izleyici kendini toparladı, daemon etkilenmedi
- [x] `systemctl --user restart wireplumber` → 32 node ve 116 bağlantı korundu
- [x] Bozuk `config.toml` → yedeklendi, varsayılana düşüldü, daemon ayakta
- [x] **Yazılamayan config dizini** → daemon ayakta kaldı; bu test bir kusur ortaya çıkardı
      (yakalanmamış `PermissionError`), düzeltildi ve test eklendi
- [x] `SIGTERM` → graf düştü, kalan `sonar_*` node: 0
- [ ] Uyku/uyanma, 24 saat sürekli çalışma, USB kulaklığı çıkarıp takma,
      `systemctl --user restart pipewire` — **denenmedi**, oturumu kesintiye uğrattıkları
      için kullanıcının kendi kullanımında doğrulanmalı

### 4. Performans
- [x] **Gecikme ölçüldü: 1.1 ms** (ortanca, n=8) — hedef <15 ms rahatça karşılanıyor.
      Yöntem 20 ms ileri-bakışlı limiter ile doğrulandı (ölçüm 16.1 ms'ye çıktı)
- [x] CPU: boşta %5–7, iki uygulama %7–8, tüm filtreler %9–10, metrelerle %12–13
- [x] **DeepFilterNet ayrı ölçüldü: mikrofon kullanımdayken +%43** (kullanılmıyorken bedava)
- [x] Bellek: toplam ~180–200 MB (hedef <250 MB)
- [x] Sonuçlar `docs/PERFORMANCE.md`'de
- [ ] `pw-top` ile xrun sayımı — yapılmadı

### 5. Ses kalitesi
- [x] Şeffaflık: 5 aşamalı zincir bypass'ta giriş = çıkış (-23.01 dBFS, tekrarlanabilir)
- [x] Örnekleme hızı her yerde 48 kHz (conf testi)
- [x] Ekolayzer doğruluğu: çizilen eğri ile gerçek yanıt arasında **0.01 dB**
- [~] Pembe gürültüyle null testi: bir pencerede **birebir sıfır artık** (215 dB) elde
      edildi ama tekrarlanabilir değil — `pw-cat` kaydı aksıyor. Sınır ölçüm altyapısında,
      zincirde değil

---

## Kabul senaryosu — ✅

Üç uygulama aynı anda çalıyor, "müzik" kanalının yayın fader'ı kapalı, **arayüz kapalı**
(yalnızca daemon):

| | Oyun 300 Hz | Sohbet 900 Hz | Müzik 2500 Hz |
|---|---|---|---|
| **Kulaklık** | -22.8 | -22.2 | **-22.6** |
| **Yayın** | -22.8 | -22.2 | **-233.3** |

Kulaklıkta üçü de duyuluyor, yayında müzik **dijital sessizlik**. Sonar'ın var olma sebebi
bu satır.

---

## Dokümantasyon

- [x] `README.md` — tanıtım, ekran görüntüleri, kurulum, hızlı başlangıç, ölçüm özeti,
      bilinen sınırlar
- [x] `ARCHITECTURE.md` — üç süreç, ses grafı, DSP zinciri **ve koddan üretilen D-Bus API
      referansı** (43 metot, 5 sinyal; her metodun docstring'i tabloya giriyor)
- [x] `docs/OBS.md` — kaynak ekleme, çok track'li kayıt, senkron, sorunlar
- [x] `docs/PERFORMANCE.md` — bu projedeki **tüm** ölçümler tek yerde
- [x] `docs/TROUBLESHOOTING.md` — ses yok, çift ses, eklenti eksik, yüksek CPU, yanlış
      kanal, kaydedilmeyen ayarlar, sıfırlama, log toplama
- [x] `CONTRIBUTING.md` — ortam kurulumu, katman kuralları, yeni eklenti ekleme,
      "ölçerek çalışın" ilkesi

---

## Yol boyunca yakalananlar

1. **Yazılamayan config dizini yakalanmamış istisna üretiyordu.** Daemon ayakta kalıyordu
   ama kullanıcı traceback görüyordu ve ayarların kalıcı olmadığını anlamıyordu. Artık
   anlaşılır bir hata ve `save_failed` olayı üretiliyor.
2. **CLI `status` akışın kanalını göstermiyordu** (`→ ?`); `target_node` yerine daemon'ın
   yönlendirme kaydı kullanılıyor artık.
3. **Ölçümler kullanıcının gerçek uygulamalarıyla kirlendi.** Daemon çalışırken kullanıcının
   Spotify/Brave/Discord akışları da kanallara yönlendiriliyor; test tonum onların müziğiyle
   aynı kanalda karışınca "media 23 dB düşük" gibi göründü. Açık hedefle tek akış ölçünce
   -23.1 dB (kaynak -22.6) çıktı — zincir doğruydu. **Kabul testleri kullanıcının sesi
   çalmıyorken veya paylaşılmayan kanallarda yapılmalı.**
4. **Gecikme ölçümünün ilk iki tasarımı işe yaramadı** — PipeWire'ın raporladığı gecikme
   graf sınırında duruyor, mutlak darbe ölçümü ise kayıt başlangıcı belirsizliğinden
   ±18 ms saçılıyordu. Çözüm: iki darbeyi **aynı kayıt oturumunda** ölçüp kaydın başlangıcını
   denklemden düşürmek.

---

## Tamamlanma kriteri — ✅ karşılandı (bir istisnayla)

Üç uygulama aynı anda çalışırken kulaklıkta üçü de duyuluyor, yayın miksinde "müzik" kanalı
**hiç yok** (-233 dB), ve bunların hepsi **arayüz kapalıyken** çalışıyor — ölçüldü.

**Açık kalan:** gerçek OBS ile çok track'li kayıt alınıp `ffprobe` ile doğrulanmadı. OBS'in
kaynak ekleme ve track atama adımları elle yapılıyor; Sonar tarafındaki her şey doğrulandı.
`docs/OBS.md` adım adım anlatıyor.

```bash
ruff check src/ tests/ && pytest -q          # 715 test geçti, lint temiz
```
