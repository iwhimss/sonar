# Faz 24 — Doğrulama ve dokümantasyon (test turu 2)

**Durum:** 🟡 Kod tarafı bitti, ekran testleri kullanıcıda
**Bağımlılık:** Faz 18–23
**Çıktı:** `README.md`, `ARCHITECTURE.md`, `docs/OBS.md`,
`docs/TROUBLESHOOTING.md`, `packaging/`, `.plan/00-overview.md`

---

## Otomatik testler

- [x] `ruff check src/ tests/` temiz
- [x] `pytest -q` yeşil
- [x] Yeni testler:
  - [x] bağlantı bekçisi uzlaştırması (eksik bağlantı ikinci turda kapanıyor)
  - [x] canlı cihaz değişimi conf metnini değiştirmiyor
  - [x] `Router.reassert` restart sonrası akışları yerine oturtuyor
  - [x] çoklu bus göçü (şema 2 → 3)
  - [x] kanal çıkışını değiştirmek yapısal değil
  - [x] giriş yönlü kurallar (`direction`)
  - [x] `StageGraph` kurulumu ve doğrusal aşamaların geriye dönük eşliği
  - [x] ducking zarfı (saf fonksiyon)
  - [ ] HID rapor çözücüsü — *kullanıcının udev kuralını kurmasını bekliyor (Faz 23)*

---

## Elle senaryo

Daemon açık, gerçek uygulamalarla.

- [x] Spotify çalarken hiç kesinti olmuyor; cihaz değiştirmek müziği durdurmuyor *(ölçüldü: node id 108 → 108, kesinti kayıt gürültüsünün içinde)*
- [ ] Mikser mute (✕) düğmeleri anında tepki veriyor ve gerçekten susturuyor
- [ ] Arayüz daemon'daki her değişikliği anında yansıtıyor
- [ ] Sürüklenen uygulama kutucuğu hiçbir sütunun altında kalmıyor
- [ ] Kanal silme (✕) düğmesi tam görünüyor; pencere boyutu değişince yerleşim kaymıyor
- [x] Uygulama kanal değiştirince ses kesilmiyor (20/20) *(taşıma artık bağlantıyı doğruluyor ve bir kez daha deniyor)*
- [x] Game hoparlöre, Media kulaklığa — ikisi aynı anda doğru cihazda *(ölçüldü: her biri kendi bus'ında -37.0 dBFS, diğerinde -240 dBFS)*
- [x] Discord giriş şeridinde görünüyor ve mikrofonu şeritler arası taşınabiliyor *(pw-cat kayıt akışıyla ölçüldü; pw-link bağlantısı takip etti)*
- [x] Spatial Audio açılıp kapanınca fark duyuluyor, kapalıyken bit-eş *(ölçüldü: 30° → ITD 0.38 ms, kapalı → kazanç 0.00 dB / sağ kanal -240 dBFS)*
- [x] Volume Boost +6 dB duyuluyor ve kırpma yok *(ölçüldü: tam +6.00 dB)*
- [x] Smart Volume: Discord'da biri konuşunca müzik kısılıyor, susunca dönüyor *(ölçüldü: -12.1 dB indirim, ~200 ms atak, ~600 ms bırakma)*
- [ ] Kulaklık tekeri ChatMix slider'ını sürüyor; slider salt okunur *(Faz 23 udev kuralını bekliyor)*
- [ ] ChatMix "Sıfırla" düğmesi 50'ye döndürüyor
- [ ] OBS'te yalnızca `Sonar Stream Mix — Virtual Input` ile kayıt
- [x] `sonar-cli doctor` temiz
- [ ] Faz 17'den devreden: görev çubuğu ses uygletinde Sonar sink'leri, dropdown
      katmanlaması, Noise Gate ilk tıklama, 15+ uygulamayla Apps kutusu

---

## Dokümantasyon

- [x] `README.md` — çoklu çıkış bus'ı, kanal → çıkış eşlemesi, mikrofon yönlendirme,
      Spatial / Boost / Smart Volume, donanım tekeri kurulumu (udev)
- [x] `ARCHITECTURE.md` — N çıkış bus'lı graf diyagramı, bus/gönderi tablosu,
      `StageGraph`, ducking döngüsü, bağlantı bekçisi, güncellenmiş D-Bus tablosu
- [x] `docs/OBS.md` — "Yayın Miksi" satırının yeni hâli
- [x] `docs/TROUBLESHOOTING.md` — "hiç ses gelmiyor" maddesi + `sonar-cli doctor`
- [x] `packaging/99-sonar-headset.rules` + kurulum notu
- [x] `.plan/00-overview.md` faz tablosu, test sayısı, mimari özeti
- [x] Her faz sonunda commit + `iwhimss/sonar` `main` dalına push


---

## Durum

**Kod tarafı bitti:** 805 test geçiyor, `ruff` temiz, 54 D-Bus metodu.
Ölçülebilen her madde ölçüldü ve sonuçlar `docs/PERFORMANCE.md` içinde.

**Kullanıcıda kalanlar** — ekrana bakmayı gerektirenler:

- [ ] Mikser mute (✕) düğmeleri anında tepki veriyor ve gerçekten susturuyor
- [ ] Arayüz daemon'daki her değişikliği anında yansıtıyor
- [ ] Sürüklenen uygulama kutucuğu hiçbir sütunun altında kalmıyor
- [ ] Kanal silme (✕) düğmesi tam görünüyor; pencere boyutu değişince yerleşim kaymıyor
- [ ] ChatMix "Sıfırla" düğmesi 50'ye döndürüyor
- [ ] OBS'te yalnızca `Sonar Stream Mix — Virtual Input` ile kayıt
- [ ] Görev çubuğu ses uygletinde Sonar sink'leri *(Faz 17'den devrediyor)*
- [ ] Dropdown katmanlaması, Noise Gate ilk tıklama, 15+ uygulamayla Apps kutusu
      *(Faz 17'den devrediyor)*

**Faz 23 için gereken tek seferlik sudo** — bkz. `.plan/23-chatmix-hid.md`:

```bash
sudo cp packaging/99-sonar-headset.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
./scripts/sonar-hid-capture       # tekeri uçtan uca çevir
```
