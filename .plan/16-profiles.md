# Faz 16 — Profil deneyimi

**Durum:** 🟢 Tamamlandı
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

- [x] `api.new_profile(target, name)` — düz profil, kaydet, geç
- [x] `NewProfile` D-Bus metodu + `sonar-cli new` ve `sonar-cli favorite`
- [x] "Farklı kaydet" düğmesi kaldırılır, "＋ Yeni profil" gelir
- [x] `SonarConfig.favorites` + şema 2 migrasyonu (`favorite_slot` → liste)
- [x] `SetProfileFavorite(target, name, bool)` + `ReorderFavorites(target, names)`
- [x] FX sayfasında yıldız düğmesi
- [x] Sürüklenerek sıralanan, sınırsız favori şeridi
- [x] Mikser dropdown'ı: favoriler + ayraç + tümü
- [x] "değişiklikler otomatik kaydediliyor" notu profil şeridinde
- [x] Gömülü preset kopyası bildirimi (`profile_copied`)
- [x] `FileDialog` ile içe aktarma (sonuç penceresi Faz 17'ye — köprü şu an
      sonucu yutuyor, hata/uyarı akışı orada bağlanacak)
- [x] `FileDialog` ile dışa aktarma (`.sonarprofile` / AutoEQ)
- [x] Testler: migrasyon, favori sıralaması, `new_profile` düzlüğü

---

## Doğrulama (2026-09-01, çalışan daemon üzerinde)

```
$ sonar-cli new game "CS2"            → yeni düz profil 'CS2' oluşturuldu ve etkin
$ sonar-cli new game "Arc Raiders"    → yeni düz profil 'Arc Raiders' oluşturuldu ve etkin
$ sonar-cli favorite add game CS2
$ sonar-cli favorite add game "Arc Raiders"
$ sonar-cli favorite list game        → Flat, CS2, Arc Raiders
```

**Şema 2 göçü gerçek config'te çalıştı.** Kullanıcının test oturumundan kalan
`favorite_slot` değerleri otomatik taşındı: `config.toml` içinde artık
`[favorites] game = ["Flat", "CS2"]`, `media = ["Default", "Default2"]` ve
`schema_version = 2`.

**Sıralama köprüden doğrulandı** (D-Bus üzerinden, gerçek daemon):

```
önce:  ['Flat', 'CS2', 'Arc Raiders']
reorderFavorites(game, ['Arc Raiders', 'Flat', 'CS2'])
sonra: ['Arc Raiders', 'Flat', 'CS2']       ← diskten geri okundu
```

Dışa aktarma çağrısı da içerik döndürüyor.

Kullanıcının ikinci testte bakacakları:

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

**Otomatik kaydetme zaten çalışıyordu.** Her profil düzenlemesi `_live_target()` →
`_dirty_profiles` → `_save_soon()` (500 ms) üzerinden diske yazılıyordu; eksik olan
kullanıcının bunu **bilmesiydi**. Profil şeridine kısa bir not eklendi ve "Farklı
kaydet" düğmesi kaldırıldı — o düğme, "kaydetmezsem kaybolur" yanılgısını
besleyen şeydi.

**`favorite_slot` profil dosyasında yaşıyordu, `config.toml`'da değil.** Bu yüzden
şema 2 göçü yalnızca `config.toml`'a bakamıyor; `ConfigStore._migrate_favorites()`
her hedefin profil dosyalarını tarayıp eski slot numaralarına göre sıralıyor.
`schema_version < 2` koşuluna bağlı, yani bir kez çalışıyor — kullanıcı sonradan
tüm favorileri silerse geri gelmiyorlar.

**Favori listesi profil silme ve yeniden adlandırmayı takip ediyor.** Silinen profil
listeden düşüyor, yeniden adlandırılan profil yeni adıyla yerinde kalıyor,
silinen kanalın tüm favorileri gidiyor. `list_favorites()` ayrıca artık var olmayan
adları okuma anında eliyor — elle düzenlenmiş bir `config.toml` arayüzü bozmasın.

**Sıralamada "unutulan adlar" korunuyor.** `reorder_favorites()` çağıranın
listesinde olmayan favorileri sona ekliyor. Arayüz eski bir sırayla çağırırsa
(iki pencere açıkken olabilir) favori sessizce kaybolmuyor.
