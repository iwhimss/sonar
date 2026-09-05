from __future__ import annotations

import numpy as np
import pytest

from sonar.core.dsp.response import eq_response
from sonar.core.model import FilterStage
from sonar.core.presets import (
    BUILTIN_MIC,
    BUILTIN_OUTPUT,
    builtin_names,
    builtin_profile,
    is_builtin,
)


def state_of(profile, kind):
    """Bir aşamanın profildeki durumu. Şema 7'de zincir slot listesi; testler aşama
    üzerinden bakmaya devam edebilsin diye ilk eşleşen slot dönüyor."""
    effect = next((e for e in profile.effects if e.kind is kind), None)
    return profile.state(effect.slot) if effect else None


def gain_at(profile, hz: float) -> float:
    _, db = eq_response(profile.eq, freqs=np.array([hz]))
    return float(db[0])


# --------------------------------------------------------------------------- katalog


def test_output_and_mic_have_separate_catalogues():
    assert "FPS Footsteps" in builtin_names("game")
    assert "FPS Footsteps" not in builtin_names("mic")
    assert "Broadcast" in builtin_names("mic")
    assert "Broadcast" not in builtin_names("game")


def test_flat_is_available_everywhere():
    assert "Flat" in builtin_names("game")
    assert "Flat" in builtin_names("mic")


def test_is_builtin_matches_the_catalogue():
    assert is_builtin("game", "Bass Boost") is True
    assert is_builtin("game", "Broadcast") is False
    assert is_builtin("mic", "Podcast") is True
    assert is_builtin("game", "CS2") is False


def test_unknown_preset_returns_none():
    assert builtin_profile("game", "YokBöyle") is None


def test_each_call_returns_a_fresh_copy():
    """Ortak nesne paylaşılırsa bir kanalın düzenlemesi diğerine sızar."""
    first = builtin_profile("game", "Bass Boost")
    first.eq.bands[0].gain_db = 99.0
    assert builtin_profile("game", "Bass Boost").eq.bands[0].gain_db != 99.0


@pytest.mark.parametrize("name", list(BUILTIN_OUTPUT))
def test_every_output_preset_builds(name):
    profile = builtin_profile("game", name)
    assert profile.name == name
    assert len(profile.eq.bands) == 10


@pytest.mark.parametrize("name", list(BUILTIN_MIC))
def test_every_mic_preset_builds(name):
    profile = builtin_profile("mic", name)
    assert profile.name == name


@pytest.mark.parametrize("name", list(BUILTIN_OUTPUT) + list(BUILTIN_MIC))
def test_no_preset_exceeds_the_gain_limits(name):
    target = "mic" if name in BUILTIN_MIC and name not in BUILTIN_OUTPUT else "game"
    profile = builtin_profile(target, name)
    for band in profile.eq.bands:
        assert -36.0 <= band.gain_db <= 36.0
        assert 0.05 <= band.q <= 100.0


# --------------------------------------------------------------------------- ses karakteri
#
# Preset'in adı ne vaat ediyorsa eğri onu yapmalı. Bunlar eğrinin gerçek DSP yanıtı olduğu
# ölçüldüğü için (Faz 8, sapma 0.01 dB) anlamlı testler.


def test_flat_is_transparent():
    profile = builtin_profile("game", "Flat")
    assert profile.eq.enabled is False
    # Şema 7: "Düz" preset'inde zincirde ekolayzerden başka efekt yok.
    assert [e.kind for e in profile.effects] == [FilterStage.EQ]


def test_fps_footsteps_lifts_the_presence_and_cuts_the_rumble():
    profile = builtin_profile("game", "FPS Footsteps")
    assert gain_at(profile, 3000.0) > 4.0, "ayak sesi bandı yükselmeli"
    assert gain_at(profile, 40.0) < -2.0, "gürültülü alt uç kısılmalı"


def test_bass_boost_lifts_the_bottom_only():
    profile = builtin_profile("game", "Bass Boost")
    assert gain_at(profile, 50.0) > 4.0
    assert gain_at(profile, 8000.0) == pytest.approx(0.0, abs=1.0)


def test_vocal_clarity_cuts_the_mud_and_lifts_speech():
    profile = builtin_profile("game", "Vocal Clarity")
    assert gain_at(profile, 250.0) < -2.0
    assert gain_at(profile, 2500.0) > 2.0


def test_music_is_a_v_curve():
    profile = builtin_profile("game", "Music")
    assert gain_at(profile, 50.0) > 2.0
    assert gain_at(profile, 12000.0) > 2.0
    assert gain_at(profile, 500.0) < 0.0


def test_night_mode_compresses_and_limits():
    profile = builtin_profile("game", "Night Mode")
    assert state_of(profile, FilterStage.COMP).enabled is True
    assert state_of(profile, FilterStage.COMP).params["ratio"] >= 4.0
    assert state_of(profile, FilterStage.LIMITER).enabled is True
    assert state_of(profile, FilterStage.LIMITER).params["ceiling_db"] <= -3.0


def test_broadcast_has_a_high_pass_and_a_compressor():
    profile = builtin_profile("mic", "Broadcast")
    types = [b.band_type for b in profile.eq.active_bands()]
    assert "high_pass" in types
    assert state_of(profile, FilterStage.COMP).enabled is True
    assert state_of(profile, FilterStage.LIMITER).enabled is True


def test_broadcast_removes_the_low_rumble():
    profile = builtin_profile("mic", "Broadcast")
    assert gain_at(profile, 30.0) < -6.0
    assert gain_at(profile, 1000.0) == pytest.approx(0.0, abs=2.0)


def test_podcast_tames_the_sibilance():
    profile = builtin_profile("mic", "Podcast")
    assert gain_at(profile, 8000.0) < -2.0


def test_aggressive_cleanup_maxes_the_noise_removal():
    profile = builtin_profile("mic", "Aggressive Cleanup")
    df = state_of(profile, FilterStage.DEEPFILTER)
    assert df.enabled is True
    assert df.params["attenuation_db"] == 100.0
    assert state_of(profile, FilterStage.GATE).enabled is True
