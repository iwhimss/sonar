# Faz 43 — Efekt kataloğu

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 42
**Çıktı:** 9 yeni efekt (7 → 16), `core/dsp/effects.py`, `scripts/sonar-lv2-ports`

---

## Ne eklendi

| Efekt | Eklenti | Bypass yolu |
|---|---|---|
| Genişletici | `lsp expander_stereo` | `enabled = 0` |
| De-esser | `calf Deesser` | `bypass = 1` |
| Bas Zenginleştirici | `calf BassEnhancer` | `bypass = 1` |
| Exciter | `calf Exciter` | `bypass = 1` |
| Stereo Araçları | `calf StereoTools` | `bypass = 1` |
| Gecikme | `lsp comp_delay_stereo` | `enabled = 0` |
| Yankı | `calf Reverb` | `on = 0` |
| Gürlük Dengeleme | `lsp loud_comp_stereo` | `enabled = 0` |
| Maximizer | `ZaMaximX2` (LADSPA) | tavan 0 dB + kazanç 0 dB |

Mevcut yedi ile birlikte **16 efekt**. Bypass yolu her eklentide farklı ve yönü ters
çevirmek "kullanıcı efekti hiç açmadan sesin değişmesi" demek olurdu; `_STAGE_BYPASS`,
`_STAGE_ACTIVE` ve `_NO_ENABLED_PORT` bu üç deseni ayırıyor.

## Eklenmeyenler ve nedenleri

Kullanıcıya 19 efekt sözü verilmişti; dokuzu eklendi, dördü **bilinçli** olarak dışarıda:

* **Convolver** — IR dosyası bir **yol** parametresi ister; `EffectSlot.params` bugün
  yalnızca sayı tutuyor. Model değişikliği gerektiriyor, kendi fazını hak ediyor.
* **Çok bandlı kompresör / gate** — `sc_mb_compressor_stereo` **247** kontrol portu
  taşıyor ve anlamı band başına. Yalnızca global parametreleri açmak, ayarlanamayan bir
  kompresör vermek olurdu; doğrusu band başına arayüz, o da ayrı bir iş.
* **Auto Gain** — yan zincirle çalışıyor ve kullanıcının fader'ıyla çekişiyor. Bir
  mikserde "senin çektiğin fader'ı geri iten" bir efekt yanlış his verir.
* **Filtre** — LSP `filter_stereo` fiilen tek bandlı bir ekolayzer; 32 bandlık eğri
  editörümüzün yanında daha zayıf bir kopya olurdu.

Karşılığı olan eklentisi bulunmayanlar (Crystalizer, Pitch, RNNoise, Speex, Echo
Canceller) zaten kapsam dışıydı.

---

## Görevler

- [x] `scripts/sonar-lv2-ports` — TTL'den (ve LADSPA descriptor'ından) port tablosu çıkarır
- [x] Betiğin çıktısı mevcut `_GATE_PORTS` ile **birebir** eşleşiyor; katalog ve betik
      birbirini doğruluyor
- [x] `registry.py`'ye dokuz eklenti, port sınırları eklentilerin kendi tanımından
- [x] `model.py`: dokuz yeni `FilterStage`, `CHAIN_ORDER`, `DEFAULT_FILTER_PARAMS`
- [x] `params.py`: port eşlemeleri, üç ayrı bypass deseni, `_PERCENT` dönüşümü
- [x] `_PLUGIN_KEYS` tek kaynak — `chain._plugin_key` de onu okuyor
- [x] `core/dsp/effects.py`: kategoriler, arayüz aralıkları, birimler, ondalık sayısı.
      İçe aktarma anında katalog/model uyumunu doğruluyor
- [x] `list_effects` / `list_effect_kinds` parametre meta verisini de döndürüyor —
      arayüz her yeni efekt için QML yazmak zorunda değil
- [x] 75 çeviri anahtarı (efekt adları, parametre etiketleri, kategoriler, ipuçları)

---

## Ölçüm

Katalogdaki **16 efektin hepsi** bu makinede kurulu ve tek başına zincir kurabiliyor
(`test_every_effect_kind_builds_a_graph`, `test_every_effect_is_actually_installed`).
Her efektin conf'a **bypass'ta** doğduğu ayrıca sınanıyor.

Canlı grafta, `media` kanalına dokuz efekt birden eklendi (zincir: eq + 9):

```
conf → sonar_media ['eq','reverb','deesser','bass','exciter','stereo',
                    'delay','loudness','maximizer','expander']
440 Hz ton, zincirin girişi          : -24.7 dBFS
hepsi AÇIK iken zincirin çıkışı      :  -2.2 dBFS, tepe 440 Hz
hepsi KAPALI iken zincirin çıkışı    : -24.7 dBFS  ← bit-şeffaf
```

Yani on efekt de gerçekten işliyor, kapalıyken hiçbiri sese dokunmuyor ve graf ayakta
kalıyor (`doctor`: 6/6 gönderi bağlantısı).

Ölçüm yöntemi notu: `pw-cat -r --target=<sink>` işe yaramıyor — Sonar'ın kendi
yönlendiricisi kayıt akışını mikrofon zincirine taşıyor (logda görüldü). Monitör
portları `pw-link` ile elle bağlanmalı.
