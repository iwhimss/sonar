# Faz 26 — Yerleşim onarımı

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 27–31 (arayüz son hâlini aldıktan sonra)

---

> **Sıra değişikliği (uygulama sırasında):** Faz 26 (yerleşim) **en sona**, Faz 31'den
> sonra alındı. Faz 27–31 arayüzden panel siliyor ve taşıyor; yerleşimi önce düzeltmek
> aynı işi iki kez yapmak olurdu. Gerçek sıra: 25 → 27 → 28 → 29 → 30 → 31 → 26 → 32.

---

Kullanıcının önerisi doğrultusunda **sayfa kaydırılabilir** olacak; ayrıca sabit piksel
yüksekliklerinin kalanları temizlenecek.

- [x] `Main.qml` içeriği bir `Flickable` + ince kaydırma göstergesine alınsın. Mikser ve
      FX sayfaları kendi doğal yüksekliklerini bildirsin; pencere küçükse kaydırılsın,
      büyükse esnesin. `minimumWidth/Height` gerçekten sığan bir değere indirilsin.
- [x] `Mixer.qml`: şeritler `Row` yerine yatay kaydırılabilir bir alanda dursun (çok
      kanalda taşma bitsin). "＋ Kanal ekle" paneli şerit yüksekliğini takip etsin ve
      düğme üstte hizalansın.
- [x] `MasterStrip` yüksekliği kanal şeritleriyle **aynı** olsun; cihaz bölümü Faz 28'de
      dişliyle katlanacağı için kalan alan fader'lara değil boşluğa gitsin.
- [x] **Tüm diyaloglar tek bir bileşene taşınsın** (yeni `ui/SonarDialog.qml`):
      `Overlay` katmanında açılır, ekrana göre ortalanır, yüksekliği içeriğinden gelir,
      dışarı tıklayınca kapanır. `Mixer.qml` kanal ekleme/silme ve `MasterStrip` çıkış
      ekleme (Faz 27'de kalkıyor) bunu kullansın. `parent: root.parent` kalıbı silinsin —
      `Row` içinde `anchors` uyarısının kaynağı bu.
- [x] `ChannelFx.qml` `dynamics` satırı sabit 168 px yerine `implicitHeight`inden
      beslensin; panel sayısı **görünen** panellerden hesaplansın (mikrofonda da 4).
      Dar pencerede paneller alt satıra sarsın.
- [x] Sürükleme vekili yeniden yazılsın: konum `Overlay` katmanında, global imleç
      konumundan; `DropArea` hedefi asıl kutucuktan gelmeye devam etsin. Vekil hiçbir
      koşulda görünmezse sürükleme yine çalışsın (sessiz bozulma olmasın).
- [x] `MİKROFONU KULLANANLAR` gibi uzun başlıklar `elide` edilsin.

**Ölçüm:** ekrana bakmayı gerektiriyor → `.plan/32-verify.md`'de kullanıcı testine
bırakılır. Kod tarafında: GUI hiçbir QML uyarısı vermeden açılmalı (bugün
`Mixer.qml:14` uyarısı yağıyor).


---

## Uygulanan hâli

**Ortak `ui/SonarDialog.qml`.** `QtQuick.Controls`'un `Popup`'ı üzerine: `Overlay`
katmanında açılıyor, ebeveynin yerleşiminden bağımsız, yüksekliği içeriğinden geliyor,
dışarı tıklayınca kapanıyor. `Mixer`'daki üç pencere (akış menüsü, kanal silme, kanal
ekleme) buna geçti. `parent: root.parent` kalıbı — `Mixer.qml:14` uyarısının ve yarım
görünen "Çıkış ekle" penceresinin kaynağı — tamamen kalktı.

**Kaydırma üç yerde:**
* Mikser şeritleri yatay `ScrollView` içinde — kanal sayısı arttıkça taşmıyor.
* FX sayfası dikey `ScrollView` içinde ve kendi `implicitHeight`ini bildiriyor.
* Master şeridinin cihaz bölümü kendi içinde kayıyor — kısa pencerede fader'ları
  eziyordu, artık fader panelinin payı garanti.

**Panel satırı `Flow` oldu** (Faz 30'da): sığdığı kadar yan yana, sığmayınca alt satıra.
Sabit `height: 168` ve yanlış `panelCount` hesabı gitti.

**Sürükleme vekili** artık konumu ve görünürlüğü aynı yerden alıyor (`onPositionChanged`).
Tek bir "başlat" çağrısına bağlı kalmak, o çağrı kaçırıldığında kutucuğun tamamen
kaybolması demekti. Asıl kutucuk `opacity: 0` yerine `0.25` — nereden geldiği görünüyor.

Pencere alt sınırı 900×620 → **640×420**.

## Doğrulama

`QT_QPA_PLATFORM=offscreen` ile dört boyutta ekran görüntüsü alınıp gözle kontrol edildi
(`scratchpad/shots/`): mikser 1180×720 ve 900×560, FX 1400×900 ve 900×560. GUI **sıfır
QML uyarısıyla** açılıyor; test turu 3'te `Mixer.qml:14` uyarısı yağıyordu.

Kalan küçük ayar: dar pencerede "değişiklikler otomatik kaydediliyor" notu yarım
kırpılıyordu; artık sığmıyorsa tamamen gizleniyor.
