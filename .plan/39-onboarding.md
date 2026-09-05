# Faz 39 — Kurulum sihirbazı ve kaldırıcı

**Durum:** 🟢 Tamamlandı
**Bağımlılık:** Faz 38
**Çıktı:** `Welcome.qml`, `UninstallDialog.qml`, `api.provision/deprovision`,
`sonar-cli install/uninstall`

---

## Amaç

Kullanıcının isteği (test turu 5): *"Uygulama şu an açılırken farklı kodlar vs. girmek
gerekiyor ve direkt olarak sanal kanallar kuruluyor… kısa bir tanıtım ekranı gelsin,
ardından 'sanal kanalları kur' butonu olsun… kaldırmak isterse de bir kaldırıcı yapalım."*

### Bugün ne oluyordu

`SonarApi.start()` koşulsuz `supervisor.reconcile()` çağırıyordu: daemon ayağa kalktığı
anda `default_config()` yazılıp dört kanal + iki bus + iki mikrofon zinciri PipeWire'a
kuruluyordu. Onay hiçbir yerde sorulmuyordu. Bırakma yolu ise yalnızca terminaldeydi
(`scripts/sonar-dev reset`).

GUI daemon'ı **hiç** başlatmıyordu: bağlanamayınca ekrana `systemctl --user start
sonar-daemon` yazıyordu. D-Bus etkinleştirme dosyası yazılmıştı ama kullanılmıyordu.

---

## Görevler

### Durum
- [x] `Settings.provisioned` (şema 6, Faz 37'de eklendi). Göç mevcut kullanıcıları
      "kurulu" sayıyor
- [x] `api.start()` kurulu değilken PipeWire'a **hiç** dokunmuyor. Graf izleyicisi yine
      de çalışıyor: salt okunur ve cihaz listesi kurulum ekranında da lazım
- [x] `get_state()` → `provisioned`; köprüde `bridge.provisioned`.
      Bağlı **değilken** `True` sayılıyor — bilinmeyen durumda kurulum sihirbazı açmak yanlış

### API
- [x] `api.provision()` — kurar, `_structural` ile grafı yeniden inşa eder, teker
      okuyucusunu başlatır, varsayılan çıkışı devralır, **ne kurduğunu** döner
- [x] `api.setup_summary()` — kurulacakların gerçek listesi; kurulumdan önce de çağrılabilir
- [x] `api.deprovision(purge_settings=False)` — grafı söker, varsayılan cihazı geri verir,
      `graph.conf`'u siler; istenirse yapılandırma dizinini de. Root'a ait işleri
      **yapmaz**, komutlarını döner
- [x] D-Bus: `Provision`, `Deprovision`, `SetupSummary` → 57 metot
- [x] `sonar-cli install` / `uninstall [--purge]`
- [x] `sonar-cli status` kurulu değilken bunu açıkça yazıyor ("graf hazır değil" yerine)

### Arayüz
- [x] `Welcome.qml` — dört sayfa: dil, Sonar ne yapar, ne kurulacak, kur
- [x] "Ne kurulacak" sayfası **gerçek** listeyi gösteriyor (`setupSummary`), sabit metin
      değil. Test turu 4'ün OBS karışıklığı tam olarak dokümandaki sabit adın kullanıcının
      makinesinde bulunmamasından çıkmıştı
- [x] Kurulum bloke eden bir çağrı (~1.1 sn ölçüldü); köprü işi bir sonraki olay döngüsü
      turuna atıyor ki ekran önce "Kuruluyor…" yazabilsin
- [x] Başarısızlıkta hata gösteriliyor ve tekrar denenebiliyor
- [x] Ayarlardan "Tanıtımı tekrar göster" — aynı akış, son sayfada "kur" yerine "kapat"
- [x] `UninstallDialog.qml` — ne olacağı madde madde, "ayarları da sil" kutucuğu
      **kapalı** geliyor, sonrasında root gerektiren komutlar kopyalanabilir hâlde

### Daemon'ı arayüzden başlatmak
- [x] `DBusClient.start_service()` — D-Bus etkinleştirmesi (servis dosyası kuruluysa)
- [x] `bridge.startDaemon()` — etkinleştirme olmazsa süreci doğrudan başlatır
- [x] "Servis çalışmıyor" panelinde artık **düğme** var; komut yedek olarak duruyor

### Betik
- [x] `scripts/sonar-dev reset` artık `sonar-cli uninstall`a bağlı — iki ayrı sökme yolu
      tutmak, birinin diğerinden sapması demekti

---

## Ölçüm

Kullanıcının gerçek yapılandırması bir kenara alınıp sıfırdan denendi:

```
daemon başladı            → pw-dump: sonar node = 0        (kanal kurulmadı)
GUI açıldı                → karşılama ekranı, dil sayfası
"Ne kurulacak" sayfası    → 8 gerçek cihaz adı, Sonar Personal Mix … Sonar Stream Mic
"Sanal kanalları kur"     → ok=True, 1.13 sn, sonar node = 40, mikser açıldı
sonar-cli uninstall       → sonar node = 0, varsayılan çıkış geri verildi,
                            ~/.config/sonar yerinde (config.toml, profiles, ui.json)
sonar-cli install         → sonar node = 40
```

Sonra kullanıcının yapılandırması geri kondu; `diff` ile doğrulandı (yalnızca test
sırasında değiştirilen `language` satırı farklıydı, o da geri alındı).
