# Faz 17 — Doğrulama ve dokümantasyon (test turu 1)

**Durum:** 🟢 Tamamlandı
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

- [x] `ruff check src/` temiz
- [x] `pytest -q` yeşil
- [x] Yeni testler:
  - [x] `pwstate` silme olayı regresyonu
  - [x] kanal silme kısıtları (son kanal, varsayılan devri, ChatMix temizliği)
  - [x] favori migrasyonu (`favorite_slot` → sıralı liste)
  - [x] `direction` / `stream_source` alanlı confgen altın dosyası
  - [x] `pw-link` bağlantı planlayıcısı (saf fonksiyon)
  - [x] `new_profile` düz profil üretiyor

---

## Elle senaryo

Daemon açık, gerçek uygulamalarla. ✅ işaretliler bu oturumda ölçülerek doğrulandı;
işaretsizler ekrana bakmayı gerektirdiği için **kullanıcının ikinci test turuna** kaldı.

- [x] `pactl list short sources | grep sonar` → sahte mikrofon yok
- [x] Cihaz adları İngilizce ve yön belirtiyor (Virtual Input / Virtual Output)
- [ ] Görev çubuğu ses uygletinde Sonar sink'leri görünüyor *(kullanıcı testine kaldı —
      `node.nick`, `device.icon-name` ve `priority.session` eklendi, sonucu ekranda
      görmek gerekiyor)*
- [x] Aux silinir, ses kesintisiz devam eder
- [x] "Podcast" adında bir **giriş** kanalı eklenir, Discord onu görür
- [ ] Profil dropdown'ı EQ panelinin üstünde açılıyor, kırpılmıyor, kaydırılıyor *(kullanıcı testine kaldı)*
- [ ] Noise Gate anahtarı ilk tıklamada açılıyor *(kullanıcı testine kaldı)*
- [x] Metreler oynuyor, sessizde düşüyor
- [x] Brave açılıp kapatılınca Apps listesinden düşüyor
- [ ] 15+ uygulama açıkken Apps kutusu taşmıyor, kaydırılıyor *(kullanıcı testine kaldı)*
- [x] Akış Media → Game'e taşınınca Game'in profilinden geçiyor
- [x] Yeni profil (düz) + favori ekleme + sıralama
- [x] AutoEQ `.txt` içe aktarma, `.sonarprofile` dışa aktarma
- [ ] OBS'te yalnızca `Sonar Stream Mix — Virtual Input` ile kayıt *(kullanıcı testine kaldı)*
- [x] `systemctl --user restart pipewire` → graf ve `pw-link` bağlantıları toparlanıyor

---

## Dokümantasyon

- [x] `README.md`
  - [x] Sanal cihaz adları tablosu (yön belirtir)
  - [x] Kanal yönü kavramı (çıkış / giriş kanalı)
  - [x] Profil akışı: yeni profil, otomatik kaydetme, favoriler, içe/dışa aktarma
  - [x] Kanal silme
- [x] `ARCHITECTURE.md`
  - [x] Yeni graf diyagramı (`_fx` opsiyonel, açık `pw-link` bağlantıları)
  - [x] Güncellenmiş D-Bus metot tablosu
- [x] `docs/OBS.md` — "sadece Stream Mix" varsayılanına göre yeniden yazılır;
      kanal başına track isteyenler için `stream_source` anahtarı anlatılır
- [x] `docs/TROUBLESHOOTING.md`
  - [x] "Sanal cihazı göremiyorum"
  - [x] "Kanal sesi hiç gelmiyor" → `pw-link -l` ile bağlantı kontrolü
- [x] `.plan/00-overview.md` — faz tablosu, test sayısı, "şu an neredeyiz"

---

## Ölçülen kabul kriteri (2026-09-01)

**Müzik kulaklıkta duyuluyor, yayında yok.** Media kanalının yayın fader'ı kapatıldı,
440 Hz sinüs çalındı, iki bus da monitörlerinden ölçüldü:

| bus | seviye |
|---|---|
| `sonar_personal` (kulaklık) | **-14.0 dBFS** |
| `sonar_stream` (yayın) | **-240 dBFS** — dijital sessizlik |

**Cihaz listesi temiz.** Çıkışlar: game, chat, media, aux, personal, stream.
Girişler (monitor hariç): `sonar_stream_out`, `sonar_mic`, `sonar_stream_mic`.
Kanal başına sahte mikrofon yok. Tüm açıklamalar yönü söylüyor.

**Gönderi bağlantıları:** `pw-link -l` çıktısında 16 bağlantı (4 kanal × 2 bus × 2 port).

**İçe/dışa aktarma köprüden uçtan uca:**

```
[bilgi] 'AutoEQ' içe aktarıldı (autoeq)
[bilgi] out.sonarprofile kaydedildi
```

**GUI** QML konsolunda tek uyarı olmadan yükleniyor.

---

## Commit / push

Her faz sonunda anlamlı bir commit ve `iwhimss/sonar` `main` dalına push.

---

## Yol boyunca yakalananlar

**Arayüz hiçbir geri bildirim göstermiyordu.** `errorRaised` sinyali köprüde vardı ama
QML'de hiçbir yere bağlı değildi; içe aktarma sonucu, "gömülü preset kopyalandı" ve
"ayarlar diske yazılamadı" yalnızca loga düşüyordu. `Main.qml`'e bir bildirim şeridi
eklendi: bilgiler 8 saniyede geçiyor, hatalar kullanıcı kapatana kadar duruyor.
`profile_copied` özellikle önemliydi — kullanıcı gömülü bir preseti kurcalayınca daemon
arkada kopya açıp aktif profili değiştiriyor, söylenmezse "seçtiğim preset neden
değişti?" oluyor.

**D-Bus tablosu koddan yeniden üretildi.** 43 → 47 metot. Elle güncellemek yerine
`ast` ile `dbus_iface.py`'den okunup `ARCHITECTURE.md`'ye yazıldı; imza ve ilk docstring
satırı doğrudan koddan geliyor.
