# Faz 11 — Paketleme ve dağıtım

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 10
**Çıktı:** `packaging/`, ilk sürüm etiketi

---

## Amaç

Projeyi "klonlayıp çalıştırılan bir betik" olmaktan çıkarıp kurulabilir bir uygulamaya
dönüştürmek.

---

## Faz 4'ten devreden

- [ ] `sonar-daemon.service`'i gerçekten kurup `systemctl --user enable --now sonar-daemon`
      ile doğrula. Unit Faz 4'te yazıldı ama `/usr/bin/sonar-daemon` gerektirdiği için
      systemd altında denenmedi
- [ ] Oturum kapat/aç → daemon otomatik başlıyor mu, kanallar hazır mı
- [ ] Daemon'u öldür → systemd 2 sn içinde geri getiriyor mu

---

## Görevler

### Arch / CachyOS paketi
- [ ] `packaging/PKGBUILD`
  - `depends`: `pipewire`, `pipewire-pulse`, `wireplumber`, `pyside6`, `python-numpy`, `lsp-plugins-lv2`
  - `optdepends`:
    - `deepfilter-ladspa` — AI gürültü engelleme
    - `calf` — ek efekt eklentileri
    - `qpwgraph` — graf hata ayıklama
  - `makedepends`: `python-build`, `python-installer`, `python-hatchling`
- [ ] `.SRCINFO` üretimi, yerel `makepkg -si` testi
- [ ] (Opsiyonel, sonra) AUR'a `sonar-linux` olarak gönderim

### D-Bus etkinleştirme (Faz 39'dan devreden)
- [ ] `packaging/io.github.iwhimss.Sonar.service` gerçekten kurulsun
      (`/usr/share/dbus-1/services/`). Kuruluyken arayüz daemon'ı **kendisi** kaldırıyor;
      kurulu değilken "Servisi başlat" düğmesi süreci doğrudan başlatıyor
- [ ] `Exec=` yolu paketin kurduğu `sonar-daemon` ile eşleşmeli
- [ ] Paket kaldırılırken (`post_remove`) uyarı: sanal kanallar kaldırılmadıysa
      `sonar-cli uninstall` önerilsin

### Çeviri katalogu
- [ ] `src/sonar/i18n/*.json` pakete girdiği doğrulansın
      (`pyproject.toml` `force-include` var; `makepkg` sonrası dosyalar yerinde mi)

### `sonar-uninstall` — ayrı kaldırıcı (test turu 6 isteği)

Kullanıcı: *"Kaldırma kısmını uygulama içerisine gömmüşsün. Fakat istediğim bu değil.
Bunun yerine ayrı bir uygulama gibi olsun. Bu çalıştığında terminalde bir kod çalıştırsın.
Kullanıcı eğer onay verirse sonar programıyla alakalı şeyleri tamamen silsin."*

- [ ] Terminalde çalışan ayrı araç: ne silineceğini listeler, **onay ister**, sonra
      sanal kanalları söker, `~/.config/sonar` ve `~/.local/state/sonar`'ı siler,
      systemd unit'ini kapatır, udev kuralı ve paket için `sudo` komutlarını çalıştırır
- [ ] Yedek **almaz** — kullanıcının açık isteği
- [ ] `.desktop` girdisi (`Terminal=true`), uygulama menüsünden de açılabilsin
- [ ] Uygulama içindeki pencere geri alınabilir "sanal kanalları kaldır"a indirgenir;
      adı da onu söyler

### Masaüstü entegrasyonu
- [ ] `packaging/io.github.iwhimss.Sonar.desktop`
      — kategori `AudioVideo;Audio;Mixer;`, `StartupWMClass` doğru ayarlı
- [ ] Uygulama ikonu — SVG, köşesiz tasarım diliyle uyumlu, 16/24/32/48/64/128/256 px
- [ ] `packaging/io.github.iwhimss.Sonar.metainfo.xml` (AppStream — yazılım merkezlerinde görünür)
- [ ] `packaging/sonar-daemon.service` kurulumu (`/usr/lib/systemd/user/`)
- [ ] D-Bus servis dosyası (`/usr/share/dbus-1/services/`) — daemon talep üzerine başlar
- [ ] Kurulum sonrası mesajı: `systemctl --user enable --now sonar-daemon`

### İlk çalıştırma sihirbazı
- [ ] Gerekli LV2/LADSPA eklentilerini doğrula; eksikse hangi paketi kuracağını göster
      (kopyalanabilir `pacman` komutuyla)
- [ ] Fiziksel çıkış ve mikrofon cihazını seçtir
- [ ] Önerilen yönlendirme kurallarını göster, kullanıcı onaylasın
- [ ] "Varsayılan çıkışı Sonar yap" sorusunu açıkça sor (varsayılan: hayır)
- [ ] OBS kullanıcısı mısın? → evetse `docs/OBS.md`'ye kısa yol

### Sürüm
- [ ] Sürümleme: SemVer, `v1.0.0`
- [ ] `CHANGELOG.md`
- [ ] `git tag v1.0.0` + `gh release create` (ekran görüntüleri ve kurulum notlarıyla)
- [ ] README rozetleri: lisans, sürüm, platform

### Geliştirici deneyimi
- [ ] `just` veya `Makefile`: `dev` (daemon + GUI birlikte), `test`, `lint`, `pkg`
- [ ] Kurulum yapmadan çalıştırma: `python -m sonar.daemon` / `python -m sonar.gui`
- [ ] (Opsiyonel) GitHub Actions: `ruff` + `pytest` (headless testler)

---

## Doğrulama

```bash
cd packaging && makepkg -si
systemctl --user enable --now sonar-daemon
systemctl --user status sonar-daemon      # aktif
# Uygulama menüsünden "Sonar" ile aç
```

- Temiz bir kullanıcı hesabında sıfırdan kurulum çalışıyor mu
- Eksik eklentiyle kurulum → sihirbaz doğru yönlendiriyor mu
- Paket kaldırıldığında sanal cihazlar temizleniyor mu (daemon durunca)
- `.desktop` girdisi doğru ikon ve adla görünüyor mu

---

## Tamamlanma kriteri

`makepkg -si` ile kurulan, uygulama menüsünden açılan, systemd ile otomatik başlayan,
eksik bağımlılıkları kendisi bildiren bir v1.0.0 paketi.
