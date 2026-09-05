from __future__ import annotations

import itertools
import math

import pytest

from sonar.core.dsp import params, registry
from sonar.core.model import (
    DEFAULT_FILTER_PARAMS,
    EffectSlot,
    EqBand,
    EqBandType,
    EqState,
    FilterStage,
    FilterState,
    default_band_frequencies,
    default_band_q,
    default_profile,
)

# --------------------------------------------------------------------------- dB ↔ lineer


@pytest.mark.parametrize(
    ("db", "linear"),
    [(0.0, 1.0), (6.0206, 2.0), (-6.0206, 0.5), (20.0, 10.0), (-20.0, 0.1), (-36.0, 0.015849)],
)
def test_db_to_linear(db, linear):
    assert params.db_to_linear(db) == pytest.approx(linear, rel=1e-4)


def test_db_linear_roundtrip():
    for db in (-60.0, -12.5, 0.0, 3.3, 24.0):
        assert params.linear_to_db(params.db_to_linear(db)) == pytest.approx(db)


def test_silence_maps_to_zero():
    assert params.db_to_linear(-200.0) == 0.0
    assert params.linear_to_db(0.0) == params.SILENCE_DB
    assert params.linear_to_db(-1.0) == params.SILENCE_DB


# --------------------------------------------------------------------------- band varsayılanları


def test_ten_bands_are_octave_spaced():
    freqs = default_band_frequencies(10)
    assert freqs[0] == pytest.approx(31.25)
    assert freqs[-1] == pytest.approx(16_000.0)
    for lo, hi in itertools.pairwise(freqs):
        assert hi / lo == pytest.approx(2.0, rel=1e-3)


def test_octave_bands_get_classic_q():
    assert default_band_q(10) == pytest.approx(1.414, abs=1e-3)


@pytest.mark.parametrize("count", [5, 10, 16, 32])
def test_band_defaults_are_sane(count):
    freqs = default_band_frequencies(count)
    assert len(freqs) == count
    assert freqs == sorted(freqs)
    assert 0.05 < default_band_q(count) < 100.0


# --------------------------------------------------------------------------- EQ


def test_eq_gain_is_written_as_linear_not_db():
    eq = EqState(enabled=True, band_count=10, bands=[EqBand(freq=1000.0, gain_db=6.0206)])
    out = params.eq_params(eq, capacity=16)
    assert out["eq:g_0"] == pytest.approx(2.0, rel=1e-4)


def test_preamp_becomes_input_gain():
    eq = EqState(enabled=True, band_count=10, preamp_db=-6.0206, bands=[])
    assert params.eq_params(eq, 16)["eq:g_in"] == pytest.approx(0.5, rel=1e-4)


def test_unused_bands_are_switched_off():
    eq = EqState(enabled=True, band_count=2, bands=[EqBand(100.0), EqBand(1000.0)])
    out = params.eq_params(eq, capacity=16)
    assert out["eq:ft_0"] == float(params.BAND_TYPE_TO_LSP[EqBandType.PEAK])
    for index in range(2, 16):
        assert out[f"eq:ft_{index}"] == 0.0
        assert f"eq:g_{index}" not in out


def test_disabled_band_is_switched_off():
    eq = EqState(enabled=True, band_count=2, bands=[EqBand(100.0, enabled=False), EqBand(1000.0)])
    out = params.eq_params(eq, 16)
    assert out["eq:ft_0"] == 0.0
    assert out["eq:ft_1"] != 0.0


def test_eq_disabled_writes_enabled_zero_but_keeps_band_values():
    eq = EqState(enabled=False, band_count=1, bands=[EqBand(1000.0, gain_db=6.0)])
    out = params.eq_params(eq, 8)
    assert out["eq:enabled"] == 0.0
    assert out["eq:g_0"] == pytest.approx(params.db_to_linear(6.0))


def test_filter_model_is_apo_so_the_drawn_curve_matches():
    out = params.eq_params(EqState(band_count=1, bands=[EqBand(1000.0)]), 8)
    assert out["eq:fm_0"] == float(params.LSP_FILTER_MODEL_APO)


def test_band_values_are_clamped_to_plugin_range():
    eq = EqState(band_count=1, bands=[EqBand(freq=99_999.0, gain_db=999.0, q=999.0)])
    out = params.eq_params(eq, 8)
    spec = registry.plugin("lsp_para_eq_x8_stereo")
    assert out["eq:f_0"] <= spec.port("f_0").maximum
    assert out["eq:g_0"] <= spec.port("g_0").maximum
    assert out["eq:q_0"] <= spec.port("q_0").maximum


