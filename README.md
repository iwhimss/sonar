# Sonar

**Linux için kanal tabanlı ses mikseri.** SteelSeries GG'nin Sonar modülünün yaptığı işi
PipeWire üzerinde native olarak yapar: uygulamaları adlandırılmış kanallara ayırır, her
kanala kendi EQ ve filtre zincirini verir ve **kulaklığına giden ses ile yayına giden sesi
birbirinden ayırır.**

![Mikser](docs/reference/sonar-mixer.png)

---

## Neden

Linux'ta EasyEffects sistem geneli **tek** bir efekt zinciri sunuyor, qpwgraph elle
yamalama yaptırıyor. İkisinde de "kanal" kavramı ve kişisel/yayın miks ayrımı yok.

Sonar bunları veriyor:

* **Kanallar** — Game, Chat, Media, Aux (+ istediğin kadarını ekle). Uygulamalar açıldıkları
  anda doğru kanala düşer.
* **Çift miks** — her kanalın iki bağımsız fader'ı var: 🎧 kulaklık, 📡 yayın. Telifli
  müziği kendin duyarsın, yayında duyulmaz.
* **Kanal başına DSP** — EasyEffects'in kullandığı LSP eklentileriyle aynı kalitede
  ekolayzer, noise gate, kompresör, limiter. Mikrofonda ayrıca DeepFilterNet AI gürültü
  engelleme.
* **Profiller** — bir kanal için istediğin kadar profil kaydet, aralarında **anında ve
  kesintisiz** geçiş yap. (Ölçüldü: 3.4 saniyede 12 geçiş, 0 kesinti.)
* **OBS uyumu** — birleşik yayın miksi ve kanal başına ayrı yakalama noktaları.
* **ChatMix** — tek slider'la oyun ↔ sohbet dengesi. Yalnızca kulaklığını etkiler, yayını
  bozmaz.

---

## Ekranlar

| Mikser | Kanal FX |
|---|---|
| ![](docs/reference/sonar-mixer.png) | ![](docs/reference/sonar-fx-game.png) |

Mikrofon sayfası, AI gürültü engelleme açıkken Noise Gate'i devre dışı bırakır:

![Mikrofon](docs/reference/sonar-fx-mic.png)

---

## Kurulum

### Arch / CachyOS

```bash
sudo pacman -S pipewire wireplumber lsp-plugins-lv2 pyside6 python-numpy
paru -S deepfilter-ladspa          # isteğe bağlı: AI gürültü engelleme

git clone https://github.com/iwhimss/sonar && cd sonar
pip install --user .
```

### Kurmadan denemek

Sisteme hiçbir şey kurmadan, depodan çalıştırabilirsin:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .

./scripts/sonar-dev start     # daemon
./scripts/sonar-dev gui       # arayüz
./scripts/sonar-dev status
./scripts/sonar-dev stop      # her şeyi durdur
```

Daemon durduğunda çalan uygulamalar **kendiliğinden** varsayılan cihaza geri döner; ses
kesilmez.

> **EasyEffects çalışıyorsa önce durdur** (`pkill easyeffects`) — ikisi aynı anda
> çalışamaz, bkz. [Bilinen sınırlar](#bilinen-sınırlar).

### Servisi başlat

```bash
mkdir -p ~/.config/systemd/user
cp packaging/sonar-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now sonar-daemon
```

Arayüzü aç:

```bash
sonar
```

### Gereksinimler

| Bileşen | En az |
|---|---|
| PipeWire | 1.0 (1.6 ile geliştirildi ve test edildi) |
| WirePlumber | 0.5 |
| Python | 3.11 |
| PySide6 | 6.6 |
| `lsp-plugins-lv2` | 1.2 — **zorunlu**, DSP zinciri buna dayanıyor |
| `deepfilter-ladspa` | isteğe bağlı, yalnızca AI gürültü engelleme için |

Kurulu olmayan bir eklenti zincirden **sessizce düşer** — graf yine kurulur, o efekt
görünmez.

---

## Hızlı başlangıç

```bash
sonar-cli status                       # kanallar, fader'lar, çalan uygulamalar
sonar-cli volume game personal 70      # oyun sesini kulaklıkta %70 yap
sonar-cli volume media stream 0        # müziği yayından çıkar
sonar-cli presets game                 # hazır preset'ler
sonar-cli profile game "FPS Footsteps" # anında geçiş
sonar-cli meters                       # terminalde canlı seviye metreleri
```

Kanallar ve profiller:

```bash
sonar-cli channel add "Müzik"                    # yeni çıkış kanalı
sonar-cli channel add "Podcast" --direction input # yeni giriş kanalı (sanal mikrofon)
sonar-cli channel remove aux                     # kullanmadığın kanalı sil

sonar-cli new game "CS2"                # sıfırdan düz bir profil, hemen etkin
sonar-cli favorite add game "CS2"       # hızlı geçiş için favorilere
sonar-cli favorite list game

