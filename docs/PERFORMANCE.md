# Ölçümler

Bu dosyadaki her sayı bu depodaki kodla, gerçek donanımda ölçüldü. Test makinesi:
CachyOS, PipeWire 1.6.8, WirePlumber 0.5.15, SteelSeries Arctis 7+.

Yüzdeler **tek çekirdeğin** yüzdesidir.

---

## Gecikme

Yöntem: fiziksel cihazın monitörü sürekli kaydedilirken aynı darbe dosyası bir kez doğrudan
cihaza, bir kez Sonar kanalına çalınır. İki darbe **aynı kayıt oturumunda** olduğu için
kaydın ne zaman başladığı sadeleşir; geriye `pw-cat` başlatma titremesi kalır, o da
tekrarla ortalanır.

| durum | eklenen gecikme |
|---|---|
| tüm filtreler kapalı | **1.1 ms** (ortanca, n=8, yayılım ±3.7) |
| limiter açık, ileri-bakış 20 ms | 16.1 ms (ortanca, n=7, ±2.4) |

Birinci satır ölçüm gürültüsünün içinde: **Sonar ölçülebilir bir gecikme eklemiyor.**
İkinci satır yöntemin gerçekten hassas olduğunu gösteriyor — bilerek 20 ms ileri-bakış
eklendiğinde ölçüm 15 ms sıçrıyor.

Sebebi mimarî: PipeWire birbirine bağlı node'ları **aynı çevrimde** işliyor, dolayısıyla
zincire node eklemek tampon eklemiyor. Gecikme yalnızca eklentinin kendi ileri-bakışından
gelir (limiter varsayılan 5 ms, DeepFilterNet ~20 ms).

> Plandaki hedef "ek gecikme < 15 ms" idi. Varsayılan ayarlarla **karşılanıyor**; limiter'ın
> ileri-bakışını 20 ms'ye çıkarmak hedefi aşar, ama bu kullanıcının bilinçli seçimi.

---

## CPU

### Temel

| durum | CPU |
|---|---|
| graf boşta (ses yok, metre yok) | %5–7 |
| iki uygulama çalıyor | %7–8 |
| + tüm filtreler açık (EQ, gate, comp, limiter) | %9–10 |
| + seviye metreleri açık (mikser penceresi) | %12–13 |

