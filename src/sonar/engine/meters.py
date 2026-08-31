"""Seviye metreleri: kanal başına peak/RMS ölçümü.

Her ölçüm noktası için düşük hızda bir yakalama akışı açılır:

```
pw-cat --record --target <node> --rate 8000 --channels 1 --format f32 -
```

8 kHz mono f32 = 32 KB/s. Ölçüldü: **8 kaynak toplam %0.87 CPU**, kaynak başına 3.4 MB
gerçek (PSS) bellek. Hedef %2'nin altında.

## Neden eklentinin kendi metreleri kullanılmıyor

LSP `para_equalizer`'ın `iml`/`imr`/`sml`/`smr` ("Input/Output signal meter") çıkış kontrol
portları var ve bedava olurdu. Ama PipeWire'ın filter-chain'i **yalnızca giriş** kontrol
portlarını `Props` içinde açığa çıkarıyor; çıkış portları görünmüyor (denendi, boş döndü).

## Talep üzerine

Ölçüm yalnızca bir istemci abone olduğunda çalışır, son abone gidince tüm süreçler durur.
Daemon tek başına çalışırken **sıfır maliyet** — arayüz kapalıyken metre için bir tek süreç
bile açık kalmaz.

## Master metreleri neyi gösterir

`sonar_personal` ve `sonar_stream` birer sink; monitörleri **master DSP'den önceki** miksi
verir. Yani metre tüm kanal katkılarını ve fader'ları yansıtır ama master EQ/limiter
etkisini göstermez. Klasik bir mikserde master metresi de genelde bunu gösterir; ayrıca
post-DSP çıkış (`sonar_personal_out`) bir akış olduğu için ondan yakalama yapılamıyor.
"""

from __future__ import annotations

import logging
import math
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from sonar.core.model import SonarConfig

__all__ = [
    "CLIP_HOLD_S",
    "FLOOR_DB",
    "Level",
    "MeterManager",
    "MeterSource",
    "PeakHold",
    "analyse",
    "meter_sources",
    "to_db",
]

log = logging.getLogger(__name__)

#: Metrenin tabanı. Bunun altındaki her şey "sessiz" sayılır.
FLOOR_DB = -60.0

#: Tepe göstergesi bu kadar süre tutulur, sonra `DECAY_DB_PER_S` hızıyla düşer.
HOLD_S = 1.5
DECAY_DB_PER_S = 20.0

#: Clip bayrağının yanık kalma süresi.
CLIP_HOLD_S = 2.0

#: `|x|` bu değeri aşarsa clip sayılır.
CLIP_THRESHOLD = 0.999

#: `pw-cat`'in kendi tampon boyutu. Ölçüldü: 100 ms yerine 500 ms istemek `pw-cat`'in
#: CPU'sunu **üçte bire** düşürüyor (%1.00 → %0.33) ve **hiçbir gecikme eklemiyor** —
#: stdout'a teslim aralığı da (53 ms) tepki süresi de (53 ms) değişmiyor, çünkü akışı bizim
#: okuma boyumuz pace ediyor. Metre hızı bundan değil `WINDOW_S`'ten geliyor.
CAPTURE_LATENCY = "500ms"

#: Ölçüm penceresi (saniye) ve yakalama hızı.
#:
#: Pencere bilinçli olarak rapor aralığıyla (50 ms, 20 Hz) aynı: daha kısa pencere ekstra
#: bilgi vermez, yalnızca iş parçacığı uyanmalarını artırır. 20 ms'den 50 ms'ye çıkarmak
#: 8 kaynakta saniyede 400 uyanmayı 160'a indirdi.
WINDOW_S = 0.05
CAPTURE_RATE = 8000


@dataclass(frozen=True, slots=True)
class Level:
    """Bir ölçüm noktasının anlık durumu. Hepsi dBFS."""

    peak_db: float = FLOOR_DB
    rms_db: float = FLOOR_DB
    hold_db: float = FLOOR_DB
    clipped: bool = False

    @property
    def silent(self) -> bool:
        return self.peak_db <= FLOOR_DB


def to_db(linear: float) -> float:
    """Lineer genlik → dBFS, `FLOOR_DB` tabanlı."""
    if linear <= 0.0:
        return FLOOR_DB
    return max(FLOOR_DB, 20.0 * math.log10(linear))


