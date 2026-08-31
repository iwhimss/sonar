# OBS ile kullanım

Sonar'ın yayıncılar için asıl faydası: **kulaklığından duyduğun ses ile yayına giden ses
ayrı.** Telifli müziği kendin duyarsın, yayında duyulmaz. Ayrıca her kanalı ayrı bir OBS
track'ine verip kayıttan sonra tek tek düzenleyebilirsin.

---

## Sonar'ın OBS'e sunduğu kaynaklar

Daemon çalışırken OBS'in ses kaynağı listesinde şunlar görünür:

| Kaynak | Ne içerir |
|---|---|
| **Sonar Stream Mix** | Yayın fader'larıyla mikslenmiş birleşik ses |
| **Sonar Stream Mic** | Mikrofonun yayına özel işlenmiş hâli |
| **Sonar Game (FX)** | Yalnızca Game kanalı, DSP sonrası |
| **Sonar Chat (FX)** | Yalnızca Chat kanalı |
| **Sonar Media (FX)** | Yalnızca Media kanalı |
| **Sonar Aux (FX)** | Yalnızca Aux kanalı |

`_fx` kaynakları **fader'lardan bağımsızdır** — Stream Mix'te kısılmış bir kanalı yine de
ayrı track'e alabilirsin.

---

## En basit kurulum: tek track

1. OBS → **Kaynaklar** → `+` → **Ses Girişi Yakalama**
2. Cihaz: **Sonar Stream Mix**
3. İkinci bir kaynak ekle → **Sonar Stream Mic**

Bitti. Yayına giden her şey Sonar'ın yayın fader'larından geçiyor.

**Müziği yayından çıkarmak:** Sonar'da Media kanalının 📡 (yayın) fader'ını kapat.
Kulaklığında duymaya devam edersin, yayında duyulmaz.

---

## Çok track'li kayıt

Her kanalı ayrı track'e almak, kayıttan sonra "oyun sesi çok yüksek olmuş" gibi sorunları
düzeltmeni sağlar.

1. Kaynakları ekle: **Sonar Game (FX)**, **Sonar Chat (FX)**, **Sonar Stream Mic**
2. **Ayarlar → Çıktı → Kayıt** → Kayıt biçimi `mkv`, **Ses Parçaları**: 1–4 işaretle
3. Miksleyicide her kaynağın `⋮` menüsü → **Gelişmiş Ses Özellikleri**
4. Her kaynağı yalnızca kendi track'ine ata:

   | Kaynak | Track |
   |---|---|
   | Sonar Stream Mix | 1 |
   | Sonar Game (FX) | 2 |
   | Sonar Chat (FX) | 3 |
   | Sonar Stream Mic | 4 |

5. Kaydı başlat.

Doğrulamak için:

```bash
ffprobe -hide_banner kayit.mkv 2>&1 | grep Audio
```

Dört ayrı ses akışı görmelisin.

> **Not:** Yayın (streaming) tek bir ses track'i gönderir — çok track yalnızca **kayıt**
> içindir. OBS'te "Ses Parçaları" ayarı Yayın ve Kayıt için ayrıdır.

---

## Senkron

Sonar ölçülebilir bir gecikme eklemiyor (bkz. `docs/PERFORMANCE.md`: filtreler kapalıyken
1.1 ms, ölçüm gürültüsünün içinde). Yani OBS'te ses gecikmesi (sync offset) ayarlamana
gerek yok.

İstisna: limiter'ın **ileri-bakış** değerini büyütürsen o kadar gecikme eklenir (20 ms
ileri-bakış = ~16 ms ölçüldü). Yayında limiter kullanıyorsan ileri-bakışı düşük tut.

---

## Sık karşılaşılan sorunlar

**Kaynak listesinde Sonar cihazları yok.**
Daemon çalışmıyordur:
```bash
systemctl --user status sonar-daemon
sonar-cli status
```

**Stream Mix sessiz.**
Kanalların yayın fader'ları kapalı olabilir:
```bash
sonar-cli status        # 📡 sütunundaki değerlere bak
sonar-cli volume game stream 100
```

**Oyun sesi yanlış track'te.**
Uygulama yanlış kanala düşmüştür. `sonar-cli status` ile bak, gerekirse taşı:
```bash
sonar-cli move <akış-id> game --remember
```

**Kayıtta yalnızca bir track var.**
OBS → Ayarlar → Çıktı → **Kayıt** sekmesindeki "Ses Parçaları" kutularını işaretlemeyi
unutmuş olabilirsin (Yayın sekmesindeki ayar ayrıdır).

**EasyEffects açıkken ses beklenmedik yoldan gidiyor.**
İkisi birlikte çalışmaz; bkz. `docs/TROUBLESHOOTING.md`.
