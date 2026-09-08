# Faz 11 — Paketleme, kısayol, otomatik başlatma, kaldırıcı

**Durum:** 🟡 Kurulum testi kullanıcıda
**Bağımlılık:** Faz 50 (test turu 8 sorunsuz geçti)
**Çıktı:** `packaging/PKGBUILD`, `.desktop`, ikon, `sonar-uninstall`, otomatik başlatma

---

## Amaç

Kullanıcının isteği (test turu 8): *"Paketleme işini yapalım. Uygulamayı normal bir
uygulama gibi kısayolla açmak istiyorum. Bu uygulamayı son kullanıcıya uygun yapmalıyız.
Başka birisi de kolaylıkla kurabilmeli repo üzerinden public yaptığımda… Bilgisayar
açıldığında otomatik olarak başlaması için de bir ayar yapalım tıpkı SteelSeries GG gibi.
İsteğe bağlı açılsın veya kapatılsın. Arkaplanda çalışsın."*

Bugün proje hâlâ `./scripts/sonar-dev` ile depodan çalışıyor: uygulama menüsünde yok,
oturum açılışında başlamıyor, kaldırmanın tek yolu elle dosya silmek.

---

## Görevler

### Sürüm ve paket
- [x] `version` `0.1.0.dev0` → **`0.1.0`**. İlk gerçek sürüm; dış kullanıcı yok, abartılı
      bir 1.0 iddiası doğru olmaz
- [x] `packaging/PKGBUILD`
  - `depends`: `pipewire`, `pipewire-pulse`, `wireplumber`, `pyside6`, `python-numpy`,
    `lsp-plugins-lv2`
  - `optdepends`: `calf` ve `zam-plugins-ladspa` (efekt kataloğunun bir kısmı), 
    `deepfilternet-plus-bin` (AI gürültü engelleme), `qpwgraph` (hata ayıklama).
    Adlar `pacman -Qo` ile ölçüldü: `zam-plugins` meta paket, LADSPA vermiyor;
    `deepfilter-ladspa` diye bir paket ne depoda ne AUR'da var.
  - `makedepends`: `python-build`, `python-installer`, `python-hatchling`
- [x] `makepkg --printsrcinfo` geçiyor; tekerlek `python -m build` ile derlendi ve içeriği doğrulandı
- [x] Kurulan dosyalar: `sonar`, `sonar-daemon`, `sonar-cli`, `sonar-uninstall`,
      systemd user unit, D-Bus servis dosyası, udev kuralı, `.desktop`, ikon

### Kısayol ve ikon
- [x] `packaging/io.github.iwhimss.Sonar.desktop` — uygulama menüsünde "Sonar"
- [x] `packaging/io.github.iwhimss.Sonar.svg` — tasarım dilinde, yuvarlatma yok
- [x] Pencere ve tepsi ikonu tema ikonundan değil **kendi** ikonumuzdan gelsin
      (bugün `QIcon.fromTheme("audio-volume-high")`)

### Otomatik başlatma (SteelSeries GG gibi)
- [x] `Settings.autostart_daemon` — oturum açılışında ses düzeni hazır olsun
      (`systemctl --user enable/disable sonar-daemon`)
- [x] `Settings.autostart_gui` — arayüz de açılsın, **tepside** (XDG autostart girdisi,
      `sonar --minimized`)
- [x] `sonar --minimized` bayrağı ve mevcut `start_minimized` ayarının bağlanması —
      alan modelde vardı, hiç kullanılmıyordu
- [x] Ayarlar penceresinde iki kutucuk; depodan çalıştırırken unit kurulu olmadığı için
      başarısız olursa **söylensin**, sessizce yutulmasın

### `sonar-uninstall`
- [x] Terminalde çalışan ayrı araç: ne silineceğini listeler, **onay ister**
- [x] Sanal kanalları söker, varsayılan cihazı geri verir, `~/.config/sonar` ve
      `~/.local/state/sonar`'ı siler, systemd unit'ini ve autostart girdisini kaldırır
- [x] udev kuralı ve paketin kendisi için `sudo` komutlarını **çalıştırmayı önerir**
- [x] Yedek almaz (kullanıcının açık isteği)
- [x] `.desktop` girdisi (`Terminal=true`) — menüden de açılabilsin
- [x] Uygulama içindeki pencere zaten geri alınabilir kanal kaldırma; `sonar-uninstall` kalıcı olanı yapıyor. İkisi ayrı "sanal kanalları kaldır"a indirgenir

### Dokümantasyon
- [x] `README.md` — public depo için kurulum: `makepkg -si`, ilk açılış, otomatik başlatma
- [x] `docs/TROUBLESHOOTING.md` — "oturum açılışında başlamıyor"
- [x] `ARCHITECTURE.md` — paketleme ve oturum açılışı bölümü

---

## Ölçüm

Yapılabilenler (sudo gerektirmeyenler):

- [x] `makepkg --printsrcinfo` PKGBUILD'i ayrıştırıyor
- [x] Tekerlek derleniyor: 77 girdi, dört giriş noktası, 29 QML dosyası, iki dil kataloğu
- [x] `python -m installer` tekerleği hedef dizine kuruyor
- [x] `desktop-file-validate` iki `.desktop` dosyasını da geçiyor
- [x] `sonar-uninstall` listeyi doğru basıyor ve onay verilmezse **hiçbir şeye dokunmuyor**
- [x] Ayarlar penceresi: kurulu değilken kutucuklar pasif ve nedeni yazıyor
- [x] 1036 test geçiyor, `ruff` temiz

Kullanıcının makinesinde (sudo gerekiyor):

- [ ] `cd packaging && makepkg -si`
- [ ] `sonar` uygulama menüsünde görünüyor ve tıklayınca açılıyor
- [ ] Ayarlar → Oturum açılışında başlat kutucukları artık **etkin**
- [ ] Oturum kapat/aç → kanallar hazır
- [ ] `sonar-uninstall` → `pw-dump | grep sonar_` boş, `~/.config/sonar` yok

### Derleme sırasında bulunan hata

Paket **ilk kez** burada derlendi ve `pyproject.toml` tekerleği hiç kuramıyordu:

```
ValueError: A second file is being added to the wheel archive at the same path:
`sonar/i18n/en.json`
```

`force-include` ile eklenen QML ve JSON dosyaları hatchling'in `packages` ayarıyla zaten
alınıyordu. `force-include` tamamen kaldırıldı. Bu satırlar Faz 37'den beri duruyordu ama
paket hiç derlenmediği için fark edilmemişti.
