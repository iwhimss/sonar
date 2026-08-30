# Sonar for Linux

**PipeWire tabanlı kanal mikseri — Linux için SteelSeries Sonar alternatifi.**

> ⚠️ **Durum: geliştirme aşamasında (pre-alpha).** Henüz kullanılabilir bir sürüm yok.
> Yol haritası ve ilerleme için [`.plan/00-overview.md`](.plan/00-overview.md) dosyasına bakın.

---

## Ne işe yarar

Windows'ta SteelSeries GG'nin Sonar modülü, uygulama seslerini ayrı kanallara bölüp her birini
bağımsız olarak eşitlemene ve yayına giden sesle kulaklığına gelen sesi ayırmana izin verir.
Linux'ta bunun dengi bir araç yok: EasyEffects sistem geneli **tek** bir efekt zinciri sunuyor,
qpwgraph elle yamalama yaptırıyor.

Sonar for Linux bu boşluğu dolduruyor:

- 🎚 **Ayrı ses kanalları** — Game, Chat, Media, Aux ve istediğin kadar ek kanal.
  Her biri sistemde gerçek bir sanal ses cihazı olarak görünür.
- 🎧 **Personal Mix / Stream Mix ayrımı** — kulaklığına gelen sesle yayına giden ses
  bağımsız fader'lara sahip. Telifli müziği kendin duyarsın, yayına gitmez.
- 🎛 **Kanal başına EQ ve filtreler** — parametrik EQ, noise gate, compressor, limiter.
  EasyEffects ile **birebir aynı** LV2 eklentileri (LSP Plugins), aynı ses kalitesi.
- 💾 **Kanal başına çoklu profil** — oyun kanalı için CS2'ye ayrı, Arc Raiders'a ayrı
  EQ kaydet, favori slotlarından anında geçiş yap.
- 🎤 **Mikrofon zinciri** — DeepFilterNet ile AI gürültü engelleme, gate, EQ, compressor.
  Uygulamalar için ve yayın için **ayrı** sanal mikrofonlar.
- 📺 **OBS uyumlu** — birleşik Stream Mix'in yanı sıra her kanal ayrı bir yakalama kaynağı
  olarak görünür; OBS'de ayrı track'lere basabilirsin.
- 🖱 **Uygulama yönlendirme** — hangi uygulamanın hangi kanalda olduğunu gör,
  sürükleyerek taşı, kalıcı kural yap.
- ⚡ **Arka planda çalışır** — arayüzü kapatsan bile ses düzeni ayakta kalır.

---

## Tasarım

Sade, modern ve **köşesiz**. Yuvarlatılmış köşe, gradyan ve gölge yok; ayrım ince kenarlıklar
ve yüzey tonlarıyla yapılıyor.

Tasarım referansı olarak SteelSeries GG'nin arayüzü kullanıldı
([`docs/reference/steelseries-gg/`](docs/reference/steelseries-gg/)).

---

## Mimari

Üç parça: arka planda çalışan bir **daemon**, onun yönettiği **PipeWire grafı**, ve D-Bus
üzerinden bağlanan **GUI/CLI** istemcileri.

```
sonar-daemon ──D-Bus──▶ sonar (GUI) · sonar-cli
     │
     ▼
pipewire -c graph.conf     ← tüm sanal cihazlar, DSP zincirleri ve loopback'ler
```

Ses işleme bizim sürecimizde değil, PipeWire'ın kendi `filter-chain` modülünde çalışır —
yani gerçek zamanlı ses yolunda Python yok. Ayrıntılar için
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Gereksinimler

| Bileşen | Minimum |
|---|---|
| PipeWire | 1.0+ (`filter-chain` ve `loopback` modülleriyle) |
| WirePlumber | 0.5+ |
| Python | 3.11+ |
| PySide6 | 6.6+ |
| numpy | 1.26+ |
| LSP Plugins (LV2) | 1.2+ — EQ, gate, compressor, limiter |

**Opsiyonel:**
- `deepfilter-ladspa` — AI gürültü engelleme
- `calf` — ek efekt eklentileri
- `qpwgraph` — graf hata ayıklama

---

## Kurulum

Henüz yayınlanmış bir sürüm yok. Paketleme [Faz 11](.plan/11-packaging.md)'de yapılacak.

---

## Geliştirme

```bash
git clone https://github.com/iwhimss/sonar.git
cd sonar
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check src/ && pytest -q
```

Yol haritası ve her fazın ayrıntılı görev listesi [`.plan/`](.plan/) klasöründe.
Nerede kalındığını görmek için [`.plan/00-overview.md`](.plan/00-overview.md).

---

## Lisans

[GPL-3.0](LICENSE)
