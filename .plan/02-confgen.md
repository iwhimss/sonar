# Faz 2 — graph.conf üreteci

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 1
**Çıktı:** `src/sonar/core/dsp/chain.py`, `src/sonar/engine/confgen.py`,
`tests/test_chain.py`, `tests/test_confgen.py`, `tests/data/graph.conf.golden` — 212 test

---

## Amaç

`SonarConfig` nesnesinden, `pipewire -c` ile çalıştırılabilir tam bir `graph.conf` üretmek.
Bu conf tüm sanal cihazları, DSP zincirlerini ve loopback'leri tanımlar.

---

## ✅ İlk iş: canlı parametre doğrulaması — **TAMAMLANDI**

Plandaki en büyük risk buydu. Kod yazmadan önce elle doğrulandı. **Kulakla değil ölçülerek:**
1 kHz sinüs (-20 dBFS tepe) zincire basıldı, çıkış `pw-cat --record` ile kaydedildi ve
genlik numpy ile ölçüldü.

- [x] LSP `para_equalizer` kazanç portu canlı değişiyor mu? → **Evet.** `eq:g_3 = 8.0`
      yazıldığında çıkış tam olarak **+18.06 dB** arttı (teorik `20·log₁₀8 = 18.06`).
- [x] `enabled` portu canlı bypass yapıyor mu? → **Evet.** Kapalıyken -23.01 dBFS
      (girişle bit-şeffaf), açıkken -4.95 dBFS. Geçiş kesintisiz.
- [x] LSP `gate` / `compressor` / `limiter` portları canlı değişiyor mu? → **Evet**, üçü de.
      Bypass'a döndüklerinde çıkış tam olarak -23.01 dBFS'e geri dönüyor.
- [x] DeepFilterNet LADSPA filter-chain içinde yükleniyor mu? → **Evet**, 5 aşamalı zincirin
      (`df → gate → eq → comp → lim`) tamamı tek `filter.graph` içinde sorunsuz kuruldu.
      `Attenuation Limit (dB)` portu canlı: 0 → şeffaf, 100 → -86 dBFS.
- [x] Değer yazımı sırasında tık/pop sesi var mı? → **Yok.** 3 saniye boyunca 100 ardışık
      kazanç yazımı (fader sürükleme benzetimi) yapıldı:
      - dropout sayısı: **0**
      - ölçülen maksimum örnek adımı / teorik maksimum: **1.00×** (klik olsa ≫1 olurdu)
      - 1.5× eşiğini aşan sıçrama: **0**

**Sonuç: yedek plana (builtin biquad) gerek yok. Ana plan geçerli.**

---

## Doğrulama sırasında ortaya çıkan üç düzeltme

Bunlar plandaki varsayımları değiştiriyor:

### 1. `Audio/Source/Virtual` filter-chain içinde çalışmıyor
`playback.props` içinde `media.class = Audio/Source/Virtual` verildiğinde PipeWire 1.6.8
node'u kuramıyor:
```
pw.node | can't add port: -28 (ENOSPC)
```
Süreç ayakta kalıyor ama **hiçbir node oluşmuyor**. Yeniden üretilebilir.
`media.class = Audio/Source` ile sorunsuz çalışıyor.

**Karar:** `_fx` node'ları `Audio/Source` olacak. Varsayılan mikrofon seçilmelerini önlemek
için `priority.session = 0` verilecek — EasyEffects'in `easyeffects_source` için kullandığı
yöntemin aynısı (sistemdeki gerçek mikrofonlar 2009–2100 önceliğinde).

### 2. Limiter'ın `boost` ve `alr` portları kapatılmalı
LSP limiter varsayılan olarak `boost = 1` (Gain boost) ve `alr = 1` (Automatic Level
Regulation) ile geliyor. Bu hâliyle `th` bir **tavan değil**, sinyali 0 dBFS'e taşıyan bir
hedef seviye: `th = -30 dB` verdiğimizde çıkış -20 dBFS girişten **daha yüksek** çıktı.

`boost = 0` ve `alr = 0` yazıldığında `th` tam olarak tavan oluyor — ölçüm:

| `th` | ölçülen tepe |
|---|---|
| -30 dB | -30.01 dBFS |
| -25 dB | -25.00 dBFS |
| -20 dB (girişe eşit) | -20.00 dBFS |

**Karar:** `params.py` limiter aşamasını yazarken `boost = 0.0` ve `alr = 0.0` sabitlerini de
göndermeli. Aksi hâlde limiter'ı açmak sesi yükseltir — kullanıcının beklediğinin tam tersi.

