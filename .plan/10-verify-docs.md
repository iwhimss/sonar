# Faz 10 — Uçtan uca doğrulama ve dokümantasyon

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 9
**Çıktı:** `README.md`, `ARCHITECTURE.md`, `docs/OBS.md`, `docs/TROUBLESHOOTING.md`

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
- [ ] OBS'e kaynak ekle:
  - `Sonar Stream Mix` (monitör) — birleşik yayın sesi
  - `Sonar Stream Mic` — mikrofon
  - `sonar_game_fx` — oyun sesi ayrı track
  - `sonar_chat_fx` — sohbet sesi ayrı track
- [ ] OBS Gelişmiş Ses Özellikleri'nden her kaynağı ayrı track'e ata
- [ ] Çok track'li kayıt al, `ffprobe` ile track sayısını doğrula
- [ ] Her track'i ayrı ayrı dinle: izolasyon tam mı, senkron kayması var mı
- [ ] Media kanalının stream fader'ını 0 yap → yayında müzik duyulmamalı,
      kulaklıkta duyulmaya devam etmeli **(Sonar'ın asıl amacı — telif riski olan müziği yayına sokmama)**
- [ ] Yayın sırasında profil değiştir → kayıtta kesinti/pop olmamalı

### 2. Uygulama yönlendirme senaryosu
- [ ] Oyun (Steam/Proton) + Discord + tarayıcı + Spotify aynı anda
- [ ] Her biri doğru kanala düşüyor mu
- [ ] Elle taşıma çalışıyor ve kalıcılaştırılabiliyor mu
- [ ] Uygulama kapanıp açılınca kural hatırlanıyor mu
- [ ] Tarayıcının birden fazla ses akışı (2 sekme) doğru yönetiliyor mu

### 3. Dayanıklılık
- [ ] Arctis 7 USB'yi çıkar/tak → graf toparlanıyor, ses geri geliyor
- [ ] `systemctl --user restart pipewire` → graf yeniden kuruluyor
- [ ] `systemctl --user restart wireplumber` → bağlantılar korunuyor
- [ ] Uyku / uyanma döngüsü
- [ ] Daemon'u `kill -9` → systemd geri getiriyor, durum korunuyor
- [ ] Graf sürecini `kill -9` → supervisor geri getiriyor
- [ ] Bozuk `config.toml` → yedeklenip varsayılana düşülüyor, kullanıcı bilgilendiriliyor
- [ ] Disk dolu / config yazılamıyor → daemon çökmüyor, uyarı veriyor
- [ ] 24 saat sürekli çalışma → bellek sızıntısı yok (RSS izlenir)

### 4. Performans
- [ ] **Gecikme ölçümü**: tüm filtreler kapalıyken ve açıkken uçtan uca gecikme
      (referans: doğrudan cihaza çalma). Hedef: ek gecikme **< 15 ms**
- [ ] CPU kullanımı: boşta, müzik çalarken, tüm filtreler + metreler açıkken
      (hedef: toplam < %5 tek çekirdek)
- [ ] Bellek: daemon + graf süreci + GUI (hedef: toplam < 250 MB)
- [ ] Oyun sırasında xrun/underrun sayısı (`pw-top` ile izle) — sıfıra yakın olmalı
- [ ] Sonuçlar `docs/PERFORMANCE.md`'e yazılır

### 5. Ses kalitesi
- [ ] Null test: EQ düz + tüm filtreler kapalı → giriş ile çıkış bit-eşdeğere yakın olmalı
      (yalnızca float dönüşüm farkı)
- [ ] Örnekleme hızı dönüşümü olmadığı doğrulanır (her yer 48 kHz)
- [ ] Zincirde clip yok: yüksek kazançlı EQ + limiter ile test

---

## Dokümantasyon

### `README.md`
- [ ] Proje tanıtımı: ne işe yarar, neden var (SteelSeries Sonar alternatifi)
- [ ] Ekran görüntüleri (mikser + FX sayfası)
- [ ] Özellik listesi
- [ ] Kurulum: Arch/CachyOS (`PKGBUILD`), diğer dağıtımlar (elle)
- [ ] Hızlı başlangıç: daemon'u etkinleştir → uygulamayı aç → kanalları ayarla
- [ ] Gereksinimler ve bağımlılıklar
- [ ] Lisans, katkı daveti

### `ARCHITECTURE.md`
- [ ] Üç süreç diyagramı ve gerekçesi
- [ ] Ses grafı diyagramı (node isimleriyle)
- [ ] DSP zinciri ve kullanılan eklentiler
- [ ] D-Bus API tam referansı (metotlar, sinyaller, JSON şemaları)
- [ ] Yapılandırma dosyası formatı
- [ ] "Neden bu şekilde" kararları (tek pipewire süreci, filter-chain, LV2)

### `docs/OBS.md`
- [ ] Hangi kaynağı nasıl eklersin (ekran görüntülü)
- [ ] Çok track'li kayıt kurulumu
- [ ] Telifli müziği yayından çıkarma tarifi
- [ ] Sık karşılaşılan OBS sorunları

### `docs/TROUBLESHOOTING.md`
- [ ] Ses yok → kontrol listesi
- [ ] Çift ses / yankı → loopback döngüsü teşhisi
- [ ] "Eklenti bulunamadı" → kurulum komutları
- [ ] Yüksek CPU → hangi ayar, nasıl azaltılır
- [ ] Uygulama yanlış kanalda → kural teşhisi
- [ ] Her şeyi sıfırlama: `sonar-cli reset` / config silme
- [ ] Log toplama: `journalctl --user -u sonar-daemon`

### `CONTRIBUTING.md`
- [ ] Geliştirme ortamı kurulumu, `ruff` + `pytest`, kod stili
- [ ] Yeni efekt eklentisi ekleme rehberi (`registry.py`'ye `PluginSpec` ekleme)

---

## Tamamlanma kriteri

**Kabul senaryosu:** Oyun + Discord + Spotify aynı anda çalışırken —
kulaklıkta üçü de duyuluyor, OBS kaydında Game ve Chat ayrı track'lerde,
Media hiç yok (stream fader'ı kapalı), mikrofon DeepFilterNet ile temiz,
**ve tüm bunlar GUI kapalıyken çalışıyor.**
