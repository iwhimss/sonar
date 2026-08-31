from __future__ import annotations

import numpy as np
import pytest

from sonar.core.dsp.response import (
    DISPLAY_MAX_HZ,
    DISPLAY_MIN_HZ,
    band_response,
    biquad,
    eq_response,
    log_frequencies,
)
from sonar.core.model import EqBand, EqBandType, EqState, default_profile


def db_at(freqs: np.ndarray, db: np.ndarray, hz: float) -> float:
    return float(db[int(np.argmin(np.abs(freqs - hz)))])


def one_band(**kwargs) -> EqState:
    band = EqBand(freq=1000.0, **kwargs)
    return EqState(enabled=True, band_count=1, bands=[band])


# --------------------------------------------------------------------------- ızgara


def test_grid_is_logarithmic_and_covers_the_audible_range():
    freqs = log_frequencies(256)
    assert freqs[0] == pytest.approx(DISPLAY_MIN_HZ)
    assert freqs[-1] == pytest.approx(DISPLAY_MAX_HZ)
    ratios = freqs[1:] / freqs[:-1]
    assert np.allclose(ratios, ratios[0]), "adımlar logaritmik olmalı"


# --------------------------------------------------------------------------- doğruluk
#
# Eğri tahmini bir görsel değil: Faz 1'de LSP filtre modeli `fm_N = 6` (APO DR) seçildi
# çünkü RBJ cookbook ile birebir örtüşüyor. Bu testler o örtüşmeyi koruyor.


@pytest.mark.parametrize("gain", [-12.0, -6.0, 3.0, 6.0, 12.0])
def test_peak_band_hits_its_gain_exactly_at_the_centre(gain):
    freqs, db = eq_response(one_band(gain_db=gain))
    assert db_at(freqs, db, 1000.0) == pytest.approx(gain, abs=0.02)


def test_peak_band_is_flat_far_from_its_centre():
    freqs, db = eq_response(one_band(gain_db=12.0, q=4.0))
    assert db_at(freqs, db, 20.0) == pytest.approx(0.0, abs=0.05)
    assert db_at(freqs, db, 20_000.0) == pytest.approx(0.0, abs=0.05)


def test_higher_q_narrows_the_bell():
    freqs, wide = eq_response(one_band(gain_db=12.0, q=0.5))
    _, narrow = eq_response(one_band(gain_db=12.0, q=8.0))
    # Merkezde ikisi de +12 dB; bir oktav uzakta dar olan çok daha düz olmalı.
    assert db_at(freqs, wide, 2000.0) > db_at(freqs, narrow, 2000.0)


def test_low_shelf_lifts_the_bottom_and_leaves_the_top():
    state = one_band(gain_db=9.0, band_type=EqBandType.LOW_SHELF)
    freqs, db = eq_response(state)
    assert db_at(freqs, db, 20.0) == pytest.approx(9.0, abs=0.3)
    assert db_at(freqs, db, 20_000.0) == pytest.approx(0.0, abs=0.3)


def test_high_shelf_lifts_the_top_and_leaves_the_bottom():
    state = one_band(gain_db=9.0, band_type=EqBandType.HIGH_SHELF)
    freqs, db = eq_response(state)
    assert db_at(freqs, db, 20_000.0) == pytest.approx(9.0, abs=0.5)
    assert db_at(freqs, db, 20.0) == pytest.approx(0.0, abs=0.3)


def test_low_pass_is_minus_three_db_at_the_cutoff():
    """Butterworth Q (1/√2) ile kesim frekansında tam -3 dB."""
    state = one_band(band_type=EqBandType.LOW_PASS, q=0.7071)
    freqs, db = eq_response(state)
    assert db_at(freqs, db, 1000.0) == pytest.approx(-3.0, abs=0.1)
    assert db_at(freqs, db, 20.0) == pytest.approx(0.0, abs=0.1)
    assert db_at(freqs, db, 16_000.0) < -40


def test_high_pass_mirrors_the_low_pass():
    state = one_band(band_type=EqBandType.HIGH_PASS, q=0.7071)
    freqs, db = eq_response(state)
    assert db_at(freqs, db, 1000.0) == pytest.approx(-3.0, abs=0.1)
    assert db_at(freqs, db, 20_000.0) == pytest.approx(0.0, abs=0.1)
    assert db_at(freqs, db, 25.0) < -40


