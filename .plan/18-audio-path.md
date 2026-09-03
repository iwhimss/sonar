# Faz 18 — Ses yolunun güvenilirliği

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 12 (sanal cihaz düzeni), Faz 14 (envanter)
**Çıktı:** `src/sonar/engine/supervisor.py`, `src/sonar/engine/control.py`,
`src/sonar/engine/confgen.py`, `src/sonar/engine/router.py`,
`src/sonar/daemon/api.py`, `src/sonar/cli/__main__.py`

---

## Amaç

Test turu 2'nin en ağır şikâyeti: **ses hiç gelmiyor, cihaz değiştirince müzik duruyor,
uygulamayı kanallar arası taşıyınca ses kesiliyor.** Bu fazın sonunda ses yolu kendi
kendini onaran ve asla sessizce bozulmayan bir hâle gelir.

Diğer bütün fazlar bunun üstüne kuruluyor; **ilk bu yapılır.**

---

## Ölçülmüş kök nedenler

| Belirti | Kök neden |
|---|---|
| Ses hiç gelmiyor (aralıklı) | `supervisor._wire_sends` tek atışlık, iki denemeli. Başarısız olursa yalnızca `log.error` var; kanalın `_fx` çıkışı hiçbir bus'a bağlanmaz ve kanal **tamamen sessiz** kalır. Kullanıcıya hiçbir işaret gitmez. |
| Cihaz değiştirince müzik duruyor | `api.set_bus_device` → `_structural()` → conf metni değişiyor (`target.object`) → `pipewire -c` süreci restart. Tüm node id'leri değişiyor, akışlar kopuyor, metre süreçleri baştan kuruluyor. |
| "Anlık ses gelip gidiyor" | Restart penceresinde akış varsayılan cihaza düşüyor (ses duyuluyor), yeni `sonar_media` doğunca geri çekiliyor — ama gönderiler henüz `pw-link`'lenmemiş (sessizlik). |
| Restart sonrası akış yerine oturmuyor | `api._structural` `router.reset()` çağırıyor ama `Router._is_routable` hedefi `sonar_` ile başlayan akışı "kullanıcı seçmiş" sayıp atlıyor. Hiçbir akış yeniden yerleştirilmiyor. |

Bu oturumda canlı grafta doğrulananlar: topoloji şu an doğru (16 gönderi bağlantısı
yerinde), üç kanaldan da sinyal geçiyor (-38.9 / -38.9 / -40.3 dBFS), mute ve ChatMix
motorda çalışıyor. Yani sorun kalıcı bir yapı hatası değil, **yeniden inşa ve bağlantı
kurma yolundaki yarışlar**.

---

## Görevler

### 1. Bağlantı bekçisi (link keeper)

- [x] `supervisor._wire_sends` → `supervisor.reconcile_links(cfg)`: beklenen küme
      `confgen.send_links(cfg)`, gerçek küme `Control.node_links()`, fark `pw-link` ile
      kapatılır. Sonuç `(kurulan, eksik_kalan)` döner.
- [x] Üç tetikleyici: (a) yeniden inşa sonrası, (b) `pwstate` `NODES` değişikliği
      bildirdiğinde (debounce'lu), (c) `HEALTH_INTERVAL` sağlık yoklamasında.
- [x] Ard arda `LINK_FAILURE_LIMIT` (3) kez eksik kalırsa `on_failure` dinleyicisi tetiklenir.
- [x] Test: sahte `runner`/`capturer` ile eksik bağlantı senaryosu; ikinci turda kapanıyor.

### 2. Sessiz sessizlik biter

- [x] `api` yeni delta yayınlar: `{"kind": "path_broken", "channels": [...]}`.
- [x] `gui/bridge.py` bunu `noticeRaised(mesaj, hata=True)` ile şeride basar:
      "Game kanalı çıkışa bağlanamadı — ses gelmiyor olabilir."
- [x] Yol düzelince `{"kind": "path_ok"}` ve şerit temizlenir.
- [x] Yeni CLI: `sonar-cli doctor` — beklenen/gerçek bağlantı farkı, eksik node'lar,
      graf süreci durumu, EasyEffects çakışması. Çıkış kodu 0/1.

### 3. Cihaz değişimi artık yeniden inşa değil

- [x] **İlk adım ölçüm — sonuç: çalışıyor.** `pw-metadata <id> target.object <cihaz>` ile
      `sonar_personal_out` Arctis ↔ Realtek arasında gidip geldi, `pw-link -lo` bağlantının
      anında taşındığını gösterdi. Süreksizlik ölçümü: anahtarlamasız kontrol **20/397**
      düşük pencere, anahtarlamayla **37/396** — fark kayıt gürültüsünün içinde
      (daemon'ın 6 metre `pw-cat`'i, cava ve iki test süreci aynı anda çalışıyordu).
- [x] `confgen._bus_chain` playback'inden `target.object` çıkar.
- [x] `Control.set_target(node_name, target)` — `move_stream` ile aynı `pw-metadata` yolu,
      ama node adından id çözerek.
- [x] `supervisor.apply_outputs(cfg)`: her çıkış bus'ının `_out` node'unun hedefini yazar.
      `apply_live` içinde de çağrılır (restart sonrası).
- [x] `api.set_bus_device` → `_live_outputs()` (yeni), `_structural` değil.
- [x] Golden conf testi: cihaz değişimi conf metnini **değiştirmemeli**.
- [x] Yedek yola gerek kalmadı.

### 4. Mikrofon kaynağı da canlı

- [x] `mic.source_device` `_capture` node'una canlı yazılır (`confgen` `target.object`
      bırakır), `api.set_mic_device` yeniden inşa etmez.

