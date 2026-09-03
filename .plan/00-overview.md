# Sonar for Linux — Genel Plan ve Durum

> **Bu dosya projenin canlı durum panosudur.** Herhangi bir anda buraya bakıp nerede kalındığı görülebilir.
> Her faz kendi dosyasında (`NN-*.md`) ayrıntılı görev listesi tutar.

---

## Şu an neredeyiz

**Aktif faz:** — (test turu 3 bekleniyor)
**Son güncelleme:** 2026-09-03
**Sonraki adım:** Kullanıcı üçüncü test turunu yapacak. Ekrana bakmayı gerektiren
maddeler `.plan/24-verify.md` içinde işaretsiz duruyor. Faz 23 (ChatMix tekeri) tek
seferlik bir `sudo` bekliyor. Sonra Faz 11 — Paketleme.

> **Test turu 2 (2026-09-03).** Kullanıcı ikinci turu yaptı. Çıkan tablo: ses yolu
> aralıklı kopuyor, arayüz daemon'ı hiç yansıtmıyor ve dört yeni yetenek isteniyor.
> Kök nedenler yine ölçülerek bulundu:
> `Mixer.qml` şeride donmuş bir sözlük kopyası veriyordu (arayüzün tamamı bu yüzden
> ölüydü); cihaz değişimi conf'u değiştirip grafı restart ediyordu; `_wire_sends`
> tek atışlıktı ve başarısız olunca kanal sessizce susuyordu.
> Kullanıcı kararları: **çoklu çıkış bus'ı** (her cihaz kendi master'ını alır),
> **Spatial Audio stereo binaural**, **donanım ChatMix tekeri için udev kuralı**.

