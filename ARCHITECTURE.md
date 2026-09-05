# Mimari

> Bu belge tasarım kararlarını ve gerekçelerini anlatır. Uygulama ilerledikçe güncellenir.
> Faz bazlı görev listeleri için [`.plan/`](.plan/) klasörüne bakın.

---

## Genel bakış

Sonar üç parçadan oluşur:

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

### Neden daemon + istemci?

Sanal ses cihazlarının ömrü, onları oluşturan sürecin ömrüne bağlıdır. Tek bir GUI uygulaması
olsaydı, pencereyi kapatmak tüm kanalları yok eder ve o an ses çalan uygulamaların sesini
keserdi. Daemon `systemd --user` altında çalışır; GUI yalnızca bir görüntüleyici/denetleyicidir.

Aynı D-Bus API'sini `sonar-cli` de kullanır — betiklerden ve klavye kısayollarından kontrol
mümkün olur.

### Neden ses işleme bizim sürecimizde değil?

Gerçek zamanlı ses işleme, GC duraklamalarına ve GIL'e toleranslı değildir. Python'da DSP
yazmak yerine, işi PipeWire'ın kendi `filter-chain` modülüne bırakıyoruz. Bu modül LV2 ve
LADSPA eklentilerini yükleyebiliyor — yani EasyEffects'in kullandığı **birebir aynı** LSP
Plugins eklentilerini kullanıp aynı kaliteyi elde ediyoruz.

Sonuç: bizim kodumuzda hiç realtime yol yok. Yaptığımız iş graf topolojisini tanımlamak ve
parametre yazmak.

### Neden tek `pipewire -c` süreci?

Alternatif, her kanal ve loopback için ayrı bir süreç açmaktı — yaklaşık 18 süreç ve ~150 MB
RSS. Hepsi tek bir conf dosyasında toplanınca bellek ~15 MB'a düşüyor.

Bedeli: **yapısal** bir değişiklik (kanal ekleme/silme) conf'un yeniden üretilip sürecin
yeniden başlatılmasını gerektirir — yaklaşık 200 ms kesinti. Bu nadir ve kullanıcı tetikli
bir işlem.

Buna karşılık şunların hepsi **canlı ve kesintisiz**dir:
ses seviyesi, mute, EQ, filtre parametreleri, profil geçişi, çıkış cihazı değişimi,
uygulama yönlendirme.

---

## Ses grafı

```
     UYGULAMALAR                                       ÇIKIŞLAR
  ┌───────────────┐
  │ oyun          ├──▶ [sonar_game]  ─DSP─▶ sonar_game_fx ──┐
  │ Discord       ├──▶ [sonar_chat]  ─DSP─▶ sonar_chat_fx ──┤   pw-link ile
  │ tarayıcı      ├──▶ [sonar_media] ─DSP─▶ sonar_media_fx ─┤   açıkça bağlanır
  │ diğer         ├──▶ [sonar_aux]   ─DSP─▶ sonar_aux_fx ───┤
  └───────────────┘                                          │
       her kanaldan HER bus'a bir gönderi loopback'i         │
                     ┌────────────────────────────────────────┘
                     │
                     ├──▶ [sonar_personal] ─master DSP─▶ sonar_personal_out ─▶ kulaklık
                     └──▶ [sonar_stream]   ─master DSP─▶ sonar_stream_out ───▶ OBS

     GİRİŞ KANALLARI
  fiziksel ─┬──▶ [mic zinciri]        ─▶ sonar_mic         (→ Discord vb.)
            └──▶ [stream mic zinciri] ─▶ sonar_stream_mic  (→ OBS)
                      └── sidetone ──▶ sonar_personal   (mute ile aç/kapa)
                      └── yayına ────▶ sonar_stream     (mute ile aç/kapa)
```

Conf her kanaldan **her** bus'a bir gönderi kurar; fader o gönderi node'una uygulanıyor.

Bir dönem birden fazla **çıkış** bus'ı olabiliyordu (kanal başına ayrı fiziksel cihaz,
Faz 20). Kullanıcı için karışıklık ürettiği ve SteelSeries'te de yalnızca yayın modu
kapalıyken bulunduğu için geri alındı (Faz 27). `MasterBus.kind` duruyor — yayın bus'ını
çıkıştan ayıran alan o — ama çıkış her zaman bir tane.

### Node isimleri