def analyse(samples: np.ndarray) -> tuple[float, float, bool]:
    """Bir örnek bloğundan `(peak dB, rms dB, clip)` üretir.

    Hızlı yol hiç kopya almaz. NaN/inf ancak bozuk bir akışta görülür; o zaman ayıklanmış
    yola düşülür. Her blokta `isfinite` maskesi almak saniyede yüzlerce gereksiz ayırma
    demekti.
    """
    if samples.size == 0:
        return FLOOR_DB, FLOOR_DB, False
    peak = float(np.abs(samples).max())
    if not math.isfinite(peak):
        return _analyse_sanitised(samples)
    mean_square = float(np.dot(samples, samples)) / samples.size
    if not math.isfinite(mean_square):  # pragma: no cover - taşma
        return _analyse_sanitised(samples)
    return to_db(peak), to_db(math.sqrt(mean_square)), peak >= CLIP_THRESHOLD


def _analyse_sanitised(samples: np.ndarray) -> tuple[float, float, bool]:
    finite = samples[np.isfinite(samples)]
    if finite.size == 0:  # pragma: no cover - tamamen bozuk blok
        return FLOOR_DB, FLOOR_DB, False
    peak = float(np.abs(finite).max())
    rms = float(np.sqrt(np.mean(np.square(finite, dtype=np.float64))))
    return to_db(peak), to_db(rms), peak >= CLIP_THRESHOLD


class PeakHold:
    """Klasik mikser davranışı: tepe tutulur, sonra sabit hızla düşer."""

    def __init__(self, hold_s: float = HOLD_S, decay_db_per_s: float = DECAY_DB_PER_S) -> None:
        self.hold_s = hold_s
        self.decay = decay_db_per_s
        self._value = FLOOR_DB
        self._since = 0.0

    def update(self, peak_db: float, now: float) -> float:
        if peak_db >= self._value:
            self._value = peak_db
            self._since = now
            return self._value
        elapsed = now - self._since
        if elapsed > self.hold_s:
            self._value = max(FLOOR_DB, self._value - self.decay * (elapsed - self.hold_s))
            self._since = now - self.hold_s  # düşüş sürsün
        return self._value

    @property
    def value(self) -> float:
        return self._value


def meter_sources(config: SonarConfig) -> dict[str, bool]:
    """Ölçülecek node'lar → sink monitörü mü yakalanacak.

    Kanalların `_fx` node'ları DSP sonrası sanal kaynaklar, doğrudan yakalanır.
    Bus'lar birer sink olduğu için monitörleri yakalanır.
    """
    sources: dict[str, bool] = {}
    for channel in config.ordered_channels():
        sources[channel.fx_node] = False
    for bus in sorted(config.buses, key=lambda b: b.id.value):
        sources[bus.sink_node] = True
    for mic in config.mic_chains:
        sources[mic.source_node] = False
    return sources


def _capture_command(node: str, capture_sink: bool, rate: int) -> list[str]:
    args = ["pw-cat", "--record", "--target", node]
    if capture_sink:
        args += ["-P", "stream.capture.sink=true"]
    args += ["--latency", CAPTURE_LATENCY]
    args += ["--rate", str(rate), "--channels", "1", "--format", "f32", "-"]
    return args


