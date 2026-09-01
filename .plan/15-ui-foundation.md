# Faz 15 — Arayüz altyapısı: popup katmanı ve canlı bağlama

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 7, Faz 8
**Çıktı:** `src/sonar/gui/qml/ui/SonarComboBox.qml`,
`src/sonar/gui/qml/ui/SonarLevelMeter.qml`, `src/sonar/gui/qml/ChannelFx.qml`,
`src/sonar/gui/qml/ChannelStrip.qml`, `src/sonar/gui/bridge.py`,
`src/sonar/gui/app.py`

---

## Amaç

Kullanıcının bildirdiği üç arayüz hatası aynı iki kök nedene iniyor.

> Uygulamadaki neredeyse tüm dropdown menüler sıkıntılı. Başka kısımların altına
> giriyor, düzgün görünmüyor altta kaldığı için.

> Kanallar için ayarlama ekranlarında eq gibi switchleri açmak zor. Tıklıyorum
> açılmıyor, başka kanala geçiş yapıp tekrar geri dönünce açık görünüyor.

> Mikser ekranında ses seviyesi sliderları yanında boş kısımlar var. Ses seviyesini
> gösteren gösterge varsa çalışmıyordu, boş görünüyordu.

---

## Kök neden 1 — popup katmanı

`SonarComboBox.qml`'deki açılır liste sıradan bir `Rectangle` çocuğu. QML'de `z`
yalnızca **kardeşler arasında** geçerlidir; başka bir panelin içindeki bir öğe, dış
panelin `z`'sini aşamaz ve üst kapsayıcı `clip` yapıyorsa kırpılır. Ayrıca dışarı
tıklayınca kapanmıyor ve uzun listelerde kaydırma göstergesi yok.

**Çözüm:** `QtQuick.Controls`'un `Popup`'ı. Popup `Overlay.overlay` katmanında,
yani sahnenin en üstünde açılır. Görsel öğelerin hepsi bizim kalır — **radius 0
kuralı geçerli**, Controls'un varsayılan stili kullanılmaz. `app.py` içinde
`QQuickStyle.setStyle("Basic")` çağrılır ki platform stili araya girmesin.

Kazanılanlar: hiçbir panelin altında kalmama, dışarı tıklayınca kapanma, `ListView`
+ `clip` + `ScrollBar` ile kaydırma, ekranın altına taşacaksa yukarı açılma, klavye
ile gezinme (yukarı/aşağı/Enter/Esc).

Kullanım yerleri: `ChannelFx.qml` (profil seçici), `ChannelStrip.qml` (profil
seçici), `MasterStrip.qml` (cihaz seçicileri), `Mixer.qml`.

## Kök neden 2 — fonksiyon çağrısı bağlama değildir

`ChannelFx.qml`:

```qml
active: root.stageOn("gate")     // ← fonksiyon çağrısı, revision'a bağlı değil
```

QML bir bağlamayı yalnızca içinde okunan **property'ler** değişince yeniden
değerlendirir. `stageOn()` içeride `bridge.filterOf(...)` çağırıyor ama hiçbir
property okumuyor, bu yüzden `bridge.revision` artınca bağlama tazelenmiyor.
Kanal değiştirip dönmek `target`'ı değiştirdiği için bağlama o zaman yeniden
değerlendiriliyor — kullanıcının gördüğü tam olarak bu.

Doğru kalıp zaten `ChannelStrip.qml:20`'de var:

```qml
readonly property real chatmixGain:
    bridge ? (bridge.revision, bridge.chatmixGain(channel.id)) : 1.0
```

`stageOn()` ve `paramOf()` aynı kalıba çekilir. `EqPanel.qml` de aynı gözle taranır.

## Kök neden 3 — metreler

`Mixer.qml` şeride `channel: bridge.channels.get(index)` ile **anlık bir sözlük
kopyası** veriyor. `LevelsUpdated` → `ChannelModel.update_row()` modeli güncelliyor
ama kopya tazelenmiyor, dolayısıyla `channel.personalPeak` hiç değişmiyor.

Şeridin tamamını 20 Hz'de yeniden değerlendirmek israf olur. Çözüm dar tutulur:

- Köprüye `levelsRevision` sayacı (`Property(int, notify=levelsChanged)`) ve
  `levelOf(channelId)` slotu
- `onLevelsUpdated` bu sayacı artırır
- `ChannelStrip` **yalnızca metre bileşenlerini** bu sayaca bağlar

`SonarLevelMeter` görsel olarak da tamamlanır: -60…0 dB ölçek, yeşil (< -18 dB),
sarı (-18…-6 dB), kırmızı (> -6 dB) bölgeleri, peak-hold çizgisi, clip göstergesi.

---

## Görevler

- [ ] `app.py`: `QQuickStyle.setStyle("Basic")`
- [ ] `SonarComboBox` → `Popup` tabanlı, radius 0, kaydırmalı, dışarı tıklayınca kapanır
- [ ] Ekran altına taşan popup yukarı açılır
- [ ] Klavye ile gezinme (↑ ↓ Enter Esc)
- [ ] `ChannelFx.stageOn()` / `paramOf()` → `bridge.revision`'a bağlanır
- [ ] `EqPanel.qml` aynı hata için taranır
- [ ] Köprüye `levelsRevision` + `levelOf(channelId)`
- [ ] `ChannelStrip` metreleri `levelsRevision`'a bağlanır
- [ ] `SonarLevelMeter`: renk bölgeleri, peak-hold, clip
- [ ] QML yükleme testi (alt süreçte) yeni `Popup` bağımlılığıyla geçer

---

## Kontrol listesi — "fonksiyon çağrısı bağlama değildir"

Bunu bir testle korumak mümkün değil, bu yüzden elle taranan yerler burada tutulur:

- [ ] `ChannelFx.qml` — `stageOn`, `paramOf`
- [ ] `EqPanel.qml`
- [ ] `ChannelStrip.qml` — `chatmixGain` ✅ (zaten doğru)
- [ ] `MasterStrip.qml`
- [ ] `Mixer.qml`

---

## Doğrulama

- Profil dropdown'ı EQ panelinin üstünde açılıyor, hiçbir yerde kırpılmıyor
- 30 profilli bir listede kaydırma çalışıyor, tıklama doğru satırı seçiyor
- Noise Gate anahtarı **ilk tıklamada** açılıyor, ses anında değişiyor
- Müzik çalarken Media şeridinin metresi oynuyor, sessizde -60 dB'ye düşüyor
- Metre CPU maliyeti ölçülür (Faz 6'da 3–5% idi, artmamalı)

---

## Yol boyunca yakalananlar

_(faz sırasında doldurulacak)_