| Node | Sınıf | `node.description` | Amaç |
|---|---|---|---|
| `sonar_<kanal>` | `Audio/Sink` | `Sonar <Ad> — Virtual Output` | Uygulamalar buraya çalar |
| `sonar_<kanal>_fx` | *(yok)* | `Sonar <Ad> FX` | DSP çıkışı — **cihaz değil** |
| `sonar_<kanal>_fx` | `Audio/Source` | `Sonar <Ad> — Stream Source (Virtual Input)` | `stream_source` açıkken: OBS kanal track'i |
| `sonar_<kanal>_to_<bus>` | loopback | — | O bus'a giden fader; kanal başına her bus için bir tane |
| `sonar_personal` | `Audio/Sink` | `Sonar Personal Mix` | Varsayılan çıkış bus'ı |
| `sonar_<bus>_out` | *(akış)* | `Sonar <Ad> Output` | Çıkış bus'ının fiziksel cihaza giden akışı |
| `sonar_stream` | `Audio/Sink` | `Sonar Stream Mix` | Yayın miksi — **OBS'te Masaüstü Sesi olarak bu seçilir** |
| `sonar_stream_out` | `Audio/Source` | `Sonar Stream Mix (alternatif giriş)` | Aynı miksin ikinci yolu |
| `sonar_<giriş>` | `Audio/Source` | `Sonar <Ad> — Virtual Input` | İşlenmiş mikrofon |

Adlar İngilizce ve yönü söylüyor: bir cihaz listesinde "Sonar Media" görmek onun sink mi
source mu olduğunu anlatmıyordu.

**Bus'lar bu kuralın dışında.** Sink'in adı tam olarak `Sonar <Ad>`, çünkü OBS'in
Masaüstü Sesi listesinde görünen ad budur ve dokümanın söylediğiyle birebir aynı olmak
zorunda. Çıkış node'u aynı miksin ikinci kopyası; adı eskiden "— Virtual Input"tı ve
sink'in "— Virtual Output"una o kadar benziyordu ki kullanıcı ikisini birden ekleyip
aynı miksi iki kez aldı. `api.stream_setup()` bu durumu graftan okuyup uyarıyor.

### Kanal başına OBS kaynağı — varsayılan kapalı

`sonar_<kanal>_fx` node'u varsayılan olarak **`media.class` taşımaz**: zincirin çıkışıdır
ama bir *cihaz* değildir, hiçbir listede görünmez. Sebebi kullanıcı geri bildirimi: her
çıkış kanalı `Audio/Source` olduğunda sistemin **mikrofon listesinde** dört sahte giriş
beliriyordu ("Media kanalı neden mikrofon?").

`sonar-cli obs <kanal> on` (veya kanal ayarı) bunu açar; o kanal OBS'te ayrı bir track
olarak yakalanabilir hâle gelir. Faydası kayıt sonrası düzenlemede: oyun sesini kısıp
Discord'u bırakmak. EQ ile ilgisi yok — EQ zaten kanal başına.

### Master fader monitörü de kısıyor

Bus sink'lerinin `capture.props` bölümünde `monitor.channel-volumes = true` var.
Varsayılan `false` ve o hâlde sink'in **monitör portları master fader'dan önce**
dallanıyor. Bedeli ölçüldü: OBS "Ses Çıkışı Yakalama" ile yayın miksini dinlediğinde
master fader'ı hiç duymuyordu, "Ses Girişi Yakalama" duyuyordu — aynı miks iki farklı
seviyede. Master her şeyi kısmalı.

### Cihaz seçimi conf'a girmiyor

`sonar_<bus>_out` bir **akış** node'u; hedefi `pw-metadata <id> target.object <cihaz>` ile
canlı değiştirilebiliyor — akış taşımayla aynı mekanizma. Ölçüldü (Faz 18): bağlantı
`pw-link -lo` çıktısında anında taşındı ve kesinti kayıt gürültüsünün üstüne çıkmadı.

Eskiden cihaz adı conf'a `target.object` olarak yazılıyordu, yani her cihaz değişimi grafı
yeniden kurup çalan müziği kesiyordu. Aynı şey mikrofon kaynağı için de geçerli.

### Gönderiler neden `pw-link` ile bağlanıyor

`media.class` taşımayan bir node'u WirePlumber'ın yönlendirme politikası bir kaynak
saymaz; gönderi loopback'lerinin `capture.props` bölümündeki `target.object` işe yaramaz.
Bu yüzden loopback yakalama tarafı bilerek **bağlantısız** doğar
(`node.autoconnect = false`) ve `Supervisor.reconcile_links()` `pw-link` ile bağlar,
`pw-link -l` çıktısıyla doğrular.

