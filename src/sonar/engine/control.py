"""Canlı kontrol: parametre, ses seviyesi, sustur, akış taşıma.

## Neden kalıcı bir `pw-cli` oturumu

Ölçüm (Faz 3, gerçek grafta):

| yöntem | maliyet |
|---|---|
| her yazım için `pw-cli` süreci açmak | **14.03 ms** |
| aynı süreçte 64 portu tek çağrıda yazmak | 12.97 ms |
| **kalıcı `pw-cli` oturumuna stdin'den yazmak** | **0.003 ms** |

İki sonuç çıkıyor:

1. Maliyet tamamen süreç açmakta; yükün büyüklüğü neredeyse ücretsiz. Bu yüzden profil
   geçişi (≈130 port) tek çağrıda gönderilir.
2. Süreç açmak fader sürüklemek için kullanılamaz: 20 ms'lik debounce'la bile saniyede 50
   çağrı × 14 ms = 700 ms CPU demekti. Kalıcı oturum bunu 4600 kat ucuzlatıyor.

Debounce yine de var ama artık zorunluluk değil, nezaket: PipeWire'ın kendi tarafındaki
gereksiz yeniden hesaplamayı azaltıyor.

## Akış taşıma neden `pactl` ile değil

`pactl move-sink-input` **PulseAudio sink-input indeksi** ister; bizim elimizdeki ise
PipeWire **node id**'si. İkisi ayrı numaralandırma (ölçüldü: node 251 ↔ indeks 13163) ve
node id'siyle çağrıldığında komut sessizce `exit 1` veriyor. Yerine PipeWire'ın kendi yolu:

```
pw-metadata <node-id> target.object <hedef node adı>
```

Bu doğrudan node id'siyle çalışıyor ve akışı kesintisiz taşıyor (ölçüldü). Değerin
**tırnaksız** verilmesi şart: `'"sonar_media"'` gibi JSON tırnağı eklendiğinde ad eşleşmiyor
ve WirePlumber akışı sessizce varsayılan cihaza gönderiyor.

## Ses seviyesi neden `wpctl` ile değil

`wpctl set-volume` kübik ölçek uygular (0.5 → -18 dB ölçüldü), modelimiz lineer tutar
(0.5 → -6.02 dB). Doğrudan `Props.channelVolumes` yazıyoruz.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable, Iterable

from sonar.engine.pwstate import GraphState

__all__ = ["Control", "PwCliSession", "format_params", "format_value", "parse_links"]

log = logging.getLogger(__name__)

#: Toplu yazım penceresi. Sürükleme sırasında aynı node'a gelen yazımlar burada birikir.
#:
#: Plan 20 ms diyordu; ölçüm 40 ms'yi gösterdi. 60 Hz'lik gerçekçi bir fader sürüklemesi
#: kaydedilip örnekler arası süreksizlik arandı (1 kHz sinüs; normal adımın 1.5 katını aşan
#: sıçrama = tık), her pencere birkaç kez tekrarlandı:
#:
#: | pencere | tık içeren deneme |
#: |---|---|
#: | 0 ms (biriktirme yok) | 3/3 |
#: | 20 ms | 2/3 |
#: | 30 ms | 2/4 |
#: | **40 ms** | **1/4** |
#:
#: PipeWire seviye değişimini kendi içinde yumuşatıyor — tek seferlik büyük sıçrama
#: (1.0 → 0.1) ve mute **hiç** tık üretmiyor. Sorun yalnızca ardışık yazımların birbirinin
#: rampasını kesmesi. 40 ms bunu belirgin biçimde azaltıyor ama tamamen bitirmiyor; kalan
#: artefakt çok hafif (normal örnek adımının ~2 katı). Tam çözüm için seviye rampasını
#: kendimiz yürütmek gerekebilir — .plan/99-backlog.md'de kayıtlı.
DEFAULT_WINDOW_MS = 40.0

#: Alt süreç çağrılarının zaman aşımı. Aşılırsa loglanır, daemon çökmez.
COMMAND_TIMEOUT = 5.0


def format_value(value: float | bool | int) -> str:
    """SPA-JSON sayı biçimi. Sabit ondalık — `pw-cli` yerel ayara duyarlı olmasın diye."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return f"{float(value):.6f}"


def format_params(params: dict[str, float]) -> str:
    """`{"eq:g_3": 2.0}` → `{ params = [ "eq:g_3" 2.000000 ] }`"""
    body = " ".join(f'"{port}" {format_value(value)}' for port, value in params.items())
    return f"{{ params = [ {body} ] }}"