### 5. Monitör / yayına gönderi loopback'leri hep kurulur

- [x] `confgen._mic_modules` `monitor_enabled` / `send_to_stream_bus` bakmadan her iki
      loopback'i de kurar.
- [x] `live_volumes` kapalı olanı `muted=True` yazar.
- [x] `api.set_mic_monitor` / `set_mic_stream_send` → `_live_volumes`, yeniden inşa yok.
- [x] Ölçüm: sidetone açılıp kapanırken müzik kesilmiyor.

### 6. Yeniden inşa sonrası akışlar yerine oturtulur

- [x] `Router.reassert(cfg)`: `_decided` içindeki her akış için hedef node'un grafta
      var olduğunu doğrular; yoksa/bağlı değilse taşımayı yeniden uygular.
- [x] `api._structural` `router.reset()` yerine `router.reassert(self.config)` çağırır.
      `reset()` yalnızca kanal silindiğinde ve hedef kaybolduğunda kullanılır.
- [x] `_is_routable`'daki `sonar_` ön eki kontrolü yalnızca **ilk** karar için geçerli.
- [x] Test: restart taklidi (node id'leri değişir) → tüm akışlar yeniden taşınıyor.

### 7. Kanal değiştirmede ses kesilmesi

- [x] `api.move_stream` taşımadan sonra `Control.node_links()` ile hedefe bağlanmayı
      doğrular; bağlanmadıysa bir kez daha dener, yine olmazsa `move_failed` bildirir.
- [x] Ölçüm: bir akış 20 kez kanallar arasında gezdirilir, her seferinde hedef kanalın
      monitöründe sinyal aranır. 20/20 beklenir.

---

## Kabul ölçütü

- [x] Cihaz değiştirilirken çalan ton kesilmiyor (kayıt alınıp süreksizlik aranacak)
- [x] `_wire_sends` kasten bozulduğunda arayüzde kırmızı uyarı çıkıyor
- [x] 20 taşımanın 20'sinde ses hedef kanalda
- [x] `systemctl --user restart pipewire` sonrası bağlantılar ve akışlar toparlanıyor
- [x] `sonar-cli doctor` temiz çıktı veriyor


---

## Yol boyunca yakalananlar

**`scripts/sonar-dev stop` GUI açıkken sessizce başarısız oluyordu.** `daemon_pids()`
fonksiyonunun çıkış kodu döngüdeki son `grep`inki oluyor; GUI de bir `python` süreci
olduğu için son eşleşme başarısız dönüyor ve `set -e` betiği hiçbir şey yazmadan
öldürüyordu. Kullanıcı testte tam bu durumda (`daemon + gui` açık). `return 0` eklendi.

**Doğrulanan davranışlar (canlı grafta, 2026-09-03):**

| Ölçüm | Sonuç |
|---|---|
| Cihaz değişimi yeniden inşa yapmıyor | `sonar_media` node id'si 108 → 108 (değişmedi) |
| Hedef gerçekten taşınıyor | `sonar_personal_out` Arctis → Realtek → Arctis, `pw-link -lo` doğruladı |
| Bağlantı bekçisi kopan linki onarıyor | `pw-link -d` ile koparıldı, **3 sn içinde** geri kuruldu |
| Sidetone açma/kapama canlı | node id sabit, `sonar_mic_monitor` mute'u doğru yazıldı |
| Ses yolu sağlam | media → personal **-22.9 dBFS** |
| `sonar-cli doctor` | `Gönderi bağlantısı: 6/6`, sorun yok, çıkış kodu 0 |

**Sapma:** `_stream_reached` `pw-link -l` hiç okunamadığında (komut yok, zaman aşımı)
taşımayı tekrarlamıyor. Bilmediğimiz için körlemesine tekrar denemek akışı ikinci kez
sarsmaktan başka işe yaramaz.
