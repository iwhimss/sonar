# Faz 30 — DSP: crossfeed, Boost ayrımı, mikrofon zinciri

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 26

---

### Spatial Audio → crossfeed (kullanıcı kararı)

HRTF ölçümü tasarımı çürüttü: iki konvolver ses akarken tek çekirdeğin **%17'sini**
yiyor ve bypass etmek ucuzlatmadığı için açıp kapatmak grafı yeniden kurmayı
gerektiriyordu. Yerine PipeWire'ın kendi ucuz bloklarıyla **kulaklar arası sızıntı**:

```
L ─┬──────────────────────────────────► mix_l  (doğrudan)
   └─► delay_lr ─► lowpass ─► gain ────► mix_r  (karşı kulağa sızıntı)
R ─┬──────────────────────────────────► mix_r
   └─► delay_rl ─► lowpass ─► gain ────► mix_l
```

- [ ] `FilterStage.SPATIAL` bloğu `sofa` yerine `builtin` `delay` + `bq_lowpass` +
      `mixer` ile kurulsun. Hepsi PipeWire'ın kendi eklentileri, kurulum gerektirmiyor.
- [ ] **Yapısal olmaktan çıksın:** blok her zaman kurulu, bypass sızıntı kazancını 0
      yapmak — yani bit-şeffaf ve grafi yeniden kurmuyor. `Channel.spatial` /
      `MasterBus.spatial` alanları ve `SetSpatial` D-Bus metodu kalksın; aşama diğerleri
      gibi profilde `enabled` olsun.
- [ ] Kullanıcı kontrolleri SteelSeries'e göre yeniden adlandırılsın:
      **Performans ↔ Sürükleyicilik** (sızıntı miktarı, 0–100) ve **Mesafe**
      (gecikme + alçak geçiren kesim, 0–100). Ham azimut/yükseklik kaybolsun.
- [ ] `registry` içindeki SOFA/HRTF keşfi (`hrtf_file`, `sofa_available`) ve ilgili
      testler kaldırılsın.
- [ ] `docs/` ve `README` "gerçek surround değil, stereo genişletme" desin.

### Volume Boost ayrı panel

- [ ] Spatial panelinin içinden çıkarılıp kendi `SonarFilterPanel`'ine alınsın
      (kullanıcı isteği). Zincirdeki yeri değişmiyor: limiter'dan önce.

### Mikrofon zincirinde Compressor ve Limiter ayrılsın

- [ ] Bugün mikrofon FX'inde tek panelde "Compressor + Limiter" var ama zincirde ikisi
      ayrı aşama. Panel ikiye bölünsün; mikrofonda da çıkıştaki gibi Gate / Compressor /
      Limiter / Boost dizilsin.

**Ölçüm:** crossfeed kapalıyken çıkış girişe bit-eş; açıkken sol-tek sinyalin sağ kanalda
ölçülebilir bir kopyası oluşuyor ve gecikme "Mesafe" ile artıyor. Açık/kapalı CPU farkı
ölçülüp `docs/PERFORMANCE.md`'ye yazılsın (hedef: ölçüm gürültüsünün içinde).