class MeterSource:
    """Tek bir node'un seviyesini okur. Süreç ölürse yeniden açılır."""

    def __init__(
        self,
        node: str,
        *,
        capture_sink: bool = False,
        rate: int = CAPTURE_RATE,
        spawn: Callable[[list[str]], subprocess.Popen] | None = None,
        retry_delay: float = 1.0,
    ) -> None:
        self.node = node
        self.capture_sink = capture_sink
        self.rate = rate
        self.retry_delay = retry_delay
        self._spawn = spawn if spawn is not None else _spawn_capture
        self._hold = PeakHold()
        self._level = Level()
        self._clip_until = 0.0
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None

    @property
    def command(self) -> list[str]:
        return _capture_command(self.node, self.capture_sink, self.rate)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"sonar-meter-{self.node}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stopping.set()
        with self._lock:
            process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:  # pragma: no cover - nadir
                process.kill()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        with self._lock:
            self._level = Level()
            self._hold = PeakHold()

    def level(self, now: float | None = None) -> Level:
        """Son ölçüm. Ses kesildiyse tutulan tepe zamanla düşer."""
        now = time.monotonic() if now is None else now
        with self._lock:
            level = self._level
            hold = self._hold.update(level.peak_db, now)
            clipped = now < self._clip_until
        return Level(level.peak_db, level.rms_db, hold, clipped)

    def feed(self, block: np.ndarray, now: float | None = None) -> None:
        """Ham örnekleri işler. Süreçten bağımsız — testler doğrudan çağırır."""
        now = time.monotonic() if now is None else now
        peak_db, rms_db, clipped = analyse(block)
        with self._lock:
            self._hold.update(peak_db, now)
            if clipped:
                self._clip_until = now + CLIP_HOLD_S
            self._level = Level(peak_db, rms_db, self._hold.value, now < self._clip_until)

    # ------------------------------------------------------------------ iç kısım

    def _run(self) -> None:
        chunk = max(1, int(self.rate * WINDOW_S)) * 4  # f32 = 4 bayt
        while not self._stopping.is_set():
            try:
                self._pump(chunk)
            except FileNotFoundError:
                log.error("pw-cat bulunamadı; seviye ölçümü kapalı")
                return
            except Exception:  # pragma: no cover - beklenmeyen
                log.exception("seviye ölçümü düştü: %s", self.node)
            if self._stopping.wait(self.retry_delay):
                return
            log.debug("seviye ölçümü yeniden başlatılıyor: %s", self.node)

    def _pump(self, chunk: int) -> None:
        process = self._spawn(self.command)
        with self._lock:
            self._process = process
        assert process.stdout is not None
        while not self._stopping.is_set():
            data = process.stdout.read(chunk)
            if not data:
                break
            self.feed(np.frombuffer(data, dtype="<f4"))
        process.wait()


class MeterManager:
    """Abonelik sayacı + ölçüm kaynaklarının yaşam döngüsü.

    Arayüz `pw-cat`'ten bağımsız tutuldu: ileride tek bir native yardımcı süreçle
    değiştirilirse D-Bus sinyali ve GUI tarafı aynı kalır.
    """

    def __init__(
        self,
        *,
        interval: float = 0.05,
        on_levels: Callable[[dict[str, Level]], None] | None = None,
        source_factory: Callable[[str, bool], MeterSource] | None = None,
    ) -> None:
        self.interval = interval
        self.on_levels = on_levels
        self._factory = source_factory if source_factory is not None else _default_source
        self._sources: dict[str, MeterSource] = {}
        self._wanted: dict[str, bool] = {}
        self._subscribers = 0
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None

    @property
    def subscribers(self) -> int:
        return self._subscribers

    @property
    def running(self) -> bool:
        return bool(self._sources)

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(self._sources)

    def configure(self, sources: dict[str, bool]) -> None:
        """Ölçüm noktalarını belirler. Graf yeniden kurulduğunda yeniden çağrılır."""
        with self._lock:
            self._wanted = dict(sources)
            if self._subscribers > 0:
                self._stop_sources()
                self._start_sources()

    def subscribe(self) -> int:
        with self._lock:
            self._subscribers += 1
            if self._subscribers == 1:
                self._start_sources()
                self._schedule()
            return self._subscribers

    def unsubscribe(self) -> int:
        with self._lock:
            self._subscribers = max(0, self._subscribers - 1)
            if self._subscribers == 0:
                self._stop_sources()
            return self._subscribers

    def levels(self) -> dict[str, Level]:
        now = time.monotonic()
        with self._lock:
            return {name: source.level(now) for name, source in self._sources.items()}

    def stop(self) -> None:
        with self._lock:
            self._subscribers = 0
            self._stop_sources()

    # ------------------------------------------------------------------ iç kısım

    def _start_sources(self) -> None:
        for node, capture_sink in self._wanted.items():
            source = self._factory(node, capture_sink)
            self._sources[node] = source
            source.start()

    def _stop_sources(self) -> None:
        sources, self._sources = self._sources, {}
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        for source in sources.values():
            source.stop()

    def _schedule(self) -> None:
        if self.on_levels is None or self.interval <= 0:
            return
        self._timer = threading.Timer(self.interval, self._tick)
        self._timer.name = "sonar-meters"
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        with self._lock:
            if self._subscribers == 0:
                return
        try:
            if self.on_levels is not None:
                self.on_levels(self.levels())
        except Exception:  # pragma: no cover - dinleyici hatası ölçümü durdurmasın
            log.exception("seviye dinleyicisi hata verdi")
        with self._lock:
            if self._subscribers > 0:
                self._schedule()


def _default_source(node: str, capture_sink: bool) -> MeterSource:
    return MeterSource(node, capture_sink=capture_sink)


def _spawn_capture(argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
