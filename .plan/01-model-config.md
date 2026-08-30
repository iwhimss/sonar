# Faz 1 — Veri modeli ve yapılandırma

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 0
**Çıktı:** `src/sonar/core/{model,config}.py`, `src/sonar/core/dsp/{registry,params}.py`, testler

---

## Amaç

Tüm uygulamanın üzerine kurulacağı saf (PipeWire'dan bağımsız, yan etkisiz) veri modelini ve
kalıcılık katmanını yazmak. Bu katman hem daemon hem GUI hem CLI tarafından kullanılır ve
tamamen birim testlerle doğrulanabilir olmalıdır.

---

## Görevler

### `core/model.py` — veri modeli
- [ ] `FilterStage` enum: `DEEPFILTER`, `GATE`, `EQ`, `COMP`, `LIMITER`
- [ ] `FilterState` — `stage`, `enabled: bool`, `params: dict[str, float]`
- [ ] `EqBand` — `index`, `enabled`, `type` (peak/lowshelf/highshelf/lowpass/highpass/notch), `freq`, `gain`, `q`, `slope`
- [ ] `EqState` — `enabled`, `band_count` (5/10/16/32), `bands: list[EqBand]`, `preamp`
- [ ] `Profile` — `name`, `eq: EqState`, `filters: dict[FilterStage, FilterState]`, `favorite_slot: int | None`
- [ ] `Channel` — `id`, `name`, `color`, `icon`, `personal: BusSend`, `stream: BusSend`, `active_profile`, `is_builtin`
- [ ] `BusSend` — `volume: float`, `muted: bool`
- [ ] `MicChain` — `id` (`mic` / `stream_mic`), `source_device`, `profile`, `share_chain_with_mic: bool`
- [ ] `MasterBus` — `id` (`personal` / `stream`), `device`, `volume`, `muted`, `profile`
- [ ] `RoutingRule` — `match_key` (binary/app_name/media_name), `pattern`, `is_regex`, `channel_id`, `priority`
- [ ] `ChatMixConfig` — `enabled`, `value`, `left_channel`, `right_channel`
- [ ] `SonarConfig` — kök nesne: `schema_version`, `channels`, `buses`, `mic_chains`, `rules`, `chatmix`, `settings`
- [ ] Hepsi `@dataclass(slots=True)`, tam tip anotasyonlu, `to_dict()` / `from_dict()` ile

### `core/config.py` — kalıcılık
- [ ] Yollar: `~/.config/sonar/config.toml`, `~/.config/sonar/profiles/<kanal>/<profil>.json`
      (XDG_CONFIG_HOME'a saygılı), durum dosyaları `~/.local/state/sonar/`
- [ ] `load() -> SonarConfig` — dosya yoksa varsayılanı üret ve yaz
- [ ] `save(cfg)` — **atomik yazım** (geçici dosya + `os.replace`), fsync
- [ ] `schema_version` alanı + `migrate()` iskeleti (v1 → gelecek sürümler)
- [ ] Bozuk/ayrıştırılamayan config → `config.toml.corrupt-<zaman>` olarak yedeklenir, varsayılana düşülür, uyarı loglanır
- [ ] Profil dosyaları ayrı: profil ekleme/silme config.toml'u yeniden yazmaz

### `core/dsp/registry.py` — eklenti kataloğu
- [ ] Kürasyonlu **statik katalog**: desteklenen her eklenti için `PluginSpec`
      (URI/LADSPA yolu+label, tip, port sembolleri, her port için `min`/`max`/`default`/`scale` (lin|log|db)/`unit`)
- [ ] Kapsam: LSP `para_equalizer_x8/x16/x32_stereo` ve `_mono`, `gate_stereo/mono`,
      `compressor_stereo/mono`, `limiter_stereo/mono`; DeepFilterNet LADSPA
- [ ] `probe()` — eklentinin diskte gerçekten var olup olmadığını doğrular
      (LV2 için `/usr/lib/lv2/**/manifest.ttl` içinde URI araması, LADSPA için dosya varlığı);
      sonuç önbelleklenir
- [ ] Eksik eklenti → `PluginSpec.available = False`; UI o efekti "kurulu değil" gösterir,
      confgen o aşamayı zincirden çıkarır (topoloji o kurulum için sabit kalır)

### `core/dsp/params.py` — değer dönüşümü
- [ ] `ui_to_port(spec, port, value)` / `port_to_ui(...)` — dB ↔ lineer, log frekans ölçeği, enum indeksleri
- [ ] `clamp()` — port aralığına kırpma, aralık dışı değerde uyarı
- [ ] EQ band tipi ↔ LSP `ft_N` enum eşlemesi (peak=1, lowshelf=…, tam eşleme TTL'den doğrulanacak)
- [ ] `profile_to_params(profile) -> dict[str, float]` — bir profili `"eq:g_3" → 4.5` biçiminde
      düz parametre sözlüğüne çevirir (canlı yazımın tek kaynağı)

### Varsayılan yapılandırma
- [ ] Kanallar: **Game** (`#22C58B`), **Chat** (`#3B9EFF`), **Media** (`#F0479A`), **Aux** (`#8B95A5`)
- [ ] Bus'lar: **Personal** (varsayılan cihaz = mevcut sistem varsayılanı), **Stream**
- [ ] Mic zincirleri: `mic`, `stream_mic` (varsayılan olarak zincir paylaşımı **kapalı**)
- [ ] Tüm profiller "Default": düz EQ (tüm bandlar 0 dB), tüm filtreler **kapalı**
- [ ] Varsayılan fader'lar: personal 100 %, stream 100 %; Media'nın stream'i 100 % (kullanıcı kısar)
- [ ] `settings`: `take_over_default_sink = false`, `sample_rate = 48000`, `default_channel = "media"`

### Testler
- [ ] `test_config.py` — yuvarlak yolculuk (`save` → `load` → eşit), atomik yazım, bozuk dosya kurtarma, migrasyon iskeleti
- [ ] `test_params.py` — dB/lineer dönüşümü, kırpma, EQ tipi eşlemesi, `profile_to_params` çıktısı

---

## Tamamlanma kriteri

```bash
ruff check src/ && pytest -q            # yeşil
python -c "from sonar.core.config import load; print(load())"   # varsayılan config üretir ve yazar
python -c "from sonar.core.dsp.registry import probe; print(probe())"  # sistemdeki eklentileri doğru raporlar
```
`~/.config/sonar/config.toml` okunabilir, elle düzenlenebilir ve tekrar yüklenebilir olmalı.
