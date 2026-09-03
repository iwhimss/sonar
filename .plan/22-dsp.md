# Faz 22 — Spatial Audio, Volume Boost, Smart Volume

**Durum:** ⚪ Bekliyor
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

- [ ] `StageGraph` kavramı: node listesi + iç linkler + dışarıya açılan giriş/çıkış
      portları. Doğrusal aşamalar bunun tek node'lu özel hâli olur.
- [ ] `registry.PluginKind` iki değer kazanır: `BUILTIN`, `SOFA`.
- [ ] Mevcut altın conf testleri bozulmamalı (tek node'lu yol byte-eşdeğer kalmalı).

---

## 1. Volume Boost

- [ ] `FilterStage.BOOST` — PipeWire `builtin` `linear` eklentisi (`Mult` kontrolü).
- [ ] Zincirde **limiter'ın öncesine** yerleşir; böylece boost kırpma üretmez.
- [ ] 0…+12 dB, varsayılan 0 dB ve kapalı. Bypass = `Mult 1.0` → conf değişmez.
- [ ] Profilde saklanır; kanal, çıkış bus'ı ve mikrofon için ayrı.
- [ ] Ölçüm: +6 dB → çıkışta tam +6.0 dB (limiter kapalıyken).

## 2. Spatial Audio

- [ ] `FilterStage.SPATIAL` — SOFA `spatializer`.
- [ ] Alt graf: `copy` ile L/R ayrılır → iki `spatializer` (`Azimuth ±width`,
      `Elevation`, `Radius`) → `mixer` ile binaural toplanır.
- [ ] HRTF dosyası `/usr/share/libmysofa/default.sofa`; yoksa aşama zincirden düşer
      (mevcut "eklenti kurulu değil" yolu aynen çalışır).
- [ ] Kontroller: açık/kapalı, **genişlik** (azimut 0…60°, varsayılan 30°),
      **yükseklik** (−20…+20°), **mesafe**.
- [ ] Yalnızca çıkış zincirlerinde (kanal + çıkış bus'ı); mikrofonda anlamsız.
- [ ] Ölçüm: kapalıyken sinyal bit-eş geçiyor; açıkken L-only sinyalin sağ kanalda
      ölçülebilir bir kopyası (ITD/ILD) oluşuyor.
- [ ] Gerçek 7.1 sanal surround `.plan/99-backlog.md`'ye yazılır.

## 3. Smart Volume (ducking)

DSP değil, **daemon tarafında bir kontrol döngüsü**. Metre altyapısı (20 Hz,
`engine/meters.py`) zaten her kanalın seviyesini veriyor.

- [ ] Yeni `engine/ducking.py`: saf bir zarf hesabı (`DuckState.step(levels, dt)` →
      kanal başına kazanç) + onu `Control.set_volume`'a bağlayan ince bir sürücü.
- [ ] Ayarlar: açık/kapalı, tetikleyici kanal(lar) (varsayılan Chat), hedef kanal(lar),
      indirim (dB, varsayılan −12), eşik (dB, varsayılan −40), attack (ms), hold (ms),
      release (ms).
- [ ] ChatMix çarpanıyla **çarpılarak** birleşir; `live_volumes` tek toplanma noktası
      olduğu için çakışma olmaz.
- [ ] Ducking aktifken kanal fader'ının altında rozet (ChatMix rozetiyle aynı desen).
- [ ] Ducking açıkken metre aboneliğini daemon kendisi tutar (GUI kapalıyken de çalışsın).
- [ ] Ölçüm: Chat'e ton verilince Media'nın seviyesi ayarlanan dB kadar düşüyor,
      bırakınca release süresinde geri dönüyor — kayıt alınıp zarf çıkarılacak.

## Arayüz

- [ ] FX sayfasında Spatial ve Boost birer `SonarFilterPanel`.
- [ ] Smart Volume kanal profilinin değil **ayarların** parçası → Master şeridinde
      kendi küçük paneli.

---

## Kabul ölçütü

- [ ] Boost +6 dB → +6.0 dB ölçüldü
- [ ] Spatial kapalıyken unity, açıkken binaural fark ölçüldü
- [ ] Ducking zarfı ölçüldü ve ayarlanan değerlerle örtüşüyor
- [ ] Üçü de kapalıyken conf metni ve CPU tüketimi bugünküyle aynı
