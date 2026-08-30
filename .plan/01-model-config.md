# Faz 1 — Veri modeli ve yapılandırma

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 0
**Çıktı:** `src/sonar/core/{model,config,serde,tomlio}.py`, `src/sonar/core/dsp/{registry,params}.py`, 176 test

---

## Amaç

Tüm uygulamanın üzerine kurulacağı saf (PipeWire'dan bağımsız, yan etkisiz) veri modelini ve
kalıcılık katmanını yazmak. Bu katman hem daemon hem GUI hem CLI tarafından kullanılır ve
tamamen birim testlerle doğrulanabilir olmalıdır.

---

## Görevler

### `core/serde.py` — dataclass ↔ sözlük kodeki *(planda yoktu, eklendi)*
20'den fazla dataclass'a elle `to_dict`/`from_dict` yazmak yerine tip anotasyonlarından
türeyen tek bir kodek. İki uyumluluk garantisi verir:
- [x] **İleriye dönük:** bilinmeyen anahtarlar yok sayılır (eski sürüm yeni dosyayı okuyabilir)
- [x] **Geriye dönük:** eksik anahtarlar dataclass varsayılanına düşer (yeni alan eski dosyayı bozmaz)
- [x] Enum, `X | None`, `list[X]`, `dict[K, V]`, iç içe dataclass desteği
- [x] Hata mesajlarında alanın tam yolu (`children.1.value`)

### `core/tomlio.py` — TOML yazıcı *(planda yoktu, eklendi)*
Python'da `tomllib` yalnızca **okur**. Yapılandırmayı JSON'a çevirmek yerine TOML'da tutmayı
seçtik çünkü kullanıcının `config.toml`'u elle düzenlemesi tasarımın parçası.
- [x] Tablolar, tablo dizileri (`[[channels]]`), ilkel değerler ve diziler
- [x] Kaçış dizileri, tırnak gerektiren anahtarlar (`"Attenuation Limit (dB)"`)
- [x] Tam sayı görünümlü float'lar `1.0` olarak yazılır (TOML'da tip korunur)
- [x] `tomllib` ile yuvarlak yolculuk testleri

### `core/model.py` — veri modeli
- [x] `FilterStage` enum: `DEEPFILTER`/`GATE`/`EQ`/`COMP`/`LIMITER` — değerler zincirdeki
      node adlarıyla birebir aynı (`df`, `gate`, `eq`, `comp`, `lim`)
- [x] `FilterState` — `enabled`, `params: dict[str, float]`
- [x] `EqBand` — `freq`, `gain_db`, `q`, `band_type`, `slope`, `enabled` + `clamped()`
- [x] `EqState` — `enabled`, `band_count`, `preamp_db`, `bands` + `active_bands()`
- [x] `Profile` — `name`, `eq`, `filters`, `favorite_slot` + tembel `filter(stage)`
- [x] `Channel` — kimlik, renk, ikon, sıra, `personal`/`stream` gönderileri, aktif profil
      + node adı türetme (`sink_node`, `fx_node`, `loopback_node`)
- [x] `BusSend`, `MasterBus`, `MicChain`, `RoutingRule` (+ `matches()`, `specificity`)
- [x] `ChatMixConfig`, `Settings`, `SonarConfig` + arama yardımcıları
- [x] `default_band_frequencies()` / `default_band_q()` — 10 bandda tam oktav aralık,
      klasik `Q = 1.414`
- [x] Hepsi `@dataclass(slots=True)`, tam tip anotasyonlu, `StrEnum` tabanlı

**Önemli karar:** filtre parametreleri **insan birimlerinde** tutulur (`threshold_db`,
`attack_ms`, `ratio`), eklenti port birimlerinde değil. Böylece yapılandırma dosyası
kullanılan LV2 eklentisinden bağımsız kalır — Faz 2'nin yedek planı (builtin biquad'lar)
devreye girse bile kullanıcının profilleri geçerliliğini korur.

### `core/config.py` — kalıcılık
- [x] `Paths` — XDG'ye saygılı; testler kendi kökünü verebilir
- [x] `ConfigStore.load()` — dosya yoksa varsayılan üretilip yazılır
- [x] `save()` — atomik (geçici dosya → `fsync` → `os.replace` → dizin `fsync`)
- [x] `schema_version` + `migrate()` iskeleti; daha yeni sürüm reddedilir
- [x] Bozuk config → `config.toml.corrupt-<zaman>` yedeği, varsayılana düşüş, uyarı logu
- [x] Profiller ayrı JSON dosyalarında; ekleme/silme `config.toml`'u yeniden yazmaz
- [x] `safe_name()` — dizin geçişi imkânsız (eğik çizgi kaldırılır, `.` korunur)
- [x] `Default` profili silinemez; yeniden adlandırma, kopyalama, listeleme

### `core/dsp/registry.py` — eklenti kataloğu
- [x] Kürasyonlu statik katalog: LSP `para_equalizer_x8/x16/x32`, `gate`, `compressor`,
      `limiter` (mono + stereo) ve DeepFilterNet LADSPA — **14 eklenti**