class PwCliSession:
    """Kalıcı `pw-cli` alt süreci. Ölürse bir sonraki yazımda sessizce yeniden açılır."""

    def __init__(self, command: tuple[str, ...] = ("pw-cli",)) -> None:
        self.command = command
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self.sent: list[str] = []  # testler için; üretimde sadece son komutu tutar
        self._keep_history = False

    def keep_history(self, enabled: bool = True) -> None:
        """Testlerin gönderilen komutları doğrulayabilmesi için."""
        self._keep_history = enabled

    def send(self, line: str) -> bool:
        """Bir `pw-cli` komutu gönderir. Başarı durumunu döndürür, asla yükseltmez."""
        with self._lock:
            if self._keep_history:
                self.sent.append(line)
            for attempt in (1, 2):
                process = self._ensure()
                if process is None:
                    return False
                try:
                    assert process.stdin is not None
                    process.stdin.write(line + "\n")
                    process.stdin.flush()
                    return True
                except (BrokenPipeError, ValueError, OSError):
                    log.warning("pw-cli oturumu koptu, yeniden açılıyor (deneme %d)", attempt)
                    self._close_locked()
            return False

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    # ------------------------------------------------------------------ iç kısım

    def _close_locked(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:  # pragma: no cover - nadir
                process.kill()

    def _ensure(self) -> subprocess.Popen[str] | None:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._process = None
        try:
            self._process = subprocess.Popen(
                list(self.command),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            log.error("pw-cli bulunamadı; PipeWire araçları kurulu mu?")
            return None
        return self._process


class Control:
    """Canlı kontrol arayüzü. Node adı alır, id çözümünü `GraphState`'ten yapar."""

    def __init__(
        self,
        state: GraphState,
        session: PwCliSession | None = None,
        *,
        window_ms: float = DEFAULT_WINDOW_MS,
        runner: Callable[[list[str]], bool] | None = None,
        capturer: Callable[[list[str]], str | None] | None = None,
    ) -> None:
        self.state = state
        self.session = session if session is not None else PwCliSession()
        self.window = window_ms / 1000.0
        self._run = runner if runner is not None else _run_command
        self._capture = capturer if capturer is not None else _capture_command
        self._pending: dict[str, dict[str, float]] = {}
        self._pending_props: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # ------------------------------------------------------------------ parametreler

    def set_param(self, node: str, port: str, value: float) -> None:
        self.set_params(node, {port: value})

    def set_params(self, node: str, params: dict[str, float]) -> None:
        """Bir node'un DSP portlarını yazar. Pencere içinde biriktirilir."""
        if not params:
            return
        with self._lock:
            self._pending.setdefault(node, {}).update(params)
        self._schedule()

    # ------------------------------------------------------------------ seviye

    def set_volume(self, node: str, volume: float, channels: int = 2) -> None:
        """Lineer ses seviyesi (1.0 = birim kazanç). `wpctl`'in kübik ölçeği değil."""
        value = max(0.0, float(volume))
        with self._lock:
            self._pending_props.setdefault(node, {})["channelVolumes"] = [value] * channels
        self._schedule()

    def set_mute(self, node: str, muted: bool) -> None:
        with self._lock:
            self._pending_props.setdefault(node, {})["mute"] = bool(muted)
        self._schedule()

    # ------------------------------------------------------------------ nadir işlemler

    def move_stream(self, stream_id: int, target_node: str) -> bool:
        """Bir uygulama akışını başka bir kanala taşır. Kesintisiz.

        `stream_id` bir PipeWire node id'sidir. Hedef adı tırnaksız gönderilir — bkz.
        modül başlığı.
        """
        return self._run(["pw-metadata", str(int(stream_id)), "target.object", target_node])

    def set_default_sink(self, node: str) -> bool:
        return self._run(["wpctl", "set-default", str(self.state.node_id(node) or node)])

    def link_nodes(self, output_node: str, input_node: str) -> bool:
        """İki node'un portlarını sırayla bağlar.

        `pw-link`'e port değil **node adı** verilir; portları o eşleştirir. Port adlarını
        burada sabitleyemiyoruz: bir filter-chain çıkışının portları `media.class`
        taşıdığında `capture_FL`, taşımadığında `output_FL` adını alıyor.

        Bağlantı zaten varsa `pw-link` sıfırdan farklı döner; bu bir hata değil, o yüzden
        çağıran taraf sonucu `node_links()` ile doğrular.
        """
        return self._run(["pw-link", output_node, input_node])

    def node_links(self) -> set[tuple[str, str]]:
        """Graftaki bağlantılar, **node düzeyinde** (çıkış node'u, giriş node'u)."""
        text = self._capture(["pw-link", "-l"])
        return {
            (_node_of(source), _node_of(target)) for source, target in parse_links(text or "")
        }

    # ------------------------------------------------------------------ boşaltma

    def flush(self) -> None:
        """Bekleyen tüm yazımları hemen gönderir."""
        with self._lock:
            self._cancel_timer()
            params, self._pending = self._pending, {}
            props, self._pending_props = self._pending_props, {}

        for node, values in params.items():
            node_id = self.state.node_id(node)
            if node_id is None:
                log.debug("node haritada yok, parametre yazımı atlandı: %s", node)
                continue
            self.session.send(f"set-param {node_id} Props {format_params(values)}")

        for node, values in props.items():
            node_id = self.state.node_id(node)
            if node_id is None:
                log.debug("node haritada yok, seviye yazımı atlandı: %s", node)
                continue
            self.session.send(f"set-param {node_id} Props {_format_props(values)}")

    def close(self) -> None:
        self.flush()
        with self._lock:
            self._cancel_timer()
        self.session.close()

    def pending_nodes(self) -> frozenset[str]:
        """Bekleyen yazımı olan node'lar — testler ve hata ayıklama için."""
        with self._lock:
            return frozenset(self._pending) | frozenset(self._pending_props)

    # ------------------------------------------------------------------ iç kısım

    def _schedule(self) -> None:
        if self.window <= 0:
            self.flush()
            return
        with self._lock:
            if self._timer is not None:
                return  # zaten bir boşaltma planlı; son değer o zaman gider
            self._timer = threading.Timer(self.window, self.flush)
            self._timer.name = "sonar-control-flush"
            self._timer.daemon = True
            self._timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


def _format_props(values: dict[str, object]) -> str:
    parts = []
    for key, value in values.items():
        if isinstance(value, list):
            inner = ", ".join(format_value(v) for v in value)  # type: ignore[arg-type]
            parts.append(f"{key} = [ {inner} ]")
        else:
            parts.append(f"{key} = {format_value(value)}")  # type: ignore[arg-type]
    return "{ " + ", ".join(parts) + " }"


def parse_links(text: str) -> set[tuple[str, str]]:
    """`pw-link -l` çıktısını (çıkış portu, giriş portu) çiftlerine ayırır.

    Biçim: sütun 0'da bir port adı, altında ona bağlı portlar `|->` (çıkıştan girişe)
    veya `|<-` (girişten çıkışa) ile girintili. Her bağlantı iki kez görünür; yön
    okları sayesinde tek yönde normalleştiriliyor.
    """
    links: set[tuple[str, str]] = set()
    current = ""
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            current = line.strip()
            continue
        body = line.strip()
        if body.startswith("|->"):
            links.add((current, body[3:].strip()))
        elif body.startswith("|<-"):
            links.add((body[3:].strip(), current))
    return links


def _node_of(port: str) -> str:
    """`node:port` → `node`. Node adında `:` olmadığı için sondan bölünür."""
    return port.rsplit(":", 1)[0]


def _capture_command(argv: Iterable[str]) -> str | None:
    """Çıktısı okunacak alt süreç çağrıları."""
    argv = list(argv)
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT, check=False
        )
    except FileNotFoundError:
        log.error("komut bulunamadı: %s", argv[0])
        return None
    except subprocess.TimeoutExpired:
        log.error("komut zaman aşımına uğradı: %s", " ".join(argv))
        return None
    if result.returncode != 0:
        log.warning("komut başarısız (%d): %s", result.returncode, " ".join(argv))
        return None
    return result.stdout


def _run_command(argv: Iterable[str]) -> bool:
    """Nadir alt süreç çağrıları. Hata daemon'ı düşürmez, loglanır."""
    argv = list(argv)
    try:
        result = subprocess.run(argv, capture_output=True, timeout=COMMAND_TIMEOUT, check=False)
    except FileNotFoundError:
        log.error("komut bulunamadı: %s", argv[0])
        return False
    except subprocess.TimeoutExpired:
        log.error("komut zaman aşımına uğradı: %s", " ".join(argv))
        return False
    if result.returncode != 0:
        log.warning("komut başarısız (%d): %s", result.returncode, " ".join(argv))
        return False
    return True
