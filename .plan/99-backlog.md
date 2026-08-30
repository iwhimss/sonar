# v1 Sonrası — Backlog

**Durum:** 📋 Liste — v1.0.0 çıktıktan sonra değerlendirilecek

Bu maddeler bilinçli olarak v1 kapsamı dışında bırakıldı. Sıra öncelik sırasıdır.

---

## v1.1 — Otomasyon

### Global kısayollar
Ses artır/azalt/sustur, kanal mute, mikrofon mute, profil değiştir — uygulama odakta olmadan.

- KDE Wayland'da `org.freedesktop.portal.GlobalShortcuts` XDG portalı kullanılır
- Portal desteği yoksa: KDE'nin kendi kısayol sistemine `sonar-cli` komutları bağlanabilir
  (dokümante edilir, otomatik kurulmaz)
- Kısayol yakalama UI'si + çakışma uyarısı

### Otomatik profil değişimi
Kullanıcının asıl senaryosunun otomatik hâli: CS2 açılınca Game kanalı "CS2" profiline geçsin.

- Çalışan süreçleri izle (`/proc` tarama veya PipeWire akış meta verisi)
- Kural: `süreç adı → kanal + profil`
- Oyun kapanınca önceki profile dön
- Tetikleyici olarak akış açılışı (yeni sink-input) da kullanılabilir — daha ucuz
- Çakışma yönetimi: birden fazla eşleşen kural, kullanıcı elle geçiş yaptıysa saygı gösterme

---

## v1.2 — Ses özellikleri

### Spatial audio / sanal surround
SteelSeries'in "Spatial Audio" karşılığı.

- PipeWire `filter-chain`'in `sofa` node'u ile HRIR konvolüsyon
- SOFA dosyası (MIT KEMAR veya kullanıcının kendi HRTF'i)
- 7.1 → binaural downmix; kanal başına açık/kapalı
- "Performance ↔ Immersion" ayarı (erken yansıma miktarı)
- Not: kaliteli bir HRTF pipeline'ı ciddi iş; alternatif olarak mevcut
  `hesuvi`/`atmos` HRIR setlerinin desteklenmesi düşünülebilir

### Spektrum analizörü
EQ eğrisinin arkasında canlı frekans spektrumu (EasyEffects'teki gibi).
- Metre altyapısının genişletilmesi: 8 kHz yerine tam bant yakalama + FFT
- Bu, `pw-cat` yaklaşımının sınırına dayanır → native yardımcı süreç gerekebilir

### Ek efektler
- De-esser, exciter, bass enhancer, stereo genişletici (LSP/Calf'ta hepsi mevcut)
- Convolver (kulaklık düzeltme IR'leri)
- Auto-gain / loudness normalizasyonu (EBU R128)

### VST3 desteği
- `yabridge` veya native Linux VST3 host entegrasyonu
- filter-chain VST3'ü doğrudan desteklemiyor → mimari değişiklik gerekir
  (kendi lilv/VST3 host'umuz) — büyük iş, gerçek talep olursa

---

## v1.3 — Kalite ve erişim

- **Kanal başına kayıt**: her kanalı ayrı WAV'a kaydetme (yayın sonrası düzenleme için)
- **Açık/koyu tema**: şu an yalnızca koyu; açık tema paleti
- **Çoklu dil**: Türkçe + İngilizce (Qt Linguist)
- **Erişilebilirlik**: ekran okuyucu etiketleri, yüksek kontrast modu, tam klavye navigasyonu
- **Yedekleme/geri yükleme**: tüm yapılandırmayı tek dosyaya alma
- **Profil paylaşımı**: profilleri paylaşmak için basit bir dışa aktarma/link formatı

---

## Değerlendirilecek (karar verilmedi)

- **Diğer dağıtımlar**: Flatpak paketi (PipeWire soketi ve LV2 eklenti erişimi portal ile karmaşık)
- **GNOME desteği**: uygulama Qt olduğu için çalışır; global kısayol portalı GNOME'da da var
- **Native motor geçişi**: performans veya kesintisiz efekt ekleme kritik hâle gelirse
  C++/lilv tabanlı motora geçiş (EasyEffects mimarisi). API sınırı korunduğu için
  GUI'yi etkilemez — `engine/` katmanı değişir
- **Donanım entegrasyonu**: Arctis ve benzeri kulaklıklar için HID tabanlı kontrol
  (ChatMix tekeri, pil durumu, yan ton) — `headsetcontrol` projesiyle entegrasyon