def test_notch_cuts_deeply_at_its_centre():
    """Tam merkezde ölçülüyor: notch sonsuz derindir ama çizim ızgarası oraya düşmeyebilir.

    (Bu, eğrinin bir sınırı: dar bir notch ızgarada olduğundan sığ görünür. Kabul edilebilir,
    çünkü aynı sınır kulakta da var — 512 noktalık log ızgara ekranın çözünürlüğünden ince.)
    """
    state = one_band(band_type=EqBandType.NOTCH, q=8.0)
    _, exact = eq_response(state, freqs=np.array([1000.0]))
    assert exact[0] < -80
    freqs, db = eq_response(state)
    assert db_at(freqs, db, 100.0) == pytest.approx(0.0, abs=0.5)


def test_allpass_does_not_change_the_magnitude():
    """Allpass yalnızca fazı çevirir; genlik eğrisi düz kalmalı."""
    freqs, db = eq_response(one_band(band_type=EqBandType.ALLPASS))
    assert np.allclose(db, 0.0, atol=0.01)
    del freqs


def test_bandpass_peaks_at_its_centre():
    freqs, db = eq_response(one_band(band_type=EqBandType.BANDPASS, q=2.0))
    assert db_at(freqs, db, 1000.0) > db_at(freqs, db, 100.0) + 10


def test_off_band_is_transparent():
    freqs, db = eq_response(one_band(gain_db=12.0, band_type=EqBandType.OFF))
    assert np.allclose(db, 0.0, atol=1e-9)
    del freqs


def test_disabled_band_is_transparent():
    freqs, db = eq_response(one_band(gain_db=12.0, enabled=False))
    assert np.allclose(db, 0.0, atol=1e-9)
    del freqs


# --------------------------------------------------------------------------- eğim (slope)


def test_slope_cascades_the_filter():
    """LSP `s_N`: 0 → ×1, 3 → ×4. Kaskat kazancı katlar."""
    freqs = log_frequencies()
    single = band_response(EqBand(freq=1000.0, gain_db=6.0), freqs)
    quad = band_response(EqBand(freq=1000.0, gain_db=6.0, slope=3), freqs)
    index = int(np.argmin(np.abs(freqs - 1000.0)))
    assert 20 * np.log10(abs(quad[index])) == pytest.approx(
        4 * 20 * np.log10(abs(single[index])), abs=0.05
    )


# --------------------------------------------------------------------------- birleşik


def test_bands_combine_multiplicatively():
    state = EqState(
        enabled=True,
        band_count=2,
        bands=[EqBand(freq=1000.0, gain_db=4.0), EqBand(freq=1000.0, gain_db=3.0)],
    )
    freqs, db = eq_response(state)
    assert db_at(freqs, db, 1000.0) == pytest.approx(7.0, abs=0.05)


def test_preamp_shifts_the_whole_curve():
    state = one_band(gain_db=0.0)
    state.preamp_db = -6.0
    freqs, db = eq_response(state)
    assert np.allclose(db, -6.0, atol=0.02)
    del freqs


def test_disabled_eq_draws_a_flat_line():
    """Bypass'ta eğri düz olmalı — kullanıcı kapalıyken ne duyduğunu görüyor."""
    profile = default_profile()
    profile.eq.bands[3].gain_db = 12.0
    assert profile.eq.enabled is False
    freqs, db = eq_response(profile.eq)
    assert np.allclose(db, 0.0)
    del freqs


def test_only_active_bands_count():
    profile = default_profile(band_count=10)
    profile.eq.enabled = True
    profile.eq.bands[9].gain_db = 12.0
    profile.eq.band_count = 5  # 9. band artık kapsam dışı
    freqs, db = eq_response(profile.eq)
    assert np.allclose(db, 0.0, atol=0.01)
    del freqs


# --------------------------------------------------------------------------- sağlamlık


def test_extreme_frequency_does_not_explode():
    """Nyquist'e dayanan bir band biquad formüllerinde patlayabilir."""
    state = one_band(gain_db=12.0)
    state.bands[0].freq = 23_999.0
    freqs, db = eq_response(state, rate=48_000)
    assert np.all(np.isfinite(db))
    del freqs


def test_zero_q_is_clamped():
    state = one_band(gain_db=6.0, q=0.0)
    freqs, db = eq_response(state)
    assert np.all(np.isfinite(db))
    del freqs


def test_coefficients_are_normalised():
    b, a = biquad(EqBand(freq=1000.0, gain_db=6.0))
    assert a[0] == pytest.approx(1.0)
    assert len(b) == len(a) == 3


def test_empty_eq_is_flat():
    freqs, db = eq_response(EqState(enabled=True, band_count=0, bands=[]))
    assert np.allclose(db, 0.0)
    del freqs