@pytest.mark.parametrize("band_type", list(EqBandType))
def test_every_band_type_maps_to_an_lsp_value(band_type):
    assert band_type in params.BAND_TYPE_TO_LSP


# --------------------------------------------------------------------------- dinamik aşamalar


def test_disabled_stage_only_writes_bypass():
    out = params.stage_params(FilterStage.GATE, FilterState(enabled=False))
    assert out == {"gate:enabled": 0.0}


def test_deepfilter_bypasses_via_zero_attenuation():
    """DeepFilterNet'in `enabled` portu yok; sıfır azaltma sınırı fiilen bypass demektir."""
    out = params.stage_params(FilterStage.DEEPFILTER, FilterState(enabled=False))
    assert out == {"df:Attenuation Limit (dB)": 0.0}


def test_enabled_gate_converts_units():
    state = FilterState(
        enabled=True,
        params={"threshold_db": -20.0, "attack_ms": 12.0, "release_ms": 250.0},
    )
    out = params.stage_params(FilterStage.GATE, state)
    assert out["gate:enabled"] == 1.0
    assert out["gate:gt"] == pytest.approx(0.1, rel=1e-4)  # -20 dB
    assert out["gate:at"] == 12.0  # ms doğrudan geçer
    assert out["gate:rt"] == 250.0


def test_missing_param_falls_back_to_stage_default():
    out = params.stage_params(FilterStage.COMP, FilterState(enabled=True, params={}))
    assert out["comp:cr"] == 4.0
    assert out["comp:al"] == pytest.approx(params.db_to_linear(-18.0))


def test_compressor_ratio_passes_through():
    state = FilterState(enabled=True, params={"ratio": 8.0})
    assert params.stage_params(FilterStage.COMP, state)["comp:cr"] == 8.0


def test_limiter_ceiling_is_linear():
    state = FilterState(enabled=True, params={"ceiling_db": -6.0206})
    assert params.stage_params(FilterStage.LIMITER, state)["lim:th"] == pytest.approx(0.5, rel=1e-4)


def test_stage_values_are_clamped_to_plugin_range():
    spec = registry.plugin("lsp_gate_stereo")
    state = FilterState(enabled=True, params={"attack_ms": 99_999.0, "threshold_db": -300.0})
    out = params.stage_params(FilterStage.GATE, state, spec)
    assert out["gate:at"] == spec.port("at").maximum
    assert out["gate:gt"] == spec.port("gt").minimum


def test_hysteresis_is_boolean():
    on = params.stage_params(FilterStage.GATE, FilterState(True, {"hysteresis": 1.0}))
    off = params.stage_params(FilterStage.GATE, FilterState(True, {"hysteresis": 0.0}))
    assert on["gate:gh"] == 1.0
    assert off["gate:gh"] == 0.0


def test_eq_via_stage_params_is_rejected():
    with pytest.raises(ValueError, match="eq_params"):
        params.stage_params(FilterStage.EQ, FilterState())


# --------------------------------------------------------------------------- profil

#: Node türlerini kapsayan temsili zincir; `CHAIN_ORDER`'ın tamamı değil.
CORE_CHAIN = (
    FilterStage.DEEPFILTER,
    FilterStage.GATE,
    FilterStage.EQ,
    FilterStage.COMP,
    FilterStage.SPATIAL,
    FilterStage.BOOST,
    FilterStage.LIMITER,
)


def full_profile(**kw):
    """Tüm aşamaları içeren bir profil. Şema 7'de varsayılan profilde yalnızca EQ var;
    zincirin tamamını sınayan testler efektleri kendisi ekliyor."""
    profile = default_profile(**kw)
    profile.effects = [
        # `enabled=False`: şema 6'daki "hepsi var ama kapalı" hâlinin karşılığı.
        # Kullanıcının **eklediği** bir efekt açık geliyor (`EffectSlot` varsayılanı).
        EffectSlot(
            kind=k, slot=k.value, enabled=False, params=dict(DEFAULT_FILTER_PARAMS.get(k, {}))
        )
        for k in CORE_CHAIN
    ]
    return profile


def without(profile, kind):
    profile.effects = [e for e in profile.effects if e.kind is not kind]
    return profile


def slot_of(profile, kind):
    return next(e for e in profile.effects if e.kind is kind)




