# Faz 5 — Uygulama yönlendirme

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 4
**Çıktı:** `src/sonar/engine/router.py`, `tests/test_router.py`

---

## Amaç

Hangi uygulamanın hangi kanala gideceğini belirlemek: yeni bir ses akışı açıldığında
kurallara bakıp doğru sanal cihaza yönlendirmek, kullanıcının elle yaptığı taşımaları
kalıcı kural hâline getirmek.

---

## Görevler

### `engine/router.py` — kural motoru
- [ ] `PwState.streams_changed` → yeni akışları tespit et (id bazlı diff)
- [ ] **Eşleştirme anahtarları, öncelik sırasıyla:**
  1. `application.process.binary` (ör. `cs2`, `Discord`, `firefox`) — en güvenilir
  2. `application.name` (ör. `Firefox`, `Spotify`)
  3. `media.name` regex (ör. `.*YouTube.*`)
- [ ] Aynı öncelikte birden fazla kural eşleşirse: daha uzun/spesifik desen kazanır
- [ ] Eşleşme yoksa → `settings.default_channel` (varsayılan: `media`)
- [ ] Zaten doğru hedefteki akış tekrar taşınmaz (gereksiz `pactl` çağrısı yok)
- [ ] Kullanıcının **elle** taşıdığı akış o oturum boyunca kural motoru tarafından geri alınmaz
      (manuel override kaydı, akış kapanınca temizlenir)

### Yarış koşulu koruması
Akış oluşturulduktan sonra taşımak, sesin ilk 10–20 ms'sini yanlış cihazda çalabilir.
- [ ] **Birincil yol:** `pw-metadata` ile ilgili uygulama için `target.object` **önceden** ayarlanır
      (uygulama bilinen bir binary ise, akış açılmadan)
- [ ] **Yedek yol:** akış göründüğü an `pactl move-sink-input` (birincil yol tutmazsa)
- [ ] Ölçüm: yönlendirme gecikmesi loglanır, kabul edilebilir mi görülür

### Kalıcı kurallar
- [ ] GUI'den elle taşıma → "Bu uygulamayı hep **Game**'e gönder" onay kutusu → `SetRule`
- [ ] Kurallar `config.toml` içinde `[[rules]]` listesinde tutulur, elle düzenlenebilir
- [ ] Varsayılan ön tanımlı kurallar (ilk kurulumda önerilir, kullanıcı onaylar):
  - Chat ← `Discord`, `discord`, `TeamSpeak`, `Mumble`, `WEBRTC VoiceEngine`
  - Media ← `firefox`, `chrome`, `chromium`, `brave`, `spotify`, `mpv`, `vlc`
  - Game ← Steam/Proton altındaki süreçler (`steam_app_*`, `wine`, `proton`)
- [ ] Kural listesi GUI'de düzenlenebilir (ekle/sil/sırala)

### Varsayılan sink devralma (opsiyonel, varsayılan kapalı)
- [ ] `settings.take_over_default_sink = true` ise sistem varsayılan sink'i `sonar_media` yapılır
- [ ] Daemon kapanırken **mutlaka** eski değere geri alınır (kullanıcı sessiz sistemle kalmasın)
- [ ] Kapalıyken hiçbir sistem ayarına dokunulmaz — kullanıcı cihazları elle seçer

### Testler
- [ ] `test_router.py` — kural önceliği (binary > app_name > media_name)
- [ ] Regex eşleşmesi ve hatalı regex'in güvenli reddi
- [ ] Çakışan kurallarda spesifiklik kazanıyor mu
- [ ] Eşleşme yoksa varsayılan kanala düşüyor mu
- [ ] Manuel override kural tarafından ezilmiyor mu

---

## Doğrulama

```bash
mpv müzik.mp3 &
pactl list short sink-inputs        # sonar_media'ya bağlı olmalı

sonar-cli route mpv game
pkill mpv; mpv müzik.mp3 &
pactl list short sink-inputs        # şimdi sonar_game'e bağlı olmalı
```

**Çoklu uygulama testi:** Bir oyun + Discord + tarayıcı aynı anda açık;
`sonar-cli status` üçünü de doğru kanallarda göstermeli.

**Kenar durumlar:**
- Uygulama açılırken kanal henüz hazır değilse ne oluyor (graf restart sırasında)
- Aynı uygulamanın birden fazla akışı (tarayıcı sekmeleri)
- Akış kapanıp hemen yeniden açılıyorsa

---

## Tamamlanma kriteri

Uygulamalar açıldıkları anda doğru kanala düşüyor; elle taşıma çalışıyor ve
istenirse kalıcılaşıyor; hatalı kural sistemi bozmuyor.
