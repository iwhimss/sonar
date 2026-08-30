# Faz 4 — Daemon ve D-Bus API

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 3
**Çıktı:** `src/sonar/daemon/`, `src/sonar/cli/`, `packaging/sonar-daemon.service`

---

## Amaç

Motoru arka planda çalışan bir servise dönüştürmek ve GUI ile CLI'ın kullanacağı tek
D-Bus API'sini tanımlamak. Bu API sabitlendikten sonra GUI tamamen bağımsız geliştirilebilir.

---

## Görevler

### `daemon/service.py`
- [ ] `QCoreApplication` tabanlı olay döngüsü
- [ ] Açılış: config yükle → `Supervisor.reconcile()` → `PwState` izlemeye başla → D-Bus'a kaydol
- [ ] Tek örnek garantisi: D-Bus adı zaten alınmışsa temiz çıkış (hata değil)
- [ ] Durum değişikliklerini config'e **debounce'lu** yazma (500 ms; her fader hareketinde diske yazma)
- [ ] `SIGTERM`/`SIGINT` → temiz kapanış (graf süreci öldürülür, varsayılan sink geri alınır)
- [ ] Yapılandırılabilir loglama (`SONAR_LOG=debug`), journald'a gider

### `daemon/dbus_iface.py`
Servis adı `io.github.iwhimss.Sonar`, yol `/io/github/iwhimss/Sonar`, arayüz `io.github.iwhimss.Sonar`

**Metotlar:**
- [ ] `GetState() -> s` — tüm durumun JSON'u (kanallar, bus'lar, profiller, kurallar, akışlar, cihazlar)
- [ ] `SetChannelVolume(s channel, s bus, d value)` — `bus` ∈ {`personal`, `stream`}
- [ ] `SetChannelMute(s channel, s bus, b muted)`
- [ ] `SetMasterVolume(s bus, d value)` / `SetMasterMute(s bus, b muted)`
- [ ] `SetFilterEnabled(s target, s stage, b enabled)` — `target` = kanal id / `mic` / `stream_mic` / `personal` / `stream`
- [ ] `SetFilterParam(s target, s stage, s port, d value)`
- [ ] `SetEqBand(s target, i band, s field, d value)` — EQ için kolaylık metodu
- [ ] `LoadProfile(s target, s name)` / `SaveProfile(s target, s name)` / `DeleteProfile` / `RenameProfile`
- [ ] `ListProfiles(s target) -> s`
- [ ] `SetProfileFavorite(s target, s name, i slot)`
- [ ] `SetChannelDevice(s bus, s device)` — Personal/Stream çıkış cihazı, canlı
- [ ] `SetMicDevice(s chain, s device)`
- [ ] `AddChannel(s name, s color) -> s` / `RemoveChannel(s channel)` — yapısal, restart tetikler
- [ ] `MoveStream(u stream_id, s channel)` — anlık taşıma
- [ ] `SetRule(s match_key, s pattern, s channel, b is_regex)` / `RemoveRule` / `ListRules`
- [ ] `SetChatMix(d value)` / `SetChatMixConfig(b enabled, s left, s right)`
- [ ] `SubscribeMeters(b on)` — ölçüm sadece talep varken çalışır
- [ ] `Reload()` — config'i diskten yeniden oku (elle düzenleme sonrası)
- [ ] `GetDevices() -> s` — fiziksel sink/source listesi

**Sinyaller:**
- [ ] `StateChanged(s json)` — kısmi delta (tam durum değil), 50 ms debounce
- [ ] `StreamsChanged(s json)` — çalan uygulamalar değişti
- [ ] `LevelsUpdated(s json)` — seviye metreleri (Faz 6), 50 ms'de bir toplu
- [ ] `GraphRebuilt()` — yapısal değişiklik oldu, GUI tam yenilesin
- [ ] `Error(s code, s message)` — eklenti eksik, graf kurulamadı vb.

**Notlar:**
- [ ] Karmaşık yapılar D-Bus struct yerine **JSON string** olarak taşınır — sürüm uyumluluğu ve
      hata ayıklama kolaylığı için. Metot argümanları basit tiplerde kalır
- [ ] Her metot doğrulama yapar; geçersiz argümanda D-Bus hatası döner (daemon çökmez)

### `packaging/sonar-daemon.service`
- [ ] `systemd --user` unit'i, `Type=dbus`, `BusName=io.github.iwhimss.Sonar`
- [ ] `After=pipewire.service wireplumber.service`, `PartOf=pipewire.service`
- [ ] `Restart=on-failure`, `RestartSec=2`
- [ ] `WantedBy=default.target`
- [ ] D-Bus servis dosyası (`io.github.iwhimss.Sonar.service`) → otomatik başlatma

### `cli/__main__.py`
- [ ] `sonar-cli status` — kanallar, fader'lar, aktif profiller, çalan uygulamalar (tablo)
- [ ] `sonar-cli volume <kanal> <personal|stream> <0-100>`
- [ ] `sonar-cli mute <kanal> <personal|stream> [on|off|toggle]`
- [ ] `sonar-cli profile <kanal> [<ad>]` — argümansız: listeler
- [ ] `sonar-cli route <uygulama> <kanal>` — kural ekler
- [ ] `sonar-cli rules [list|remove]`
- [ ] `sonar-cli chatmix <0-100>`
- [ ] `sonar-cli devices`
- [ ] `--json` bayrağı (betikleme için)
- [ ] Daemon çalışmıyorsa anlaşılır hata + `systemctl --user start sonar-daemon` önerisi

---

## Doğrulama

```bash
systemctl --user daemon-reload && systemctl --user start sonar-daemon
busctl --user introspect io.github.iwhimss.Sonar /io/github/iwhimss/Sonar
busctl --user call io.github.iwhimss.Sonar /io/github/iwhimss/Sonar \
       io.github.iwhimss.Sonar GetState

sonar-cli status
sonar-cli volume game personal 50     # kulaklıkta anında duyulur, kesinti yok
sonar-cli profile game                # profilleri listeler
```

- `busctl --user monitor io.github.iwhimss.Sonar` ile sinyaller akıyor mu
- Daemon'u öldür → systemd 2 sn içinde geri getiriyor, ses düzeni bozulmuyor
- Oturumu kapat/aç → daemon otomatik başlıyor, kanallar hazır

---

## Tamamlanma kriteri

Daemon systemd altında çalışıyor, tüm D-Bus metotları `busctl` ile çağrılabiliyor,
`sonar-cli` ile GUI olmadan tam kontrol mümkün.
