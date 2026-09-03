# Faz 30 — DSP: crossfeed, Boost ayrımı, mikrofon zinciri

**Durum:** 🟢 Tamamlandı
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

- [x] `FilterStage.SPATIAL` bloğu `sofa` yerine `builtin` `delay` + `bq_lowpass` +
      `mixer` ile kurulsun. Hepsi PipeWire'ın kendi eklentileri, kurulum gerektirmiyor.
- [x] **Yapısal olmaktan çıksın:** blok her zaman kurulu, bypass sızıntı kazancını 0
      yapmak — yani bit-şeffaf ve grafi yeniden kurmuyor. `Channel.spatial` /
      `MasterBus.spatial` alanları ve `SetSpatial` D-Bus metodu kalksın; aşama diğerleri
      gibi profilde `enabled` olsun.
- [x] Kullanıcı kontrolleri SteelSeries'e göre yeniden adlandırılsın:
      **Performans ↔ Sürükleyicilik** (sızıntı miktarı, 0–100) ve **Mesafe**
      (gecikme + alçak geçiren kesim, 0–100). Ham azimut/yükseklik kaybolsun.
- [x] `registry` içindeki SOFA/HRTF keşfi (`hrtf_file`, `sofa_available`) ve ilgili
      testler kaldırılsın.
- [x] `docs/` ve `README` "gerçek surround değil, stereo genişletme" desin.

### Volume Boost ayrı panel

- [x] Spatial panelinin içinden çıkarılıp kendi `SonarFilterPanel`'ine alınsın
      (kullanıcı isteği). Zincirdeki yeri değişmiyor: limiter'dan önce.

### Mikrofon zincirinde Compressor ve Limiter ayrılsın

- [x] Bugün mikrofon FX'inde tek panelde "Compressor + Limiter" var ama zincirde ikisi
      ayrı aşama. Panel ikiye bölünsün; mikrofonda da çıkıştaki gibi Gate / Compressor /
      Limiter / Boost dizilsin.

**Ölçüm:** crossfeed kapalıyken çıkış girişe bit-eş; açıkken sol-tek sinyalin sağ kanalda
ölçülebilir bir kopyası oluşuyor ve gecikme "Mesafe" ile artıyor. Açık/kapalı CPU farkı
ölçülüp `docs/PERFORMANCE.md`'ye yazılsın (hedef: ölçüm gürültüsünün içinde).


---

## Uygulanan hâli

Spatial Audio artık **crossfeed**: `copy` → `delay` → `bq_lowpass` → `mixer`, hepsi
PipeWire'ın kendi `builtin` blokları. Sol kanalın sesi biraz geç ve tizleri kısılmış
hâlde sağ kulağa da gidiyor — gerçek hoparlörlerde olan, kulaklıkta hiç olmayan şey.

Aşama **yapısal olmaktan çıktı**: blok her zaman kurulu, bypass sızıntı kazancını 0
yapmak. `Channel.spatial`, `MasterBus.spatial`, `SetSpatial`, `sonar-cli spatial` ve
`registry`'deki SOFA/HRTF keşfi kalktı.

Kullanıcı kontrolleri SteelSeries'e göre: **Sürükleyicilik** (0–100, sızıntı miktarı ve
yumuşaklığı) ve **Mesafe** (0–100, kulaklar arası gecikme).

Volume Boost kendi paneline alındı; mikrofon zincirinde Compressor ve Limiter ayrıldı.
FX sayfasındaki panel satırı `Flow` oldu: sığdığı kadar yan yana, sığmayınca alt satıra.

## Ölçümler (canlı graf, 2026-09-04)

| Ölçüm | Sonuç |
|---|---|
| Kapalıyken | L=-17.0 dBFS, R=**-240 dBFS** — bit-şeffaf |
| Performans ucu (0/0) | sızıntı **-18.4 dB**, gecikme **0.29 ms** |
| Sürükleyicilik ucu (100/100) | sızıntı **-5.1 dB**, gecikme **1.15 ms** |
| CPU — bloklar grafta yokken vs varken, boşta | %9.8 → **%10.2** |
| CPU — bloklar grafta yokken vs varken, ses akarken | %10.2 → **%12.0** |
| CPU — aynı grafta yalnızca aç/kapa | %14.0 · %13.8 (gürültünün içinde) |

Yani crossfeed'in bedeli altı zincir için tek çekirdeğin **~%1.8'i**. Kıyas için HRTF
sürümü boşta **+%14.4** yiyordu ve açıp kapatmak grafı yeniden kurmayı gerektiriyordu.

> **Ölçüm hatası ve düzeltmesi:** ilk turda `pgrep -f "pipewire -c ..."` `timeout`
> sarmalayıcısını yakaladı ve her şey %0.0 okundu. Yukarıdaki sayılar `pipewire`
> sürecinin kendi PID'iyle yeniden ölçüldü. Aynı hatanın etkilediği tek yer buydu;
> daemon'ın kendi grafındaki ölçümler doğru PID'i kullanıyordu.

## Yol boyunca yakalananlar

**Eski profiller yeni parametreleri reddediyordu.** Diskteki profiller Spatial'ın HRTF
dönemindeki anahtarlarını (`width_deg`, `elevation_deg`, `distance_m`) taşıyordu ve
`api.set_filter_param` doğrulamayı **depolanan** sözlüğe yapıyordu; `immersion`
"böyle bir parametre yok" diye reddediliyordu. İki düzeltme: doğrulama artık
`DEFAULT_FILTER_PARAMS` tanımına bakıyor, ve `ConfigStore.load_profile` her aşamanın
parametrelerini tanıma göre normalleştiriyor (fazlası düşer, eksiği varsayılanla dolar).
Bu, ileride herhangi bir aşamanın parametre seti değişirse de çalışacak.