Bu **sürekli bir uzlaştırıcı**, tek atışlık değil: yeniden inşadan sonra, grafta node
değiştiğinde (300 ms debounce) ve sağlık yoklamasında çalışır. Eskiden tek seferlikti ve
tutmazsa yalnızca bir log satırı bırakıyordu — kanal **tamamen ve sessizce** susuyordu.
Test turu 2'deki "hiç ses gelmiyor" şikâyetinin bir ayağı buydu. Ölçüldü: elle koparılan
bir gönderi 3 saniye içinde geri kuruluyor.

Üst üste üç tur onarılamazsa arayüze kırmızı bir uyarı düşer ve `sonar-cli doctor`
beklenen/gerçek farkı basar. Sessiz sessizlik kalmadı.

Port adları moda göre değiştiği için (`output_FL` / `capture_FL`) `pw-link`'e port değil
**node adı** verilir; portları o eşleştirir.

> **Neden `Audio/Source/Virtual` değil?** PipeWire 1.6.8'de `filter-chain`'in
> `playback.props` bölümünde bu sınıf verildiğinde node kurulamıyor (`can't add port: -28`)
> ve süreç sessizce boş bir grafla ayakta kalıyor. `Audio/Source` sorunsuz çalışıyor.

> **Neden hepsinde `priority.session = 0`?** Sanal düğümlerimiz asla varsayılan cihaz
> seçilmemeli. Kulaklık çıkarıldığında WirePlumber `sonar_personal`'ı varsayılan sink
> seçerse, personal bus kendi çıkışını kendine besler. Varsayılanı devralmak isteyen
> `settings.take_over_default_sink` bunu `pw-metadata` ile açıkça yapar.

### Kanal yönü ve akış yönü

| Yön | Model | Üretilen |
|---|---|---|
| Çıkış | `Channel` | sink + DSP + iki bus gönderisi |
| Giriş | `MicChain` | fiziksel kaynak → DSP → sanal kaynak |

Yön modelde ayrı bir alan değil; hangi listede durduğu zaten söylüyor. Her ikisi de
kullanıcı tarafından eklenip silinebilir. Kısıtlar: en az bir çıkış kanalı ve kendi DSP
zincirine sahip en az bir giriş kanalı kalmalı.

**Akışların** da yönü var ve `RoutingRule.direction` bunu taşıyor: `out` uygulamanın
çaldığı ses, `in` dinlediği mikrofon. Bir uygulamanın ikisi için ayrı kuralı olabilir —
Discord'un sesi `chat` kanalına, mikrofonu `mic` zincirine. Taşıma mekanizması ikisinde
de aynı (`pw-metadata target.object`), yalnızca hedef node farklı.