Boştaki maliyetin çoğu LSP eklentilerinin sürekli çalışmasından. Bir kereye mahsus büyük
kazanç Faz 2'de elde edildi: LSP ekolayzerinin FFT analizörleri kapatılınca boştaki CPU
**%21.1 → %6.6** düştü (analizörler bypass'ta bile çalışıyorlardı).

### DeepFilterNet — dikkat

AI gürültü engelleme bir sinir ağı ve pahalı:

| durum | graf CPU |
|---|---|
| mikrofon kimse tarafından kullanılmıyor, DFN kapalı | %7.25 |
| mikrofon kimse tarafından kullanılmıyor, **DFN açık** | %7.37 |
| mikrofon kullanılıyor (Discord vb.), DFN kapalı | %10.0 |
| mikrofon kullanılıyor, **DFN açık** | **%53** |

İki sonuç:

1. **Kimse mikrofonu dinlemiyorken DFN bedava** — zincir askıya alınıyor.
2. Mikrofon kullanımdayken DFN **yaklaşık yarım çekirdek** harcıyor. Oyun oynarken Discord
   açıksa bunu hesaba katın; gerekmiyorsa Noise Gate çok daha ucuz.

### Seviye ölçümü

8 ölçüm noktası (`pw-cat --record`, 8 kHz mono) net **%3–5** ekliyor: daemon tarafı ~%2,
`pw-cat` süreçleri ~%0.4–0.9, kalanı PipeWire'ın yeniden örnekleme işi.

Plandaki hedef %2'ydi, tutturulamadı. Yalnızca mikser penceresi açıkken oluşuyor; abone
yokken **sıfır** süreç çalışıyor (doğrulandı). Tek bir native yardımcı süreçle çözülebilir,
`.plan/99-backlog.md`'de kayıtlı.

`pw-cat --latency 500ms` bedava üç kat kazanç sağladı: CPU %1.00 → %0.33, teslimat aralığı
(53 ms) ve tepki gecikmesi (53 ms) hiç değişmedi.

---

## Bellek

| bileşen | PSS |
|---|---|
| graf süreci (`pipewire -c`) | ~136 MB |
| daemon (Python) | ~40 MB |
| seviye ölçümü (8 × `pw-cat`) | ~27 MB |
| **toplam (mikser açık)** | **~180–200 MB** |

Plandaki "~15 MB" tahmini yanlıştı: LSP eklentileri örnek başına birkaç MB önceden ayırıyor.
Yine de kanal başına ayrı süreç seçeneğinin (~18 süreç) çok altında ve hedeflenen 250 MB'ın
içinde.

---

## Ses kalitesi

### Şeffaflık

Tüm filtreler kapalıyken zincir sinyali değiştirmiyor. Tekrarlanabilir ölçüm (1 kHz sinüs,
5 aşamalı zincir df → gate → eq → comp → lim, hepsi bypass):

```
giriş  -23.01 dBFS
çıkış  -23.01 dBFS
```

Her aşama tek tek açılıp kapatıldığında çıkış tam olarak bu değere geri dönüyor.

Geniş bantlı pembe gürültüyle null testi de denendi: bir pencerede **birebir sıfır artık**
(215 dB null) elde edildi, yani zincir o pencerede bit düzeyinde şeffaf. Ancak ölçüm
tekrarlanabilir değil — `pw-cat` kaydı zaman zaman aksıyor ve pencereler ~40 dB'de kalıyor.
**Sınır ölçüm altyapısında, zincirde değil**; sinüs ölçümleri kesin ve tekrarlanabilir.

### Ekolayzer doğruluğu

Arayüzde çizilen eğri **gerçek DSP yanıtı**. Üç bandlı bir eğri kurulup 8 frekansta ölçüldü:

| Hz | çizilen | ölçülen | fark |
|---|---|---|---|
| 63 | +1.57 | +1.55 | -0.01 |
| 125 | +7.90 | +7.90 | -0.00 |
| 250 | +1.15 | +1.15 | 0.00 |
| 500 | -1.69 | -1.69 | 0.00 |
| 1000 | -9.89 | -9.89 | -0.00 |
| 2000 | -1.83 | -1.83 | 0.00 |
| 4000 | +0.38 | +0.38 | 0.00 |
| 8000 | +4.92 | +4.92 | 0.00 |

Ortalama sapma **0.00 dB**, en büyük **0.01 dB**.

### Tık / kesinti

| işlem | sonuç |
|---|---|
| profil geçişi (3.4 s'de 12 geçiş) | 0 dropout, 0 tık |
| tek seferlik büyük fader sıçraması | temiz |
| mute aç/kapa | temiz |
| 60 Hz fader sürükleme | 4 denemenin 1'inde çok hafif süreksizlik |

Son satır: PipeWire seviye değişimini kendi yumuşatıyor, sorun yalnızca ardışık yazımların
birbirinin rampasını kesmesinden. Toplu yazım penceresi ölçümle 40 ms'ye ayarlandı
(0 ms'de 3/3, 20 ms'de 2/3, 40 ms'de 1/4 denemede artefakt).

---

## Yönlendirme

| ölçüm | sonuç |
|---|---|
| karar gecikmesi | 3.5 – 23 ms (yeni akış görüldüğünden taşıma bitene kadar) |
| duyulabilir kayıp | **21 ms** — tam bir PipeWire kuantumu (1024/48000) |
| dört uygulama aynı anda | dördü de doğru kanala düştü |

En fazla **tek bir tampon** varsayılan cihaza gidiyor. Planın önerdiği "önceden hedef
ayarlama" yoluna gerek kalmadı.

---

## Dayanıklılık

| senaryo | sonuç |
|---|---|
| graf sürecine `kill -9` | süpervizör yeniden başlattı, 32 node geri geldi |
| `pw-dump` izleyicisine `kill -9` | izleyici kendini toparladı, daemon etkilenmedi |
| `systemctl --user restart wireplumber` | 32 node ve 116 bağlantı korundu |
| bozuk `config.toml` | yedeklendi, varsayılana düşüldü, daemon ayakta |
| yazılamayan config dizini | ayarlar bellekte kaldı, daemon ayakta, kullanıcı uyarıldı |
| `SIGTERM` | graf düştü, kalan `sonar_*` node: 0 |

**Denenmeyenler:** uyku/uyanma döngüsü, 24 saat sürekli çalışma (bellek sızıntısı),
USB kulaklığı çıkarıp takma, `systemctl --user restart pipewire`. Bunlar oturumu kesintiye
uğrattığı için kullanıcının kendi kullanımında doğrulanmalı.

---

## Test turu 2 ölçümleri (2026-09-03)

Faz 18–23'te canlı graf üzerinde yapılan ölçümler. Hepsi ton enjeksiyonu + numpy
analiziyle; kulakla değil.

### Ses yolu

| ölçüm | sonuç |
|---|---|
| Cihaz değişimi yeniden inşa yapıyor mu | **hayır** — `sonar_media` node id'si 108 → 108 |
| Cihaz değişiminde kesinti | kayıt gürültüsünün içinde (kontrol 20/397 düşük pencere, anahtarlamayla 37/396) |
| Bağlantı bekçisi onarım süresi | elle koparılan gönderi **3 saniyede** geri kuruldu |
| Kanal çıkışını değiştirmek | node id sabit (304 → 304 → 304), conf değişmiyor |
| Sidetone açma/kapama | node id sabit; mute yazımı |

### Çoklu çıkış izolasyonu

Game hoparlörde, Media kulaklıkta; her kanala ayrı ton verildi.

| | kendi bus'ında | diğer bus'ta |
|---|---|---|
| Game → Hoparlör | **-37.0 dBFS** | -240.0 dBFS |
| Media → Kişisel | **-37.0 dBFS** | -240.0 dBFS |

-240 dBFS dijital sessizlik; sızıntı **yok**.

### Yeni efektler

| ölçüm | sonuç |
|---|---|
| Volume Boost +6 dB | çıkışta tam **+6.00 dB** |
| Boost + Spatial kapalıyken zincir | kazanç **0.00 dB**, sağ kanal -240 dBFS (bit-şeffaf) |
| Spatial 30° | kulaklar arası gecikme **0.38 ms**, seviye farkı **2.5 dB** |
| Spatial 60° | **0.65 ms**, **4.1 dB** — geniş açı, büyük fark |
| Spatial'ın kazanç kaybı | **-7.8 dB** (HRTF normalizasyonu) |
| Smart Volume indirimi | ayar -12.0 dB → ölçüm **-12.1 dB** |
| Smart Volume zarfı | atak ~200 ms, bırakma ~600 ms (ayar 100/600 ms + 50 ms ölçüm çözünürlüğü) |

### Spatial Audio'nun CPU maliyeti

Bu ölçüm tasarımı değiştirdi: aşama **yapısal** oldu.

| durum | tek çekirdeğin yüzdesi |
|---|---|
| Spatial zincirde yok, boşta | **%0.0** |
| Spatial zincirde ama bypass'ta, boşta | **%14.4** |
| Spatial açık, tek kanalda ses akarken | **%17** |
| Spatial kapalı, aynı kanalda ses akarken | **%0** |

**Bir HRTF konvolverini bypass etmek onu ucuzlatmıyor.** Bu yüzden Spatial kapalıyken
node'lar grafta hiç bulunmuyor ve açıp kapatmak — projedeki tek istisna olarak — grafı
yeniden kuruyor.

### Kabul senaryosu

Media'nın yayın fader'ı kapalıyken müzik çalıyor:

| | |
|---|---|
| kulaklıkta | **-23.0 dBFS** |
| yayında | **-240.0 dBFS** |

---

## Test turu 3 ölçümleri (2026-09-04)

Faz 25–32. Hepsi canlı graf üzerinde, ton enjeksiyonu + numpy analiziyle.

> **Ölçüm yöntemi hakkında bir uyarı.** Bu turda CPU ölçümlerinin bir kısmı
> `pgrep -f "pipewire -c <conf>"` ile PID buluyordu ve bu `timeout` sarmalayıcısını
> yakalıyordu — her şey %0.0 okunuyordu. Aşağıdaki sayılar `pipewire` sürecinin kendi
> PID'iyle yeniden ölçüldü.

### Master ve fader

| ölçüm | sonuç |
|---|---|
| Master yayın fader'ı %50, OBS "Ses Çıkışı Yakalama" (monitör) | -23.0 → **-29.1 dBFS** |
| Aynı ayarla OBS "Ses Girişi Yakalama" (sanal kaynak) | -23.0 → **-29.1 dBFS** |
| Fader %200 | `channelVolumes = 2.0` = **+6.02 dB** |
| Fader %300 | `channelVolumes = 3.0` = **+9.54 dB** |

Düzeltmeden önce monitör master fader'ını hiç duymuyordu (`monitor.channel-volumes`
varsayılan `false`); OBS'e iki kaynak ekleyen kullanıcı aynı miksi iki farklı seviyede
alıyordu.

### Spatial Audio: HRTF → crossfeed

| | HRTF (eski) | crossfeed (yeni) |
|---|---|---|
| Kapalıyken çıkış | grafta yok | **bit-eş** (R = -240 dBFS) |
| Boştaki CPU bedeli | **+%14.4** | +%0.4 |
| Ses akarkenki CPU bedeli | ~%17 (tek kanal) | **+%1.8** (altı zincir) |
| Açıp kapatmak | grafı yeniden kurar | **kesintisiz** |

Crossfeed'in ölçülen davranışı:

| ayar | karşı kulaktaki sızıntı | kulaklar arası gecikme |
|---|---|---|
| Performans ucu (0/0) | -18.4 dB | 0.29 ms |
| Varsayılan (50/40) | -9.0 dB | 0.60 ms |
| Sürükleyicilik ucu (100/100) | -5.1 dB | 1.15 ms |

### EQ kapasitesi

Band ekleme/silmenin canlı olabilmesi için zincir her zaman 32 bandlık eklentiyle
kuruluyor. Bedeli (altı zincir, ses akarken): x16 **%11.6** → x32 **%12.0**.

| ölçüm | sonuç |
|---|---|
| Band eklemek grafı kuruyor mu | `sonar_game` id 112 → 112 — **hayır** |
| Eklenen bandın yanıtı (3 kHz, -18 dB) | -26.03 → **-44.03 dBFS** (tam -18.00) |
| Band silince | **-26.03 dBFS** — birebir geri |

### Smart Volume (profilde)

| ölçüm | sonuç |
|---|---|
| İndirim | ayar -12.0 dB → ölçüm **-12.3 dB** |
| Zarf | atak ~200 ms, bırakma ~600 ms (ayar 100/600 ms + 50 ms ölçüm çözünürlüğü) |

### Metreler ve giriş kanalları

| ölçüm | sonuç |
|---|---|
| Yeniden inşadan sonra metre sayacı | 31 → **166** (akmaya devam ediyor) |
| İkinci giriş kanalının mute'u | `sonar_test mute=True`, `sonar_mic mute=False` |
