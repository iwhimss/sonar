# Faz 29 — Smart Volume profile taşınıyor

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 25

---

Kullanıcı: *"Bu ayar kanal profili ayarlarında olmalı. Her profilde bu ayar olmalı. Bu
ayar açıksa o profilde ses varken diğer kanalların sesi ayarlar değerinde kısılmalı."*

- [x] `DuckingConfig` `SonarConfig`'ten `Profile`'a taşınsın. Anlamı: **profili bu ayarı
      açık olan kanal tetikleyicidir**, diğer tüm çıkış kanalları kısılır. Birden fazla
      kanalda açıksa hepsi tetikleyici olur.
- [x] `engine/ducking.py` tetikleyicileri artık `config` + aktif profillerden çıkarsın
      (`duck_targets` imzası profil sağlayıcı alsın). Zarf mantığı aynen kalsın —
      ölçülmüş ve doğru çalışıyor (-12.1 dB, ~200 ms atak, ~600 ms bırakma).
- [x] Master şeridindeki Smart Volume paneli kaldırılsın; FX sayfasına kendi
      `SonarFilterPanel`'i gelsin (indirim, eşik, atak, tut, bırakma).
- [x] `settings.ducking` alanı göçte profile taşınsın (şema 4): mevcut ayar,
      `trigger_channels` listesindeki kanalların **aktif profillerine** yazılsın.
- [x] `sonar-cli smart` komutu hedef alsın: `sonar-cli smart chat on --reduction-db -12`.

**Ölçüm:** Chat profilinde Smart Volume açıkken Chat'e ton verilince Media kısılıyor;
Chat'in profilini kapalı bir profile çevirince ducking duruyor.


---

## Uygulanan hâli

`DuckingConfig` `SonarConfig`'ten `Profile`'a taşındı (şema 4). `trigger_channels` alanı
**kalktı**: tetikleyici, ayarı açık olan profili taşıyan kanalın kendisi. `target_channels`
boşsa "kendisi dışındaki her çıkış kanalı".

`Ducker` artık **tetikleyici başına ayrı zarf** tutuyor — her kanalın kendi indirimi ve
kendi atak/bırakma süresi var. Bir hedef birden fazla tetikleyicinin kapsamındaysa
**en derin** indirim uygulanıyor (çarpmak yerine), böylece toplam indirim ayarlanan
değerlerin ötesine geçmiyor.

Panel master şeridinden FX sayfasına taşındı. `sonar-cli smart <kanal> on|off`.

## Ölçüm (canlı graf, 2026-09-04)

Chat'in `Default` profilinde Smart Volume açık, Chat'e 2 saniyelik ton:

```
440 Hz (media) zarfı: -20 … -20 -26 -32 … -32 -30 -28 -26 -24 -22 -20 … -20
indirim 12.3 dB (ayar -12.0)
```

## Yol boyunca yakalananlar

**`SetSpatial` silinirken `SetDucking` de silindi.** İki metot arasındaki dilimi
kaldırırken aradaki metot da gitti; `sonar-cli smart` "No such method" verdi. Ders:
dilim silmek yerine hedefli değiştirme yapmak gerekiyor — aynı hata `bridge.py`'de de
oldu (`_get_outputs` silerken 19 metot birden gitti) ve orada `git checkout` ile
geri alındı.
