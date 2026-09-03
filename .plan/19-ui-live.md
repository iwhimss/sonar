# Faz 19 — Arayüzün canlılığı ve yerleşimi

**Durum:** ⚪ Bekliyor
**Bağımlılık:** —
**Çıktı:** `src/sonar/gui/qml/Mixer.qml`, `ChannelStrip.qml`, `MasterStrip.qml`,
`ChannelFx.qml`, `Main.qml`, yeni `ui/SonarDragProxy.qml`

---

## Amaç

Kullanıcının "mute düğmeleri çalışmıyor", "gui anlık güncellenmiyor", "sürüklediğim
kutucuk sütunların altında kalıyor", "silme butonu taşmış" şikâyetlerinin tamamı tek bir
kök nedene ve iki yerleşim hatasına dayanıyor.

---

## Ölçülmüş kök neden

`Mixer.qml:29`:

```qml
channel: root.bridge.channels.get(index)
```

`get()` bir **fonksiyon çağrısı** ve `bridge.channels` (model nesnesi) hiç değişmiyor.
Yani bu bağlama bir kez değerlenip donuyor; `ChannelStrip` içindeki her `root.channel.*`
okuması şeridin doğduğu andan kalma bir sözlük kopyası. Model `dataChanged` yayınlasa
bile şerit onu görmüyor.

Sonuçları: mute düğmesi hiç güncellenmiyor, fader daemon'dan gelen değeri göstermiyor,
profil adı değişmiyor, ChatMix rozeti donuk. Aynı hatanın metre sürümü Faz 15'te
`levelsRevision` ile düzeltilmişti; kanal satırında kalmış.

---

## Görevler

### 1. Kanal satırı canlı bağlanır

- [ ] `ChannelStrip` artık sözlük almıyor: `required property int index` +
      `Repeater` rol özellikleri (`required property string id`, `name`, `color`,
      `activeProfile`, `personalVolume`, `personalMuted`, `streamVolume`, `streamMuted`,
      `kind`, `profiles`). Rol adları `ChannelModel.keys` ile birebir aynı.
- [ ] Fader/mute Repeater'ının model dizisi artık `modelData` üzerinden donmuş değer
      taşımaz; her alt öğe doğrudan şeridin özelliklerini okur.
- [ ] `MasterStrip` ve `ChannelFx` aynı gözle taranır.

### 2. `bridge.<fonksiyon>()` bağlama denetimi

Faz 15'te başlanan kontrol listesi genişletiliyor. Kural: **bir fonksiyon çağrısı
bağlama kurmaz**; ya bir `Property` okunmalı (`revision`, `levelsRevision`) ya da değer
bir sinyalle itilmeli.

- [ ] `Mixer.qml` — `channels.get(index)` (düzeltildi), akış menüsündeki `channels.get(index)`
- [ ] `MasterStrip.qml` — `deviceList()`, `deviceOf()`, `volumeOf()`, `mutedOf()`
- [ ] `ChannelStrip.qml` — `chatmixGain()`, `streamsFor()`, `favoritesOf()`
- [ ] `ChannelFx.qml` — `stageOn()`, `paramOf()`, `profileOptions`
- [ ] `EqPanel.qml`

### 3. Sürükleme vekili

- [ ] Yeni `ui/SonarDragProxy.qml`: `Overlay.overlay` üzerinde duran, imleci izleyen
      köşesiz bir kutucuk kopyası.
- [ ] `ChannelStrip` kutucuğu sürüklenirken vekili gösterir, kendi yerinde soluk kalır.
      `Drag.source` yine asıl kutucuk (bırakma mantığı değişmez).
- [ ] Bırakma hedefi vurgusu (`DropArea.containsDrag`) korunur.

### 4. Yerleşim sabitlenir

- [ ] `MasterStrip` (34+200+250) ve `ChannelStrip` (34+30+250+kalan) sabit piksel
      yükseklikleri bırakılır → `ColumnLayout` + `Layout.fillHeight`.
- [ ] Pencereye `minimumWidth` / `minimumHeight` verilir (`Main.qml`).
- [ ] Başlık satırı taşmaz: ikon + `elide`'lı ad solda, dişli ve çarpı sağa sabit.
      Şerit genişliği 132 → 148 px.
- [ ] Apps kutusu hiçbir pencere boyunda negatif yüksekliğe düşmez.
- [ ] **Radius 0 kuralı korunur.**

### 5. Sıfırlanabilir ChatMix

- [ ] Slider'ın yanına "Sıfırla" düğmesi (50'ye döner); slider'a çift tıklama da sıfırlar.
- [ ] Donanım tekeri etkinken slider salt okunur (Faz 23 bunu doldurur).

---

## Kabul ölçütü

Ekrana bakmayı gerektiren maddeler `.plan/24-verify.md`'ye taşınır. Kod tarafında:

- [ ] `bridge` seviyesinde satır güncellemesi testi: `apply_state` sonrası
      `ChannelModel` doğru rolleri `dataChanged` ile bildiriyor
- [ ] `ruff` + `pytest` yeşil