`stream.capture.sink` bayrağı taşıyan akışlar (cava, OBS'in "Masaüstü Sesi" kaynağı)
mikrofon kullanıcısı sayılmaz ve yönlendirilmez. Bu ayrım ölçümle bulundu: yakalama
akışları yönlendirilmeye başlayınca cava sessizce `sonar_mic`'e çekildi.

### OBS erişim noktaları

1. **`Sonar Stream Mix` (`sonar_stream_out`)** — stream fader'larıyla mikslenmiş birleşik
   ses. Varsayılan ve çoğu kurulum için tek gereken.
2. **`Sonar Stream Mic`** — mikrofonun yayına özel zinciri.
3. **`sonar_<kanal>_fx`** — yalnızca `stream_source` açıksa. Kanal başına ayrı track.

---

## DSP zinciri

Zincir **profilin efekt listesinden** kuruluyor (şema 7). Kullanıcı efekt ekliyor, siliyor
ve sürükleyerek sıralıyor; sinyal listedeki sırayla akıyor. Yeni bir profilde yalnızca
ekolayzer var.

```
Oyun / CS2 profili:   giriş ─▶ eq ─▶ gate ─▶ comp ─▶ çıkış
Oyun / Müzik profili: giriş ─▶ eq ─▶ bass ─▶ reverb ─▶ çıkış
```

**Ne kesinti yaratır:**

| İşlem | Etki |
|---|---|
| Efekti aç/kapa, parametre değiştir, profil değiştir (aynı efekt listesi) | canlı, kesintisiz |
| Efekt ekle / sil / sırala, efekt listesi **farklı** bir profile geç | conf değişir → ~200 ms |

Bu ayrım için yeni bir mekanizma yok: `supervisor.reconcile` "üretilen conf metni değişti
mi" diye bakıyor ve efekt listesi conf'un içinde. Aç/kapa bypass portuna yazıyor, o da
conf'u değiştirmiyor.

### Katalog (16 efekt)

| Efekt | Eklenti | Bypass |
|---|---|---|
| AI Gürültü Engelleme | LADSPA `libdeep_filter_ladspa.so` | attenuation = 0 |
| Gürültü Kapısı | `lsp gate_stereo` | `enabled` = 0 |
| Genişletici | `lsp expander_stereo` | `enabled` = 0 |
| Ekolayzer | `lsp para_equalizer_x32_stereo` | `enabled` = 0 |
| Kompresör | `lsp compressor_stereo` | `enabled` = 0 |
| De-esser | `calf Deesser` | `bypass` = 1 |
| Bas Zenginleştirici | `calf BassEnhancer` | `bypass` = 1 |
| Exciter | `calf Exciter` | `bypass` = 1 |
| Stereo Araçları | `calf StereoTools` | `bypass` = 1 |
| Gecikme | `lsp comp_delay_stereo` | `enabled` = 0 |
| Yankı | `calf Reverb` | `on` = 0 |
| Uzamsal Ses | PipeWire `builtin` `copy`+`delay`+`bq_lowpass`+`mixer` | sızıntı kazancı 0 |
| Gürlük Dengeleme | `lsp loud_comp_stereo` | `enabled` = 0 |
| Ses Yükseltme | PipeWire `builtin` `linear` | `Mult` = 1.0 |
| Maximizer | LADSPA `ZaMaximX2` | tavan 0 dB + kazanç 0 dB |
| Limitleyici | `lsp limiter_stereo` | `enabled` = 0 |

Bypass yolu üç desende ve yönü ters çevirmek "kullanıcı efekti hiç açmadan sesin
değişmesi" demek olurdu; `params._STAGE_BYPASS`, `_STAGE_ACTIVE` ve `_NO_ENABLED_PORT`
bunları ayırıyor. Her efektin conf'a bypass'ta doğduğu testle sabitleniyor.

Port sınırları eklentilerin **kendi tanımlarından** geliyor; `scripts/sonar-lv2-ports`
TTL'i (ve LADSPA descriptor'ını) okuyup katalog satırı basıyor. Katalog yine de
kürasyonlu: betiğin çıktısı elle gözden geçirilip yalnızca kullanılan portlar alınıyor.

**Kataloğa girmeyenler:** Convolver (IR dosyası bir *yol* parametresi ister, `params`
yalnızca sayı tutuyor), çok bandlı kompresör/gate (247 kontrol portu; anlamı band başına,
doğrusu ayrı bir arayüz), Auto Gain (yan zincirle çalışıyor ve kullanıcının fader'ıyla
çekişiyor), Filtre (32 bandlık eğri editörünün zayıf kopyası olurdu).

### Node adları

Node adı **slot kimliğidir** (`eq`, `gate`, `comp2`) ve profil içinde benzersizdir; aynı
efektten birden fazla eklenebiliyor. Canlı parametre anahtarı `"<slot>:<port>"` —
`"eq:g_3"`, `"comp2:al"`.

### Çok node'lu aşamalar

`spatializer` ve `linear` **mono** eklentiler; stereo bir zincire tek node olarak
girmiyorlar. Bu yüzden `core.dsp.chain` bir aşamayı `StageBlock` olarak modelliyor: bir
ya da birden çok node, kendi iç linkleri ve dışarıya kanal başına tek bir port çifti.
Tek node'lu aşamalar bunun özel hâli — link sırası korunduğu için mevcut zincirler byte
olarak değişmedi.

Spatial bloğu (stereo):

```
cp_l ─┬───────────────────────────────► mix_l:"In 1"   (doğrudan)
      └─► delay_l ─► lowpass_l ────────► mix_r:"In 2"   (karşı kulağa sızıntı)
cp_r ─┬───────────────────────────────► mix_r:"In 1"
      └─► delay_r ─► lowpass_r ────────► mix_l:"In 2"
```

Gerçek hoparlörlerde sol hoparlörün sesi sağ kulağa da ulaşır: biraz geç ve kafanın
gölgelediği tizler kısılmış hâlde. Kulaklıkta bu hiç olmaz, ses "kafanın içinde" kalır.
Blok tam bunu geri koyuyor. Bypass mikserin sızıntı kazancını 0 yapmak, yani
**bit-şeffaf** ve graf hiç değişmiyor.

### Spatial Audio neden HRTF değil

İlk sürüm PipeWire'ın `sofa` `spatializer`'ıyla iki sanal hoparlör kuruyordu. Ölçüm onu
çürüttü:

| | boştaki CPU |
|---|---|
| HRTF zincirde yok | %0.0 |
| HRTF zincirde, bypass'ta | **%14.4** |

