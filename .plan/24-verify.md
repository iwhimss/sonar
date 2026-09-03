# Faz 24 — Doğrulama ve dokümantasyon (test turu 2)

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 18–23
**Çıktı:** `README.md`, `ARCHITECTURE.md`, `docs/OBS.md`,
`docs/TROUBLESHOOTING.md`, `packaging/`, `.plan/00-overview.md`

---

## Otomatik testler

- [ ] `ruff check src/ tests/` temiz
- [ ] `pytest -q` yeşil
- [ ] Yeni testler:
  - [ ] bağlantı bekçisi uzlaştırması (eksik bağlantı ikinci turda kapanıyor)
  - [ ] canlı cihaz değişimi conf metnini değiştirmiyor
  - [ ] `Router.reassert` restart sonrası akışları yerine oturtuyor
  - [ ] çoklu bus göçü (şema 2 → 3)
  - [ ] kanal çıkışını değiştirmek yapısal değil
  - [ ] giriş yönlü kurallar (`direction`)
  - [ ] `StageGraph` kurulumu ve doğrusal aşamaların geriye dönük eşliği
  - [ ] ducking zarfı (saf fonksiyon)
  - [ ] HID rapor çözücüsü (kaydedilmiş raporlarla)

---

## Elle senaryo

Daemon açık, gerçek uygulamalarla.

- [ ] Spotify çalarken hiç kesinti olmuyor; cihaz değiştirmek müziği durdurmuyor
- [ ] Mikser mute (✕) düğmeleri anında tepki veriyor ve gerçekten susturuyor
- [ ] Arayüz daemon'daki her değişikliği anında yansıtıyor
- [ ] Sürüklenen uygulama kutucuğu hiçbir sütunun altında kalmıyor
- [ ] Kanal silme (✕) düğmesi tam görünüyor; pencere boyutu değişince yerleşim kaymıyor
- [ ] Uygulama kanal değiştirince ses kesilmiyor (20/20)
- [ ] Game hoparlöre, Media kulaklığa — ikisi aynı anda doğru cihazda
- [ ] Discord giriş şeridinde görünüyor ve mikrofonu şeritler arası taşınabiliyor
- [ ] Spatial Audio açılıp kapanınca fark duyuluyor, kapalıyken bit-eş
- [ ] Volume Boost +6 dB duyuluyor ve kırpma yok
- [ ] Smart Volume: Discord'da biri konuşunca müzik kısılıyor, susunca dönüyor
- [ ] Kulaklık tekeri ChatMix slider'ını sürüyor; slider salt okunur
- [ ] ChatMix "Sıfırla" düğmesi 50'ye döndürüyor
- [ ] OBS'te yalnızca `Sonar Stream Mix — Virtual Input` ile kayıt
- [ ] `sonar-cli doctor` temiz
- [ ] Faz 17'den devreden: görev çubuğu ses uygletinde Sonar sink'leri, dropdown
      katmanlaması, Noise Gate ilk tıklama, 15+ uygulamayla Apps kutusu

---

## Dokümantasyon

- [ ] `README.md` — çoklu çıkış bus'ı, kanal → çıkış eşlemesi, mikrofon yönlendirme,
      Spatial / Boost / Smart Volume, donanım tekeri kurulumu (udev)
- [ ] `ARCHITECTURE.md` — N çıkış bus'lı graf diyagramı, bus/gönderi tablosu,
      `StageGraph`, ducking döngüsü, bağlantı bekçisi, güncellenmiş D-Bus tablosu
- [ ] `docs/OBS.md` — "Yayın Miksi" satırının yeni hâli
- [ ] `docs/TROUBLESHOOTING.md` — "hiç ses gelmiyor" maddesi + `sonar-cli doctor`
- [ ] `packaging/99-sonar-headset.rules` + kurulum notu
- [ ] `.plan/00-overview.md` faz tablosu, test sayısı, mimari özeti
- [ ] Her faz sonunda commit + `iwhimss/sonar` `main` dalına push
