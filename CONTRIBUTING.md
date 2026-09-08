# Katkı

## Geliştirme ortamı

```bash
git clone https://github.com/iwhimss/sonar && cd sonar
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Çalıştırmak için PipeWire araçları ve LSP eklentileri gerekir:

```bash
sudo pacman -S pipewire wireplumber lsp-plugins-lv2
paru -S deepfilternet-plus-bin   # isteğe bağlı (AUR)
```

## Kontroller

```bash
ruff check src/ tests/     # lint
ruff format src/ tests/    # biçimlendirme
pytest                     # 715 test, ~12 sn
```

Üçü de temiz olmadan commit etmeyin.

## Testleri sisteminizi kirletmeden çalıştırmak

Testlerin hiçbiri gerçek PipeWire'a dokunmaz; süreçler sahtelenir. Elle uçtan uca denemek
isterseniz ayrı bir XDG dizini kullanın, böylece kendi yapılandırmanız bozulmaz:

```bash
mkdir -p /tmp/sonar-test/{config,state}
XDG_CONFIG_HOME=/tmp/sonar-test/config XDG_STATE_HOME=/tmp/sonar-test/state \
  python -m sonar.daemon.service --log debug
```

Graf sürecini elle görmek için:

```bash
python -m sonar.engine.confgen > /tmp/graph.conf
pipewire -c /tmp/graph.conf &
qpwgraph                       # bağlantıları gözle doğrula
```

## Kod düzeni

| Katman | Kural |
|---|---|
| `core/` | **Saf.** PipeWire, Qt, dosya sistemi yok (yalnızca `config.py` diske yazar). |
| `engine/` | PipeWire ile konuşur. Qt yok — `subprocess` + iş parçacığı. |
| `daemon/` | `api.py` saf iş mantığı; `dbus_iface.py` ince sarmalayıcı; `service.py` Qt döngüsü. |
| `gui/` | Qt/QML. Mantık yok — her şey D-Bus üzerinden. |

Bu ayrım testlerin çoğunun gerçek ses altyapısı olmadan çalışmasını sağlıyor.

## Tasarım kuralları

* **Köşe yuvarlatma yok.** `radius`, `Gradient`, `DropShadow` QML dosyalarında yasak;
  `tests/test_qml.py` bunu denetliyor.
* **Filtre parametreleri insan biriminde** saklanır (dB, ms, oran), eklenti port biriminde
  değil. Dönüşüm yalnızca `core/dsp/params.py` içinde.
* **`graph.conf` profilden bağımsız.** Conf'a nötr değerler yazılır; gerçek değerler canlı
  yazımla uygulanır. Aksi hâlde her EQ dokunuşu grafı yeniden kurar ve ses kesilir.
  `tests/test_confgen.py` bu ayrımı test ediyor.

## Yeni bir efekt eklentisi eklemek

1. `core/dsp/registry.py` içine bir `PluginSpec` ekleyin: URI, ses portları, kontrol
   portlarının sembol/min/max/varsayılan bilgisi.
2. `tests/test_registry.py`'deki çapraz doğrulama testine ekleyin — katalog kurulu
   eklentinin TTL'iyle karşılaştırılır, böylece bir sürüm yükseltmesi port aralıklarını
   kaydırırsa test kırılır.
3. `core/dsp/params.py` içinde insan birimi → port eşlemesini yazın.
4. `core/model.py`'deki `FilterStage` ve `CHAIN_ORDER`'a ekleyin.

**Uyarı:** eklentinin varsayılanlarına güvenmeyin. Ölçtük: LSP limiter'ın `boost` ve `alr`
portları varsayılan açık geliyor ve `th`'yi tavan olmaktan çıkarıyor; LSP ekolayzerinin FFT
analizörleri bypass'ta bile çalışıp CPU'yu üçe katlıyor. Yeni bir eklenti eklerken boştaki
CPU'yu ölçün.

## Ölçerek çalışın

Bu projede "çalışıyor gibi görünüyor" yeterli sayılmadı. Ses değişiklikleri kulakla değil,
sinyal basıp kaydı numpy ile ölçerek doğrulandı — birkaç kez bu yaklaşım sessiz hataları
yakaladı (bkz. `.plan/` dosyalarındaki "Yol boyunca yakalananlar" bölümleri).

Ses davranışını değiştiren bir katkı gönderirken ölçümünüzü de ekleyin.

## Commit ve PR

* Commit mesajları Türkçe, açıklayıcı ve **neden**i anlatan gövdeyle.
* Faz planı `.plan/` altında; ilgili faz dosyasındaki kutucukları güncelleyin.
* Ölçüm yaptıysanız sayıları `docs/PERFORMANCE.md`'ye işleyin.
