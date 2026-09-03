# Faz 22 — Spatial Audio, Volume Boost, Smart Volume

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 20 (bus modeli), Faz 6 (metreler — ducking bunları kullanır)
**Çıktı:** `src/sonar/core/dsp/{chain,registry,params}.py`, `core/model.py`,
yeni `src/sonar/engine/ducking.py`, `gui/qml/ChannelFx.qml`, `MasterStrip.qml`

---

## Amaç

SteelSeries GG'de olup bizde olmayan üç özellik. Kullanıcı kararı: **Spatial Audio
stereo binaural genişletme** olarak yapılacak (gerçek 7.1 sanal surround backlog'a).

---

## Ölçülmüş ön koşullar

Bu oturumda doğrulandı:

* `/usr/lib/spa-0.2/filter-graph/libspa-filter-graph-plugin-sofa.so` **kurulu**
* `/usr/share/libmysofa/default.sofa` ve `MIT_KEMAR_normal_pinna.sofa` **mevcut**
* PipeWire 1.6.8 `builtin` filter-graph eklentileri (`copy`, `mixer`, `linear`) mevcut

---

## Zincir altyapısı (önce bu)

`core/dsp/chain.build_chain` bugün yalnızca doğrusal 2-in/2-out aşama dizisi kurabiliyor
(`pairwise` ile ardışık bağlama). Spatial bir aşamanın **birden çok node'dan oluşan bir
alt graf** olmasını gerektiriyor.

- [x] `StageGraph` kavramı: node listesi + iç linkler + dışarıya açılan giriş/çıkış
      portları. Doğrusal aşamalar bunun tek node'lu özel hâli olur.
- [x] `registry.PluginKind` iki değer kazanır: `BUILTIN`, `SOFA`.
- [x] Mevcut altın conf testleri bozulmamalı (tek node'lu yol byte-eşdeğer kalmalı).

---

## 1. Volume Boost

- [x] `FilterStage.BOOST` — PipeWire `builtin` `linear` eklentisi (`Mult` kontrolü).
- [x] Zincirde **limiter'ın öncesine** yerleşir; böylece boost kırpma üretmez.
- [x] 0…+12 dB, varsayılan 0 dB ve kapalı. Bypass = `Mult 1.0` → conf değişmez.
- [x] Profilde saklanır; kanal, çıkış bus'ı ve mikrofon için ayrı.
- [x] Ölçüm: +6 dB → çıkışta tam +6.0 dB (limiter kapalıyken).

## 2. Spatial Audio

- [x] `FilterStage.SPATIAL` — SOFA `spatializer`.
- [x] Alt graf: `copy` ile L/R ayrılır → iki `spatializer` (`Azimuth ±width`,
      `Elevation`, `Radius`) → `mixer` ile binaural toplanır.
- [x] HRTF dosyası `/usr/share/libmysofa/default.sofa`; yoksa aşama zincirden düşer
      (mevcut "eklenti kurulu değil" yolu aynen çalışır).
- [x] Kontroller: açık/kapalı, **genişlik** (azimut 0…60°, varsayılan 30°),
      **yükseklik** (−20…+20°), **mesafe**.
- [x] Yalnızca çıkış zincirlerinde (kanal + çıkış bus'ı); mikrofonda anlamsız.
- [x] Ölçüm: kapalıyken sinyal bit-eş geçiyor; açıkken L-only sinyalin sağ kanalda
      ölçülebilir bir kopyası (ITD/ILD) oluşuyor.
- [x] Gerçek 7.1 sanal surround `.plan/99-backlog.md`'ye yazılır.

## 3. Smart Volume (ducking)

DSP değil, **daemon tarafında bir kontrol döngüsü**. Metre altyapısı (20 Hz,
`engine/meters.py`) zaten her kanalın seviyesini veriyor.

- [x] Yeni `engine/ducking.py`: saf bir zarf hesabı (`DuckState.step(levels, dt)` →
      kanal başına kazanç) + onu `Control.set_volume`'a bağlayan ince bir sürücü.
- [x] Ayarlar: açık/kapalı, tetikleyici kanal(lar) (varsayılan Chat), hedef kanal(lar),
      indirim (dB, varsayılan −12), eşik (dB, varsayılan −40), attack (ms), hold (ms),
      release (ms).
- [x] ChatMix çarpanıyla **çarpılarak** birleşir; `live_volumes` tek toplanma noktası
      olduğu için çakışma olmaz.
- [x] Ducking aktifken kanal fader'ının altında rozet (ChatMix rozetiyle aynı desen).
- [x] Ducking açıkken metre aboneliğini daemon kendisi tutar (GUI kapalıyken de çalışsın).
- [x] Ölçüm: Chat'e ton verilince Media'nın seviyesi ayarlanan dB kadar düşüyor,
      bırakınca release süresinde geri dönüyor — kayıt alınıp zarf çıkarılacak.

## Arayüz

- [x] FX sayfasında Spatial ve Boost birer `SonarFilterPanel`.
- [x] Smart Volume kanal profilinin değil **ayarların** parçası → Master şeridinde
      kendi küçük paneli.

---

## Kabul ölçütü

- [x] Boost +6 dB → +6.0 dB ölçüldü
- [x] Spatial kapalıyken unity, açıkken binaural fark ölçüldü
- [x] Ducking zarfı ölçüldü ve ayarlanan değerlerle örtüşüyor
- [x] Üçü de kapalıyken conf metni ve CPU tüketimi bugünküyle aynı


---

## Uygulanan hâli

`chain.build_chain` artık **`StageBlock`** üzerinden çalışıyor: bir aşama bir ya da
birden çok node olabiliyor, kendi iç linklerini taşıyor ve dışarıya kanal başına tek bir
port çifti açıyor. Tek node'lu aşamalar bunun özel hâli; link sırası eski `pairwise`
düzeniyle birebir aynı tutuldu, böylece mevcut zincirler byte olarak değişmedi.

`registry.PluginKind` iki değer kazandı: `BUILTIN` (PipeWire'ın kendi `linear`, `mixer`
eklentileri) ve `SOFA`. `hrtf_file()` / `sofa_available()` HRTF dosyasını ve eklentiyi
arıyor; ikisi de yoksa Spatial aşaması zincirden düşüyor (mevcut "eklenti kurulu değil"
yolu).

### Sapma: Spatial **yapısal** oldu

Plan onu diğer aşamalar gibi bypass'lanabilir bir aşama olarak tarif ediyordu ve ilk
sürüm öyle yazıldı: kuru yol + karışım kazancıyla bit-şeffaf bypass. Sonra ölçüldü —
**bir HRTF konvolverini bypass etmek onu ucuzlatmıyor.** Altı zincirde:

| | boşta CPU |
|---|---|
| Spatial zincirde yok | **%0.0** |
| Spatial zincirde, bypass'ta | **%14.4** |

Bu yüzden Spatial, projedeki tek "aşamayı aç/kapa = grafı yeniden kur" istisnası oldu.
Açma/kapama profilde değil hedefin kendi ayarında (`Channel.spatial`, `MasterBus.spatial`)
— profilde olsaydı **profil değiştirmek grafı yeniden kurardı** ve Faz 2'nin değişmez
kuralı bozulurdu. Genişlik/yükseklik/mesafe profilde ve canlı.

Kuru yol da kalktı: blok altı node yerine dört (iki `spatializer`, iki `mixer`).

## Ölçümler (canlı graf, 2026-09-03)

| Ölçüm | Sonuç |
|---|---|
| Volume Boost +6 dB | çıkışta tam **+6.00 dB** |
| Boost ve Spatial kapalıyken | kazanç **0.00 dB**, sağ kanal **-240 dBFS** — bit-şeffaf |
| Spatial 30° | ILD **2.5 dB**, ITD **0.38 ms** |
| Spatial 60° | ILD **4.1 dB**, ITD **0.65 ms** — geniş açı, büyük fark (fizik böyle) |
| Spatial'ın kendi kazanç kaybı | **-7.8 dB** (HRTF normalizasyonu; Boost'un ondan sonra gelmesinin sebebi) |
| Spatial CPU (ses akarken, tek kanal) | **%17** → kapalıyken **%0** |
| Smart Volume zarfı | indirim **-12.1 dB** (ayar -12.0), atak ~200 ms, bırakma ~600 ms |

## Yol boyunca yakalananlar

**Bağlantı bekçisinin uyarıları arayüze hiç ulaşmıyormuş.** Zincire altı node eklenince
açılışta `pw-link` birkaç tur 255 döndü ve `path_broken` deltası tetiklendi — ama
loglarda `QObject::startTimer: Timers cannot be started from another thread` çıktı.
`_queue_delta` bir `QTimer` başlatıyor ve bu yalnızca Qt'nin iş parçacığında yasal;
bekçi ise kendi iş parçacığından yayınlıyordu. Faz 18'de eklenen bildirim yolu bu yüzden
sessizmiş. Delta artık `_ThreadBridge` üzerinden geçiyor.

**Yeniden inşadan sonra portlar geç beliriyor.** Node'lar doğmuş görünse de `pw-link`
birkaç yüz milisaniye 255 dönüyor. `reconcile_links(attempts=5)` yalnızca yeniden inşa
sonrasında kullanılıyor; açılışta artık tek bir uyarı bile çıkmıyor.

**PipeWire'ın azimut yönü ölçülerek bulundu:** `Azimuth = 330` verilen sol kanal sağ
kulakta daha yüksek çıktı, yani 0 = ön ve artan derece **sola**. İlk yazımda ters
konmuştu.
