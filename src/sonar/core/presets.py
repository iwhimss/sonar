"""Gömülü preset kütüphanesi.

Presetler **Python verisi** olarak tanımlı, dosya olarak değil: kod incelemesinden geçiyorlar,
paketleme kenar durumu yok ve dosya okuma hatası diye bir ihtimal kalmıyor. Kullanıcı bir
preset'i düzenlemek isterse kendi profili olarak kopyalanır (bkz. `daemon.api`).

Presetler **salt okunur**. Sebebi Faz 8'de ölçümle görüldü: düzenlemeler aktif profile
otomatik kalıcı olduğu için, bir preset'i kurcalamak preset'in kendisini bozuyor. Artık
salt okunur bir preset düzenlenmeye başlandığında kendiliğinden bir kopya oluşturuluyor.

Preset formatı kullanıcı profilleriyle **birebir aynı** — içe aktarılan bir dosya ile gömülü
bir preset arasında yapısal fark yok.
"""

from __future__ import annotations

from sonar.core.model import (
    EqBandType,
    FilterStage,
    Profile,
    default_band_frequencies,
    default_profile,
)

__all__ = [
    "BUILTIN_MIC",
    "BUILTIN_OUTPUT",
    "builtin_names",
    "builtin_profile",
    "is_builtin",
]

#: Kullanıcının bir preset'i düzenlemeye başladığında oluşturulan kopyanın ad eki.
COPY_SUFFIX = "özel"


def _band_index(freq: float, band_count: int = 10) -> int:
    """Verilen frekansa en yakın bandın indeksi."""
    freqs = default_band_frequencies(band_count)
    return min(range(len(freqs)), key=lambda i: abs(freqs[i] - freq))


def _profile(
    name: str,
    *,
    gains: dict[float, float] | None = None,
    shapes: dict[float, tuple[EqBandType, float, float]] | None = None,
    filters: dict[FilterStage, dict] | None = None,
    band_count: int = 10,
) -> Profile:
    """Varsayılan profilden başlayıp üstüne preset farklarını uygular.

    `gains`: `{frekans: dB}` — en yakın banda peak olarak uygulanır.
    `shapes`: `{frekans: (tip, dB, Q)}` — bandın tipini de değiştirir.
    `filters`: `{aşama: {"enabled": bool, "params": {...}}}`.
    """
    profile = default_profile(name, band_count=band_count)
    profile.eq.enabled = True

    for freq, gain in (gains or {}).items():
        index = _band_index(freq, band_count)
        profile.eq.bands[index].gain_db = gain

    for freq, (kind, gain, q) in (shapes or {}).items():
        index = _band_index(freq, band_count)
        band = profile.eq.bands[index]
        band.band_type = kind
        band.gain_db = gain
        band.q = q

    for stage, spec in (filters or {}).items():
        state = profile.filter(stage)
        state.enabled = bool(spec.get("enabled", True))
        state.params.update(spec.get("params", {}))

    return profile


def _flat(name: str = "Flat") -> Profile:
    """Tamamen şeffaf: EQ kapalı, tüm filtreler kapalı. Referans nokta."""
    profile = default_profile(name)
    profile.eq.enabled = False
    return profile


#: Çıkış kanalları (Game / Chat / Media / Aux / bus'lar) için presetler.
BUILTIN_OUTPUT: dict[str, object] = {
    "Flat": _flat,
    "FPS Footsteps": lambda: _profile(
        "FPS Footsteps",
        # Ayak sesi ve yön ipuçları 2–5 kHz'te; patlama/motor gürültüsü altta.
        gains={31.25: -5.0, 62.5: -4.0, 250.0: -2.5, 2000.0: 6.0, 4000.0: 5.0, 8000.0: 2.0},
    ),
    "Bass Boost": lambda: _profile(
        "Bass Boost",
        shapes={62.5: (EqBandType.LOW_SHELF, 6.5, 0.7)},
        gains={125.0: 2.0},
    ),
    "Vocal Clarity": lambda: _profile(
        "Vocal Clarity",
        # 250–400 Hz "çamur", 1–4 kHz anlaşılırlık.
        gains={250.0: -3.5, 1000.0: 2.0, 2000.0: 4.0, 4000.0: 3.0},
    ),
    "Night Mode": lambda: _profile(
        "Night Mode",
        # Geç saatte: dinamiği daralt, tepe noktaları kes, basları hafifçe kıs.
        gains={31.25: -4.0, 62.5: -3.0},
        filters={
            FilterStage.COMP: {
                "enabled": True,
                "params": {
                    "threshold_db": -30.0,
                    "ratio": 6.0,
                    "attack_ms": 8.0,
                    "release_ms": 200.0,
                    "makeup_db": 6.0,
                },
            },
            FilterStage.LIMITER: {"enabled": True, "params": {"ceiling_db": -6.0}},
        },
    ),
    "Movie": lambda: _profile(
        "Movie",
        shapes={62.5: (EqBandType.LOW_SHELF, 3.0, 0.7), 8000.0: (EqBandType.HIGH_SHELF, 2.5, 0.7)},
        gains={2000.0: 1.5},
    ),
    "Music": lambda: _profile(
        "Music",
        # Hafif V eğrisi.
        shapes={62.5: (EqBandType.LOW_SHELF, 3.0, 0.7), 8000.0: (EqBandType.HIGH_SHELF, 3.0, 0.7)},
        gains={500.0: -1.5},
    ),
}

