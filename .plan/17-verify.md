# Faz 17 — Doğrulama ve dokümantasyon (test turu 1)

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 12–16
**Çıktı:** `README.md`, `ARCHITECTURE.md`, `docs/OBS.md`,
`docs/TROUBLESHOOTING.md`, `.plan/00-overview.md`

---

## Amaç

Faz 12–16'nın gerçekten çalıştığını uçtan uca doğrulamak ve dokümanları yeni
davranışa göre güncellemek. Bu faz bittikten sonra kullanıcı **ikinci test turunu**
yapar; ancak ondan sonra Faz 11 (Paketleme) başlar.

---

## Otomatik testler

- [ ] `ruff check src/` temiz
- [ ] `pytest -q` yeşil
- [ ] Yeni testler:
  - [ ] `pwstate` silme olayı regresyonu
  - [ ] kanal silme kısıtları (son kanal, varsayılan devri, ChatMix temizliği)
  - [ ] favori migrasyonu (`favorite_slot` → sıralı liste)
  - [ ] `direction` / `stream_source` alanlı confgen altın dosyası
  - [ ] `pw-link` bağlantı planlayıcısı (saf fonksiyon)
  - [ ] `new_profile` düz profil üretiyor

---

## Elle senaryo

Daemon açık, gerçek uygulamalarla, sırayla:

- [ ] `pactl list short sources | grep sonar` → sahte mikrofon yok
- [ ] Cihaz adları İngilizce ve yön belirtiyor (Virtual Input / Virtual Output)
- [ ] Görev çubuğu ses uygletinde Sonar sink'leri görünüyor
- [ ] Aux silinir, ses kesintisiz devam eder
- [ ] "Podcast" adında bir **giriş** kanalı eklenir, Discord onu görür
- [ ] Profil dropdown'ı EQ panelinin üstünde açılıyor, kırpılmıyor, kaydırılıyor
- [ ] Noise Gate anahtarı ilk tıklamada açılıyor
- [ ] Metreler oynuyor, sessizde düşüyor
- [ ] Brave açılıp kapatılınca Apps listesinden düşüyor
- [ ] 15+ uygulama açıkken Apps kutusu taşmıyor, kaydırılıyor
- [ ] Akış Media → Game'e taşınınca Game'in profilinden geçiyor
- [ ] Yeni profil (düz) + favori ekleme + sıralama
- [ ] AutoEQ `.txt` içe aktarma, `.sonarprofile` dışa aktarma
- [ ] OBS'te yalnızca `Sonar Stream Mix — Virtual Input` ile kayıt
- [ ] `systemctl --user restart pipewire` → graf ve `pw-link` bağlantıları toparlanıyor

---

## Dokümantasyon

- [ ] `README.md`
  - [ ] Sanal cihaz adları tablosu (yön belirtir)
  - [ ] Kanal yönü kavramı (çıkış / giriş kanalı)
  - [ ] Profil akışı: yeni profil, otomatik kaydetme, favoriler, içe/dışa aktarma
  - [ ] Kanal silme
- [ ] `ARCHITECTURE.md`
  - [ ] Yeni graf diyagramı (`_fx` opsiyonel, açık `pw-link` bağlantıları)
  - [ ] Güncellenmiş D-Bus metot tablosu
- [ ] `docs/OBS.md` — "sadece Stream Mix" varsayılanına göre yeniden yazılır;
      kanal başına track isteyenler için `stream_source` anahtarı anlatılır
- [ ] `docs/TROUBLESHOOTING.md`
  - [ ] "Sanal cihazı göremiyorum"
  - [ ] "Kanal sesi hiç gelmiyor" → `pw-link -l` ile bağlantı kontrolü
- [ ] `.plan/00-overview.md` — faz tablosu, test sayısı, "şu an neredeyiz"

---

## Commit / push

Her faz sonunda anlamlı bir commit ve `iwhimss/sonar` `main` dalına push.

---

## Yol boyunca yakalananlar

_(faz sırasında doldurulacak)_