def test_profile_to_params_covers_the_whole_chain():
    out = params.profile_to_params(full_profile())
    prefixes = {key.split(":", 1)[0] for key in out}
    # Spatial ve Boost kanal başına ayrı node'lara yayılıyor; anahtar öneki node adı.
    # Spatial kapalıyken yalnızca mikserin sızıntı kazancı yazılıyor (bypass).
    assert prefixes == {
        "df", "gate", "eq", "comp", "lim",
        "boost_l", "boost_r", "spatial_mix_l", "spatial_mix_r",
    }  # fmt: skip


def test_spatial_params_are_skipped_when_the_stage_is_not_in_the_chain():
    """Spatial yapısal; kapalıyken node'lar grafta yok, onlara yazmak kayıp olurdu."""
    out = params.profile_to_params(without(full_profile(), FilterStage.SPATIAL))
    assert not any(key.startswith("spatial_") for key in out)


def test_spatial_bypass_is_bit_transparent():
    """Sızıntı kazancı 0 → çıkış girişe birebir eşit (ölçüldü: R = -240 dBFS)."""
    out = params.profile_to_params(full_profile())
    assert out["spatial_mix_l:Gain 2"] == 0.0
    assert out["spatial_mix_r:Gain 2"] == 0.0


def test_spatial_maps_its_two_sliders_onto_the_crossfeed():
    profile = full_profile()
    spatial = slot_of(profile, FilterStage.SPATIAL)
    spatial.enabled = True
    spatial.params = {"immersion": 100.0, "distance": 100.0}
    out = params.profile_to_params(profile)

    assert out["spatial_mix_l:Gain 2"] == pytest.approx(params.SPATIAL_BLEED_MAX)
    assert out["spatial_delay_l:Delay (s)"] == pytest.approx(params.SPATIAL_DELAY_MAX_S)
    # Sürükleyicilik ucunda tizler daha erken kesiliyor.
    assert out["spatial_lp_l:Freq"] == pytest.approx(params.SPATIAL_CUTOFF_MIN_HZ)

    spatial.params = {"immersion": 0.0, "distance": 0.0}
    out = params.profile_to_params(profile)
    assert out["spatial_mix_l:Gain 2"] == pytest.approx(params.SPATIAL_BLEED_MIN)
    assert out["spatial_lp_l:Freq"] == pytest.approx(params.SPATIAL_CUTOFF_MAX_HZ)


def test_spatial_values_are_clamped():
    profile = full_profile()
    spatial = slot_of(profile, FilterStage.SPATIAL)
    spatial.enabled = True
    spatial.params = {"immersion": 500.0, "distance": -20.0}
    out = params.profile_to_params(profile)
    assert out["spatial_mix_l:Gain 2"] == pytest.approx(params.SPATIAL_BLEED_MAX)
    assert out["spatial_delay_l:Delay (s)"] == pytest.approx(params.SPATIAL_DELAY_MIN_S)


def test_profile_to_params_honours_a_shorter_chain():
    """DeepFilterNet kurulu değilse zincirden düşer; ona parametre yazmaya çalışmamalıyız."""
    out = params.profile_to_params(without(full_profile(), FilterStage.DEEPFILTER))
    assert not any(key.startswith("df:") for key in out)


def test_profile_to_params_picks_the_right_eq_capacity():
    profile = full_profile(band_count=32)
    out = params.profile_to_params(profile)
    assert "eq:ft_31" in out
    assert "eq:ft_32" not in out


def test_default_profile_only_has_the_equalizer():
    """Şema 7: yeni profil yalnızca ekolayzerle geliyor, o da kapalı.

    Kullanıcının isteği (test turu 6): *"Profil ayarlarına girince sadece ekolayzer ayarı
    gözüksün. Diğer ayarları kullanıcı kendisi eklesin."*
    """
    out = params.profile_to_params(default_profile())
    assert {key.split(":", 1)[0] for key in out} == {"eq"}
    assert out["eq:enabled"] == 0.0
    for index in range(10):
        assert out[f"eq:g_{index}"] == pytest.approx(1.0)


def test_a_full_chain_is_transparent_while_every_effect_is_off():
    """Zincirdeki her efekt kapalıyken graf hiçbir şeyi değiştirmemeli."""
    out = params.profile_to_params(full_profile())
    assert out["eq:enabled"] == 0.0
    assert out["gate:enabled"] == 0.0
    assert out["comp:enabled"] == 0.0
    assert out["lim:enabled"] == 0.0
    assert out["df:Attenuation Limit (dB)"] == 0.0


def test_all_values_are_finite():
    out = params.profile_to_params(default_profile(band_count=32))
    assert all(math.isfinite(v) for v in out.values())


def test_param_key_format():
    assert params.param_key(FilterStage.EQ, "g_3") == "eq:g_3"
