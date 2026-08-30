# Faz 2 — graph.conf üreteci

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 1
**Çıktı:** `src/sonar/core/dsp/chain.py`, `src/sonar/engine/confgen.py`, `tests/test_confgen.py`

---

## Amaç

`SonarConfig` nesnesinden, `pipewire -c` ile çalıştırılabilir tam bir `graph.conf` üretmek.
Bu conf tüm sanal cihazları, DSP zincirlerini ve loopback'leri tanımlar.

---

## ⚠️ İlk iş: canlı parametre doğrulaması

Plandaki en büyük risk burada. Kod yazmadan **önce** elle doğrulanacak:

```bash
# minimal bir filter-chain conf'u elle yaz, tek LSP para_equalizer ile
pipewire -c /tmp/probe.conf &
pw-dump | grep -A5 sonar_probe          # node id'sini bul
pw-cli s <id> Props '{ params = [ "eq:g_3" 6.0 ] }'
# müzik çalarken duyulabilir bir değişiklik olmalı, ses kesintisi OLMAMALI
```

- [ ] LSP `para_equalizer` kazanç portu canlı değişiyor mu?
- [ ] `enabled` portu canlı bypass yapıyor mu?
- [ ] LSP `gate` / `compressor` / `limiter` portları canlı değişiyor mu?
- [ ] DeepFilterNet LADSPA filter-chain içinde yükleniyor mu? Attenuation portu canlı mı?
- [ ] Değer yazımı sırasında tık/pop sesi var mı?

**Başarısızsa yedek plan:** PipeWire `builtin` `bq_*` biquad node'larıyla kendi EQ'muzu kurarız
(canlı parametre desteği belgelenmiş), dinamikler için `builtin noisegate` + Zam LADSPA.
`registry.py` bunu bir "backend" seçimi olarak soyutlar; plan ayakta kalır.

---

## Görevler

### `core/dsp/chain.py` — zincir şablonu
- [ ] `build_graph(stages, channels=2) -> dict` — verilen aşama listesinden
      PipeWire `filter.graph` sözlüğü üretir: `nodes`, `links`, `inputs`, `outputs`
- [ ] Aşama adları sabit ve öngörülebilir: `df`, `gate`, `eq`, `comp`, `lim`
      → parametre anahtarları `"eq:g_3"`, `"gate:at"` gibi kararlı olur
- [ ] Stereo/mono varyant seçimi (mikrofon mono kaynaksa mono eklentiler)
- [ ] Kurulu olmayan eklenti aşaması zincirden atlanır, linkler buna göre yeniden bağlanır

### `engine/confgen.py` — conf üreteci
- [ ] `generate(cfg: SonarConfig) -> str`
- [ ] **Kanal bölümü** — her kanal için bir `libpipewire-module-filter-chain`:
  - `capture.props`: `node.name = sonar_<id>`, `media.class = Audio/Sink`, `audio.channels = 2`,
    `audio.position = [FL FR]`, `node.description = "Sonar <Ad>"`
  - `playback.props`: `node.name = sonar_<id>_fx`, `media.class = Audio/Source/Virtual`,
    `node.description = "Sonar <Ad> (FX)"`
- [ ] **Bus bölümü** — `sonar_personal` ve `sonar_stream`:
  - `capture.props`: `media.class = Audio/Sink` (uygulamalar doğrudan da hedefleyebilsin)
  - `playback.props`: fiziksel cihaza bağlanan akış (`target.object`), master EQ + limiter zinciriyle
  - `sonar_stream`'in monitörü OBS tarafından yakalanır
- [ ] **Loopback bölümü** — kanal başına 2 adet `libpipewire-module-loopback`:
  - `capture.props`: `target.object = sonar_<id>_fx`, `stream.capture.sink = false`
  - `playback.props`: `target.object = sonar_personal` veya `sonar_stream`
  - `node.name = sonar_<id>_to_personal` / `_to_stream` → fader bu node'a `wpctl set-volume` ile uygulanır
- [ ] **Mikrofon bölümü** — `sonar_mic` ve `sonar_stream_mic` filter-chain'leri:
  - `capture.props`: `target.object = <fiziksel mic>`
  - `playback.props`: `media.class = Audio/Source/Virtual`
  - `share_chain_with_mic = true` ise tek zincir + loopback ile ikinci sanal kaynak
- [ ] **Opsiyonel loopback'ler** — sidetone (`sonar_mic` → `sonar_personal`), mic → `sonar_stream`
      (ikisi de varsayılan **kapalı**)
- [ ] Global: `audio.rate = 48000` her yerde sabit (DeepFilterNet zorunluluğu)
- [ ] **Deterministik çıktı**: aynı `SonarConfig` → byte-eşdeğer metin.
      Sıralama sabit, kayan nokta biçimi sabit. Reconcile'ın "yeniden inşa gerekli mi" kararı buna dayanır
- [ ] Conf metnindeki parametre değerleri **başlangıç değerleri**dir; sonrası canlı yazımla yönetilir.
      → Sadece profil değişikliği conf'u değiştirmemeli (aksi hâlde her EQ tweak'i restart tetikler).
      **Karar: conf'a nötr/varsayılan değerler yazılır; gerçek değerler açılışta canlı yazımla uygulanır.**
- [ ] `python -m sonar.engine.confgen` — stdout'a conf basan CLI (hata ayıklama için)

### Testler
- [ ] `test_confgen.py` — altın dosya (golden file) karşılaştırması
- [ ] Determinizm testi: aynı config'i 2 kez üret → eşit
- [ ] Kanal ekleme/silme → conf değişiyor; profil değiştirme → conf **değişmiyor** (kritik)
- [ ] Eksik eklenti senaryosu: DeepFilterNet yoksa mic zinciri onsuz kuruluyor

---

## Manuel doğrulama

```bash
python -m sonar.engine.confgen > /tmp/graph.conf
pipewire -c /tmp/graph.conf &
pw-dump | jq -r '.[] | select(.info.props["node.name"] // "" | startswith("sonar")) | .info.props["node.name"]'
qpwgraph      # bağlantıları gözle doğrula
```

**Beklenen node'lar:**
`sonar_game`, `sonar_game_fx`, `sonar_chat`, `sonar_chat_fx`, `sonar_media`, `sonar_media_fx`,
`sonar_aux`, `sonar_aux_fx`, `sonar_personal`, `sonar_stream`, `sonar_mic`, `sonar_stream_mic`,
ve `sonar_*_to_personal` / `sonar_*_to_stream` loopback'leri.

**Ses testi:** `pactl` ile bir uygulamayı `sonar_game`'e taşı → kulaklıkta duyulmalı;
`sonar_stream` monitörünü `pw-cat --record` ile kaydet → aynı ses orada da olmalı.

---

## Tamamlanma kriteri

Graf elle çalıştırıldığında tüm sanal cihazlar görünüyor, ses kulaklığa ve stream miksine
akıyor, `pw-cli s ... Props` ile EQ canlı değişiyor.
