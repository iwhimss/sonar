"""Smart Volume zarfı.

Zarf saf bir fonksiyon olarak yazıldı (`next_depth`), bu yüzden PipeWire olmadan
zamanı elle ilerleterek test edilebiliyor.

Şema 4'ten beri ayar **profilin** içinde: tetikleyici, Smart Volume'u açık olan profili
taşıyan kanalın kendisi.
"""

from __future__ import annotations

import pytest

from sonar.core.model import Profile, default_config
from sonar.engine.ducking import Ducker, duck_pairs, next_depth

# --------------------------------------------------------------------------- zarf


def test_attack_reaches_full_depth_in_the_configured_time():
    depth = 0.0
    for _ in range(10):  # 10 × 10 ms = 100 ms
        depth = next_depth(
            depth, speaking=True, depth_db=-12, attack_ms=100, release_ms=500, dt=0.01
        )
    assert depth == pytest.approx(1.0)


def test_release_is_slower_than_attack():
    depth = 1.0
    for _ in range(10):  # 100 ms, 500 ms'lik zarfın beşte biri
        depth = next_depth(
            depth, speaking=False, depth_db=-12, attack_ms=100, release_ms=500, dt=0.01
        )
    assert depth == pytest.approx(0.8)


def test_depth_never_leaves_the_unit_range():
    assert next_depth(1.0, speaking=True, depth_db=-12, attack_ms=1, release_ms=1, dt=10) == 1.0
    assert next_depth(0.0, speaking=False, depth_db=-12, attack_ms=1, release_ms=1, dt=10) == 0.0


# --------------------------------------------------------------------------- eşleşmeler


def _profiles(**enabled_for) -> dict[str, Profile]:
    """Kanal → profil. `enabled_for` verilen kanalların profilinde Smart Volume açık."""
    out: dict[str, Profile] = {}
    for channel in ("game", "chat", "media", "aux"):
        profile = Profile(name="Default")
        settings = enabled_for.get(channel)
        if settings is not None:
            profile.ducking.enabled = True
            for key, value in settings.items():
                setattr(profile.ducking, key, value)
        out[channel] = profile
    return out


def test_the_channel_that_owns_the_profile_is_the_trigger():
    config = default_config()
    profiles = _profiles(chat={})
    assert duck_pairs(config, profiles.__getitem__) == {"chat": {"game", "media", "aux"}}


def test_a_trigger_is_never_its_own_target():
    config = default_config()
    profiles = _profiles(chat={"target_channels": ["chat", "media"]})
    assert duck_pairs(config, profiles.__getitem__) == {"chat": {"media"}}


def test_no_enabled_profile_means_no_pairs():
    config = default_config()
    assert duck_pairs(config, _profiles().__getitem__) == {}


def test_two_channels_can_duck_independently():
    config = default_config()
    profiles = _profiles(chat={"target_channels": ["media"]}, game={"target_channels": ["media"]})
    assert duck_pairs(config, profiles.__getitem__) == {"chat": {"media"}, "game": {"media"}}


# --------------------------------------------------------------------------- döngü


@pytest.fixture
def config():
    return default_config()


def _fast(**extra) -> dict:
    return {"reduction_db": -12.0, "threshold_db": -40.0, "attack_ms": 100.0,
            "hold_ms": 200.0, "release_ms": 400.0, **extra}  # fmt: skip


def test_disabled_ducking_produces_no_gains(config):
    profiles = _profiles()
    assert Ducker().step(config, profiles.__getitem__, {"chat": 0.0}, 0.05) == {}


def test_a_loud_trigger_pulls_the_others_down(config):
    profiles = _profiles(chat=_fast())
    ducker = Ducker()
    for _ in range(4):  # 4 × 25 ms = 100 ms = tam attack
        gains = ducker.step(config, profiles.__getitem__, {"chat": -10.0}, 0.025)
    assert gains["media"] == pytest.approx(0.251, abs=0.01)  # -12 dB
    assert "chat" not in gains, "tetikleyici kendini kısmaz"


def test_silence_below_the_threshold_never_ducks(config):
    profiles = _profiles(chat=_fast())
    ducker = Ducker()
    for _ in range(10):
        gains = ducker.step(config, profiles.__getitem__, {"chat": -60.0}, 0.05)
    assert gains["media"] == pytest.approx(1.0)


def test_hold_keeps_the_duck_down_between_words(config):
    profiles = _profiles(chat=_fast())
    ducker = Ducker()
    for _ in range(4):
        ducker.step(config, profiles.__getitem__, {"chat": -10.0}, 0.025)
    assert ducker.depth["chat"] == pytest.approx(1.0)

    # 100 ms sessizlik: hold 200 ms olduğu için hâlâ inik olmalı.
    for _ in range(4):
        ducker.step(config, profiles.__getitem__, {"chat": -80.0}, 0.025)
    assert ducker.depth["chat"] == pytest.approx(1.0), "hold bitmeden çıkmamalı"

    for _ in range(8):
        ducker.step(config, profiles.__getitem__, {"chat": -80.0}, 0.025)
    assert ducker.depth["chat"] < 1.0


def test_the_deepest_duck_wins_when_two_triggers_overlap(config):
    """Çarpmak yerine en derin indirimi almak toplam indirimi ayarların ötesine taşımıyor."""
    profiles = _profiles(
        chat=_fast(reduction_db=-6.0, target_channels=["media"]),
        game=_fast(reduction_db=-18.0, target_channels=["media"]),
    )
    ducker = Ducker()
    for _ in range(6):
        gains = ducker.step(config, profiles.__getitem__, {"chat": -10.0, "game": -10.0}, 0.025)
    assert gains["media"] == pytest.approx(0.126, abs=0.01)  # -18 dB, -24 değil


def test_reset_clears_every_envelope(config):
    profiles = _profiles(chat=_fast())
    ducker = Ducker()
    ducker.step(config, profiles.__getitem__, {"chat": -10.0}, 0.05)
    ducker.reset()
    assert ducker.depth == {}
    assert ducker.gains == {}