- [x] Her portun sembolü, adı, min/max/varsayılan, birimi, log/integer bayrakları
- [x] Band varsayılan frekansları ISO R10 serisinden (LSP'nin kendi değerleri)
- [x] `is_available()` — LV2 için manifest taraması, LADSPA için dosya varlığı, önbellekli
- [x] `extract_ttl_uris()` — Turtle `@prefix` kısaltmalarını açar
- [x] `eq_plugin_for(band_count)` — 5→x8, 10/16→x16, 32→x32

### `core/dsp/params.py` — değer dönüşümü
- [x] `db_to_linear()` / `linear_to_db()` — **LSP'nin tüm kazanç portları lineerdir**, dB değil
- [x] `eq_params()` — EQ durumunu port değerlerine çevirir; kullanılmayan bandlar `ft = 0` (Off)
- [x] `stage_params()` — dinamik aşamalar; kapalıyken yalnızca bypass portu yazılır
- [x] `profile_to_params()` — bir profili `{"eq:g_3": 1.6788, ...}` biçimine indirger
      (canlı yazımın tek kaynağı)
- [x] Tüm değerler eklentinin port aralığına kırpılır
- [x] EQ band tipi ↔ LSP `ft_N` eşlemesi TTL'den doğrulandı
      (0=Off, 1=Bell, 2=Hi-pass, 3=Hi-shelf, 4=Lo-pass, 5=Lo-shelf, 6=Notch, 8=Allpass, 9=Bandpass)
- [x] Filtre modeli `fm_N = 6` (**APO DR**) seçildi — RBJ cookbook biquad'ıyla birebir örtüşür,
      böylece Faz 8'de çizeceğimiz EQ eğrisi kulağın duyduğuyla aynı olur

### Varsayılan yapılandırma
- [x] Kanallar: Game `#22C58B`, Chat `#3B9EFF`, Media `#F0479A`, Aux `#8B95A5`
- [x] Bus'lar: Personal Mix, Stream Mix (cihaz boş = sistem varsayılanı)
- [x] Mikrofonlar: `mic`, `stream_mic` (zincir paylaşımı kapalı)
- [x] Tüm profiller "Default": düz EQ, tüm filtreler kapalı → **ilk kurulumda ses değişmez**
- [x] 13 önerilen yönlendirme kuralı (Discord/TeamSpeak → Chat, tarayıcı/Spotify → Media)
- [x] `take_over_default_sink = false`, `sample_rate = 48000`, `default_channel = "media"`

### Testler — 176 test, hepsi geçiyor
- [x] `test_serde.py` (10) — yuvarlak yolculuk, uyumluluk, hata yolları
- [x] `test_tomlio.py` (12) — `tomllib` ile yuvarlak yolculuk, kaçışlar, tip korunumu
- [x] `test_model.py` (44) — node adı çakışması, kural eşleştirme, band kırpma, varsayılanlar
- [x] `test_config.py` (39) — kalıcılık, atomiklik, bozuk dosya kurtarma, dosya adı güvenliği
- [x] `test_params.py` (45) — dB/lineer, kırpma, bypass, profil indirgeme
- [x] `test_registry.py` (26) — katalog tutarlılığı **ve kurulu eklentilere karşı çapraz doğrulama**

---

## Yol boyunca yakalananlar

1. **LSP kazanç portları lineer.** `g_N` aralığı 0.01585–63.096 (yani ±36 dB), dB değil.
   dB yazsaydık ekolayzer tamamen yanlış çalışırdı.
2. **Band varsayılan frekansları banda göre değişiyor.** Kataloğa hepsine 16 Hz yazmıştım;
   TTL'ye karşı çapraz doğrulama testi yakaladı. Gerçek değerler ISO R10 serisi.
3. **Band devre dışı bırakma `xs_N` değil.** `xs_N` = solo, `xm_N` = mute; bandı kapatmanın
   yolu `ft_N = 0` (Off).
4. **LV2 manifest'leri `@prefix` kısaltması kullanıyor.** İlk tarayıcı yalnızca tam
   `<http://...>` arıyordu ve kurulu LSP'yi "yok" sanıyordu. Uçtan uca doğrulama yakaladı;
   `extract_ttl_uris()` artık kısaltmaları açıyor, regresyon testi eklendi.
5. **DeepFilterNet'in `enabled` portu yok.** Bypass, azaltma sınırını 0 dB yaparak sağlanıyor.

---

## Tamamlanma kriteri — ✅ karşılandı

```bash
ruff check src/ tests/ && pytest -q          # 176 test geçti, lint temiz
```

```
Kanallar : ['game', 'chat', 'media', 'aux']
Bus'lar  : ['personal', 'stream']
Mikrofon : ['mic', 'stream_mic']
Kurallar : 13 adet
Kurulu eklentiler: 14/14 ✓
Varsayılan profil -> 94 canlı parametre
```

`~/.config/sonar/config.toml` okunabilir ve elle düzenlenebilir; düzenlenen değer geri okunuyor.