#: Mikrofon zincirleri için presetler.
BUILTIN_MIC: dict[str, object] = {
    "Flat": _flat,
    "Broadcast": lambda: _profile(
        "Broadcast",
        shapes={62.5: (EqBandType.HIGH_PASS, 0.0, 0.707)},
        gains={250.0: -2.0, 4000.0: 3.0},
        filters={
            FilterStage.GATE: {
                "enabled": True,
                "params": {"threshold_db": -42.0, "attack_ms": 5.0, "release_ms": 120.0},
            },
            FilterStage.COMP: {
                "enabled": True,
                "params": {
                    "threshold_db": -18.0,
                    "ratio": 3.0,
                    "attack_ms": 5.0,
                    "release_ms": 120.0,
                    "makeup_db": 4.0,
                },
            },
            FilterStage.LIMITER: {"enabled": True, "params": {"ceiling_db": -1.0}},
        },
    ),
    "Podcast": lambda: _profile(
        "Podcast",
        # Daha yumuşak; 6–8 kHz'te tıslama (ess) kısımı.
        shapes={62.5: (EqBandType.HIGH_PASS, 0.0, 0.707), 8000.0: (EqBandType.PEAK, -4.0, 3.0)},
        gains={2000.0: 2.0},
        filters={
            FilterStage.COMP: {
                "enabled": True,
                "params": {
                    "threshold_db": -20.0,
                    "ratio": 2.5,
                    "attack_ms": 10.0,
                    "release_ms": 180.0,
                    "makeup_db": 3.0,
                },
            },
            FilterStage.LIMITER: {"enabled": True, "params": {"ceiling_db": -1.0}},
        },
    ),
    "Aggressive Cleanup": lambda: _profile(
        "Aggressive Cleanup",
        # Gürültülü ortam: AI tam güçte, sıkı gate, alt uç tamamen kesik.
        shapes={125.0: (EqBandType.HIGH_PASS, 0.0, 0.707)},
        gains={4000.0: 3.0},
        filters={
            FilterStage.DEEPFILTER: {"enabled": True, "params": {"attenuation_db": 100.0}},
            FilterStage.GATE: {
                "enabled": True,
                "params": {
                    "threshold_db": -32.0,
                    "attack_ms": 3.0,
                    "release_ms": 80.0,
                    "reduction_db": -40.0,
                },
            },
            FilterStage.COMP: {
                "enabled": True,
                "params": {"threshold_db": -18.0, "ratio": 4.0, "makeup_db": 5.0},
            },
            FilterStage.LIMITER: {"enabled": True, "params": {"ceiling_db": -1.0}},
        },
    ),
}


def _table(target: str, mic_targets: frozenset[str]) -> dict[str, object]:
    return BUILTIN_MIC if target in mic_targets else BUILTIN_OUTPUT


def builtin_names(
    target: str, mic_targets: frozenset[str] = frozenset({"mic", "stream_mic"})
) -> list[str]:
    """Hedef için geçerli preset adları."""
    return list(_table(target, mic_targets))


def is_builtin(
    target: str, name: str, mic_targets: frozenset[str] = frozenset({"mic", "stream_mic"})
) -> bool:
    return name in _table(target, mic_targets)


def builtin_profile(
    target: str, name: str, mic_targets: frozenset[str] = frozenset({"mic", "stream_mic"})
) -> Profile | None:
    """Preset'in **taze bir kopyasını** üretir; ortak nesne paylaşılmaz."""
    factory = _table(target, mic_targets).get(name)
    return factory() if factory is not None else None  # type: ignore[operator]