| # | Faz | Durum |
|---|---|---|
| 0 | [İskelet ve repo](00-overview.md) | 🟢 Tamamlandı |
| 1 | [Veri modeli ve yapılandırma](01-model-config.md) | 🟢 Tamamlandı |
| 2 | [graph.conf üreteci](02-confgen.md) | 🟢 Tamamlandı |
| 3 | [Engine: süreç yönetimi ve canlı kontrol](03-engine.md) | 🟢 Tamamlandı |
| 4 | [Daemon ve D-Bus API](04-daemon-dbus.md) | 🟢 Tamamlandı |
| 5 | [Uygulama yönlendirme](05-routing.md) | 🟢 Tamamlandı |
| 6 | [Seviye ölçümü](06-meters.md) | 🟢 Tamamlandı |
| 7 | [GUI tasarım sistemi ve Mixer](07-gui-mixer.md) | 🟢 Tamamlandı |
| 8 | [Kanal FX sayfası](08-gui-fx.md) | 🟢 Tamamlandı |
| 9 | [Profiller, presetler, ChatMix](09-profiles-chatmix.md) | 🟢 Tamamlandı |
| 10 | [Uçtan uca doğrulama ve dokümantasyon](10-verify-docs.md) | 🟢 Tamamlandı |
| 12 | [Sanal cihaz düzeni](12-devices.md) | 🟢 Tamamlandı |
| 13 | [Kanal yönetimi: silme ve yön](13-channels.md) | 🟢 Tamamlandı |
| 14 | [Envanter doğruluğu](14-inventory.md) | 🟢 Tamamlandı |
| 15 | [Arayüz altyapısı](15-ui-foundation.md) | 🟢 Tamamlandı |
| 16 | [Profil deneyimi](16-profiles.md) | 🟢 Tamamlandı |
| 17 | [Doğrulama ve dokümantasyon](17-verify.md) | 🟢 Tamamlandı |
| 18 | [Ses yolunun güvenilirliği](18-audio-path.md) | 🟢 Tamamlandı |
| 19 | [Arayüzün canlılığı ve yerleşimi](19-ui-live.md) | 🟢 Tamamlandı |
| 20 | [Çoklu çıkış bus'ı](20-outputs.md) | 🟢 Tamamlandı |
| 21 | [Mikrofon yönlendirme](21-mic-routing.md) | 🟢 Tamamlandı |
| 22 | [Spatial / Boost / Smart Volume](22-dsp.md) | 🟢 Tamamlandı |
| 23 | [ChatMix donanım tekeri](23-chatmix-hid.md) | 🟡 Kullanıcı bekleniyor (udev) |
| 24 | [Doğrulama ve dokümantasyon](24-verify.md) | 🟡 Ekran testleri kullanıcıda |
| 11 | [Paketleme](11-packaging.md) | ⚪ Bekliyor (test turu 3'ten sonra) |
| — | [v1 sonrası backlog](99-backlog.md) | 📋 Liste |

Durum işaretleri: ⚪ bekliyor · 🟡 devam ediyor · 🟢 tamamlandı · 🔴 engellendi

**Test durumu:** 805 test geçiyor, `ruff` temiz.
**Graf durumu:** daemon D-Bus'ta yayında (54 metot, 5 sinyal); `sonar-cli` ile GUI olmadan
tam kontrol çalışıyor. Profil geçişi anında ve kesintisiz; cihaz değişimi ve kanalın
çıkış cihazını değiştirmek de artık kesintisiz.

---

## Projenin amacı

Kullanıcı Windows'ta SteelSeries GG'nin **Sonar** modülünü kullanıyordu; Linux'a (CachyOS / KDE Wayland)
geçtikten sonra dengi bir araç bulamadı. EasyEffects sistem geneli tek bir efekt zinciri sunuyor,
qpwgraph elle yamalama yaptırıyor; ikisi de "kanal" kavramına ve yayın/kişisel miks ayrımına sahip değil.

Sonar for Linux, PipeWire üzerine kurulu native bir alternatif:

- Uygulama seslerini adlandırılmış kanallara ayırır (**Game / Chat / Media / Aux**)
- Her kanalın kendi EQ + dinamik filtre zinciri ve **birden fazla kaydedilebilir profili** vardır
- Kulaklığa giden **Personal Mix** ile OBS'e giden **Stream Mix**'i bağımsız fader'larla ayırır
- Hangi uygulamanın hangi kanalda olduğunu gösterir ve değiştirmeye izin verir
- GUI kapalıyken bile ses düzenini ayakta tutar

Tasarım referansı: `docs/reference/steelseries-gg/` (SteelSeries GG ekran görüntüleri).

---

## Onaylanmış kararlar

| Konu | Karar | Gerekçe |
|---|---|---|
| Teknoloji | Python 3 + PySide6 (Qt6/QML) | DSP PipeWire içinde çalışır; bizim tarafta realtime kod yok |
| DSP | PipeWire `filter-chain` + LSP/Calf LV2 eklentileri | EasyEffects ile **birebir aynı** eklentiler, aynı kalite |
| Mimari | Daemon (systemd user service) + D-Bus + GUI istemci | GUI kapalıyken ses düzeni ayakta kalır |
| Yayın düzeni | Birleşik `Sonar Stream Mix` **+** kanal başına ayrı OBS çıkışı | OBS'de hem tek track hem kanal başına ayrı track mümkün |
| v1 kapsamı | AI gürültü engelleme (DeepFilterNet) + ChatMix | Global kısayollar ve otomatik profil değişimi → v1.1+ |
| Lisans | GPL-3.0 | LV2 eklenti ekosistemiyle uyumlu |

---

## Mimari özeti

### Üç süreç

```
┌─────────────────────────┐   D-Bus (session)          ┌──────────────────────┐
│  sonar-daemon           │◄──io.github.iwhimss.Sonar──│  sonar (GUI)         │
│  QCoreApplication       │                            │  QGuiApplication+QML │
│  · durum modeli         │                            └──────────────────────┘
│  · config kalıcılığı    │◄──────── aynı API ─────────  sonar-cli
│  · graf reconcile       │
│  · uygulama yönlendirme │
│  · seviye ölçümü        │
└───────────┬─────────────┘
            │ spawn / pw-cli / wpctl / pactl
            ▼
┌──────────────────────────────────────────────────────┐
│  pipewire -c ~/.local/state/sonar/graph.conf         │
│  TEK süreç — tüm filter-chain ve loopback node'ları  │
└──────────────────────────────────────────────────────┘
```

**Neden tek `pipewire -c` süreci:** kanal başına ayrı süreç ~18 süreç ve ~150 MB RSS demekti.
Hepsi tek conf'ta toplanınca bellek ~15 MB'a düşer. Yapısal değişiklik (kanal ekle/sil) conf'un
yeniden üretilip sürecin restart edilmesini gerektirir (~200 ms kesinti, nadir ve kullanıcı tetikli).
**Ses seviyesi, EQ, filtre parametresi, profil geçişi, cihaz değişimi, uygulama yönlendirme → canlı, kesintisiz.**

### Ses grafı

```
     UYGULAMALAR                                       ÇIKIŞLAR
  ┌───────────────┐
  │ oyun          ├──▶ [sonar_game]  ─DSP─▶ sonar_game_fx ──┐
  │ Discord       ├──▶ [sonar_chat]  ─DSP─▶ sonar_chat_fx ──┤   pw-link ile
  │ tarayıcı      ├──▶ [sonar_media] ─DSP─▶ sonar_media_fx ─┤   açıkça bağlanır
  │ diğer         ├──▶ [sonar_aux]   ─DSP─▶ sonar_aux_fx ───┤   (sürekli bekçi)
  └───────────────┘                                          │
       her kanaldan HER bus'a bir gönderi loopback'i         │
                     ┌────────────────────────────────────────┘
                     ├──▶ [sonar_personal]  ─master DSP─▶ ► Arctis 7
                     ├──▶ [sonar_<çıkış-2>] ─master DSP─▶ ► başka bir cihaz
                     └──▶ [sonar_stream]    ─master DSP─▶ ► sonar_stream_out → OBS

     GİRİŞ KANALLARI                        (uygulamalar buraya da yönlendirilir)
  Fifine ──┬──▶ [mic zinciri]        ─▶ sonar_mic         (→ Discord)
           └──▶ [stream mic zinciri] ─▶ sonar_stream_mic  (→ OBS)
                     └── sidetone ──▶ sonar_personal   (mute ile aç/kapa)
                     └── yayına ────▶ sonar_stream     (mute ile aç/kapa)
```

Kanal **tek bir** çıkışa gider; diğer çıkışlara giden gönderileri susturulur. Bu yüzden
kanalı başka bir cihaza taşımak bir mute yazımı, yeniden inşa değil.

**OBS erişim noktaları** (Faz 12'de sadeleşti):

1. `Sonar Stream Mix — Virtual Input` — stream fader'larıyla mikslenmiş birleşik ses.
   Varsayılan ve çoğu kurulum için tek gereken.
2. `Sonar Stream Mic — Virtual Input` — mikrofonun yayına özel zinciri.
3. `sonar_<kanal>_fx` — **yalnızca `stream_source` açıksa.** Kanal başına ayrı track.

`_fx` node'u varsayılan olarak `media.class` taşımaz: zincirin çıkışıdır ama bir *cihaz*
değildir, hiçbir listede görünmez. Açıkken `Audio/Source` olur. Sınıfsız bir node'u
WirePlumber bağlamadığı için gönderiler `pw-link` ile daemon tarafından kuruluyor.

### DSP zinciri (sabit topoloji, bypass ile açma/kapama)

```
kanal:  giriş ─▶ gate ─▶ eq ─▶ comp ─▶ [spatial] ─▶ boost ─▶ limiter ─▶ çıkış
mic:    giriş ─▶ deepfilter ─▶ gate ─▶ eq ─▶ comp ─▶ boost ─▶ limiter ─▶ çıkış
```

Köşeli parantez = **yapısal** aşama: kapalıyken grafta hiç yok. Spatial bunun tek
örneği; bir HRTF konvolverini bypass etmek onu ucuzlatmadığı için (ölçüldü: boştaki CPU
%0.0 → %14.4).

| Aşama | Eklenti | Bypass |
|---|---|---|
| DeepFilterNet | LADSPA `libdeep_filter_ladspa.so` (`deep_filter_mono`/`deep_filter_stereo`) | attenuation = 0 |
| Gate | `http://lsp-plug.in/plugins/lv2/gate_stereo` | `enabled` = 0 |
| EQ | `http://lsp-plug.in/plugins/lv2/para_equalizer_x16_stereo` | `enabled` = 0 |
| Compressor | `http://lsp-plug.in/plugins/lv2/compressor_stereo` | `enabled` = 0 |
| Spatial | PipeWire `sofa` `spatializer` + `mixer` | *(yapısal)* |
| Volume Boost | PipeWire `builtin` `linear` | `Mult` = 1.0 |
| Limiter | `http://lsp-plug.in/plugins/lv2/limiter_stereo` | `enabled` = 0 |

Topoloji **hiç değişmez** → efekt açıp kapatmak sadece bir parametre yazımı, ses kesintisi yok.

### Faz 1'de doğrulanan DSP ayrıntıları

* LSP'nin **tüm kazanç portları lineerdir** (`g_N` aralığı 0.01585–63.096 = ±36 dB), dB değil.
  Dönüşüm `core/dsp/params.py` içinde tek noktada yapılır.
* Bir EQ bandını kapatmanın yolu `ft_N = 0` (Off). `xs_N` = solo, `xm_N` = mute.
* `fm_N = 6` (**APO DR**) filtre modeli seçildi: RBJ cookbook biquad'ıyla birebir örtüşür,
  böylece arayüzde çizilen eğri kulağın duyduğuyla aynı olur.
* Band varsayılan frekansları ISO R10 (1/3 oktav) serisidir.
* DeepFilterNet'in `enabled` portu yoktur; bypass = azaltma sınırı 0 dB.

### Faz 2'de ölçümle doğrulananlar

Hepsi 1 kHz sinüs basılıp çıkış kaydedilerek, numpy ile ölçüldü — kulakla değil.

* **Canlı parametre yazımı çalışıyor.** `eq:g_3 = 8.0` → tam +18.06 dB (teorik 20·log₁₀8).
  Tek çağrıda çoklu anahtar yazımı da çalışıyor (Faz 3'ün toplu yazım tasarımı geçerli).
* **Klik/kesinti yok.** 3 saniyede 100 ardışık yazım: 0 dropout, ölçülen maksimum örnek
  adımı teorik maksimumun 1.00 katı.
* **Bypass bit-şeffaf.** Beş aşamanın tamamı kapalıyken çıkış girişe birebir eşit.
* `Audio/Source/Virtual` filter-chain içinde **çalışmıyor** (PipeWire 1.6.8, `-28`).
  `Audio/Source` + `priority.session = 0` kullanılıyor.
* LSP limiter'ın `boost` ve `alr` portları varsayılan **açık** ve `th`'yi tavan olmaktan
  çıkarıyor; ikisi de 0'a sabitleniyor.
* LSP EQ'nun FFT analizörleri bypass'ta bile çalışıyor — kapatınca grafın boştaki CPU'su
  **%21.1 → %6.6** düştü.
* `wpctl set-volume` **kübik** ölçekli; fader için `Props.channelVolumes` (lineer) kullanılacak.

### Faz 3'te ölçümle doğrulananlar

* **Süreç açmak pahalı, yazmak bedava.** `pw-cli` süreci açmak 14.03 ms; aynı süreçte 64
  portu tek çağrıda yazmak 12.97 ms; **kalıcı oturuma stdin'den yazmak 0.003 ms.**
  Bu yüzden kalıcı bir `pw-cli` oturumu tutuluyor ve profil geçişi (~130 port) tek çağrı.
* **Toplu yazım penceresi 40 ms** (plandaki 20 ms değil). Ölçüm: 60 Hz fader sürüklemesinde
  0 ms → 3/3 denemede tık, 20 ms → 2/3, 30 ms → 2/4, **40 ms → 1/4**.
* PipeWire seviye değişimini kendi yumuşatıyor: tek seferlik büyük sıçrama ve mute **hiç**
  tık üretmiyor. Kalan artefakt yalnızca ardışık yazımların rampayı kesmesinden.
* DSP portları filter-chain'in **capture** node'unda (`sonar_mic_capture` 315 port,
  `sonar_mic` 0). `confgen.dsp_nodes()` bu eşlemenin tek kaynağı.

### Faz 4'te ölçümle doğrulananlar

* **`QDBusContext.sendErrorReply()` PySide6 6.11.2'de segfault ediyor** (çıkış 139).
  Native D-Bus hatası kullanılamıyor; her metot JSON zarfı döndürüyor.
* **PySide6 Qt sinyallerini D-Bus'a relay etmiyor.** Introspection sinyalleri gösterse bile
  otobüse mesaj çıkmıyor; `QDBusMessage.createSignal()` ile elle gönderiliyor.
* **EasyEffects servis kipi cihaz seçimini eziyor.** `target.object` doğru yazılsa da akış
  `easyeffects_sink`'e çekiliyor ve elle taşıma geri alınıyor. Daemon bunu açılışta tespit
  edip uyarıyor; `docs/TROUBLESHOOTING.md` çözümü anlatıyor.

### Faz 5'te ölçümle doğrulananlar

* **Yönlendirme gecikmesi 3.5–4.8 ms.** Planın endişelendiği 10–20 ms'lik yarış penceresinin
  çok altında ve bir PipeWire kuantumundan (≈21 ms) kısa. `pw-metadata` ile **önceden**
  hedef ayarlama yoluna gerek kalmadı.
* **`pactl move-sink-input` node id ile çalışmıyor** — PulseAudio indeksi bekliyor ve
  sessizce `exit 1` veriyor. Akış taşıma `pw-metadata <node-id> target.object <ad>` ile.
* **`pw-metadata` değeri tırnaksız olmalı;** JSON tırnağı eklenirse akış sessizce
  varsayılan cihaza gider.
* **PipeWire node id'leri geri dönüştürüyor.** Yönlendirme kayıtları `object.serial` ile
  tutuluyor; id ile tutulurken beş akıştan ikisi yönlendirilmiyordu.
* **`QTimer.singleShot(0, …)` yabancı iş parçacığından sessizce çalışmıyor.** İş parçacığı
  geçişi Qt sinyaliyle yapılıyor.
* **Duyulabilir kayıp 21 ms** (EasyEffects kapalıyken ölçüldü) — tam bir PipeWire kuantumu.
* **Kanal izolasyonu ve kişisel/yayın ayrımı doğrulandı.** Bir uygulama çalarken diğer
  kanallar dijital sessizlikte (-240 dBFS); bir kanalın yayın faderini kapatmak kulaklık
  miksini etkilemiyor.

### Faz 6'da ölçümle doğrulananlar

* **LSP'nin kendi metre portları kullanılamıyor.** `iml`/`sml` gibi çıkış kontrol portları
  var ama PipeWire filter-chain yalnızca **giriş** portlarını `Props`'ta açığa çıkarıyor.
* **`pw-cat --latency 500ms` bedava üç kat kazanç:** CPU %1.00 → %0.33, teslimat aralığı
  (53 ms) ve tepki gecikmesi (53 ms) hiç değişmiyor.
* **Ölçüm maliyeti %3–5** (hedef %2'ydi, tutturulamadı). Yalnızca mikser açıkken oluşuyor;
  abone yokken sıfır süreç. Çözüm yolu backlog'da.
* Peak-hold canlı doğrulandı: 1.5 s tutup 20 dB/s düşüyor.

### Faz 7'de yakalanan PySide6 tuzakları

Üçü de sessiz: hata vermiyor, arayüz boş kalıyor.

* **Python öznitelikleri QML'e görünmüyor** — modeller `Property` olarak açılmalı.
* **Fonksiyon çağrıları binding'i tazelemiyor** — QML yalnızca özellik okumalarını izliyor;
  köprüye `revision` sayacı eklendi.
* **D-Bus sinyal yuvaları `"1"` öneki istiyor** (`"1onGraphRebuilt()"`); öneksiz form
  sessizce bağlanmıyor.

### Faz 8'de ölçümle doğrulananlar

* **Çizilen EQ eğrisi gerçek DSP yanıtıyla örtüşüyor.** 8 frekansta ortalama sapma
  **0.00 dB**, en büyük **0.01 dB**. Faz 1'deki `fm_N = 6` (APO DR) seçimi tam bunun içindi.
* Arayüzden verilen ±9 dB, ölçümde ±9.00 / -8.97 dB olarak çıktı.

### Faz 9'da ölçümle doğrulananlar

* **Profil geçişi anında ve kesintisiz.** CS2 (+9.00 dB) ↔ Arc Raiders (-9.00 dB), D-Bus
  çağrısı ~10 ms. 3.4 saniyede 12 geçiş: **0 dropout, 0 tık**.
* **ChatMix yayın miksini hiç bozmuyor.** Kulaklıkta doğru kanal ~40 dB kısılırken yayında
  her iki kanal da sabit -21.9 dB kalıyor.
* **Donanım ChatMix tekeri okunamıyor:** Arctis 7+ tek USB cihaz olarak görünüyor (planın
  öngördüğü iki cihaz değil) ve teker HID'de, `/dev/hidraw*` root'a kapalı. Tespit ve udev
  kuralı hazır; protokol çözümü backlog'da.

### Faz 10'da ölçümle doğrulananlar

* **Kabul senaryosu geçti.** Üç uygulama aynı anda; kulaklıkta üçü de (-22 dB), yayında
  "müzik" kanalı **-233 dB** (dijital sessizlik). Arayüz kapalıyken.
* **Eklenen gecikme 1.1 ms** (ortanca, n=8) — hedef <15 ms. Yöntem 20 ms ileri-bakışlı
  limiter ile doğrulandı (ölçüm 16.1 ms'ye çıktı).
* **DeepFilterNet pahalı:** mikrofon kullanımdayken +%43 CPU; kullanılmıyorken bedava.
* Dayanıklılık: `kill -9` (graf ve izleyici), wireplumber restart, bozuk config, yazılamayan
  dizin — hepsinde daemon ayakta kaldı.
* Tüm ölçümler `docs/PERFORMANCE.md`'de.

### Canlı parametre yazımı

Kalıcı `pw-cli` oturumuna gönderilen komutlar:

```
set-param <node-id> Props { params = [ "eq:g_3" 4.5 ] }        # EQ band 3 (lineer kazanç)
set-param <node-id> Props { channelVolumes = [ 0.5, 0.5 ] }    # fader — lineer, tam -6.02 dB
set-param <node-id> Props { mute = true }                      # sustur
pw-metadata <node-id> target.object <hedef-node>               # akışı taşı (kesintisiz)
```

---

## Doğrulanmış ortam

| Bileşen | Durum |
|---|---|
| PipeWire | 1.6.8 — `filter-chain`, `loopback`, `parametric-equalizer` mevcut |
| WirePlumber | 0.5.15 |
| LV2 | LSP 1.2.35, Calf 0.90.9, Zam 4.5, mda 1.2.12 |
| Gürültü engelleme | DeepFilterNet LADSPA (48 kHz zorunlu) |
| Python / numpy | 3.14.7 / 2.5.2 |
| PySide6 | 6.11.2 — QtQuick, QtQml, QtQuickControls2, QtDBus ✅ (QtCharts ❌) |
| Araçlar | `pw-cli`, `pw-dump`, `pw-cat`, `pw-link`, `pw-loopback`, `wpctl`, `pactl`, `pw-metadata` |
| Donanım | Çıkış: Arctis 7, Realtek, HDMI · Giriş: Fifine USB, Arctis 7 mic |
| Masaüstü | KDE Plasma / Wayland |

**Tek çalışma zamanı bağımlılığı: PySide6** (QtDBus hem daemon hem GUI tarafında kullanılır).

### Doğrulanmış LSP `para_equalizer` port sembolleri

Global: `enabled`, `g_in`, `g_out`, `mode`, `bal`
Band N: `ft_N` (filtre tipi), `f_N` (frekans), `g_N` (kazanç), `q_N` (Q), `s_N` (slope), `xs_N` (band aç/kapa)

---

## Riskler ve karşılıkları

| Risk | Karşılık |
|---|---|
| ~~`pw-cli set-param` LSP LV2 portlarında çalışmazsa~~ | ✅ **Kapandı.** Faz 2'de ölçülerek doğrulandı; yedek plana (builtin biquad) gerek kalmadı |
| Boştaki CPU tüketimi | LSP FFT analizörleri kapatıldı: %21.1 → %6.6. RSS ~136 MB (plandaki 15 MB tahmini yanlıştı) — kanal başına ayrı sürece göre yine çok düşük |
| Yapısal değişikte ~200 ms kesinti | Kullanıcı tetikli ve nadir. Akış taşıma `pw-metadata` ile kesintisiz |
| ~~Fader sürüklerken `pw-cli` süreç fırtınası~~ | ✅ **Kapandı.** Kalıcı `pw-cli` oturumu: yazım 14 ms yerine 0.003 ms. Pencere ölçümle 40 ms'ye ayarlandı |
| DeepFilterNet 48 kHz zorunlu | Graf tamamen 48 kHz'e sabit (`audio.rate = 48000`) |
| Varsayılan sink'i değiştirmenin yan etkileri | Varsayılan **kapalı**; daemon kapanırken eski değere döner |
| Wayland global kısayol kısıtları | v1 dışı; portal tabanlı çözüm v1.1'de |

---

## Faz 0 görev listesi — İskelet ve repo

- [x] `git init` (`main` dalı), git kimliği ayarlandı
- [x] `Steelseries GG/` → `docs/reference/steelseries-gg/` (açıklayıcı dosya adlarıyla)
- [x] `.plan/` faz dosyaları oluşturuldu
- [x] `.gitignore`
- [x] `LICENSE` (GPL-3.0)
- [x] `pyproject.toml` — hatchling, entry point'ler (`sonar`, `sonar-daemon`, `sonar-cli`), ruff + pytest ayarları
- [x] Kaynak ağacı iskeleti (`src/sonar/{core,engine,daemon,gui,cli,presets}`)
- [x] `README.md`
- [x] `ARCHITECTURE.md`
- [x] `CONTRIBUTING.md`
- [x] İlk commit + `iwhimss/sonar` `main` dalına push

---

## Çalışma düzeni

- Her faz sonunda: `ruff check src/ && pytest -q` yeşil olmalı
- Her faz sonunda: anlamlı bir commit + `iwhimss/sonar` `main` dalına push
- Her faz sonunda: bu dosyadaki durum tablosu ve ilgili faz dosyasının kutucukları güncellenir
