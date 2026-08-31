"""Ekolayzerin frekans yanıtı — arayüzde çizilen eğrinin matematiği.

Eğri **tahmini bir görsel değil**: Faz 1'de LSP'nin filtre modeli bilinçli olarak
`fm_N = 6` ("APO DR") seçildi, çünkü o model RBJ cookbook biquad'larıyla birebir örtüşür.
Burada aynı formüller uygulanıyor, dolayısıyla çizilen eğri kulağın duyduğuyla aynı.

Her band bir ikinci derece bölüm (biquad):

    H(z) = (b0 + b1·z⁻¹ + b2·z⁻²) / (a0 + a1·z⁻¹ + a2·z⁻²)

Toplam yanıt bandların çarpımıdır (seri bağlı filtreler). `slope` (LSP `s_N`) bandın kaç kez
kaskatlandığını söyler: 0 → ×1, 1 → ×2, 2 → ×3, 3 → ×4.
"""

from __future__ import annotations

import numpy as np

from sonar.core.model import EqBand, EqBandType, EqState

__all__ = [
    "DISPLAY_MAX_HZ",
    "DISPLAY_MIN_HZ",
    "band_response",
    "biquad",
    "eq_response",
    "log_frequencies",
]

#: Arayüzde gösterilen frekans aralığı.
DISPLAY_MIN_HZ = 20.0
DISPLAY_MAX_HZ = 20_000.0

#: Nyquist'e çok yaklaşan bandlar biquad formüllerinde patlar; güvenli üst sınır.
_MAX_W = np.pi * 0.999


def log_frequencies(
    count: int = 512, low: float = DISPLAY_MIN_HZ, high: float = DISPLAY_MAX_HZ
) -> np.ndarray:
    """Çizim için logaritmik frekans ızgarası. Kulak logaritmik duyar, eksen de öyle."""
    return np.geomspace(low, high, count)


def biquad(band: EqBand, rate: int = 48_000) -> tuple[np.ndarray, np.ndarray]:
    """Bandın `(b, a)` katsayıları — RBJ cookbook.

    `a0` ile normalize edilmiş hâlde döner, böylece çağıran taraf bölme yapmaz.
    """
    band = band.clamped()
    w0 = min(2.0 * np.pi * band.freq / rate, _MAX_W)
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    q = max(band.q, 1e-4)
    alpha = sin_w0 / (2.0 * q)
    amp = 10.0 ** (band.gain_db / 40.0)  # kazanç genlik olarak: √(10^(dB/20))

    kind = band.band_type
    if kind is EqBandType.PEAK:
        b = np.array([1 + alpha * amp, -2 * cos_w0, 1 - alpha * amp])
        a = np.array([1 + alpha / amp, -2 * cos_w0, 1 - alpha / amp])
    elif kind is EqBandType.LOW_SHELF:
        sqrt_a = 2.0 * np.sqrt(amp) * alpha
        b = np.array(
            [
                amp * ((amp + 1) - (amp - 1) * cos_w0 + sqrt_a),
                2 * amp * ((amp - 1) - (amp + 1) * cos_w0),
                amp * ((amp + 1) - (amp - 1) * cos_w0 - sqrt_a),
            ]
        )
        a = np.array(
            [
                (amp + 1) + (amp - 1) * cos_w0 + sqrt_a,
                -2 * ((amp - 1) + (amp + 1) * cos_w0),
                (amp + 1) + (amp - 1) * cos_w0 - sqrt_a,
            ]
        )
    elif kind is EqBandType.HIGH_SHELF:
        sqrt_a = 2.0 * np.sqrt(amp) * alpha
        b = np.array(
            [
                amp * ((amp + 1) + (amp - 1) * cos_w0 + sqrt_a),
                -2 * amp * ((amp - 1) + (amp + 1) * cos_w0),
                amp * ((amp + 1) + (amp - 1) * cos_w0 - sqrt_a),
            ]
        )
        a = np.array(
            [
                (amp + 1) - (amp - 1) * cos_w0 + sqrt_a,
                2 * ((amp - 1) - (amp + 1) * cos_w0),
                (amp + 1) - (amp - 1) * cos_w0 - sqrt_a,
            ]
        )
    elif kind is EqBandType.LOW_PASS:
        b = np.array([(1 - cos_w0) / 2, 1 - cos_w0, (1 - cos_w0) / 2])
        a = np.array([1 + alpha, -2 * cos_w0, 1 - alpha])
    elif kind is EqBandType.HIGH_PASS:
        b = np.array([(1 + cos_w0) / 2, -(1 + cos_w0), (1 + cos_w0) / 2])
        a = np.array([1 + alpha, -2 * cos_w0, 1 - alpha])
    elif kind is EqBandType.NOTCH:
        b = np.array([1.0, -2 * cos_w0, 1.0])
        a = np.array([1 + alpha, -2 * cos_w0, 1 - alpha])
    elif kind is EqBandType.BANDPASS:
        b = np.array([alpha, 0.0, -alpha])
        a = np.array([1 + alpha, -2 * cos_w0, 1 - alpha])
    elif kind is EqBandType.ALLPASS:
        b = np.array([1 - alpha, -2 * cos_w0, 1 + alpha])
        a = np.array([1 + alpha, -2 * cos_w0, 1 - alpha])
    else:  # OFF
        return np.array([1.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])

    return b / a[0], a / a[0]


def band_response(band: EqBand, freqs: np.ndarray, rate: int = 48_000) -> np.ndarray:
    """Tek bandın karmaşık frekans yanıtı. `slope` kadar kaskatlanır."""
    if not band.enabled or band.band_type is EqBandType.OFF:
        return np.ones_like(freqs, dtype=complex)
    b, a = biquad(band, rate)
    z = np.exp(-1j * 2.0 * np.pi * freqs / rate)
    numerator = b[0] + b[1] * z + b[2] * z * z
    denominator = a[0] + a[1] * z + a[2] * z * z
    response = np.divide(
        numerator,
        denominator,
        out=np.ones_like(numerator),
        where=denominator != 0,
    )
    return response ** (band.clamped().slope + 1)


def eq_response(
    eq: EqState, freqs: np.ndarray | None = None, rate: int = 48_000
) -> tuple[np.ndarray, np.ndarray]:
    """`(frekanslar, dB cinsinden toplam yanıt)`.

    EQ kapalıysa düz çizgi döner — arayüz bypass'ı böyle gösterir.
    """
    freqs = log_frequencies() if freqs is None else freqs
    if not eq.enabled:
        return freqs, np.zeros_like(freqs)

    total = np.ones_like(freqs, dtype=complex)
    for band in eq.active_bands():
        total = total * band_response(band, freqs, rate)

    magnitude = np.abs(total) * (10.0 ** (eq.preamp_db / 20.0))
    with np.errstate(divide="ignore"):
        db = 20.0 * np.log10(np.maximum(magnitude, 1e-6))
    return freqs, db
