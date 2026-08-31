# Faz 4 — Daemon ve D-Bus API

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 3
**Çıktı:** `src/sonar/daemon/{api,dbus_iface,service}.py`, `src/sonar/cli/__main__.py`,
`packaging/sonar-daemon.service`, `packaging/io.github.iwhimss.Sonar.service`,
`docs/TROUBLESHOOTING.md` — 109 yeni test (toplam 391)

---

## Amaç

Motoru arka planda çalışan bir servise dönüştürmek ve GUI ile CLI'ın kullanacağı tek
D-Bus API'sini tanımlamak. Bu API sabitlendikten sonra GUI tamamen bağımsız geliştirilebilir.

---

## Üç ölçüm, üç karar

### 1. `QDBusContext.sendErrorReply()` PySide6'da segfault ediyor
Prob ile denendi: metot içinde çağrılınca süreç **çıkış kodu 139** ile ölüyor. Kullanılsaydı
her geçersiz argüman daemon'ı düşürürdü. Ayrıca PySide6 slot içindeki Python istisnalarını
sessizce yutup boş string döndürüyor — istemci başarıyı hatadan ayıramıyor.

**Karar:** her metot bir **JSON zarfı** döndürür:
```json
{"ok": true}                                      {"ok": true, "result": …}
{"ok": false, "code": "unknown_channel", "message": "…"}
```

### 2. PySide6 Qt sinyallerini D-Bus'a relay etmiyor
Nesne `ExportAllSignals` ile kaydedilse ve `busctl introspect` sinyalleri gösterse bile,
Python'da tanımlı bir `Signal` emit edildiğinde otobüse **hiçbir mesaj çıkmıyor**
(`dbus-monitor` sıfır mesaj). Sessiz bir başarısızlık: arayüz hiç güncelleme almadan
çalışmaya devam ederdi.

**Karar:** `emit_signal()` her sinyali `QDBusMessage.createSignal()` ile elle gönderir.
Qt sinyali de ayrıca emit edilir (süreç içi dinleyiciler + introspection).

### 3. EasyEffects sistem geneli çalışırken cihaz seçimi yok sayılıyor
`target.object` doğru yazılıyor, node'un props'unda görünüyor, hedef cihaz mevcut — ama
bağlantı `easyeffects_sink`'e gidiyor. `pactl move-sink-input` hatasız dönüyor ve bağlantı
anında geri alınıyor. Yani EasyEffects "service mode" her oynatma akışını kendine çekiyor.

**Karar:** daemon açılışta tespit edip `Error` sinyali ve log uyarısı yayıyor; `sonar-cli
status` da gösteriyor. `docs/TROUBLESHOOTING.md` çözümü anlatıyor.

---

## Görevler