Bir konvolveri bypass etmek onu ucuzlatmıyor. Bu yüzden aşamayı açıp kapatmak grafı
yeniden kurmayı gerektiriyordu — projenin "efekt açmak grafı değiştirmez" kuralını
bozan tek yerdi. Kullanıcı bunun yerine ucuz bir çözüm istedi; crossfeed'in bedeli altı
zincir için **%1.8** ve yeniden kurulum gerekmiyor.

Gerçek 7.1 sanal surround sekiz konvolver ve çok kanallı bir zincir isterdi;
`.plan/99-backlog.md`'de kayıtlı.

### Smart Volume neden DSP değil

Yan-zincirli bir kompresör, tetikleyici kanalın sesini hedef kanalın kompresörüne besleme
olarak vermeyi gerektirirdi; PipeWire `filter-chain` içinde kanallar arası besleme yok.

Buna karşılık seviye ölçümü zaten var (20 Hz) ve fader yazımı zaten ucuz (0.003 ms). Bu
yüzden ducking daemon tarafında bir zarf takipçisi (`engine/ducking.py`): tetikleyici
eşiği aşınca attack boyunca in, sustuğunda hold kadar bekle, release boyunca çık.
Bedeli çözünürlük — 50 ms'lik karar aralığı, konuşma için fazlasıyla yeterli.

ChatMix ile **çarpılarak** birleşiyor; ikisi de `live_volumes()` içinde tek noktada
toplandığı için çakışmıyorlar. Ölçüldü: ayarlanan -12.0 dB indirim çıkışta -12.1 dB.

Ayar **profilin içinde** (şema 4): tetikleyici, Smart Volume'u açık olan profili taşıyan
kanalın kendisi. Böylece "Chat'in oyun profilinde açık, müzik profilinde kapalı" mümkün.
Tetikleyici başına ayrı zarf tutuluyor; bir hedef birden fazla tetikleyicinin
kapsamındaysa **en derin** indirim uygulanıyor.

### EQ kapasitesi sabit

Zincir her zaman `para_equalizer_x32` kuruyor. Eskiden band sayısı kapasiteyi seçiyordu
(8/16/32) ve kapasite değişimi **yapısaldı**. Kullanıcı band eklemeyi/silmeyi eğriye sağ
tıkla yapmak isteyince bu kabul edilemez oldu: her nokta eklemede ses kesilirdi.

Bedeli ölçüldü (altı zincir, ses akarken): x16 **%11.6**, x32 **%12.0**. Kullanılmayan
bandlar `ft = 0` ile kapalı ve analizörler zaten kapalı olduğu için fark neredeyse yok.

### LSP `para_equalizer` port sembolleri

Global: `enabled`, `g_in`, `g_out`, `mode`, `bal`
Band N: `ft_N` (filtre tipi), `f_N` (frekans), `g_N` (kazanç), `q_N` (Q), `s_N` (slope),
`xs_N` (band aç/kapa)

### Grafın tamamı 48 kHz

DeepFilterNet yalnızca 48 kHz'de çalışıyor, bu yüzden `audio.rate = 48000` her yerde sabit.
Bu aynı zamanda zincir içinde örnekleme hızı dönüşümü olmamasını garanti eder.

---

## Canlı kontrol

```bash
# EQ band 3 kazancı → +4.5 dB
pw-cli s <node-id> Props '{ params = [ "eq:g_3" 4.5 ] }'

# Kanal fader'ı
pw-cli s <loopback-node-id> Props '{ channelVolumes = [ 0.72, 0.72 ] }'   # lineer

# Çıkış cihazını değiştir (kesintisiz)
pw-metadata <node-id> target.object <hedef-node-adı>   # akışı taşı (kesintisiz)
```

Daemon `pw-dump -m` ile grafı izler ve `node.name → id` haritasını günceller.

Fader sürüklerken saniyede 60 alt süreç açılmasını önlemek için `engine/control.py`
20 ms'lik pencerelerde yazımları biriktirip toplu gönderir. Son değerin her zaman
uygulanması garanti edilir.

---

## Kurulum durumu ve dil

İki karar bu iki başlıkta toplanıyor; ikisi de `config.toml`'un `[settings]` bloğunda.

### `provisioned` — sanal kanallar kuruldu mu

`false` iken daemon D-Bus'ta ayakta durur ama **PipeWire'a hiç dokunmaz**: graf kurulmaz,
varsayılan çıkış devralınmaz, kulaklık tekeri okunmaz. Graf izleyicisi yine de çalışır;
salt okunurdur ve cihaz listesi karşılama ekranında da lazımdır.

