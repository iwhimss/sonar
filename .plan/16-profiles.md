# Faz 16 — Profil deneyimi

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 9, Faz 15
**Çıktı:** `src/sonar/core/model.py`, `src/sonar/core/config.py`,
`src/sonar/daemon/api.py`, `src/sonar/daemon/dbus_iface.py`,
`src/sonar/gui/bridge.py`, `src/sonar/gui/qml/ChannelFx.qml`,
`src/sonar/gui/qml/ChannelStrip.qml`

---

## Amaç

Kullanıcının üç isteği:

> Kanallar için yeni profil oluşturma seçeneği yok, mevcut kanalı düzenleyip farklı
> kaydet demek gerekiyor. Bu da mevcut kanalın ayarlarının bozulmasına sebep oluyor.
> Yeni dendiğinde isim sormalı ve isim girdikten sonra yeni profil oluşturmalı
> direkt. Farklı kaydet butonu olmamalı yani. Profillerde yapılan değişiklikler de
> otomatik kaydedilmeli.

> Profilleri favorilere eklemek için bir kısım ayarlamışsın fakat favorilere eklemek
> için bir buton yok. Ayrıca favori listesi sınırlı kalmış, bunu sınırsız yapmalıyız.
> Favori listesindeki yerlerini de ayarlayabilmeli.

> Profilleri içe ve dışa aktarma özelliği ekleyelim.

Kullanıcı kararı: "Yeni profil" **sıfırdan düz** bir profil oluşturur.

---

## Yaklaşım

### Yeni profil akışı

"Farklı kaydet" **kaldırılır**. Yerine tek bir **＋ Yeni profil** düğmesi:

1. İsim sorar
2. `NewProfile(target, name)` → düz profil (EQ sıfır, tüm filtreler kapalı)
3. Diske yazılır ve **hemen ona geçilir**

Böylece kullanıcı önce mevcut profili bozup sonra "farklı kaydet" demek zorunda
kalmaz. Mevcut profilin kopyasını isteyen için `CopyProfile` API'si duruyor;
arayüzde `···` menüsünde "Kopyala" olarak kalır.

### Otomatik kaydetme

Zaten çalışıyor: her düzenleme `_live_target()` → `_dirty_profiles` →
`_save_soon()` (400 ms debounce) → `store.save_profile()`. Eksik olan **görünürlük**:

- Profil adının yanında kısa bir "kaydedildi" göstergesi
- Gömülü preset düzenlenince `_editable()` (`api.py:287`) sessizce
  "`<ad> (özel)`" kopyası açıyor — bu artık kullanıcıya bildirilir
  (`profile_copied` deltası zaten yayınlanıyor, arayüz onu göstermiyor)

### Sınırsız favoriler

`Profile.favorite_slot: int | None` (9 slot) kalkar. Yerine:

```python
SonarConfig.favorites: dict[str, list[str]]   # hedef → sıralı profil adları
```

Sıralama listenin kendisidir; sınır yok. Şema 2 migrasyonu eski `favorite_slot`
değerlerini sıraya çevirir (slot 1..9 → liste sırası), sonra alanı düşürür.

| Metot | İmza |
|---|---|
| `SetProfileFavorite` | `(target, name, favorite: bool)` — eski `slot: int` yerine |
| `ReorderFavorites` | `(target, names: list[str])` |

Arayüz:

- Aktif profilin yanında **yıldız düğmesi** — favoriye ekle / çıkar
- Altında favori şeridi: sürükleyerek sıralanır, sayı sınırı yok, taşarsa kaydırılır
- Mikser şeridindeki profil dropdown'ı: önce favoriler, ayraç, sonra tümü;
  uzunsa kaydırılır (Faz 15'teki yeni popup sayesinde)

### İçe / dışa aktarma

Motor tarafı hazır — `core/importers.py` AutoEQ, EqualizerAPO, EasyEffects ve
`.sonarprofile` biçimlerini okuyor; köprüde `importProfile()` / `exportProfile()`
slotları var (`gui/bridge.py:532,544`). **Eksik olan yalnızca arayüz.**

`QtQuick.Dialogs`'un `FileDialog`'u kullanılır (KDE Wayland'da portal üzerinden
çalışır):

- **İçe aktar:** dosya seçilir, biçim içerikten bulunur, sonuç penceresi kaç band
  düştüğünü ve uyarıları gösterir
- **Dışa aktar:** `.sonarprofile` (tam profil) veya AutoEQ `.txt` (yalnız EQ) seçimi

---

## Görevler

- [ ] `api.new_profile(target, name)` — düz profil, kaydet, geç
- [ ] `NewProfile` D-Bus metodu + `sonar-cli profile new`
- [ ] "Farklı kaydet" düğmesi kaldırılır, "＋ Yeni profil" gelir
- [ ] `SonarConfig.favorites` + şema 2 migrasyonu (`favorite_slot` → liste)
- [ ] `SetProfileFavorite(target, name, bool)` + `ReorderFavorites(target, names)`
- [ ] FX sayfasında yıldız düğmesi
- [ ] Sürüklenerek sıralanan, sınırsız favori şeridi
- [ ] Mikser dropdown'ı: favoriler + ayraç + tümü
- [ ] "kaydedildi" göstergesi
- [ ] Gömülü preset kopyası bildirimi (`profile_copied`)
- [ ] `FileDialog` ile içe aktarma + sonuç penceresi
- [ ] `FileDialog` ile dışa aktarma (`.sonarprofile` / AutoEQ)
- [ ] Testler: migrasyon, favori sıralaması, `new_profile` düzlüğü

---

## Doğrulama

- CS2 için yeni profil → isim → düz açılıyor, eski profil bozulmamış
- Arc Raiders için ikinci profil, ikisi de favoriye ekleniyor, sıraları
  sürükleyerek değişiyor, uygulama yeniden açılınca sıra korunuyor
- EQ bandı sürüklenip uygulama kapatılıp açılıyor → değişiklik yerinde
  (otomatik kaydetme)
- Gömülü "FPS Footsteps" düzenlenince "(özel)" kopyası açılıyor ve kullanıcı
  bunu görüyor
- AutoEQ'dan indirilen bir `.txt` içe aktarılıyor, eğri doğru çiziliyor
- Dışa aktarılan `.sonarprofile` başka bir kanala içe aktarılınca birebir aynı

---

## Yol boyunca yakalananlar

_(faz sırasında doldurulacak)_
