# Faz 3 — Engine: süreç yönetimi ve canlı kontrol

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 2
**Çıktı:** `src/sonar/engine/{pwstate,supervisor,control}.py`,
`tests/test_{pwstate,control,supervisor}.py` — 61 yeni test (toplam 273)

---

## Amaç

Üretilen `graph.conf`'u canlı tutmak, PipeWire grafının durumunu izlemek ve tüm canlı
kontrolleri (volume, parametre, cihaz taşıma) kesintisiz uygulamak.

---

## Ölçüm: canlı yazım nasıl yapılmalı

Plan "20 ms debounce + toplu yazım, gerekirse kalıcı `pw-cli` oturumu" diyordu. Ölçüm
kalıcı oturumu **gereklilik** çıkardı — gerçek grafta:

| yöntem | maliyet |
|---|---|
| her yazım için `pw-cli` süreci açmak | **14.03 ms** |
| aynı süreçte 64 portu tek çağrıda yazmak | 12.97 ms |
| **kalıcı `pw-cli` oturumuna stdin'den yazmak** | **0.003 ms** |

İki sonuç:

1. **Maliyet tamamen süreç açmakta; yükün büyüklüğü ücretsiz.** 1 port ile 64 port aynı
   fiyata. Bu yüzden profil geçişi (≈130 port) tek çağrıda gönderiliyor.
2. **Süreç açmak fader için kullanılamaz.** 20 ms'lik pencereyle bile saniyede 50 × 14 ms
   = 700 ms CPU demekti. Kalıcı oturum bunu 4600 kat ucuzlatıyor.

Uçtan uca doğrulamada 100 fader yazımı toplam **0.3 ms** sürdü.

---

## Görevler

### `engine/pwstate.py` — graf durumu izleyicisi
- [x] `pw-dump -m` alt süreci, ardışık JSON dizisi akışının ayrıştırılması
- [x] Kısmi tamponlama — `EventSplitter` parça sınırı satır ortasına düşse de çalışır
      (olay sınırı: 0. sütunda `[` … 0. sütunda `]`; tek olay binlerce satır sürebiliyor)
- [x] `nodes: dict[str, int]` — `node.name → id`
- [x] `streams` — çalan akışlar, yönlendirme anahtarlarıyla (binary / app adı / media adı / pid)
- [x] `devices` — fiziksel sink/source envanteri, `priority.session` dâhil
- [x] `apply()` **yalnızca gerçekten değişen** envanterleri bildirir — aksi hâlde saniyede
      onlarca olay arayüzü boş yere yeniden çizerdi
