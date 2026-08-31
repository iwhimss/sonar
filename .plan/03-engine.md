# Faz 3 — Engine: süreç yönetimi ve canlı kontrol

**Durum:** ⚪ Bekliyor
**Bağımlılık:** Faz 2
**Çıktı:** `src/sonar/engine/{pwstate,supervisor,control}.py`

---

## Amaç

Üretilen `graph.conf`'u canlı tutmak, PipeWire grafının durumunu izlemek ve tüm canlı
kontrolleri (volume, parametre, cihaz taşıma) kesintisiz uygulamak.

---

## Görevler

### `engine/pwstate.py` — graf durumu izleyicisi
- [ ] `pw-dump -m` alt süreci (`QProcess`), satır tabanlı JSON olay akışı ayrıştırma
- [ ] Kısmi JSON tamponlama (olay sınırları satır sınırıyla örtüşmeyebilir)
- [ ] `nodes: dict[str, int]` — `node.name → id` haritası
- [ ] `streams: list[StreamInfo]` — çalan sink-input'lar
      (`id`, `app_binary`, `app_name`, `media_name`, `target_node`, `pid`)
- [ ] `devices: list[DeviceInfo]` — fiziksel sink/source envanteri (GUI'deki cihaz seçicileri için)
- [ ] Sinyaller: `nodes_changed`, `streams_changed`, `devices_changed`
- [ ] Kopma hâlinde otomatik yeniden başlatma + tam yeniden senkron (`pw-dump` tek atış)
- [ ] PipeWire tamamen yeniden başlarsa (soket kaybolur) → geri gelene kadar bekle, sonra graf'ı yeniden kur

### `engine/supervisor.py` — graf süreci yaşam döngüsü
- [ ] `graph.conf` → `~/.local/state/sonar/graph.conf` (atomik yazım)
- [ ] `pipewire -c <conf>` sürecini başlat/durdur/izle (`QProcess`)
- [ ] `reconcile(new_cfg)`:
  1. Yeni conf metnini üret
  2. **Metin değiştiyse** → yaz + süreci yeniden başlat (yapısal değişiklik) → `GraphRebuilt` sinyali
  3. **Değişmediyse** → yalnızca canlı fark uygula (parametre + volume + mute + cihaz)
- [ ] Yeniden başlatma sonrası: node id'leri yeniden çözülene kadar bekle, sonra **tüm** canlı
      durumu (tüm profillerin parametreleri, tüm fader'lar) baştan uygula
- [ ] Çökme hâlinde exponential backoff (1s, 2s, 4s… max 30s), 5 ardışık çökmede durup hata bildir
- [ ] Temiz kapanış: süreç öldürülür; `take_over_default_sink` açıksa varsayılan sink kullanıcının
      fiziksel cihazına geri alınır

### `engine/control.py` — canlı kontrol arayüzü
- [ ] `set_param(node_name, port, value)` — `pw-cli s <id> Props '{ params = [ "<port>" <v> ] }'`
- [ ] `set_params(node_name, {port: value, ...})` — tek çağrıda toplu yazım (profil geçişi için kritik)
- [ ] `set_volume(node_name, v)` / `set_mute(node_name, bool)` — **`wpctl` değil**,
      `pw-cli s <id> Props '{ channelVolumes = [...] }'`. Faz 2'de ölçüldü: `wpctl set-volume`
      kübik ölçek uyguluyor (0.5 → -18 dB), modelimiz ise lineer tutuyor (0.5 → -6.02 dB)
- [ ] `move_stream(stream_id, target_node)` — `pactl move-sink-input`
- [ ] `set_default_sink(node_name)` — `wpctl set-default`
- [ ] **Debounce + toplu yazım:** fader sürüklerken saniyede 60 süreç açılmaz.
      20 ms penceresinde aynı node'a gelen yazımlar birleştirilir, tek çağrıda gönderilir.
      Son değer her zaman uygulanır (trailing edge garantisi)
- [ ] Süreç açma maliyeti ölçülür; yüksekse kalıcı `pw-cli` oturumu (stdin'e komut yazma) denenir
- [ ] Tüm alt süreç çağrıları zaman aşımlı ve hata toleranslı — biri başarısız olursa loglanır,
      daemon çökmez

---

## Doğrulama

```bash
python -c "
from sonar.engine.supervisor import Supervisor
from sonar.core.config import load
s = Supervisor(); s.reconcile(load())
"
# başka bir terminalde:
pw-dump | grep sonar_game        # node'lar ayakta
```

- Fader'ı Python'dan hızlıca 100 kez değiştir → tık/pop sesi yok, CPU makul
- Profil değiştir → conf değişmedi, restart olmadı, ses kesilmedi
- Kanal ekle → conf değişti, ~200 ms kesinti, sonra tüm durum geri geldi
- `pkill -f "pipewire -c.*sonar"` → supervisor 1 sn içinde geri getirdi
- `systemctl --user restart pipewire` → graf kendini yeniden kurdu

---

## Tamamlanma kriteri

Daemon olmadan, doğrudan Python'dan graf kurulup canlı kontrol edilebiliyor;
PipeWire yeniden başlatıldığında ve graf süreci öldürüldüğünde kendini toparlıyor.
