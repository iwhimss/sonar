# Faz 34 — Fader sıfırlama ve sayısal giriş

> Kullanıcı: *"kanalların ses seviye sliderlarını sıfırlama özelliği olsun chat mixteki
> gibi. Ayrıca değerleri elle de girebilelim rakam olarak."*

Bugün her fader'ın üstünde salt okunur bir yüzde `Text`'i var
(`ChannelStrip.qml:239`, `MasterStrip.qml:190`). Doğru yer orası.

## Görevler

- [ ] `ui/SonarValueField.qml`: yüzdeyi gösteren, tıklayınca düzenlenebilir alan.
      Enter onaylar, Esc iptal, odak kaybı onaylar. "150", "%150", "150,5" kabul.
      0–300'e kırpılır. **Bağlamayı koparmaz**: `value` dışarıdan sürülür, dışarı
      `edited(real)` yayınlar (test turu 3'ün dersi — `SonarSlider`/`SonarFader`).
- [ ] Yanında sıfırlama düğmesi → 1.0. Değer 1.0'ken pasif.
- [ ] Kanal şeridi (2 fader), master şeridi (2 fader), giriş şeritleri — tek bileşen.
- [ ] Çift tıkla sıfırlama (`SonarFader.qml:114`) kalıyor; düğme onu görünür kılıyor.
- [ ] 148 px'lik şeritte taşmasın.

## Ölçüm
- `250` yazıp Enter → `channelVolumes = [2.5, 2.5]` (`pw-dump`, +7.96 dB)
- Sıfırlama → `[1.0, 1.0]` ve tutamak gerçekten ortaya dönüyor (bağlama regresyonu)