### 3. Kontrol portları `Props[1]` içinde, `Props[0]` değil
`pw-dump <id> | jq '.info.params.Props'` **iki** nesne döndürüyor: `[0]` adapter'ın kendi
dönüşüm ayarları (`channelmix.*`, `resample.*`), `[1]` filtre grafının portları
(`eq:g_3`, `gate:at`, …). Durum okuyan kod ikincisine bakmalı.

Tek çağrıda çoklu yazım doğrulandı — 5 anahtar birlikte gönderilip hepsi uygulandı:
```
pw-cli s <id> Props '{ params = [ "eq:ft_3" 1.0 "eq:fm_3" 6.0 "eq:f_3" 500.0 "eq:g_3" 2.0 "eq:q_3" 2.5 ] }'
```
Bu, Faz 3'teki toplu yazım (debounce) tasarımının uygulanabilir olduğunu doğruluyor.

### 4. LSP'nin FFT analizörleri bypass'ta bile CPU yakıyor
Graf boştayken (hiç ses çalmıyor, tüm filtreler kapalı) süreç **%21 CPU** harcıyordu.
Aşama aşama ölçüm — 6 zincirlik graf, boşta, 8 saniyelik pencere:

| Zincir içeriği | CPU | RSS |
|---|---|---|
| boş süreç (sadece modüller) | %0.00 | 5 MB |
| yalnız gate | %5.00 | 52 MB |
| yalnız compressor | %5.12 | 52 MB |
| yalnız limiter | %5.12 | 90 MB |
| **yalnız EQ** | **%16.12** | 64 MB |

Suçlu EQ. Sebebi `enabled = 0` olmaması değil: LSP `para_equalizer`'ın giriş/çıkış/dönüş
spektrum analizörleri (`ife_l`, `ife_r`, `ofe_l`, `ofe_r`, `rfe_l`, `rfe_r`) **varsayılan
olarak açık** ve bypass'ta da çalışıyorlar. Altısı da kapatıldığında:

| | önce | sonra |
|---|---|---|
| yalnız EQ (6 zincir) | %16.12 | **%4.37** |
| tam zincir (6 zincir) | %20.86 | **%9.75** |
| **gerçek graf (4 kanal + 2 bus + 2 mic)** | **%21.11** | **%6.62** |

