# Faz 31 — EQ: nokta ekleme ve silme

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 26

---

Kullanıcı: *"Bandlar kısmından sayı seçmek yerine EQ ayarında bir yere sağ tık ile ekle
diyip nokta ekleyebilmek veya olan noktayı silebilmek istiyorum."*

- [ ] "BANDLAR" açılır menüsü kaldırılsın. `EqState.band_count` alanı kalsın ama artık
      `len(bands)` ile senkron tutulsun (şema göçü gerekmez).
- [ ] `EqPanel` eğri alanında **sağ tık → o frekansta yeni band**, band düğümünde
      **sağ tık → sil**. Yeni bandın frekansı tıklanan x, kazancı tıklanan y, `Q` 1.41.
- [ ] Yeni API: `AddEqBand(target, freq, gain_db)` → yeni bandın indeksi;
      `RemoveEqBand(target, index)`. İkisi de **canlı** olmalı.
- [ ] **Bunun için EQ eklentisi kapasitesi sabitlenecek.** Bugün band sayısı
      `para_equalizer_x8/16/32` arasında seçim yapıyor ve değişimi **yapısal**.
      İlk uygulama adımı: x32'nin boştaki ve ses akarkenki CPU maliyetini ölçmek.
      Kabul edilebilirse zincir her zaman x32 kursun ve band ekleme/silme tamamen canlı
      olsun. Değilse kapasite basamağı aşıldığında yeniden inşa olacağı arayüzde söylensin.
- [ ] Üst sınır kapasiteye eşit (32); sınırda "ekle" pasifleşsin.
- [ ] `core/importers.py` içe aktarımı band sayısını artık kırpmasın, gelen kadar band
      oluştursun (kapasiteye kadar).

**Ölçüm:** 10 banddan 20'ye çıkarken ses kesilmiyor; çizilen eğri ile ölçülen yanıt
arasındaki sapma Faz 8'deki gibi ≤0.01 dB kalıyor.
