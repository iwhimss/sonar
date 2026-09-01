# Faz 12 — Sanal cihaz düzeni

**Durum:** ⚪ Bekliyor
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

- [ ] `Channel.direction` ve `Channel.stream_source` alanları
- [ ] Şema 2 migrasyonu + `test_config.py` yuvarlak yolculuk testi
- [ ] `confgen`: `_fx` node'u iki modlu (`media.class` var / yok)
- [ ] `confgen`: loopback `capture.props` → `target.object` yerine `autoconnect=false`
- [ ] `confgen`: İngilizce, yön belirten `node.description` tablosu
- [ ] `confgen`: `node.nick`, `device.icon-name`, `priority.session`
- [ ] `control.link_ports()` + `list_links()` (`pw-link`, `pw-link -l`)
- [ ] `supervisor`: graf ayağa kalkınca gönderileri bağla, doğrula, bir kez yeniden dene
- [ ] `meters.meter_sources()` → kanal sink monitörleri
- [ ] Altın dosya (`tests/test_confgen.py`) yeniden üretilir
- [ ] Ölçüm: `pw-link -l`, `pactl list short sources`, PipeWire restart dayanıklılığı

---

## Ölçüm

Faz bitince buraya yazılacak:

- `pw-link -l | grep sonar_.*_to_` → beklenen bağlantı sayısı
- `pactl list short sources | grep _fx` → boş olmalı
- `systemctl --user restart pipewire` sonrası bağlantıların kendini toparlaması
- Görev çubuğu ses uygletinde sanal sink'lerin görünüp görünmediği

---

## Risk / yedek yol

Elle `pw-link` bağlantıları tutmazsa (WirePlumber `media.class`'sız node'a link
kurmayı reddedebilir): `_fx` `Audio/Source` olarak kalır ve `stream_source` anahtarı
yalnızca adı ve `priority.session` değerini etkiler. Bu durumda kullanıcıya
"cihaz listesinde görünmeye devam ediyor, sebebi şu" diye açıkça söylenir ve
README'ye yazılır.

---

## Yol boyunca yakalananlar

_(faz sırasında doldurulacak)_
