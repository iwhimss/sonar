# Faz 26 — Yerleşim onarımı

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 27–31 (arayüz son hâlini aldıktan sonra)

---

> **Sıra değişikliği (uygulama sırasında):** Faz 26 (yerleşim) **en sona**, Faz 31'den
> sonra alındı. Faz 27–31 arayüzden panel siliyor ve taşıyor; yerleşimi önce düzeltmek
> aynı işi iki kez yapmak olurdu. Gerçek sıra: 25 → 27 → 28 → 29 → 30 → 31 → 26 → 32.

---

Kullanıcının önerisi doğrultusunda **sayfa kaydırılabilir** olacak; ayrıca sabit piksel
yüksekliklerinin kalanları temizlenecek.

- [ ] `Main.qml` içeriği bir `Flickable` + ince kaydırma göstergesine alınsın. Mikser ve
      FX sayfaları kendi doğal yüksekliklerini bildirsin; pencere küçükse kaydırılsın,
      büyükse esnesin. `minimumWidth/Height` gerçekten sığan bir değere indirilsin.
- [ ] `Mixer.qml`: şeritler `Row` yerine yatay kaydırılabilir bir alanda dursun (çok
      kanalda taşma bitsin). "＋ Kanal ekle" paneli şerit yüksekliğini takip etsin ve
      düğme üstte hizalansın.
- [ ] `MasterStrip` yüksekliği kanal şeritleriyle **aynı** olsun; cihaz bölümü Faz 28'de
      dişliyle katlanacağı için kalan alan fader'lara değil boşluğa gitsin.
- [ ] **Tüm diyaloglar tek bir bileşene taşınsın** (yeni `ui/SonarDialog.qml`):
      `Overlay` katmanında açılır, ekrana göre ortalanır, yüksekliği içeriğinden gelir,
      dışarı tıklayınca kapanır. `Mixer.qml` kanal ekleme/silme ve `MasterStrip` çıkış
      ekleme (Faz 27'de kalkıyor) bunu kullansın. `parent: root.parent` kalıbı silinsin —
      `Row` içinde `anchors` uyarısının kaynağı bu.
- [ ] `ChannelFx.qml` `dynamics` satırı sabit 168 px yerine `implicitHeight`inden
      beslensin; panel sayısı **görünen** panellerden hesaplansın (mikrofonda da 4).
      Dar pencerede paneller alt satıra sarsın.
- [ ] Sürükleme vekili yeniden yazılsın: konum `Overlay` katmanında, global imleç
      konumundan; `DropArea` hedefi asıl kutucuktan gelmeye devam etsin. Vekil hiçbir
      koşulda görünmezse sürükleme yine çalışsın (sessiz bozulma olmasın).
- [ ] `MİKROFONU KULLANANLAR` gibi uzun başlıklar `elide` edilsin.

**Ölçüm:** ekrana bakmayı gerektiriyor → `.plan/32-verify.md`'de kullanıcı testine
bırakılır. Kod tarafında: GUI hiçbir QML uyarısı vermeden açılmalı (bugün
`Mixer.qml:14` uyarısı yağıyor).
