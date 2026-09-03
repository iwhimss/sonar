# Faz 18 — Ses yolunun güvenilirliği

**Durum:** ⚪ Bekliyor
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

- [ ] `supervisor._wire_sends` → `supervisor.reconcile_links(cfg)`: beklenen küme
      `confgen.send_links(cfg)`, gerçek küme `Control.node_links()`, fark `pw-link` ile
      kapatılır. Sonuç `(kurulan, eksik_kalan)` döner.
- [ ] Üç tetikleyici: (a) yeniden inşa sonrası, (b) `pwstate` `NODES` değişikliği
      bildirdiğinde (debounce'lu), (c) `HEALTH_INTERVAL` sağlık yoklamasında.
- [ ] Ard arda `LINK_FAILURE_LIMIT` (3) kez eksik kalırsa `on_failure` dinleyicisi tetiklenir.
- [ ] Test: sahte `runner`/`capturer` ile eksik bağlantı senaryosu; ikinci turda kapanıyor.

### 2. Sessiz sessizlik biter

- [ ] `api` yeni delta yayınlar: `{"kind": "path_broken", "channels": [...]}`.
- [ ] `gui/bridge.py` bunu `noticeRaised(mesaj, hata=True)` ile şeride basar:
      "Game kanalı çıkışa bağlanamadı — ses gelmiyor olabilir."
- [ ] Yol düzelince `{"kind": "path_ok"}` ve şerit temizlenir.
- [ ] Yeni CLI: `sonar-cli doctor` — beklenen/gerçek bağlantı farkı, eksik node'lar,
      graf süreci durumu, EasyEffects çakışması. Çıkış kodu 0/1.

### 3. Cihaz değişimi artık yeniden inşa değil

- [ ] **İlk adım ölçüm:** `pw-metadata <sonar_personal_out id> target.object <cihaz>`
      canlı çalışıyor mu? `pw-link -lo` ile doğrulanacak, ton kaydedilip süreksizlik aranacak.
- [ ] `confgen._bus_chain` playback'inden `target.object` çıkar.
- [ ] `Control.set_target(node_name, target)` — `move_stream` ile aynı `pw-metadata` yolu,
      ama node adından id çözerek.
- [ ] `supervisor.apply_outputs(cfg)`: her çıkış bus'ının `_out` node'unun hedefini yazar.
      `apply_live` içinde de çağrılır (restart sonrası).
- [ ] `api.set_bus_device` → `_live_outputs()` (yeni), `_structural` değil.
- [ ] Golden conf testi: cihaz değişimi conf metnini **değiştirmemeli**.
- [ ] Yedek yol (ölçüm tutmazsa): conf'ta `target.object` kalır ama cihaz değişimi
      bekçi (madde 1) üzerinden kalıcı `pw-link` ile yapılır. Karar bu dosyaya yazılır.

### 4. Mikrofon kaynağı da canlı

- [ ] `mic.source_device` `_capture` node'una canlı yazılır (`confgen` `target.object`
      bırakır), `api.set_mic_device` yeniden inşa etmez.

### 5. Monitör / yayına gönderi loopback'leri hep kurulur

- [ ] `confgen._mic_modules` `monitor_enabled` / `send_to_stream_bus` bakmadan her iki
      loopback'i de kurar.
- [ ] `live_volumes` kapalı olanı `muted=True` yazar.
- [ ] `api.set_mic_monitor` / `set_mic_stream_send` → `_live_volumes`, yeniden inşa yok.
- [ ] Ölçüm: sidetone açılıp kapanırken müzik kesilmiyor.

### 6. Yeniden inşa sonrası akışlar yerine oturtulur

- [ ] `Router.reassert(cfg)`: `_decided` içindeki her akış için hedef node'un grafta
      var olduğunu doğrular; yoksa/bağlı değilse taşımayı yeniden uygular.
- [ ] `api._structural` `router.reset()` yerine `router.reassert(self.config)` çağırır.
      `reset()` yalnızca kanal silindiğinde ve hedef kaybolduğunda kullanılır.
- [ ] `_is_routable`'daki `sonar_` ön eki kontrolü yalnızca **ilk** karar için geçerli.
- [ ] Test: restart taklidi (node id'leri değişir) → tüm akışlar yeniden taşınıyor.

### 7. Kanal değiştirmede ses kesilmesi

- [ ] `api.move_stream` taşımadan sonra `Control.node_links()` ile hedefe bağlanmayı
      doğrular; bağlanmadıysa bir kez daha dener, yine olmazsa `move_failed` bildirir.
- [ ] Ölçüm: bir akış 20 kez kanallar arasında gezdirilir, her seferinde hedef kanalın
      monitöründe sinyal aranır. 20/20 beklenir.

---

## Kabul ölçütü

- [ ] Cihaz değiştirilirken çalan ton kesilmiyor (kayıt alınıp süreksizlik aranacak)
- [ ] `_wire_sends` kasten bozulduğunda arayüzde kırmızı uyarı çıkıyor
- [ ] 20 taşımanın 20'sinde ses hedef kanalda
- [ ] `systemctl --user restart pipewire` sonrası bağlantılar ve akışlar toparlanıyor
- [ ] `sonar-cli doctor` temiz çıktı veriyor
