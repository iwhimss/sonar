# Faz 38 — Metinlerin çevrilmesi

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 37
**Çıktı:** ~300 anahtarlık katalog, `core/names.py`, `SettingsDialog.qml`

---

## Amaç

Kullanıcının şikâyeti: *"Uygulamadaki dil kısmı şu anda çok karmaşık, yarısı İngilizce
yarısı Türkçe."* Arayüzde Türkçe metinlerin arasında `Noise Gate`, `Compressor`,
`Limiter`, `Spatial Audio`, `Volume Boost`, `Equalizer`, `MASTER`, `Game/Chat/Media/Aux`
ve `Flat`/`Bass Boost` gibi İngilizce adlar duruyordu.

---

## Ölçüm: `registry.py` etiketleri kullanıcıya hiç ulaşmıyor

Plan `core/dsp/registry.py`'deki ~40 port etiketinin anahtara çevrilmesini öngörüyordu.
`grep`'le bakıldı: `PortSpec.label` hiçbir yerden köprüye veya D-Bus'a çıkmıyor
(`chain.py:294`'teki `spec.label` **eklenti** etiketi, port değil). Arayüzdeki parametre
adları `ChannelFx.qml`'in kendi listelerinden geliyor. O yüzden `registry.py`'ye
dokunulmadı — ölçüm 40 metinlik gereksiz işi eledi.

---

## Görevler

### Arayüz
- [x] `Main.qml`, `Mixer.qml`, `ChannelStrip.qml`, `MasterStrip.qml`, `ChannelFx.qml`,
      `EqPanel.qml` — kullanıcıya görünen her metin `I18n.t(...)`
- [x] Sabit İngilizce panel başlıkları katalog anahtarı oldu: Gürültü Kapısı, Kompresör,
      Limitleyici, Uzamsal Ses, Ses Yükseltme, Ekolayzer, Akıllı Ses
- [x] `ui/*.qml` bileşenleri metin taşımıyor (hepsi dışarıdan alıyor) — dokunulmadı

### Gömülü adlar
- [x] `core/names.py`: `BUILTIN_NAMES`, `PRESET_NAMES`, `display_name()`, `preset_label()`
- [x] Kullanıcı yeniden adlandırmışsa **onun** adı kazanıyor; çeviri yalnızca ada hiç
      dokunulmamışsa devreye giriyor
- [x] `MasterStrip.busLabel()` merkezî eşlemeye bağlandı
- [x] `confgen`'e dokunulmadı — cihaz açıklamaları yapılandırmadan geliyor, dil grafı
      yeniden kurmuyor. `sonar-cli status` çıktısı bunu gösteriyor: kanal adı "Oyun",
      OBS'e verilen ad hâlâ `Sonar Stream Mix`

### Daemon, CLI, içe aktarma
- [x] `ApiError` mesajları katalogdan; **kod alanı değişmedi** (testler koda bakıyor)
- [x] `stream_setup` sorun metinleri ve `conflicts` uyarıları katalogdan
- [x] `bridge._NOTICES` şablonları anahtar tutuyor
- [x] `core/importers.py` hata metinleri
- [x] `cli/__main__.py`: çıktı, `argparse` `help=`/`description=`/`metavar=`.
      Argüman **adları** İngilizce kaldı — betikler kırılmasın

### Ayarlar penceresi (yeni)
- [x] `SettingsDialog.qml` + üst şeritte dişli düğmesi
- [x] Dil seçici (anında uygulanıyor, yeniden başlatma yok)
- [x] `take_over_default_sink` ve `chatmix_invert` — ikisinin de arayüzde hiç karşılığı
      yoktu, yalnızca CLI'den erişiliyordu
- [x] `ui/SonarCheck.qml` (yeni onay kutusu, yuvarlatma yok)

---

## Ölçümle bulunan üç hata

1. **Karışık dilli arayüz.** Köprü `apply_state` içinde çekirdek dili doğrudan
   yazıyordu; QML'in tazeleme tetiği ise `QmlI18n.language`. İkisi ayrı yerlerden
   yazılınca yükleme sırasında değerlenen bağlamalar bir dilde, sonradan tazelenenler
   ötekinde kalıyordu — ekran görüntüsünde yarısı İngilizce yarısı Türkçe çıktı. Tek yol
   bırakıldı: sinyal → `app._apply_language` → `QmlI18n` → çekirdek.
2. **`sonar-cli lang en && sonar-cli status` eski dilde çıkıyordu.** Daemon dili
   gecikmeli kaydediyor, CLI ise diskten okuyor. `set_language` artık anında yazıyor.
3. **`SonarCheck`'te bağlama döngüsü.** Sarılan bir `Text`in yüksekliğini kendi
   `implicitHeight`ine bağlamak Qt'de döngü üretiyor; `Column` görünmeyen çocuğu zaten
   atlıyor, satır kaldırıldı.

Ayrıca `doctor` ekranda ⚠ gösterirken "Sorun bulunamadı." yazıyordu — uyarılar
sayılmıyordu. Artık üçüncü bir özet satırı var.

---

## Doğrulama

- [x] 852 test geçiyor, `ruff` temiz
- [x] `tests/test_i18n.py`: katalog bütünlüğü (anahtar kümeleri, yer tutucular, ölü
      çeviri, kaynakta kullanılan her anahtar)
- [x] `tests/conftest.py`'ye `default_language` autouse fixture'ı: testler geliştiricinin
      kendi dil ayarına bağlı kalmasın
- [x] Arayüz iki dilde offscreen açıldı, ekran görüntüsü alındı, QML uyarısı yok
- [x] `sonar-cli status`/`doctor` iki dilde ölçüldü
