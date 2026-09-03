# Faz 23 — ChatMix: donanım tekeri

**Durum:** 🟡 Kullanıcı bekleniyor (udev kuralı)
**Bağımlılık:** Faz 19 (slider ve rozet)
**Çıktı:** `src/sonar/engine/headset.py`, `packaging/99-sonar-headset.rules`,
`core/model.py`, `daemon/api.py`, `gui/qml/Mixer.qml`

---

## Amaç

Kullanıcının isteği: *"Chat mix özelliği kulaklığımdaki fiziksel tekerlek üzerinden
kontrol edilmiyor. Eğer yapabiliyorsak edilebilsin (ve o zaman elle düzenlenememeli)."*

Faz 9'da tespit vardı, okuma yoktu — çünkü `/dev/hidraw*` root'a kapalıydı ve
doğrulanmamış bir HID protokolü yazmak istemedim. Kullanıcı bu turda udev kuralını
kurmayı kabul etti.

---

## Ölçülmüş durum

Bu oturumda doğrulandı:

* `hidraw0`, `hidraw1`, `hidraw2` → `HID_ID=0003:00001038:0000220E`
  (SteelSeries Arctis 7+), üçü de `crw------- root root`
* Kartın **hiçbir profilinde** ayrı "Game"/"Chat" sink'i yok — teker ALSA'da bir
  kontrol olarak görünmüyor, tek yol HID.

---

## Görevler

### 1. Erişim

- [x] `packaging/99-sonar-headset.rules` repoda hazır.
- [x] Kurulum adımı `README.md` ve `docs/TROUBLESHOOTING.md`'ye yazılır.
- [ ] Arayüzdeki bildirim kopyalanabilir komutu gösterir.
      **Kullanıcı bir kez `sudo` çalıştıracak.**

### 2. Protokolün gözlemle çözülmesi

- [x] Yakalama aracı yazıldı: **`scripts/sonar-hid-capture`** (repoda; cihaza hiçbir
      şey yazmıyor, yalnızca okuyor). Erişim yokken ne yapılması gerektiğini söylüyor.
- [ ] **Kullanıcının çalıştırması gerekiyor** — bkz. aşağıdaki "Sırada ne var".
- [ ] Hangi düğümün, hangi rapor id'sinin, hangi baytının değiştiği çıkarılır.
      Beklenen biçim iki baytlık (game, chat) bir girdi raporu.
- [ ] **Doğrulanmadan tek satır sürücü kodu yazılmaz** — Faz 9'daki kararın aynısı.
- [ ] Çözülen biçim `headset.py` başlığına ve bu dosyaya yazılır; kaydedilen ham
      raporlar `tests/data/` altına konup çözücü testi onlarla yazılır.

### 3. Sürücü

- [ ] `headset.ChatMixReader`: `hidraw` düğümünü bloklamayan bir iş parçacığında okur,
      değeri 0–100'e ölçekler, `api.set_chatmix` çağırır.
- [x] Cihaz gidince sessizce durur, gelince kendiliğinden bağlanır (düğümü yoklayarak;
      ek bağımlılık yok).
- [x] Debounce: teker gürültüsü saniyede onlarca yazım üretmesin.

### 4. Ayar ve arayüz

- [ ] `settings.chatmix_source: "software" | "hardware" | "auto"` (varsayılan `auto`).
- [x] Donanım okunuyorken slider **salt okunur** olur ve altında
      "Kulaklık tekeri yönetiyor" rozeti görünür — kullanıcının istediği bu.
- [x] Teker okunamıyorsa hiçbir şey bozulmaz: yazılım slider'ı bugünkü gibi çalışır,
      bildirim şeridinde tek seferlik bir ipucu görünür.

---

## Kabul ölçütü

- [ ] Teker uçtan uca çevrilirken kaydedilen değerler 0 ve 100'e ulaşıyor
- [ ] Gecikme < 100 ms
- [ ] `sonar_<kanal>_to_<bus>` kazançları tekerin konumuna uyuyor
- [ ] Kulaklık kapatılıp açılınca sürücü kendiliğinden toparlanıyor
- [ ] Çözülemezse: bu dosyaya neden yazılır, yazılım slider'ı bozulmadan kalır


---

## Sırada ne var — kullanıcının çalıştırması gereken iki komut

Bayt biçimi cihazdan okumadan çözülemiyor ve `/dev/hidraw*` düğümleri `root`'a kapalı.
Doğrulanmamış bir düzen yazmak, ChatMix'i rastgele bir bayta bağlamak olurdu; sessizce
yanlış çalışan bir özellik hiç çalışmayandan kötüdür. Faz 9'daki kararın aynısı.

```bash
sudo cp packaging/99-sonar-headset.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Sonra kulaklık takılıyken:

```bash
./scripts/sonar-hid-capture      # tekeri yavaşça uçtan uca çevir, Ctrl+C
```

Çıktıdaki değişen bayt `decode_chatmix()` içine yazılıp raporlar `tests/data/` altına
konacak ve testi onlarla yazılacak.

## Hazır olanlar

* `ChatMixReader` — bloklamayan okuma iş parçacığı, cihaz gidince sessizce bekliyor,
  gelince kendiliğinden bağlanıyor, aynı değeri tekrar yollamıyor (`epsilon`).
* `settings.chatmix_source` (`auto` / `hardware` / `software`).
* Teker sürerken mikserdeki slider salt okunur oluyor ve başlığı
  "ChatMix — kulaklık tekeri yönetiyor" diyor. "Sıfırla" düğmesi de pasifleşiyor.
* `decode_chatmix()` yalnızca `None` döndürüyor; sürücünün geri kalanı çalışır durumda
  ve testleri var.
