# OBS ile kullanım

Sonar'ın yayıncılar için asıl faydası: **kulaklığından duyduğun ses ile yayına giden ses
ayrı.** Telifli müziği kendin duyarsın, yayında duyulmaz.

---

## Kurulum — üç adım

1. **OBS → Ayarlar → Ses → Global Ses Aygıtları → Masaüstü Sesi** → **`Sonar Stream Mix`**
2. Aynı ekranda **Mikrofon/AUX Sesi** → **`Devre dışı`**
3. Tamam.

Bitti. Tek kaynak; oyun, sohbet, müzik ve **mikrofonun** hepsi bu aygıttan geçiyor ve
hepsi Sonar'ın yayın fader'larından geçmiş hâlde.

Bu, Windows'ta SteelSeries GG'nin "Stream" aygıtını Masaüstü Sesi olarak seçmenin birebir
karşılığıdır.

> **Aygıtın gerçek adı ne?** Sonar'da mikserin **Master** şeridindeki dişliye bas: "Yayın
> Miksi (OBS)" bölümü, o anki yapılandırmandan üretilen **gerçek** adı gösterir ve
> yanındaki ⧉ düğmesi panoya kopyalar. Kanalları yeniden adlandırdıysan ad da değişir,
> bu yüzden buradaki `Sonar Stream Mix` yalnızca varsayılan addır.

### Aynı ekran, ne olduğunu söylüyor

Aynı bölüm graftan okuduğu için ne olduğunu da söyler:

* kim yayın miksini dinliyor (OBS oradaysa "OBS — Masaüstü Sesi" yazar),
* mikrofon yayın miksinde mi,
* bir şey ters gittiyse ne olduğu.

Terminalden aynı bilgi:

```bash
sonar-cli doctor
```

---

## Neden tek kaynak

Yayın miksine **iki** yoldan erişilebiliyor ve ikisi de aynı sesi veriyor:

| Yol | OBS'te | Node |
|---|---|---|
| Sink'in monitörü — **resmî yol** | Ayarlar → Ses → Masaüstü Sesi | `sonar_stream` |
| Sanal kaynak — alternatif | Kaynaklar → Ses Girişi Yakalama | `sonar_stream_out` |

**İkisini birden eklersen her şey iki kez duyulur.** Belirtisi: müzik iki kaynakta da
görünür, seviyeler tuhaf davranır. Bu yüzden ikinci aygıtın adında "(alternatif giriş)"
yazıyor ve Sonar bu durumu tespit edip uyarıyor.

Alternatif yol yalnızca Masaüstü Sesi'ni başka bir şeye ayırdıysan gerekli.

---

## Mikrofon

Varsayılan olarak mikrofon **yayın miksinin içinde** — yani yukarıdaki tek kaynak sesini
de taşıyor ve OBS'te ayrıca mikrofon kaynağı açman gerekmiyor.

Mikrofonu ayrı bir track'te istiyorsan (kayıttan sonra ayrı düzenlemek için):

1. Sonar → Master şeridi → dişli → "Yayın Miksi (OBS)" → mikrofonun yanındaki ◎ düğmesini
   **kapat**. Terminalden: `sonar-cli mic mic stream off`
2. OBS → Kaynaklar → `+` → **Ses Girişi Yakalama** → mikrofon zincirinin sanal aygıtı
   (varsayılan kurulumda `Sonar Mic — Virtual Input`).

> Bu iki adım **birlikte** yapılmalı. Gönderiyi açık bırakıp OBS'e ayrı kaynak da
> eklersen sesin iki kez gider; gönderiyi kapatıp ayrı kaynak eklemezsen yayında hiç
> duyulmazsın. Sonar her iki durumu da tespit edip söyler.

**Mikrofon şeridindeki iki fader ne yapıyor:**

