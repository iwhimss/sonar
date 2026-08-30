# Sonar for Linux — Genel Plan ve Durum

> **Bu dosya projenin canlı durum panosudur.** Herhangi bir anda buraya bakıp nerede kalındığı görülebilir.
> Her faz kendi dosyasında (`NN-*.md`) ayrıntılı görev listesi tutar.

---

## Şu an neredeyiz

**Aktif faz:** Faz 2 — graph.conf üreteci
**Son güncelleme:** 2026-08-31
**Sonraki adım:** Faz 2 — graph.conf üreteci (ilk iş: canlı parametre doğrulaması).

| # | Faz | Durum |
|---|---|---|
| 0 | [İskelet ve repo](00-overview.md) | 🟢 Tamamlandı |
| 1 | [Veri modeli ve yapılandırma](01-model-config.md) | 🟢 Tamamlandı |
| 2 | [graph.conf üreteci](02-confgen.md) | 🟡 Sıradaki |
| 3 | [Engine: süreç yönetimi ve canlı kontrol](03-engine.md) | ⚪ Bekliyor |
| 4 | [Daemon ve D-Bus API](04-daemon-dbus.md) | ⚪ Bekliyor |
| 5 | [Uygulama yönlendirme](05-routing.md) | ⚪ Bekliyor |
| 6 | [Seviye ölçümü](06-meters.md) | ⚪ Bekliyor |
| 7 | [GUI tasarım sistemi ve Mixer](07-gui-mixer.md) | ⚪ Bekliyor |
| 8 | [Kanal FX sayfası](08-gui-fx.md) | ⚪ Bekliyor |
| 9 | [Profiller, presetler, ChatMix](09-profiles-chatmix.md) | ⚪ Bekliyor |
| 10 | [Uçtan uca doğrulama ve dokümantasyon](10-verify-docs.md) | ⚪ Bekliyor |
| 11 | [Paketleme](11-packaging.md) | ⚪ Bekliyor |
| — | [v1 sonrası backlog](99-backlog.md) | 📋 Liste |

Durum işaretleri: ⚪ bekliyor · 🟡 devam ediyor · 🟢 tamamlandı · 🔴 engellendi

**Test durumu:** 176 test geçiyor, `ruff` temiz.

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
  │ oyun          ├──▶ [sonar_game]  ─DSP─▶ sonar_game_fx ──┐  (Audio/Source/Virtual → OBS)
  │ Discord       ├──▶ [sonar_chat]  ─DSP─▶ sonar_chat_fx ──┤
  │ tarayıcı      ├──▶ [sonar_media] ─DSP─▶ sonar_media_fx ─┤
  │ diğer         ├──▶ [sonar_aux]   ─DSP─▶ sonar_aux_fx ───┤
  └───────────────┘                                          │
                          her kanaldan 2 loopback:           │
                     ┌────────────────────────────────────────┘
                     │
       personal fader ├──▶ [sonar_personal] ─master DSP─▶ ► Arctis 7 (fiziksel)
       stream  fader  └──▶ [sonar_stream]   ─master DSP─▶ ► monitor → OBS

     MİKROFON
  Fifine ──┬──▶ [mic zinciri]        ─▶ sonar_mic         (Audio/Source/Virtual → Discord)
           └──▶ [stream mic zinciri] ─▶ sonar_stream_mic  (Audio/Source/Virtual → OBS)
                     └──(ops.) sidetone ─▶ sonar_personal
                     └──(ops.) ─────────▶ sonar_stream
```

**Kanal başına 3 OBS erişim noktası:**
1. `sonar_<kanal>_fx` — DSP sonrası, fader'lardan bağımsız → OBS'de kanal başına ayrı track
2. `Sonar Stream Mix` monitörü — stream fader'larıyla mikslenmiş birleşik ses
3. `Sonar Stream Mic` — mikrofonun yayına özel zinciri

`_fx` node'ları `Audio/Source/Virtual` olduğu için WirePlumber onları otomatik bağlamaz;
sadece bizim loopback'lerimiz ve OBS onlardan okur. Ek loopback maliyeti yok.

### DSP zinciri (sabit topoloji, bypass ile açma/kapama)

```
kanal:  giriş ─▶ gate ─▶ eq ─▶ comp ─▶ limiter ─▶ çıkış
mic:    giriş ─▶ deepfilter ─▶ gate ─▶ eq ─▶ comp ─▶ limiter ─▶ çıkış
```

| Aşama | Eklenti | Bypass |
|---|---|---|
| DeepFilterNet | LADSPA `libdeep_filter_ladspa.so` (`deep_filter_mono`/`deep_filter_stereo`) | attenuation = 0 |
| Gate | `http://lsp-plug.in/plugins/lv2/gate_stereo` | `enabled` = 0 |
| EQ | `http://lsp-plug.in/plugins/lv2/para_equalizer_x16_stereo` | `enabled` = 0 |
| Compressor | `http://lsp-plug.in/plugins/lv2/compressor_stereo` | `enabled` = 0 |
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

### Canlı parametre yazımı

```bash
pw-cli s <node-id> Props '{ params = [ "eq:g_3" 4.5 ] }'   # EQ band 3 → +4.5 dB
wpctl set-volume <loopback-node-id> 0.72                    # fader
pactl move-sink-input <stream-id> <yeni-cihaz>              # cihaz değişimi (kesintisiz)
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
| `pw-cli set-param` LSP LV2 portlarında çalışmazsa | **Faz 2'nin ilk işi bunu doğrulamak.** Yedek: PipeWire `builtin` `bq_*` biquad node'ları + `builtin noisegate` + Zam LADSPA |
| Yapısal değişikte ~200 ms kesinti | Kullanıcı tetikli ve nadir. Cihaz değişimi `move-sink-input` ile kesintisiz |
| Fader sürüklerken `pw-cli` süreç fırtınası | 20 ms debounce + toplu yazım; gerekirse kalıcı `pw-cli` oturumu |
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
