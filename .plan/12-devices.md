# Faz 12 — Sanal cihaz düzeni

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 2, Faz 3, Faz 6
**Çıktı:** `src/sonar/core/model.py`, `src/sonar/core/config.py`,
`src/sonar/engine/confgen.py`, `src/sonar/engine/control.py`,
`src/sonar/engine/supervisor.py`, `src/sonar/engine/meters.py`

---

## Amaç

Kullanıcının ilk testinde çıkan iki cihaz sorununu bitirmek:

1. **Her çıkış kanalı için sahte bir mikrofon oluşuyor.** `sonar_media_fx`,
   `sonar_game_fx`, `sonar_chat_fx`, `sonar_aux_fx` — hepsi `Audio/Source`.
   Media kanalının mikrofonla ilgisi yok ama Discord'un mikrofon listesinde görünüyor.
2. **Cihaz adları yönü belirtmiyor.** "Sonar Media" bir sink mi, source mu belli değil.

Kullanıcı kararı: SteelSeries GG'de de yalnızca Stream Mix vardı, OBS'e o ekleniyordu.
Kanal başına ayrı OBS kaynağı **varsayılan olarak kapalı**, kanal ayarında opsiyonel
bir anahtar olarak kalır. (Avantajı: OBS'te kanal başına ayrı track → kayıttan sonra
oyun sesini kısıp Discord'u bırakabilmek. EQ ile ilgisi yok, EQ zaten kanal başına.)

---

## Ölçülen mevcut durum

`pactl list short sources` (daemon açıkken, 2026-09-01):

```
782  sonar_chat_fx      ← sahte mikrofon
784  sonar_media_fx     ← sahte mikrofon
786  sonar_aux_fx       ← sahte mikrofon
810  sonar_game_fx      ← sahte mikrofon
790  sonar_stream_out   ← doğru: OBS kaynağı
808  sonar_mic          ← doğru
812  sonar_stream_mic   ← doğru
```

Fiziksel sink'te olup bizim sanal sink'lerimizde **olmayan** alanlar
(`pw-dump` karşılaştırması): `priority.session`, `device.icon-name`, `node.nick`.
Kullanıcı sanal cihazları Sistem Ayarları'nda görüyor ama **görev çubuğu ses
uygletinde** görmüyor; eksik alanlar bunun en olası sebebi.

---

## Yaklaşım

### Model

`Channel`'a iki alan:

| Alan | Varsayılan | Anlamı |
|---|---|---|
| `direction` | `"output"` | Kanal çıkış mı giriş mi (Faz 13 giriş kanallarını ekliyor) |
| `stream_source` | `False` | OBS için ayrı sanal giriş cihazı üret |

Şema sürümü **2**; `core/config.py` migrasyonu eski config'lere bu alanları ekler.

### Graf

`stream_source` **kapalıyken** `_fx` node'u cihaz listesinde görünmemeli ama
loopback'lerin ondan okuyabilmesi gerek. Yaklaşım:

- `_fx` playback props'undan `media.class` ve `priority.session` düşer,
  `node.autoconnect = false` girer → artık bir cihaz değil.
- Gönderi loopback'lerinin `capture.props` kısmından `target.object` çıkar,
  `node.autoconnect = false` girer.
- Bağlantıları **daemon açıkça kurar**: `engine/control.py::link_ports()` →
  `pw-link "sonar_<id>_fx:output_FL" "sonar_<id>_to_personal_capture:input_FL"` vb.
  `supervisor`, `_wait_for_graph()` bittikten sonra tüm gönderileri bağlar ve
  `pw-link -l` çıktısıyla doğrular; eksik varsa bir kez tekrar dener.

`stream_source` **açıkken** bugünkü davranış: `media.class = Audio/Source`,
`priority.session = 0`, adı `Sonar <Ad> — Stream Source (Virtual Input)`.
Bağlantılar yine açıkça kurulur — tek kod yolu.

### Adlandırma (İngilizce, yön belirtir)

| Node | `node.description` |
|---|---|
| `sonar_<kanal>` | `Sonar <Ad> — Virtual Output` |
| `sonar_<kanal>_fx` (açıkken) | `Sonar <Ad> — Stream Source (Virtual Input)` |
| `sonar_personal` | `Sonar Personal Mix — Virtual Output` |
| `sonar_stream` | `Sonar Stream Mix — Virtual Output` |
| `sonar_stream_out` | `Sonar Stream Mix — Virtual Input` |
| `sonar_<mic>` | `Sonar <Ad> — Virtual Input` |

Ek props: `node.nick` (kısa ad), `device.icon-name`
(`audio-card` / `audio-input-microphone`), `priority.session` (sink 500, kaynak 0).

### Metreler

Metre kaynağı `sonar_<id>_fx` yerine **kanal sink monitörü** `sonar_<id>` olur.
`_fx` artık bir akış olabildiği için `pw-cat` ondan yakalayamaz; monitör her iki
modda da çalışır. Ölçüm DSP **öncesidir** — uygulamanın çaldığı seviyeyi gösterir,
fader/EQ'dan etkilenmez. Bu davranış dokümana yazılır.

---

## Görevler

- [x] `Channel.stream_source` alanı (`direction` gerekmedi — aşağıya bak)
- [x] `confgen`: `_fx` node'u iki modlu (`media.class` var / yok)
- [x] `confgen`: loopback `capture.props` → `target.object` yerine `autoconnect=false`
- [x] `confgen`: İngilizce, yön belirten `node.description` tablosu
- [x] `confgen`: `node.nick`, `device.icon-name`, `priority.session`
- [x] `control.link_nodes()` + `node_links()` + saf `parse_links()`
- [x] `supervisor`: graf ayağa kalkınca gönderileri bağla, doğrula, bir kez yeniden dene
- [x] `meters.meter_sources()` → kanal sink monitörleri
- [x] Altın dosya (`tests/test_confgen.py`) yeniden üretilir
- [x] Ölçüm: `pw-link -l`, `pactl list short sources`, PipeWire restart dayanıklılığı

---

## Ölçüm (2026-09-01, gerçek grafta)

**Cihaz listesi temiz.** `pactl list short sources`'ta artık yalnızca gerçekten giriş
olması gerekenler var:

```
sonar_stream_out    Sonar Stream Mix — Virtual Input
sonar_mic           Sonar Mic — Virtual Input
sonar_stream_mic    Sonar Stream Mic — Virtual Input
```

Dört sahte mikrofon (`sonar_game_fx`, `sonar_chat_fx`, `sonar_media_fx`,
`sonar_aux_fx`) kayboldu. (`*.monitor` girdileri kaldı; her sink'in monitörü olur,
fiziksel cihazlarda da vardır, kaçınılmaz.)

**`pw-link` tutuyor.** `media.class` taşımayan bir filter-chain çıkışına elle
bağlantı kuruldu ve kaldı. Port adları moda göre değişiyor — bu yüzden `pw-link`'e
port değil node adı veriliyor:

| mod | `_fx` çıkış portları |
|---|---|
| `stream_source` kapalı | `sonar_game_fx:output_FL` / `output_FR` |
| `stream_source` açık | `sonar_game_fx:capture_FL` / `capture_FR` |

**Sinyal yolu birebir şeffaf.** 440 Hz, 0.2 genlik (-13.98 dBFS) sinüs
`sonar_game`'e enjekte edildi, `sonar_personal` monitöründen okundu:

| nokta | seviye |
|---|---|
| `sonar_game` (kanal girişi) | **-13.98 dBFS** |
| `sonar_personal` (bus girişi) | **-13.98 dBFS** |
| `stream_source` açıkken aynı ölçüm | **-13.98 dBFS** |

Kazanç yok, kayıp yok. L/R ayrı frekans (440/660 Hz) testinde kanal sızıntısı
-139 dB, yani yok.

> Ölçüm sırasında yakalanan tuzak: `pw-cat --record --target <sink>` bir sink'in
> monitörünü **yakalamıyor**, `-P stream.capture.sink=true` şart. Bu olmadan üç ölçüm
> üst üste "-180 dBFS, sessiz" verdi ve graf bozuk sanıldı. `meters.py` bunu zaten
> doğru yapıyordu.

**PipeWire yeniden başlatma dayanıklılığı** (aşağıya bak): `systemctl --user restart
pipewire pipewire-pulse wireplumber` sonrası **6 saniyede** 6 sink ve 16 gönderi
bağlantısı geri geldi, sinyal yine -13.98 dBFS.

**Görev çubuğu ses uygleti:** `node.nick`, `device.icon-name` ve `priority.session`
eklendi; sonucu kullanıcı ikinci testte doğrulayacak.

---

## Risk / yedek yol

**Gerçekleşmedi.** Elle `pw-link` bağlantıları sorunsuz kuruldu ve kaldı; yedek yola
(`_fx`'i `Audio/Source` olarak bırakmak) gerek olmadı.

---

## Yol boyunca yakalananlar

**`direction` alanı gerekmedi.** Plan `Channel.direction` diyordu ama giriş kanalları
`MicChain` ile temsil ediliyor; `Channel` her zaman bir çıkış olurdu. Her satırı
`"output"` olan bir alan eklemek yerine yapısal ayrım korundu — arayüz zaten
`channel_rows()`'un ürettiği `kind` alanını ("channel" / "mic" / "bus") kullanıyor.
Şema sürümü de bu yüzden 1'de kaldı; `stream_source` varsayılanlı yeni bir alan,
eski config'ler olduğu gibi okunuyor.

**`priority.session` sink'lerde de 0.** Plan sink'ler için 500 diyordu. Fiziksel
kulaklık çıkarıldığında WirePlumber `sonar_personal`'ı varsayılan sink seçebilir ve
o zaman personal bus kendi çıkışını kendine besler. 0 bunu imkânsız kılıyor;
varsayılanı devralmak isteyen `settings.take_over_default_sink` bunu zaten açıkça
`pw-metadata` ile yapıyor.

**PipeWire yeniden başlatınca graf geri gelmiyordu** — Faz 10'da "denenmemiş
senaryo" olarak bırakılmıştı, burada denendi ve gerçekten kırıktı. `systemctl --user
restart pipewire` bizim `pipewire -c graph.conf` istemcimizi **öldürmüyor**, yalnızca
bağlantısını koparıyor. Süreç canlı göründüğü için gözcü (`_watch`) `process.wait()`
üzerinde bekliyor ve hiçbir şey olmuyordu; ölçüldü: 15 saniye sonra hâlâ 0 sonar
node'u. Gözcü artık süreç ölümünü **ve** "beklenen node'ların hiçbiri grafta yok"
durumunu birlikte yokluyor (`_await_trouble`, 2 sn aralık, üst üste iki boş ölçüm).
Toparlanma süresi ölçüldü: **6 saniye**.

**Metre ölçüm noktası değişti.** `_fx` artık bir cihaz olmadığı için `pw-cat` ondan
yakalayamıyor; kanal metreleri sink monitöründen okunuyor. Pratik farkı, metrenin
DSP ve fader **öncesi** seviyeyi göstermesi.
