"""Smart Volume — bir kanal konuşurken diğerlerini kısan kontrol döngüsü.

SteelSeries GG'deki "Smart Volume"un karşılığı: Discord'da biri konuşunca müzik kendini
kısar, sustuğunda geri gelir.

## Neden DSP değil

Bunu bir yan-zincirli (sidechain) kompresörle yapmak zincire ikinci bir sinyal yolu
sokmayı gerektirirdi: tetikleyici kanalın sesi hedef kanalın kompresörüne besleme olarak
girmeli. PipeWire `filter-chain` içinde kanallar arası besleme yok — her kanal ayrı bir
filter-chain node'u.

Buna karşılık **seviye ölçümü zaten var** (`engine.meters`, saniyede 20 örnek) ve fader'lar
zaten canlı yazılıyor (`engine.control`, yazım maliyeti 0.003 ms). Yani ducking'i daemon
tarafında bir zarf takipçisi olarak yürütmek hem ucuz hem de mevcut yolları kullanıyor.

Bedeli çözünürlük: 20 Hz'de bir karar, yani en hızlı tepki 50 ms. Konuşma için fazlasıyla
yeterli — insan sesinin hece süresi ~150 ms.

## Zarf

Klasik gate zarfı, ama tersine çevrilmiş: tetikleyici eşiği aşınca **attack** boyunca
hedefe iniyoruz, sustuğunda **hold** kadar bekleyip **release** boyunca geri çıkıyoruz.
Hold olmadan cümle aralarındaki nefeslerde ses pompalıyor.

Geçiş dB'de doğrusal: kulağa doğrusal gelen budur (`chatmix_gains` da öyle yapıyor).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sonar.core.dsp.params import db_to_linear
from sonar.core.model import SonarConfig

__all__ = ["Ducker", "duck_targets", "next_depth"]


def next_depth(
    current: float,
    *,
    speaking: bool,
    depth_db: float,
    attack_ms: float,
    release_ms: float,
    dt: float,
) -> float:
    """Zarfın bir sonraki derinliği (0 = dokunma, 1 = tam indirim).

    Saf: zamanı ve seviyeyi dışarıdan alır, bu yüzden PipeWire olmadan test edilebiliyor.
    `depth_db` yalnızca hız hesabında kullanılıyor — dB/saniye cinsinden sabit eğim.
    """
    del depth_db  # eğim normalize edilmiş derinlik üzerinden; dB yalnızca uygulamada
    target = 1.0 if speaking else 0.0
    span = max(attack_ms if speaking else release_ms, 1.0) / 1000.0
    step = dt / span
    if target > current:
        return min(current + step, target)
    return max(current - step, target)


def duck_targets(config: SonarConfig) -> tuple[set[str], set[str]]:
    """`(tetikleyiciler, hedefler)` kanal kimlikleri.

    Hedef listesi boşsa "tetikleyici olmayan her kanal" anlamına gelir — kullanıcı tek
    tek seçmek zorunda kalmasın diye.
    """
    duck = config.ducking
    triggers = {cid for cid in duck.trigger_channels if config.channel(cid) is not None}
    if duck.target_channels:
        targets = {cid for cid in duck.target_channels if config.channel(cid) is not None}
    else:
        targets = {c.id for c in config.channels}
    return triggers, targets - triggers


@dataclass(slots=True)
class Ducker:
    """Zarfın canlı durumu. `step()` her ölçüm turunda çağrılır."""

    #: 0 = dokunma, 1 = tam indirim.
    depth: float = 0.0
    #: Tetikleyici sustuktan sonra hold'un bitmesine kalan süre (saniye).
    hold_left: float = 0.0
    _gains: dict[str, float] = field(default_factory=dict, repr=False)

    def reset(self) -> None:
        self.depth = 0.0
        self.hold_left = 0.0
        self._gains = {}

    @property
    def gains(self) -> dict[str, float]:
        """Son hesaplanan kanal → lineer kazanç eşlemesi."""
        return dict(self._gains)

    def step(self, config: SonarConfig, levels: dict[str, float], dt: float) -> dict[str, float]:
        """Yeni kazançları hesaplar. `levels` kanal kimliği → tepe dBFS."""
        duck = config.ducking
        if not duck.enabled:
            self.reset()
            return {}

        triggers, targets = duck_targets(config)
        if not triggers or not targets:
            self.reset()
            return {}

        loudest = max((levels.get(cid, -120.0) for cid in triggers), default=-120.0)
        speaking = loudest >= duck.threshold_db
        if speaking:
            self.hold_left = max(duck.hold_ms, 0.0) / 1000.0
        elif self.hold_left > 0.0:
            self.hold_left = max(self.hold_left - dt, 0.0)
            speaking = True  # hold süresince inik kal

        self.depth = next_depth(
            self.depth,
            speaking=speaking,
            depth_db=duck.reduction_db,
            attack_ms=duck.attack_ms,
            release_ms=duck.release_ms,
            dt=dt,
        )
        gain = db_to_linear(self.depth * duck.reduction_db)
        self._gains = dict.fromkeys(targets, gain)
        return self.gains
