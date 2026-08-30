# Katkı rehberi

## Geliştirme ortamı

```bash
git clone https://github.com/iwhimss/sonar.git
cd sonar
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Sistem gereksinimleri: PipeWire 1.0+, WirePlumber 0.5+, `lsp-plugins-lv2`.
Opsiyonel: `deepfilter-ladspa`, `calf`, `qpwgraph`.

## Çalıştırma

```bash
python -m sonar.daemon      # daemon (systemd kurulumu olmadan)
python -m sonar.gui         # arayüz
python -m sonar.cli status  # CLI
```

Graf'ı elle incelemek için:

```bash
python -m sonar.engine.confgen > /tmp/graph.conf
pipewire -c /tmp/graph.conf &
qpwgraph
```

## Kalite kontrolleri

Her commit öncesi:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
pytest -q
```

## Kod stili

- Satır uzunluğu 100
- Tam tip anotasyonu — `core/` ve `engine/` katmanlarında zorunlu
- `core/` **saf** kalmalı: yan etkisiz, PipeWire'dan bağımsız, birim testlerle kaplı
- Yan etkiler (alt süreç, dosya G/Ç, D-Bus) `engine/` ve `daemon/` katmanlarında
- Kullanıcıya görünen metinler Türkçe; kod, yorumlar ve commit mesajları da Türkçe

## Yeni bir efekt eklentisi eklemek

1. `core/dsp/registry.py` içine bir `PluginSpec` ekle: URI/yol, port sembolleri,
   her portun `min`/`max`/`default`/`scale` (lin|log|db)/`unit` bilgisi
2. Port bilgilerini eklentinin TTL dosyasından doğrula:
   `grep 'lv2:symbol' /usr/lib/lv2/<eklenti>.lv2/<dosya>.ttl`
3. Zincire yeni bir aşama gerekiyorsa `core/dsp/chain.py`'de tanımla
4. GUI paneli ekle (`gui/qml/`)
5. Eklenti kurulu değilken uygulamanın çökmediğini doğrula

## Planlama

Proje faz bazlı ilerliyor. Yol haritası ve her fazın görev listesi [`.plan/`](.plan/)
klasöründe; genel durum [`.plan/00-overview.md`](.plan/00-overview.md) içinde.

Bir faza katkı yaparken o fazın kutucuklarını işaretle ve `00-overview.md`'deki durum
tablosunu güncelle.

## Sorun bildirimi

Sorun bildirirken şunları ekleyin:

```bash
pipewire --version && wireplumber --version
pactl list short sinks && pactl list short sources
journalctl --user -u sonar-daemon -n 100
```
