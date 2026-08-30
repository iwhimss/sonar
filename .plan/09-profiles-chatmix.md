# Faz 9 — Profiller, presetler ve ChatMix

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 8
**Çıktı:** `src/sonar/presets/`, profil içe/dışa aktarma, ChatMix mantığı

---

## Amaç

Kullanıcının asıl istediği senaryoyu tamamlamak:

> "Bir kanal için birden fazla EQ ayarı yapıp kaydedebilmeliyim. Örnek olarak oyun kanalı için
> CS2 için ayrı EQ ve filtre, Arc Raiders için ayrı EQ ve filtre ayarlayıp aralarında hızlıca
> geçiş yapabilmeliyim."

Ayrıca ChatMix (oyun ↔ sohbet dengesi) ve hazır preset kütüphanesi.

---

## Görevler

### Profil sistemi
- [ ] Kanal başına **sınırsız** profil; profil = tüm zincir durumu
      (EQ bandları + gate + compressor + limiter + mikrofonda DeepFilterNet)
- [ ] Depolama: `~/.config/sonar/profiles/<kanal>/<profil>.json`
      → bir profil silmek/eklemek `config.toml`'u yeniden yazmaz
- [ ] Profil geçişi **anında ve kesintisiz**: yalnızca `set_params` toplu yazımı, graf restart yok
- [ ] Geçiş noktaları: mikser şeridindeki profil açılır menüsü, FX sayfasındaki favori slotları,
      `sonar-cli profile game CS2`, D-Bus `LoadProfile`
- [ ] Aktif profil kanal bazında `config.toml`'da tutulur → yeniden başlatmada geri gelir
- [ ] Kaydedilmemiş değişiklikler geçici bellekte; "Kaydet" veya "Farklı kaydet" ile kalıcılaşır

### Preset kütüphanesi (`src/sonar/presets/`)
- [ ] **Çıkış kanalları için:**
  - `Flat` — hepsi 0 dB, tüm filtreler kapalı
  - `FPS Footsteps` — 2–5 kHz vurgusu, alt bas kısımı (ayak sesi/yön tespiti)
  - `Bass Boost` — 40–100 Hz shelf
  - `Vocal Clarity` — 1–4 kHz vurgusu, 200–400 Hz çamur temizliği
  - `Night Mode` — compressor ile dinamik daraltma (geç saatte düşük ses)
  - `Movie` — geniş sahne, hafif bas ve tiz shelf
  - `Music` — hafif V eğrisi
- [ ] **Mikrofon için:**
  - `Broadcast` — high-pass 80 Hz, hafif presence, compressor + limiter
  - `Podcast` — daha yumuşak compressor, de-esser benzeri notch
  - `Aggressive Cleanup` — DeepFilterNet max + sıkı gate (gürültülü ortam)
- [ ] Presetler salt okunur; kullanıcı "Kopyala"yla kendi düzenlenebilir sürümünü yapar
- [ ] Preset dosyaları profil formatının aynısı → içe aktarma ile ayırt edilmez

### İçe / dışa aktarma
- [ ] Tek dosya formatı `.sonarprofile` (JSON, şema sürümlü)
- [ ] **İçe aktarma desteği:**
  - [ ] AutoEQ `ParametricEQ.txt` (kulaklık düzeltme eğrileri — büyük kütüphane)
  - [ ] EasyEffects preset `.json` (EQ bölümü)
  - [ ] Equalizer APO `config.txt` (Windows'tan taşıma)
- [ ] Dışa aktarma: `.sonarprofile` + opsiyonel AutoEQ metin formatı
- [ ] İçe aktarmada band sayısı uyuşmazlığı: en yakın desteklenen band sayısına yuvarlanır,
      kullanıcı uyarılır

### ChatMix
- [ ] Tek slider (0–100). 50 = nötr (hiçbir kanala dokunmaz)
- [ ] 0'a doğru → **sol kanal** (varsayılan Game) tam, **sağ kanal** (varsayılan Chat) kısılır
- [ ] 100'e doğru → tersi
- [ ] **Yalnızca `personal` fader'ları etkiler** — stream miksi bozulmaz (yayında ses dengesi sabit kalır)
- [ ] Kısma eğrisi: lineer değil, algısal (dB tabanlı) — 0'da -∞ değil, ayarlanabilir taban (-40 dB)
- [ ] Hangi kanalların ChatMix'e bağlı olduğu ayarlardan değiştirilebilir
      (ör. sol = Game, sağ = Chat + Media)
- [ ] ChatMix aktifken kanal fader'ları GUI'de "ChatMix tarafından yönetiliyor" olarak işaretlenir;
      kullanıcı elle oynatırsa temel (base) değer güncellenir, ChatMix onun üstüne uygular
- [ ] **Arctis 7 donanım ChatMix tekeri:** cihaz ALSA'da ayrı bir kontrol/HID olarak görünüyorsa
      okunup slider'a bağlanır. Best-effort — bulunamazsa sessizce atlanır, GUI slider'ı çalışmaya devam eder
  - [ ] Araştırma notu: Arctis 7 ChatMix'i genelde iki ayrı USB ses cihazı olarak görünür
        (Game + Chat). Bu durumda donanım entegrasyonu yerine yazılım ChatMix'i yeterli

---

## Doğrulama

**Kullanıcının asıl senaryosu:**
```bash
# Game kanalı için iki profil oluştur
# GUI'de: Game → FX → EQ ayarla → Kaydet "CS2"
#         EQ'yu değiştir → Farklı Kaydet "Arc Raiders"
# İkisini de favori slotlarına ata

sonar-cli profile game CS2            # anında geçiş, kesinti yok
sonar-cli profile game "Arc Raiders"  # anında geçiş, kesinti yok
```
Müzik çalarken profiller arasında hızlıca geçiş yap → tını anında değişmeli,
hiçbir kesinti, tık veya sessizlik olmamalı.

**ChatMix:** Oyun + Discord aynı anda çalarken slider'ı uçlara çek →
kulaklıkta denge değişmeli; `sonar_stream` monitörünü kaydet → orada denge **değişmemeli**.

**Preset:** `FPS Footsteps` yükle → 2–5 kHz vurgusu duyulmalı, EQ eğrisi doğru görünmeli.

**İçe aktarma:** AutoEQ'dan bir kulaklık profili indir, içe aktar, eğrinin doğru geldiğini gör.

---

## Tamamlanma kriteri

Kullanıcı bir kanal için istediği kadar profil kaydedip favori slotlarından anında geçiş
yapabiliyor; ChatMix kişisel miksi ayarlarken yayın miksini bozmuyor;
hazır presetler ve dış format içe aktarma çalışıyor.
