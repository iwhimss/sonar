# Faz 15 — Arayüz altyapısı: popup katmanı ve canlı bağlama

**Durum:** 🟢 Tamamlandı
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

- [x] `app.py`: `QQuickStyle.setStyle("Basic")`
- [x] `SonarComboBox` → `Popup` tabanlı, radius 0, kaydırmalı, dışarı tıklayınca kapanır
- [x] Ekran altına taşan popup yukarı açılır
- [x] Klavye ile gezinme (↑ ↓ Enter Esc)
- [x] `ChannelFx.stageOn()` / `paramOf()` → `bridge.revision`'a bağlanır
- [x] `EqPanel.qml` aynı hata için tarandı — `eqPayload()` zaten `bridge.revision`
      okuyordu (Faz 8'de yakalanmış)
- [x] Köprüye `levelsRevision` + `levelOf(channelId)`
- [x] `ChannelStrip` metreleri `levelsRevision`'a bağlanır
- [x] `SonarLevelMeter`: renk bölgeleri, peak-hold, clip — **zaten vardı**,
      eksik olan yalnızca veriydi
- [x] QML yükleme testi (alt süreçte) yeni `Popup` bağımlılığıyla geçer

---

## Kontrol listesi — "fonksiyon çağrısı bağlama değildir"

Bunu bir testle korumak mümkün değil, bu yüzden elle taranan yerler burada tutulur.
Kural: **köprüde tanımlı bir `@Slot` bir bağlamanın içinde çağrılıyorsa, aynı
bağlamada `bridge.revision` (veya metreler için `bridge.levelsRevision`) da
okunmalı.**

- [x] `ChannelFx.qml` — `stageOn`, `paramOf`
- [x] `EqPanel.qml`
- [x] `ChannelStrip.qml` — `chatmixGain` (zaten doğruydu), `apps`, `level`
- [x] `MasterStrip.qml`
- [x] `Mixer.qml`

---

## Doğrulama (2026-09-01)

**Metreler çalışıyor.** Köprü D-Bus'a bağlanıp `SubscribeMeters(true)` dedi ve
6 saniye boyunca `levelOf("media")` örneklendi:

| durum | `levelsRevision` | okunan tepe |
|---|---|---|
| 0.05 genlikli 300 Hz sinüs çalarken | 4 → 122 (≈20 Hz) | **-26.0 dBFS** |
| sessizken | 5 → 117 | **-60.0 dBFS** (taban) |

-26.0 dBFS, 0.05 genliğin tam karşılığı (20·log₁₀0.05 = -26.02). Sayaç saniyede
~20 kez artıyor, yani `LevelsUpdated` akışı arayüze ulaşıyor.

**GUI hatasız yükleniyor:** `QQuickStyle.setStyle("Basic")` + `Popup` ile QML
konsolunda tek uyarı yok. (Görünen tek uyarı portal kaydı; `.desktop` dosyası
henüz kurulu olmadığı için, Faz 11'de geçecek.)

Kullanıcının ikinci testte bakacakları:
- Profil dropdown'ı EQ panelinin üstünde açılıyor, hiçbir yerde kırpılmıyor
- Uzun listede kaydırma çalışıyor, tıklama doğru satırı seçiyor
- Noise Gate anahtarı **ilk tıklamada** açılıyor

---

## Yol boyunca yakalananlar

**`ChannelFx`'in `channel`, `profile`, `names` bağlamaları da kırıktı** — yalnızca
`stageOn`/`paramOf` değil. Üçü de köprü fonksiyonu çağırıyor ve hiçbir property
okumuyordu; `tick` özelliği dosyada tanımlıydı ama **hiçbir yerde okunmuyordu.**
Hepsi `(tick, bridge.…)` kalıbına çekildi.

**`isMic` sabit bir isim listesiydi.** `target === "mic" || target === "stream_mic"`
Faz 13'ten sonra yanlış: kullanıcı kendi giriş kanalını ekleyebiliyor. Yerine
köprüde `isInputChannel(target)`.

**Metre değerleri kanal satırlarından çıkarıldı.** `ChannelModel`'in
`personalPeak`/`streamHold`/`clipped` rolleri ve `_refresh_models()`'teki "metre
değerlerini koru" bloğu silindi; seviyeler artık köprüde ayrı bir sözlükte duruyor.
Sebep: satırlara yazmak zaten işe yaramıyordu (şerit sözlük kopyası alıyor) ve
saniyede 20 kez `dataChanged` yayınlamak boşuna işti.

**Ayrı sayaç şart.** `revision` saniyede 20 kez artsaydı her şeridin her bağlaması
— profil listesi, uygulama listesi, ChatMix rozeti — 20 Hz'de yeniden
değerlendirilirdi. `levelsRevision` yalnızca metre bileşenlerini uyandırıyor.

**`SonarLevelMeter`'a dokunulmadı.** Renk bölgeleri, peak-hold çizgisi ve clip
göstergesi Faz 7'de yazılmıştı ve doğruydu; eksik olan yalnızca veriydi.