Kurulum `api.provision()` ile olur (arayüzdeki düğme veya `sonar-cli install`), kaldırma
`api.deprovision()` ile. Şema 5 → 6 göçü diskte `config.toml` bulunan kullanıcıları
"kurulu" sayar: onların grafı zaten ayaktadır ve bir güncelleme kanallarını söktürmemeli.

Daemon SIGTERM'de grafı zaten düşürüyor; `deprovision` ondan farklı olarak **kalıcı**dır —
`graph.conf` silinir ve daemon bir daha kurmaz.

### `language` — arayüz ve mesaj dili

Metinler `src/sonar/i18n/<kod>.json` altında düz anahtar–metin sözlükleri. Üç süreç de
(`daemon`, `sonar-cli`, GUI) `sonar.core.i18n` üzerinden aynı katalogu okur; böylece
daemon'ın ürettiği hata metniyle arayüzün gösterdiği metin aynı kaynaktan gelir.

Kim nereden okuyor:

| Süreç | Kaynak | Neden |
|---|---|---|
| daemon | `config.toml` | Hata mesajlarını o üretiyor |
| `sonar-cli` | `config.toml` (diskten, açılışta) | `--help` ve "daemon'a ulaşılamadı" bağlantı kurulmadan basılıyor |
| GUI | `ui.json`, sonra daemon'ın değeri | "Servis çalışmıyor" paneli ve karşılama ekranının ilk sayfası daemon olmadan çiziliyor |

Dil değişimi anında diske yazılır (gecikmeli kaydetme yetmiyordu: dil değiştirdikten
hemen sonra çalışan bir `sonar-cli` eski dili okuyordu).