- [x] Kopma hâlinde otomatik yeniden başlatma + envanter sıfırlama (kısmi envanterle devam
      etmek, silinmiş id'lere yazmak demek olurdu)
- [x] `wait_for_node()` — graf yeniden kurulduktan sonra id çözümünü beklemek için

**Plandan sapma:** `QProcess` yerine `subprocess` + okuma iş parçacığı. Böylece `engine/`
katmanı Qt olay döngüsü olmadan çalışıyor ve ayrıştırma mantığının tamamı saf, yan etkisiz
ve testlerde gerçek süreç açmadan doğrulanabilir. Daemon (Faz 4) callback'leri kendi olay
döngüsüne bağlayacak.

### `engine/supervisor.py` — graf süreci yaşam döngüsü
- [x] `graph.conf` atomik yazım
- [x] `pipewire -c <conf>` başlat/durdur/izle
- [x] `reconcile(cfg)` — conf metni değiştiyse yeniden inşa, değişmediyse canlı yazım
- [x] Yeniden başlatma sonrası tüm canlı durumu baştan uygula
- [x] Çökmede exponential backoff (1, 2, 4, 8, 16 sn), 5 ardışık çökmede vazgeç + bildir
- [x] Temiz kapanış; `take_over_default_sink` açıksa varsayılan sink geri alınır
- [x] `chatmix_gains()` / `live_volumes()` / `live_params()` — saf, PipeWire'sız test edilebilir
      hesaplar. ChatMix yalnızca kulaklık miksini etkiler, yayın miksine dokunmaz

### `engine/control.py` — canlı kontrol arayüzü
- [x] `set_param` / `set_params` — tek çağrıda toplu yazım
- [x] `set_volume` / `set_mute` — **`wpctl` değil** `Props.channelVolumes` (lineer)
- [x] `move_stream` (`pactl`), `set_default_sink` (`wpctl`) — nadir, süreç açma maliyeti görünmez
- [x] Kalıcı `pw-cli` oturumu, ölürse sessizce yeniden açılır
- [x] Toplu yazım penceresi **40 ms** (ölçüldü, aşağıya bak)
- [x] Tüm alt süreç çağrıları zaman aşımlı; başarısızlık loglanır, daemon çökmez

### Testler — 61 yeni test
- [x] `test_pwstate.py` (16) — olay bölme, parça sınırı, bozuk JSON, id geri dönüşümü
- [x] `test_control.py` (19) — biçimlendirme, toplu yazım, oturum kopması, lineer seviye
- [x] `test_supervisor.py` (26) — ChatMix, canlı değerler, ne zaman restart / ne zaman değil

---

## Doğrulama — ✅ gerçek PipeWire üzerinde yapıldı

Ayrı bir XDG dizininde, sıfırdan:

| Adım | Sonuç |
|---|---|
| 1. İlk kurulum | 0.26 s, **32 node** |
| 2. Profil değişimi | `canlı yazım`, **süreç aynı**, `eq:enabled = 1.0`, `eq:g_4 = 2.5119` (= tam +8 dB) |
| 3. Fader | `channelVolumes = [0.5, 0.5]` — lineer, kübik değil |
| 4. 100 hızlı fader yazımı | toplam **0.3 ms** |
| 5. Kanal ekleme | `yapısal değişiklik`, **yeni süreç**, 38 node, `sonar_music` var, profil geri geldi |
| 6. Graf sürecini öldür | gözetmen yeni süreç açtı, 38 node, **durum geri geldi** |
| 7. Temiz kapanış | kalan `sonar_*` node: **0** |
| 8. `pw-dump -m`'i öldür | izleyici kendini toparladı, harita canlı |

`systemctl --user restart pipewire` senaryosu Faz 10'a bırakıldı: kullanıcının çalışan ses
oturumunu (EasyEffects dâhil) kesintiye uğratıyor, dayanıklılık testleriyle birlikte
yapılması daha uygun.

### Tık/pop ölçümü

60 Hz'lik gerçekçi fader sürüklemesi kaydedilip örnekler arası süreksizlik arandı
(1 kHz sinüs; normal adımın 1.5 katını aşan sıçrama = tık):

| Durum | Sonuç |
|---|---|
| hiç dokunmadan (referans) | temiz |
| tek seferlik büyük sıçrama (1.0 → 0.1) | **temiz** |
| mute aç/kapa | **temiz** |
| 60 Hz sürükleme, 0 ms pencere | 3/3 denemede tık |
| 60 Hz sürükleme, 20 ms pencere | 2/3 denemede tık |
| 60 Hz sürükleme, 30 ms pencere | 2/4 denemede tık |
| 60 Hz sürükleme, **40 ms pencere** | **1/4 denemede tık** |

PipeWire seviye değişimini kendi içinde yumuşatıyor; sorun yalnızca ardışık yazımların
birbirinin rampasını kesmesi. Pencere plandaki 20 ms'den **40 ms'ye** çıkarıldı.

**Dürüst kayıt:** 40 ms artefaktı belirgin biçimde azaltıyor ama tamamen bitirmiyor.
Kalan süreksizlik çok hafif (normal örnek adımının ~2 katı). Tam çözüm seçenekleri
`.plan/99-backlog.md`'de.

---

## Yol boyunca yakalananlar

1. **Çökme sonrası toparlanma yapılandırmayı diskten okuyordu.** Kullanıcının henüz
   kaydetmediği değişiklikler kaybolurdu — hatta diskteki hâl çalışan graftan yapısal
   olarak farklı olabilirdi. Artık süpervizör son uzlaştırdığı yapılandırmayı hatırlıyor.
2. **Gözetmen iş parçacığı yeniden inşada ölüyordu.** Süreç değişince `return` ediyor,
   `_start_watchdog` ise "zaten canlı" görüp yenisini başlatmıyordu; aradaki yarışta graf
   gözetimsiz kalabiliyordu. Artık tek ve uzun ömürlü.
3. **Yeniden başlatmadan sonra ölü node id'lerine yazılıyordu.** Süreç öldüğünde silinme
   olayları hemen gelmiyor; eski ad bir süre daha ölü id'siyle haritada duruyor.
   `_wait_for_graph` artık adın değil **id'nin tazelenmesini** bekliyor. Bu, uçtan uca
   testte "profilim yeniden başlatmadan sonra sıfırlandı" olarak görüldü ve düzeltildi.
4. **Tek bir node'u beklemek yetmiyordu.** Conf önce filter-chain'leri, sonra loopback'leri
   kuruyor; `sonar_game` göründüğünde `sonar_game_to_personal` henüz yok ve o an yazılan
   fader değeri sessizce kayboluyordu. Artık yazılacak **tüm** node'lar bekleniyor.
5. **`PwCliSession._close_locked` hiç tanımlanmamıştı** — oturum kapatma testi yakaladı.

---

## Tamamlanma kriteri — ✅ karşılandı

Daemon olmadan, doğrudan Python'dan graf kuruluyor ve canlı kontrol ediliyor; graf süreci
öldürüldüğünde ve `pw-dump` koptuğunda sistem kendini toparlıyor.

```bash
ruff check src/ tests/ && pytest -q          # 273 test geçti, lint temiz
```