### `daemon/api.py` — iş mantığı *(planda yoktu, eklendi)*
Plan `service.py` + `dbus_iface.py` diyordu. Tüm doğrulama, mutasyon ve kalıcılık mantığı
ayrı bir saf modüle alındı; böylece Qt olay döngüsü, D-Bus oturumu veya çalışan PipeWire
olmadan test edilebiliyor. `dbus_iface.py` yalnızca ince bir sarmalayıcı.
- [x] Her mutasyon **canlı** veya **yapısal** olarak sınıflandırılıyor
- [x] Mikrofon monitörü / yayına gönderi bilinçli olarak yapısal (conf'a loopback ekliyorlar)
- [x] Profil düzenlemeleri aktif profile otomatik kalıcı; `SaveProfile` bir "farklı kaydet"
- [x] Grafın yeniden kurulması bellekteki (kaydedilmemiş) profili kullanıyor
- [x] `conflicts()` — EasyEffects/JamesDSP tespiti

### `daemon/service.py`
- [x] `QCoreApplication` olay döngüsü
- [x] Açılış: config → `reconcile()` → izleme → D-Bus kaydı
- [x] Tek örnek: ad alınmışsa **çıkış kodu 0** ile temiz çıkış (hata değil)
- [x] Config'e debounce'lu yazım (500 ms)
- [x] `SIGTERM`/`SIGINT` → temiz kapanış. Python sinyal işleyicisi Qt olay döngüsü C
      tarafında beklerken çalışmadığı için `signal.set_wakeup_fd` + `QSocketNotifier`
- [x] `SONAR_LOG=debug` ile ayrıntılı log
- [x] Sinyaller 50 ms penceresinde biriktirilip `kind` başına tekleniyor

### `daemon/dbus_iface.py` — 36 metot, 5 sinyal
- [x] Okuma: `GetState`, `GetDevices`, `ListProfiles`, `ListRules`, `Ping`
- [x] Seviye: `SetChannelVolume/Mute`, `SetMasterVolume/Mute`, `SetMicVolume/Mute`
- [x] Filtre: `SetFilterEnabled`, `SetFilterParam`, `SetEqBand`, `SetEqPreamp`, `SetBandCount`
- [x] Profil: `LoadProfile`, `SaveProfile`, `DeleteProfile`, `RenameProfile`, `SetProfileFavorite`
- [x] Yapısal: `SetBusDevice`, `SetMicDevice`, `SetMicMonitor`, `SetMicStreamSend`,
      `AddChannel`, `RemoveChannel`
- [x] Yönlendirme: `MoveStream`, `SetRule`, `RemoveRule`
- [x] ChatMix ve ayarlar: `SetChatMix`, `SetChatMixConfig`, `SetDefaultChannel`,
      `SetTakeOverDefaultSink`
- [x] `SubscribeMeters` (Faz 6'ya hazır, sayaç tutuluyor), `Reload`
- [x] Sinyaller: `StateChanged`, `StreamsChanged`, `LevelsUpdated`, `GraphRebuilt`, `Error`
- [x] Argümanlar yalnızca basit tiplerde (`s`, `b`, `d`, `i`); karmaşık yapılar JSON string
- [x] Her metot doğrulama yapıyor; geçersiz argüman zarf içinde `code` + `message` dönüyor

### `packaging/`
- [x] `sonar-daemon.service` — `Type=dbus`, `PartOf=pipewire.service`, `Restart=on-failure`
- [x] `io.github.iwhimss.Sonar.service` — D-Bus otomatik başlatma

### `cli/__main__.py` — 13 komut
- [x] `status` (tablo), `volume`, `mute` (on/off/toggle), `master`, `profile`, `save`,
      `route`, `rules`, `move`, `chatmix`, `devices`, `device`, `reload`
- [x] `--json` bayrağı
- [x] Daemon çalışmıyorsa `systemctl --user start sonar-daemon` öneren anlaşılır hata
- [x] Çakışma uyarısı `status` çıktısında görünüyor

### Testler — 109 yeni test
- [x] `test_api.py` (60) — canlı/yapısal ayrımı, 24 doğrulama vakası, profil semantiği
- [x] `test_dbus_iface.py` (22) — zarf sözleşmesi, argüman dönüşümü, sinyal yayını
- [x] `test_cli.py` (28) — her komut, çıktı biçimi, hata yolu

---

## Doğrulama — ✅ gerçek D-Bus ve PipeWire üzerinde

| Test | Sonuç |
|---|---|
| `busctl introspect` | **36 metot + 5 sinyal** göründü |
| `busctl call Ping` | `{"ok": true, "result": "pong"}` |
| Geçersiz argüman | `{"ok": false, "code": "unknown_channel", …}` — daemon ayakta |
| `sonar-cli status` | tablo, fader'lar, profiller, çalan uygulamalar |
| `sonar-cli volume game personal 40` | `sonar_game_to_personal` = **0.400000** |
| `sonar-cli mute game stream on` | `mute = true` |
| `SetEqBand game 4 gain_db 8.0` | `eq:g_4` = **2.511886** (tam +8 dB) |
| **Profil geçişi** | Default = 1.0 → CS2 = 2.5119 → Default = 1.0, **anında ve kesintisiz** |
| `sonar-cli chatmix 100` | game personal 0.004 (= -40 dB), chat personal 1.0 |
| Yapısal değişiklik | `GraphRebuilt` + `StateChanged` sinyalleri yayıldı |
| `dbus-monitor` | `StateChanged` gövdeleri doğru delta taşıyor |
| İkinci daemon | "zaten çalışıyor", **çıkış kodu 0** |
| `SIGTERM` | graf düştü, kalan `sonar_*` node: **0** |
| Çakışma tespiti | EasyEffects bulundu, log + `Error` sinyali + CLI uyarısı |

Kullanıcının en temel isteği — *"CS2 için ayrı EQ, Arc Raiders için ayrı EQ, aralarında
hızlıca geçiş"* — bu fazda uçtan uca çalışır hâle geldi.

---

## Yol boyunca yakalananlar

1. **`SonarConfig.bus()` imzası yalan söylüyordu.** `-> MasterBus | None` diyor ama
   bilinmeyen bir ad için `ValueError` yükseltiyordu; "bu ad kanal mı bus mu?" diye yoklayan
   her yer patlıyordu. Artık `channel()` ve `mic()` gibi `None` dönüyor.
2. **"Çalan uygulamalar" listesinde Sonar'ın kendi loopback'leri görünüyordu.** Kanal→bus
   loopback'leri de `Stream/Output/Audio` sınıfında. `StreamInfo.is_internal` eklendi;
   envanterde duruyorlar (graf doğru kalsın) ama kullanıcıya gösterilmiyorlar. Faz 5'teki
   yönlendirme kuralları da onlara dokunmayacak.
3. **Başlıktaki akış sayısı listelenenle uyuşmuyordu** — kayıt akışları sayılıyor ama
   basılmıyordu. Ayrı bölüm olarak gösteriliyor.

---

## Tamamlanma kriteri — ✅ karşılandı (bir istisnayla)

Tüm D-Bus metotları `busctl` ile çağrılabiliyor ve `sonar-cli` ile GUI olmadan tam kontrol
mümkün.

**Açık kalan:** systemd unit'i yazıldı ama **systemd altında çalıştırılıp denenmedi**.
`Type=dbus` unit'i `/usr/bin/sonar-daemon`u bekliyor; bu da paketin sisteme kurulmasını
gerektiriyor. Kurulum ve `systemctl --user enable` doğrulaması Faz 11'e (paketleme)
bırakıldı. Daemon bu fazda doğrudan çalıştırılarak denendi ve `SIGTERM` ile temiz kapandı —
yani systemd'nin ihtiyaç duyduğu davranış hazır.

```bash
ruff check src/ tests/ && pytest -q          # 391 test geçti, lint temiz
```