| Fader | Ne |
|---|---|
| 🎧 **Kendini duy** | Sidetone — kendi sesini kulaklığından duyma. Yayına gitmez. |
| ● **Mikrofon** | Mikrofonun kendi seviyesi. Hem Discord'a hem yayına giden ses. |

Yayın gönderisi kapalıyken şeritte "yayında değil" yazar.

---

## Müziği yayından çıkarmak

Sonar'da Media kanalının 📡 (yayın) fader'ını kapat. Kulaklığında duymaya devam edersin,
yayında duyulmaz.

```bash
sonar-cli volume media stream 0
```

---

## Senkron

Sonar ölçülebilir bir gecikme eklemiyor (bkz. `docs/PERFORMANCE.md`: filtreler kapalıyken
1.1 ms, ölçüm gürültüsünün içinde). OBS'te ses gecikmesi (sync offset) ayarlaman gerekmez.

İstisna: limiter'ın **ileri-bakış** değerini büyütürsen o kadar gecikme eklenir (20 ms
ileri-bakış = ~16 ms ölçüldü). Yayında limiter kullanıyorsan ileri-bakışı düşük tut.

---

## Sık karşılaşılan sorunlar

**Yayında hiç ses yok.**
OBS'in Masaüstü Sesi aygıtı yanlış olabilir. `sonar-cli doctor` "Yayın miksi" satırında
kimin dinlediğini yazar; boşsa OBS başka bir aygıtı dinliyordur.

**Her şey iki kez duyuluyor.**
Hem Masaüstü Sesi hem "Ses Girişi Yakalama" ile yayın miksini alıyorsun. Birini kaldır.

**Yayında sesim duyulmuyor.**
Mikrofonun yayın gönderisi kapalı ve OBS'te ayrı bir mikrofon kaynağı da yok. Yukarıdaki
"Mikrofon" bölümüne bak.

**Kaynak listesinde Sonar aygıtları yok.**
Daemon çalışmıyordur: `systemctl --user status sonar-daemon`, sonra `sonar-cli status`.

**Stream Mix sessiz.**
Kanalların yayın fader'ları kapalı olabilir: `sonar-cli status` → 📡 sütunu.

**EasyEffects açıkken ses beklenmedik yoldan gidiyor.**
İkisi birlikte çalışmaz; bkz. `docs/TROUBLESHOOTING.md`.

---

## İleri seviye: kanal başına ayrı track

Her kanalı ayrı track'e almak, kayıttan sonra "oyun sesi çok yüksek olmuş" gibi sorunları
düzeltmeni sağlar. **Bunu kurmadan önce yukarıdaki tek kaynaklı kurulumun çalıştığından
emin ol.**

0. Kanal kaynaklarını aç — graf yeniden kurulur, ~200 ms sessizlik:
   ```bash
   sonar-cli obs game on && sonar-cli obs chat on
   ```
   Bedeli: o kanal sistemin **mikrofon listesinde** de görünür. Bu yüzden varsayılan kapalı.
1. Kaynakları ekle: **Sonar Game — Stream Source**, **Sonar Chat — Stream Source**
2. **Ayarlar → Çıktı → Kayıt** → biçim `mkv`, **Ses Parçaları**: 1–4 işaretle
3. Miksleyicide her kaynağın `⋮` menüsü → **Gelişmiş Ses Özellikleri**
4. Her kaynağı yalnızca kendi track'ine ata (Stream Mix → 1, Game → 2, Chat → 3, …)
5. Kaydı başlat.

Bu kaynaklar **fader'lardan bağımsızdır**: Stream Mix'te tamamen kısılmış bir kanalı yine
de ayrı track'e alabilirsin. Kapatmak için `sonar-cli obs game off`.

Doğrulamak için:

```bash
ffprobe -hide_banner kayit.mkv 2>&1 | grep Audio
```

> **Not:** Yayın (streaming) tek bir ses track'i gönderir — çok track yalnızca **kayıt**
> içindir. OBS'te "Ses Parçaları" ayarı Yayın ve Kayıt için ayrıdır.
