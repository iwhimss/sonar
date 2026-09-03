# Faz 29 — Smart Volume profile taşınıyor

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 25

---

Kullanıcı: *"Bu ayar kanal profili ayarlarında olmalı. Her profilde bu ayar olmalı. Bu
ayar açıksa o profilde ses varken diğer kanalların sesi ayarlar değerinde kısılmalı."*

- [ ] `DuckingConfig` `SonarConfig`'ten `Profile`'a taşınsın. Anlamı: **profili bu ayarı
      açık olan kanal tetikleyicidir**, diğer tüm çıkış kanalları kısılır. Birden fazla
      kanalda açıksa hepsi tetikleyici olur.
- [ ] `engine/ducking.py` tetikleyicileri artık `config` + aktif profillerden çıkarsın
      (`duck_targets` imzası profil sağlayıcı alsın). Zarf mantığı aynen kalsın —
      ölçülmüş ve doğru çalışıyor (-12.1 dB, ~200 ms atak, ~600 ms bırakma).
- [ ] Master şeridindeki Smart Volume paneli kaldırılsın; FX sayfasına kendi
      `SonarFilterPanel`'i gelsin (indirim, eşik, atak, tut, bırakma).
- [ ] `settings.ducking` alanı göçte profile taşınsın (şema 4): mevcut ayar,
      `trigger_channels` listesindeki kanalların **aktif profillerine** yazılsın.
- [ ] `sonar-cli smart` komutu hedef alsın: `sonar-cli smart chat on --reduction-db -12`.

**Ölçüm:** Chat profilinde Smart Volume açıkken Chat'e ton verilince Media kısılıyor;
Chat'in profilini kapalı bir profile çevirince ducking duruyor.