sonar-cli obs game on                   # bu kanalı OBS'e ayrı bir kaynak olarak ver
```

Kulaklığın için AutoEQ düzeltme eğrisi varsa doğrudan içe aktarabilirsin:

```bash
sonar-cli import game ~/İndirilenler/HD650\ ParametricEQ.txt --name HD650
```

AutoEQ, Equalizer APO (Windows) ve EasyEffects preset'leri destekleniyor; biçim dosyanın
içeriğinden bulunuyor. Arayüzde de "İçe aktar" / "Dışa aktar" düğmeleri var.

**Profillerde "kaydet" yok.** Yaptığın her değişiklik aktif profile yazılır ve yarım
saniye içinde diske geçer. Yeni bir varyant istiyorsan **＋ Yeni profil** de: isim sorar,
sıfırdan düz bir profil açar, eskisine dokunmaz. Gömülü bir preseti kurcalarsan
kendiliğinden `<ad> (özel)` kopyası açılır — preset bozulmaz.

---

## Kanallar ve sanal cihazlar

Her kanal bir sanal ses cihazı üretir ve adı yönünü söyler:

| Cihaz | Ne işe yarar |
|---|---|
| `Sonar Game — Virtual Output` | Uygulamalar buraya çalar (çıkış kanalı) |
| `Sonar Mic — Virtual Input` | İşlenmiş mikrofon (giriş kanalı) — Discord bunu seçer |
| `Sonar Stream Mix — Virtual Input` | Yayın miksi — **OBS bunu seçer** |
| `Sonar Personal Mix — Virtual Output` | Kulaklığına giden miks |

Kanal eklerken **çıkış** mı **giriş** mi olduğunu seçersin; buna göre sink mi source mu
oluşturulacağı belirlenir. Her kanal silinebilir — kullanmadığın Aux'u atabilirsin.
Tek kısıt: en az bir çıkış ve en az bir giriş kanalı kalmalı.

Kanal başına ayrı OBS kaynağı **varsayılan olarak kapalı**. Açık olsaydı her çıkış kanalı
sistemin mikrofon listesinde de görünürdü ("Media neden mikrofon?"). Yayında kanal başına
ayrı track istiyorsan `sonar-cli obs <kanal> on` ile açarsın.

---

## Nasıl çalışıyor

Üç süreç:

```
sonar (arayüz)  ──D-Bus──▶  sonar-daemon  ──▶  pipewire -c graph.conf
                                                (tüm sanal cihazlar)
```

Arayüz kapalıyken ses düzeni bozulmaz — grafı daemon taşır. Ayrıntı için
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Ölçümler

Her sayı gerçek donanımda ölçüldü, ayrıntısı [docs/PERFORMANCE.md](docs/PERFORMANCE.md):

| | |
|---|---|
| Eklenen gecikme | **1.1 ms** (ölçüm gürültüsünün içinde) |
| Ekolayzer doğruluğu | çizilen eğri ile gerçek yanıt arasında **0.01 dB** |
| Profil geçişi | 12 geçişte **0 kesinti, 0 tık** |
| Boştaki CPU | %5–7 (mikser açıkken %12–13) |
| Bellek | ~180–200 MB |
| DeepFilterNet açıkken | **+%43** — pahalı, bilerek kullan |

---

## Belgeler

* [ARCHITECTURE.md](ARCHITECTURE.md) — ses grafı, D-Bus API, tasarım kararları
* [docs/OBS.md](docs/OBS.md) — yayın kurulumu, çok track'li kayıt
* [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — tüm ölçümler
* [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — sorun giderme
* [CONTRIBUTING.md](CONTRIBUTING.md) — geliştirme ortamı
* [.plan/](.plan/) — faz faz geliştirme günlüğü ve alınan kararların gerekçeleri

---

## Bilinen sınırlar

* **EasyEffects ile birlikte çalışmaz.** İkisi de sistem geneli ses işlemeye çalışıyor;
  EasyEffects servis kipindeyken Sonar'ın çıkışını kendi zincirine çekiyor. Sonar zaten
  aynı eklentilerle aynı işi kanal başına yapıyor.
* **Donanım ChatMix tekeri okunmuyor.** Cihaz tespiti ve udev kuralı hazır ama HID rapor
  biçimi çözülmedi; yazılım ChatMix'i çalışıyor.
* Kanal ekleme/silme, cihaz değiştirme ve OBS kaynağı açma/kapama grafı yeniden kurar
  (~200 ms sessizlik). Ses seviyesi, EQ, filtre ve profil değişimi kesintisizdir.
* Kanal seviye metreleri kanalın **girişini** ölçer (DSP ve fader öncesi) — uygulamanın
  ne kadar yüksek çaldığını gösterir, EQ'dan etkilenmez.

---

## Lisans

GPL-3.0. Katkılar açık — [CONTRIBUTING.md](CONTRIBUTING.md).
