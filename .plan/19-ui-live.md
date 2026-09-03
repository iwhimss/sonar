# Faz 19 — Arayüzün canlılığı ve yerleşimi

**Durum:** 🟢 Tamamlandı
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

- [x] `ChannelStrip` artık sözlük almıyor: `required property int index` +
      `Repeater` rol özellikleri (`required property string id`, `name`, `color`,
      `activeProfile`, `personalVolume`, `personalMuted`, `streamVolume`, `streamMuted`,
      `kind`, `profiles`). Rol adları `ChannelModel.keys` ile birebir aynı.
- [x] Fader/mute Repeater'ının model dizisi artık `modelData` üzerinden donmuş değer
      taşımaz; her alt öğe doğrudan şeridin özelliklerini okur.
- [x] `MasterStrip` ve `ChannelFx` aynı gözle taranır.

### 2. `bridge.<fonksiyon>()` bağlama denetimi

Faz 15'te başlanan kontrol listesi genişletiliyor. Kural: **bir fonksiyon çağrısı
bağlama kurmaz**; ya bir `Property` okunmalı (`revision`, `levelsRevision`) ya da değer
bir sinyalle itilmeli.

- [x] `Mixer.qml` — `channels.get(index)` (düzeltildi), akış menüsündeki `channels.get(index)`
- [x] `MasterStrip.qml` — `deviceList()`, `deviceOf()`, `volumeOf()`, `mutedOf()`
- [x] `ChannelStrip.qml` — `chatmixGain()`, `streamsFor()`, `favoritesOf()`
- [x] `ChannelFx.qml` — `stageOn()`, `paramOf()`, `profileOptions`
- [x] `EqPanel.qml`

### 3. Sürükleme vekili

- [x] Yeni `ui/SonarDragProxy.qml`: `Overlay.overlay` üzerinde duran, imleci izleyen
      köşesiz bir kutucuk kopyası.
- [x] `ChannelStrip` kutucuğu sürüklenirken vekili gösterir, kendi yerinde soluk kalır.
      `Drag.source` yine asıl kutucuk (bırakma mantığı değişmez).
- [x] Bırakma hedefi vurgusu (`DropArea.containsDrag`) korunur.

### 4. Yerleşim sabitlenir

- [x] `MasterStrip` (34+200+250) ve `ChannelStrip` (34+30+250+kalan) sabit piksel
      yükseklikleri bırakılır → `ColumnLayout` + `Layout.fillHeight`.
- [x] Pencereye `minimumWidth` / `minimumHeight` verilir (`Main.qml`).
- [x] Başlık satırı taşmaz: ikon + `elide`'lı ad solda, dişli ve çarpı sağa sabit.
      Şerit genişliği 132 → 148 px.
- [x] Apps kutusu hiçbir pencere boyunda negatif yüksekliğe düşmez.
- [x] **Radius 0 kuralı korunur.**

### 5. Sıfırlanabilir ChatMix

- [x] Slider'ın yanına "Sıfırla" düğmesi (50'ye döner); slider'a çift tıklama da sıfırlar.
- [x] Donanım tekeri etkinken slider salt okunur (Faz 23 bunu doldurur).

---

## Kabul ölçütü

Ekrana bakmayı gerektiren maddeler `.plan/24-verify.md`'ye taşınır. Kod tarafında:

- [x] `bridge` seviyesinde satır güncellemesi testi: `apply_state` sonrası
      `ChannelModel` doğru rolleri `dataChanged` ile bildiriyor
- [x] `ruff` + `pytest` yeşil


---

## Yol boyunca yakalananlar

**Kanal satırının donmasının ölçülmüş kanıtı.** Gerçek daemon'a bağlı bir köprüyle
`sonar-cli mute game stream on` çalıştırıldı: `StateChanged` geliyor, model satır 0 için
`dataChanged` yayınlıyor, `streamMuted` `True → False` oluyor. Yani veri yolu baştan
sağlamdı; kopan tek yer `Mixer.qml`'in şeride verdiği sözlük kopyasıydı.

**"Yayın Miksi" cihaz açılırı kaldırıldı.** Fiziksel cihaz listeliyordu ama stream
bus'ın `device` alanı `confgen`'de hiç kullanılmıyor — sessiz bir no-op'tu. Yerine
OBS'e ne ekleneceğini söyleyen bilgi satırı kondu (`Sonar Stream Mix — Virtual Input`).
Faz 20 bunu bir kopyalama düğmesi ve track anahtarıyla tamamlayacak.

**ChatMix çift tıkla zaten sıfırlanıyormuş** (`SonarSlider.onDoubleClicked`), ama
keşfedilmiyordu. Görünür bir "Sıfırla" düğmesi eklendi; nötr konumdayken pasif.

**Sürükleme vekili neden asıl kutucuğun yerini almıyor:** `DropArea` hedefi sürüklenen
öğenin **konumundan** buluyor, yani asıl kutucuk hareket etmeye devam etmeli. Bu yüzden
o görünmez oluyor (`opacity: 0`) ve imleci mikserin en üst katmanındaki vekil izliyor.

**Yerleşim:** sabit piksel yükseklikleri (`34 + 200 + 250`, `34 + 30 + 250 + kalan`)
`ColumnLayout` ile değiştirildi; fader yüksekliği kalan alandan hesaplanıyor
(`max(80, panel - 100)`), Apps kutusu artık negatif yüksekliğe düşemiyor. Şerit
genişliği 132 → 148 px ve başlık `RowLayout`: ad esniyor, dişli ile çarpı sağa sabit.
