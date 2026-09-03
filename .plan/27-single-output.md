# Faz 27 — Çoklu çıkışın geri alınması

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 26

---

Kullanıcı kararı: kanal başına ayrı fiziksel çıkış karışıklık üretiyor, SteelSeries'te de
yalnızca yayın modu kapalıyken vardı. Eski davranışa dönülüyor.

- [ ] `api.add_output_bus` / `remove_output_bus` / `rename_bus` / `set_channel_output` ve
      D-Bus karşılıkları kaldırılsın. `sonar-cli output` ve `send` komutları kaldırılsın.
- [ ] `MasterStrip`'ten "＋ Çıkış ekle" ve bus silme düğmesi, `ChannelStrip`'ten çıkış
      seçici kalksın.
- [ ] Model **sadeleşsin ama şema geriye uyumlu kalsın**: `MasterBus.kind` ve
      `Channel.sends` sözlüğü kalıyor (göç zaten yapıldı, iki bus'la bugünküyle birebir
      aynı grafı üretiyor). `Channel.output_bus` kaldırılsın; gönderi hep varsayılan
      çıkışa gitsin. Yükleme sırasında fazladan çıkış bus'ı varsa **birleştirilip
      silinsin** ve kullanıcıya bildirilsin.
- [ ] `sonar-cli volume <kanal> output …` adı korunsun (artık tek çıkış demek).

**Ölçüm:** kullanıcının mevcut `config.toml`'u fazladan bus içeriyorsa temizleniyor;
üretilen conf iki bus'lı hâle byte-eş dönüyor.
