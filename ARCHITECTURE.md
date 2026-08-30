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
  │ oyun          ├──▶ [sonar_game]  ─DSP─▶ sonar_game_fx ──┐  (Audio/Source/Virtual → OBS)
  │ Discord       ├──▶ [sonar_chat]  ─DSP─▶ sonar_chat_fx ──┤
  │ tarayıcı      ├──▶ [sonar_media] ─DSP─▶ sonar_media_fx ─┤
  │ diğer         ├──▶ [sonar_aux]   ─DSP─▶ sonar_aux_fx ───┤
  └───────────────┘                                          │
                          her kanaldan 2 loopback:           │
                     ┌────────────────────────────────────────┘
                     │
       personal fader ├──▶ [sonar_personal] ─master DSP─▶ ► fiziksel kulaklık
       stream  fader  └──▶ [sonar_stream]   ─master DSP─▶ ► monitor → OBS

     MİKROFON
  fiziksel ─┬──▶ [mic zinciri]        ─▶ sonar_mic         (→ Discord vb.)
            └──▶ [stream mic zinciri] ─▶ sonar_stream_mic  (→ OBS)
                      └──(ops.) sidetone ─▶ sonar_personal
                      └──(ops.) ─────────▶ sonar_stream
```

### Node isimleri

| Node | Sınıf | Amaç |
|---|---|---|
| `sonar_<kanal>` | `Audio/Sink` | Uygulamalar buraya çalar |
| `sonar_<kanal>_fx` | `Audio/Source/Virtual` | DSP sonrası çıkış — OBS bunu yakalar |
| `sonar_<kanal>_to_personal` | loopback | Personal fader'ı bu node'a uygulanır |
| `sonar_<kanal>_to_stream` | loopback | Stream fader'ı bu node'a uygulanır |
| `sonar_personal` | `Audio/Sink` | Kişisel miks bus'ı → fiziksel çıkış |
| `sonar_stream` | `Audio/Sink` | Yayın miksi → monitörü OBS yakalar |
| `sonar_mic` | `Audio/Source/Virtual` | İşlenmiş mikrofon (uygulamalar için) |
| `sonar_stream_mic` | `Audio/Source/Virtual` | İşlenmiş mikrofon (yayın için) |

`_fx` node'ları `Audio/Source/Virtual` sınıfında olduğu için WirePlumber onları hiçbir yere
otomatik bağlamaz. Sadece bizim loopback'lerimiz ve OBS onlardan okur — bu yüzden kanal
başına ayrı OBS çıkışı **ek maliyet getirmez**.

### OBS'in üç erişim noktası

1. **`sonar_<kanal>_fx`** — DSP sonrası, fader'lardan bağımsız. Kanal başına ayrı track için.
2. **`Sonar Stream Mix` monitörü** — stream fader'larıyla mikslenmiş birleşik ses.
3. **`Sonar Stream Mic`** — mikrofonun yayına özel zinciri.

---

## DSP zinciri

Topoloji **sabittir**; efektler açılıp kapanmaz, yalnızca bypass edilir. Bu sayede bir efekti
açıp kapatmak graf değişikliği değil, tek bir parametre yazımıdır — ses kesintisi olmaz.

```
kanal:  giriş ─▶ gate ─▶ eq ─▶ comp ─▶ limiter ─▶ çıkış
mic:    giriş ─▶ deepfilter ─▶ gate ─▶ eq ─▶ comp ─▶ limiter ─▶ çıkış
```

| Aşama | Eklenti | Bypass |
|---|---|---|
| DeepFilterNet | LADSPA `libdeep_filter_ladspa.so` (`deep_filter_mono` / `deep_filter_stereo`) | attenuation = 0 |
| Gate | `http://lsp-plug.in/plugins/lv2/gate_stereo` | `enabled` = 0 |
| EQ | `http://lsp-plug.in/plugins/lv2/para_equalizer_x16_stereo` | `enabled` = 0 |
| Compressor | `http://lsp-plug.in/plugins/lv2/compressor_stereo` | `enabled` = 0 |
| Limiter | `http://lsp-plug.in/plugins/lv2/limiter_stereo` | `enabled` = 0 |

Zincirdeki aşama adları sabittir (`df`, `gate`, `eq`, `comp`, `lim`), böylece parametre
anahtarları da kararlı olur: `"eq:g_3"`, `"gate:at"` gibi.

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
wpctl set-volume <loopback-node-id> 0.72

# Çıkış cihazını değiştir (kesintisiz)
pactl move-sink-input <stream-id> <yeni-cihaz>
```

Daemon `pw-dump -m` ile grafı izler ve `node.name → id` haritasını günceller.

Fader sürüklerken saniyede 60 alt süreç açılmasını önlemek için `engine/control.py`
20 ms'lik pencerelerde yazımları biriktirip toplu gönderir. Son değerin her zaman
uygulanması garanti edilir.

---

## Yapılandırma

```
~/.config/sonar/
├── config.toml                  # kanallar, fader'lar, kurallar, ayarlar
├── ui.json                      # pencere durumu
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

`config.toml` elle düzenlenebilir — `Reload()` D-Bus metodu diskten yeniden okur.
Bozuk bir config yedeklenir (`config.toml.corrupt-<zaman>`) ve varsayılana düşülür.

---

## D-Bus API

Servis `io.github.iwhimss.Sonar`, yol `/io/github/iwhimss/Sonar`.

Karmaşık yapılar D-Bus struct yerine **JSON string** olarak taşınır — sürüm uyumluluğu ve
hata ayıklama kolaylığı için. Metot argümanları basit tiplerde kalır.

Tam referans [`.plan/04-daemon-dbus.md`](.plan/04-daemon-dbus.md) içinde; Faz 4
tamamlandığında buraya taşınacak.

---

## İleriye dönük not

`engine/` katmanı D-Bus API'sinin arkasında izole. İleride performans veya kesintisiz efekt
ekleme kritik hâle gelirse, bu katman C++/lilv tabanlı native bir motorla (EasyEffects
mimarisi) değiştirilebilir — GUI ve CLI etkilenmez.