**Adlar çevrilmez.** `channel.name` / `bus.name` aynı anda PipeWire cihaz açıklamasıdır
(`confgen` `node.description`'ı ondan üretir); dile göre değişseydi OBS'te seçili
`Sonar Stream Mix` her dil değişiminde kaybolurdu. Çeviri yalnızca **gösterilen** ada
uygulanır (`core/names.py`) ve kullanıcı adı değiştirmişse hiç uygulanmaz.

QML tarafında tazeleme iki katmanlı: `ui/I18n.qml` singleton'ı `t()` içinde kendi
`language` özelliğini okuyor, o okuma binding'e bağımlılık olarak yazılıyor. Python
tarafında bir öznitelik okumak QML'de hiçbir bağımlılık kurmaz — dil değişince metinler
eski kalırdı.

---

## Yapılandırma

```
~/.config/sonar/
├── config.toml                  # kanallar, fader'lar, kurallar, ayarlar (dil, kurulum)
├── ui.json                      # pencere durumu + dil (daemon'dan bağımsız kopya)
└── profiles/
    ├── game/
    │   ├── Default.json
    │   ├── CS2.json
    │   └── Arc Raiders.json
    ├── chat/
    └── mic/

~/.local/state/sonar/
└── graph.conf                   # üretilen PipeWire yapılandırması
```

Profiller ayrı dosyalarda tutulur; profil eklemek/silmek `config.toml`'u yeniden yazmaz.

Favoriler **profilde değil** `config.toml` içinde, hedef başına sıralı bir ad listesi
olarak durur:

```toml
[favorites]
game = ["CS2", "Arc Raiders"]
```

Sıra listenin kendisidir ve sayı sınırı yoktur. Şema 1'de bu bilgi profil dosyalarındaki
`favorite_slot` alanındaydı (9 slot); şema 2'ye geçerken `ConfigStore._migrate_favorites()`
profil dosyalarını tarayıp eski slot numaralarına göre sıralar. Bir kez çalışır.

`config.toml` elle düzenlenebilir — `Reload()` D-Bus metodu diskten yeniden okur.
Bozuk bir config yedeklenir (`config.toml.corrupt-<zaman>`) ve varsayılana düşülür.

---


## D-Bus API

Servis `io.github.iwhimss.Sonar`, yol `/io/github/iwhimss/Sonar`, arayüz aynı ad.

**Her metot tek bir `s` döndürür — JSON zarfı:**

```json
{"ok": true}                 {"ok": true, "result": ...}
{"ok": false, "code": "unknown_channel", "message": "..."}
```

Native D-Bus hatası kullanılmıyor: `QDBusContext.sendErrorReply()` PySide6 6.11.2'de
segfault ediyor (ölçüldü, çıkış kodu 139), yani her geçersiz argüman daemon'ı düşürürdü.

Argümanlar yalnızca basit tiplerde (`s`, `b`, `d`, `i`); karmaşık yapılar JSON string
olarak taşınır. **Yapısal** işaretli metotlar `graph.conf`'u değiştirip grafı yeniden kurar
(~200 ms sessizlik); diğerleri canlı ve kesintisizdir.

### Metotlar (62)

| Metot | Argümanlar | Açıklama |
|---|---|---|
| `AddChannel` | `s name, s direction, s color` | Yeni kanal ekler ve id'sini döndürür. **Yapısal**. |
| `AddEqBand` | `s target, d freq, d gain_db` | Verilen frekansa yeni bir EQ bandı ekler. Sonuç: bandın indeksi. **Canlı**. |
| `CopyProfile` | `s target, s name` | Aktif profili yeni bir adla çoğaltır ve ona geçer. |
| `DeleteProfile` | `s target, s name` | Kullanıcı profilini siler; gömülü presetler silinemez. |
| `Deprovision` | `b purge_settings` | Sanal kanalları söker, varsayılan cihazı geri verir. `purge_settings` → yapılandırma dizini de silinir. **Yapısal**. |
| `AddEffect` | `s target, s kind, i index` | Zincire efekt ekler; sonuç slot kimliği. **Yapısal**. |
| `Diagnose` | `—` | Ses yolu teşhisi: eksik bağlantılar, doğmayan node'lar, çakışmalar. |
| `ExportProfile` | `s target, s name, b autoeq` | Profili metin olarak verir; `autoeq` ise AutoEQ/APO biçiminde. |
| `GetDevices` | `—` | Fiziksel ses cihazları (Sonar'ın kendi sanal node'ları hariç). |
| `GetLevels` | `—` | Anlık seviyeler. Sürekli akış için `LevelsUpdated` sinyalini dinleyin. |
| `GetState` | `—` | Tüm durum: yapılandırma, profiller, akışlar, cihazlar, çakışmalar. |
| `ImportProfile` | `s target, s text, s name` | Dış EQ dosyasını içe aktarır. Biçim içerikten bulunur. |
| `ListEffectKinds` | `s target` | Bu hedefe eklenebilecek efektler ve parametre meta verisi. |
| `ListEffects` | `s target` | Hedefin zinciri, sinyal sırasıyla. |
| `ListBuiltinProfiles` | `s target` | Hedefin gömülü (salt okunur) preset adları. |
| `ListFavorites` | `s target` | Hedefin sıralı favori profilleri. |
| `ListHeadsets` | `—` | Donanım ChatMix tekeri olduğu bilinen kulaklıklar. |
| `ListProfiles` | `s target` | Hedefin profilleri; gömülü presetler önce. |
| `ListRules` | `—` | Uygulama → kanal yönlendirme kuralları. |
| `LoadProfile` | `s target, s name` | Profili veya gömülü preset'i yükler. Anında ve kesintisiz. |
| `MoveStream` | `i stream_id, s channel, b remember` | `remember` → uygulamayı bundan sonra hep bu kanala gönderen bir kural üretir. |
| `MoveEffect` | `s target, s slot, i index` | Efekti listede taşır. **Yapısal**. |
| `NewProfile` | `s target, s name` | Sıfırdan düz bir profil oluşturur ve ona geçer. |
| `Provision` | `—` | Sanal kanalları kurar ve ne kurulduğunu döndürür. **Yapısal**. |
| `Ping` | `—` | İstemcinin daemon'ın ayakta olduğunu ucuzca doğrulaması için. |
| `Reload` | `—` | `config.toml`'u diskten yeniden okur (elle düzenleme sonrası). |
| `RemoveChannel` | `s channel` | Çıkış veya giriş kanalını siler. **Yapısal**. |
| `RemoveEffect` | `s target, s slot` | Efekti zincirden çıkarır. **Yapısal**. |
| `RemoveEqBand` | `s target, i index` | Bir EQ bandını siler. **Canlı**. |
| `RemoveRule` | `s match_key, s pattern, s direction` | Kuralı kaldırır. `direction` boşsa desenin her iki yönü de silinir. |
| `RenameProfile` | `s target, s old, s new` | Kullanıcı profilini yeniden adlandırır. |
| `ReorderFavorites` | `s target, ? names` | Favori sırasını yeniden yazar. |
| `ResetProfile` | `s target` | Aktif profili düz hâle döndürür (EQ sıfır, filtreler kapalı). |
| `SaveProfile` | `s target, s name` | Çalışılan profili yeni adla kaydeder ('farklı kaydet'). |
| `SetBusDevice` | `s bus, s device` | Bus'ın çıkış cihazı. **Yapısal** — graf yeniden kurulur. |
| `SetChannelMute` | `s channel, s bus, b muted` | Kanalın bir miks yolunu susturur. |
| `SetChannelStreamSource` | `s channel, b enabled` | Kanal için OBS'e ayrı bir sanal giriş cihazı yayınla. **Yapısal**. |
| `SetChannelVolume` | `s channel, s bus, d value` | Kanalın bir miks yolundaki seviyesi (lineer, 1.0 = birim kazanç). |
| `SetChatMix` | `d value` | ChatMix konumu (0–100, 50 = nötr). Yalnızca kulaklık miksini etkiler. |
| `SetChatMixConfig` | `b enabled, s left, s right` | ChatMix'in hangi kanalları sürdüğü; virgülle çoklu kanal. |
| `SetDefaultChannel` | `s channel` | Kuralla eşleşmeyen uygulamaların düşeceği kanal. |
| `SetDucking` | `s target, s fields_json` | Bir kanalın **profilindeki** Smart Volume ayarları (şema 4). |
| `SetEqBand` | `s target, i band, s field, s value` | `value` string taşınır: `band_type` metin, diğerleri sayı. |
| `SetEqPreamp` | `s target, d value_db` | Ekolayzer öncesi kazanç. |
| `SetFilterEnabled` | `s target, s slot, b enabled` | Bir efekti açar/kapatır (canlı bypass). |
| `SetFilterParam` | `s target, s slot, s name, d value` | Efektin bir parametresi; insan biriminde (dB, ms, oran). |
| `SetMasterMute` | `s bus, b muted` | Personal/Stream bus'ını susturur. |
| `SetMasterVolume` | `s bus, d value` | Personal/Stream bus'ının master seviyesi. |
| `SetMicDevice` | `s chain, s device` | Mikrofon zincirinin giriş cihazı. **Yapısal**. |
| `SetMicMonitor` | `s chain, b enabled` | Yan ton (kendi sesini kulaklıktan duyma). **Yapısal**. |
| `SetMicMonitorVolume` | `s chain, d value` | Sidetone seviyesi (0.0–4.0 lineer). |
| `SetMicMute` | `s chain, b muted` | Mikrofonu susturur. |
| `SetMicStreamSend` | `s chain, b enabled` | Mikrofonu yayın miksine de gönderir. **Yapısal**. |
| `SetMicVolume` | `s chain, d value` | Mikrofon zincirinin çıkış seviyesi. |
| `SetProfileFavorite` | `s target, s name, b favorite` | Profili favorilere ekler veya çıkarır. Sayı sınırı yok. |
| `SetRule` | `s match_key, s pattern, s channel, b is_regex, s direction` | Uygulama → hedef kuralı ekler veya günceller. |
| `SetLanguage` | `s code` | Arayüz ve mesaj dili (`tr`/`en`). Grafa dokunmaz. |
| `SetTakeOverDefaultSink` | `b enabled` | Sistem varsayılan çıkışını Sonar'a al (varsayılan kapalı). |
| `SetChatMixInvert` | `b enabled` | Donanım ChatMix tekerinin yönünü ters çevirir. Yalnızca teker okumasını etkiler. |
| `SetupSummary` | `—` | Kurulacak (veya kurulmuş) sanal cihazların listesi. Kurulumdan önce de çağrılabilir. |
| `StreamSetup` | `—` | Yayın kurulumunun canlı tanısı: miksi kim dinliyor, mikrofon yayında mı, ne ters gitmiş. |
| `SubscribeMeters` | `b enabled` | Seviye ölçümünü açar/kapatır. Sonuç: kalan abone sayısı. |

### Sinyaller

| Sinyal | Argümanlar | Ne zaman |
|---|---|---|
| `StateChanged` | `s json` | Durum değişti; 50 ms penceresinde `kind` başına teklenir |
| `StreamsChanged` | `s json` | Çalan uygulamalar veya cihaz listesi değişti |
| `LevelsUpdated` | `s json` | Seviye metreleri, 20 Hz (yalnızca abone varken) |
| `GraphRebuilt` | — | Yapısal değişiklik oldu, arayüz tam yenilemeli |
| `Error` | `s code, s message` | Eklenti eksik, graf kurulamadı, çakışan işleyici vb. |

Sinyaller `QDBusMessage.createSignal()` ile **elle** gönderiliyor: PySide6 Python
sinyallerini otobüse relay etmiyor (introspection'da görünseler bile).