Bu analizörlere hiç ihtiyacımız yok — EQ eğrisini Faz 8'de numpy ile kendimiz çizeceğiz.
`registry.eq_analyzer_ports()` port adlarını kanal sayısına göre üretiyor (stereo'da `_l`/`_r`
ekli, mono'da eksiz) ve hem conf başlangıç değerleri hem canlı yazım yolu sıfırlıyor.

**Kalan bellek dürüstçe:** RSS ~136 MB. Plandaki "~15 MB" tahmini yanlıştı; LSP eklentileri
örnek başına birkaç MB önceden ayırıyor. Yine de kanal başına ayrı süreç seçeneğinin
(~18 süreç) çok altında ve boştaki CPU artık kabul edilebilir.

### 5. Fader için `wpctl` değil `channelVolumes` kullanılmalı
`wpctl set-volume <id> 0.5` **kübik** ölçek uyguluyor: ölçümde çıkış -6 dB değil **-18 dB**
düştü. Modelimiz `volume`'ü lineer tutuyor (1.0 = birim kazanç), dolayısıyla Faz 3'ün
`control.py`'si doğrudan Props yazmalı:

```
pw-cli s <id> Props '{ channelVolumes = [ 0.5, 0.5 ] }'   # tam -6.02 dB, ölçüldü
pw-cli s <id> Props '{ mute = true }'                     # tam sessizlik, ölçüldü
```

---

### Yan doğrulama: katalog gerçeğe uyuyor
Çalışan graf `PropInfo` üzerinden port aralıklarını bildiriyor ve Faz 1 kataloğuyla birebir
örtüştü: `eq:g_3` → varsayılan 1.0, aralık [0.015850, 63.095749]; `eq:f_3` → varsayılan 63.0
(ISO R10, band 3). Faz 1'de TTL'den çıkarılan değerler çalışma zamanında da doğru.

---

## Görevler

### `core/dsp/chain.py` — zincir şablonu
- [x] `plan_chain()` + `build_chain()` — aşama listesinden PipeWire `filter.graph` sözlüğü
      (`nodes`, `links`, `inputs`, `outputs`). Planda tek fonksiyondu; ikiye ayrıldı çünkü
      "hangi aşamalar kurulabilir" sorusu ile "graf nasıl bağlanır" sorusu ayrı ayrı test edilebiliyor
- [x] Aşama adları sabit: `df`, `gate`, `eq`, `comp`, `lim` → parametre anahtarları kararlı
- [x] Stereo/mono varyant seçimi
- [x] Kurulu olmayan eklenti zincirden atlanır, linkler yeniden bağlanır
      (test: EQ düşünce `gate → comp` bağlanıyor, boşta kalan uç kalmıyor)
- [x] Tüm aşamalar **bypass** başlangıç değeriyle doğar

### `engine/confgen.py` — conf üreteci
- [x] `generate(cfg) -> str` ve yapısal `generate_modules(cfg) -> list[dict]`
- [x] **Kanal bölümü** — `sonar_<id>` (Audio/Sink) → DSP → `sonar_<id>_fx`
      (**`Audio/Source`**, `priority.session = 0` — düzeltme 1)
- [x] **Bus bölümü** — `sonar_personal` ve `sonar_stream` (Audio/Sink) + master DSP
  - personal çıkışı fiziksel cihaza giden bir akış; cihaz boşsa sistem varsayılanına düşer
  - stream çıkışı **`sonar_stream_out` adlı `Audio/Source`**. Planda "monitör yakalanır"
    yazıyordu; ayrı bir kaynak node'u hem OBS'te seçmesi kolay hem yayın miksinin
    hoparlöre sızmasını imkânsız kılıyor
- [x] **Loopback bölümü** — kanal başına `sonar_<id>_to_personal` / `_to_stream`
- [x] **Mikrofon bölümü** — `sonar_mic`, `sonar_stream_mic`; `share_chain_with_mic` ise
      ikinci zincir yerine loopback
- [x] **Opsiyonel loopback'ler** — sidetone ve mic → stream, ikisi de varsayılan kapalı
- [x] `audio.rate = 48000` her node'da + `default.clock.rate`
- [x] Deterministik çıktı (sabit sıra, sabit float biçimi) — altın dosya testiyle korunuyor
- [x] Conf'ta yalnızca nötr başlangıç değerleri; profil değerleri canlı yazımla
- [x] `python -m sonar.engine.confgen [--config <yol>]` CLI

### Testler — 40 yeni test (toplam 212)
- [x] `tests/data/graph.conf.golden` altın dosya karşılaştırması
- [x] Determinizm: aynı config iki kez → byte-eşdeğer
- [x] **Kanal ekleme/silme, cihaz değişimi, band sayısı → conf değişiyor**
- [x] **Profil, ses seviyesi, mute, ChatMix, yönlendirme kuralı → conf değişMİyor** (kritik)
- [x] Eksik eklenti: DeepFilterNet yoksa mic zinciri onsuz kuruluyor
- [x] Node adı çakışması yok; her `Audio/Source` `priority.session = 0` taşıyor
- [x] `Audio/Source/Virtual` conf'a hiç girmiyor (düzeltme 1'in regresyon testi)
- [x] **Üretilen conf `spa-json-dump` ile ayrıştırılıp yapısı doğrulanıyor** — kendi
      SPA-JSON yazıcımıza güvenmek yerine PipeWire'ın kendi ayrıştırıcısı hakem
- [x] Boşluklu/parantezli port adı (`"Attenuation Limit (dB)"`) yuvarlak yolculuktan sağ çıkıyor

---

## Manuel doğrulama — ✅ yapıldı

Üretilen conf gerçek sistemde çalıştırıldı; **32 node** beklendiği gibi oluştu, log tertemiz.
Ses yolları kulakla değil ölçülerek doğrulandı (1 kHz sinüs, -20.00 dBFS tepe girildi):

| Yol | ölçülen tepe |
|---|---|
| `sonar_game` → `sonar_stream_out` (OBS'in göreceği yayın miksi) | -20.00 dBFS (bit-şeffaf) |
| `sonar_media` → `sonar_personal` (kulaklık yolu) | -20.00 dBFS (bit-şeffaf) |
| aynı yol, `sonar_media_to_stream` faderi 0 | sessizlik |
| aynı yol, fader `channelVolumes = 0.5` | -26.02 dBFS (tam -6.02 dB) |
| aynı yol, fader `channelVolumes = 0.25` | -32.04 dBFS (tam -12.04 dB) |
| aynı yol, `mute = true` | sessizlik |
| `sonar_game` üzerinde canlı EQ, `g_5 = 2.0` | -13.98 dBFS (tam +6.02 dB) |
| aynı, `g_5 = 0.5` | -26.02 dBFS (tam -6.02 dB) |

Yani **kanal izolasyonu, çift fader ve canlı EQ üçü de gerçek grafta çalışıyor.**
Süreç durdurulduğunda geriye hiçbir `sonar_*` node'u kalmıyor.

---

## Tamamlanma kriteri — ✅ karşılandı

Graf elle çalıştırıldığında tüm sanal cihazlar görünüyor, ses hem kulaklığa hem yayın
miksine akıyor, `pw-cli s ... Props` ile EQ canlı ve kesintisiz değişiyor.

```bash
ruff check src/ tests/ && pytest -q          # 212 test geçti, lint temiz
```
