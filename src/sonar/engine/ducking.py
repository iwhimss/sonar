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

from collections.abc import Callable
from dataclasses import dataclass, field

from sonar.core.dsp.params import db_to_linear
from sonar.core.model import Profile, SonarConfig

__all__ = ["Ducker", "ProfileLookup", "duck_pairs", "next_depth"]

#: Hedef kimliğinden **aktif** profili veren fonksiyon. `daemon.api.profile` bunu
#: karşılıyor; motorun diske veya önbelleğe bakması gerekmiyor.
ProfileLookup = Callable[[str], Profile]


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


def duck_pairs(config: SonarConfig, profile_of: ProfileLookup) -> dict[str, set[str]]:
    """`tetikleyici kanal → kısılacak kanallar`.

    Tetikleyici, **Smart Volume'u açık olan profili taşıyan kanalın kendisi** (şema 4).
    Hedef listesi boşsa "kendisi dışındaki her çıkış kanalı" demek — kullanıcı tek tek
    seçmek zorunda kalmasın diye.

    Birden fazla kanalda açık olabilir; her biri kendi ayarlarıyla bağımsız çalışır.
    """
    everyone = {channel.id for channel in config.channels}
    pairs: dict[str, set[str]] = {}
    for channel in config.channels:
        duck = profile_of(channel.id).ducking
        if not duck.enabled:
            continue
        wanted = {cid for cid in duck.target_channels if cid in everyone} or everyone
        targets = wanted - {channel.id}
        if targets:
            pairs[channel.id] = targets
    return pairs


@dataclass(slots=True)
class Ducker:
    """Zarfların canlı durumu. `step()` her ölçüm turunda çağrılır.

    Tetikleyici başına ayrı bir zarf tutuluyor: her kanalın kendi profili, kendi
    indirimi ve kendi atak/bırakma süresi var. Bir hedef birden fazla tetikleyicinin
    kapsamındaysa **en derin** indirim uygulanır (çarpmak yerine) — böylece toplam
    indirim ayarlanan değerlerin ötesine geçmiyor.
    """

    #: Tetikleyici kimliği → 0 (dokunma) … 1 (tam indirim).
    depth: dict[str, float] = field(default_factory=dict)
    #: Tetikleyici sustuktan sonra hold'un bitmesine kalan süre (saniye).
    hold_left: dict[str, float] = field(default_factory=dict)
    _gains: dict[str, float] = field(default_factory=dict, repr=False)

    def reset(self) -> None:
        self.depth = {}
        self.hold_left = {}
        self._gains = {}

    @property
    def gains(self) -> dict[str, float]:
        """Son hesaplanan kanal → lineer kazanç eşlemesi."""
        return dict(self._gains)

    def step(
        self,
        config: SonarConfig,
        profile_of: ProfileLookup,
        levels: dict[str, float],
        dt: float,
    ) -> dict[str, float]:
        """Yeni kazançları hesaplar. `levels` kanal kimliği → tepe dBFS."""
        pairs = duck_pairs(config, profile_of)
        if not pairs:
            self.reset()
            return {}

        # Artık tetiklemeyen kanalların zarfını unut.
        for stale in [cid for cid in self.depth if cid not in pairs]:
            self.depth.pop(stale, None)
            self.hold_left.pop(stale, None)

        gains: dict[str, float] = {}
        for trigger, targets in pairs.items():
            duck = profile_of(trigger).ducking
            speaking = levels.get(trigger, -120.0) >= duck.threshold_db
            if speaking:
                self.hold_left[trigger] = max(duck.hold_ms, 0.0) / 1000.0
            elif self.hold_left.get(trigger, 0.0) > 0.0:
                self.hold_left[trigger] = max(self.hold_left[trigger] - dt, 0.0)
                speaking = True  # hold süresince inik kal

            depth = next_depth(
                self.depth.get(trigger, 0.0),
                speaking=speaking,
                depth_db=duck.reduction_db,
                attack_ms=duck.attack_ms,
                release_ms=duck.release_ms,
                dt=dt,
            )
            self.depth[trigger] = depth
            gain = db_to_linear(depth * duck.reduction_db)
            for target in targets:
                gains[target] = min(gains.get(target, 1.0), gain)

        self._gains = gains
        return self.gains
