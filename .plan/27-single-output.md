# Faz 27 — Çoklu çıkışın geri alınması

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 26

---

Kullanıcı kararı: kanal başına ayrı fiziksel çıkış karışıklık üretiyor, SteelSeries'te de
yalnızca yayın modu kapalıyken vardı. Eski davranışa dönülüyor.

- [x] `api.add_output_bus` / `remove_output_bus` / `rename_bus` / `set_channel_output` ve
      D-Bus karşılıkları kaldırılsın. `sonar-cli output` ve `send` komutları kaldırılsın.
- [x] `MasterStrip`'ten "＋ Çıkış ekle" ve bus silme düğmesi, `ChannelStrip`'ten çıkış
      seçici kalksın.
- [x] Model **sadeleşsin ama şema geriye uyumlu kalsın**: `MasterBus.kind` ve
      `Channel.sends` sözlüğü kalıyor (göç zaten yapıldı, iki bus'la bugünküyle birebir
      aynı grafı üretiyor). `Channel.output_bus` kaldırılsın; gönderi hep varsayılan
      çıkışa gitsin. Yükleme sırasında fazladan çıkış bus'ı varsa **birleştirilip
      silinsin** ve kullanıcıya bildirilsin.
- [x] `sonar-cli volume <kanal> output …` adı korunsun (artık tek çıkış demek).

**Ölçüm:** kullanıcının mevcut `config.toml`'u fazladan bus içeriyorsa temizleniyor;
üretilen conf iki bus'lı hâle byte-eş dönüyor.


---

## Uygulanan hâli

`MasterBus.kind` ve `Channel.sends` sözlüğü **duruyor** — göç zaten yapılmıştı ve iki
bus'la bugünküyle birebir aynı grafı üretiyor. Kalkanlar: `Channel.output_bus`,
`SonarConfig.output_bus_of()`, `next_bus_order()`, dört D-Bus metodu, `sonar-cli output`
ve `send`, arayüzdeki çıkış seçici ile "＋ Çıkış ekle".

`api._bus("output")` artık "varsayılan çıkış bus'ı" demek; arayüz bus kimliğini bilmek
zorunda değil. Köprü ayrıca `outputBusId` özelliğini veriyor.

**Göç:** `ConfigStore._collapse_extra_outputs()` yüklemede fazladan çıkış bus'ı bulursa
siliyor, kanalların o bus'a giden gönderilerini düşürüyor ve loglara yazıyor. Profil
dosyaları diskte bırakılıyor — kullanıcı geri dönmek isterse elde olsun.

**MasterStrip baştan yazıldı** (Faz 28'in dişli maddesi de burada karşılandı, aynı
dosyayı iki kez elden geçirmemek için): başlıkta dişli, cihaz bölümü katlanabilir,
Yayın Miksi satırı OBS'e "yalnızca bu aygıtı ekleyin" diyor.

**Sapma:** dişlinin katlanma durumu kalıcı **değil**. Bir arayüz tercihi için D-Bus
gidiş-dönüşü ve şema alanı eklemeye değmedi; varsayılan açık.
