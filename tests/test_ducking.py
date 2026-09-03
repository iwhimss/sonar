"""Smart Volume zarfı.

Zarf saf bir fonksiyon olarak yazıldı (`next_depth`), bu yüzden PipeWire olmadan
zamanı elle ilerleterek test edilebiliyor.
"""

from __future__ import annotations

import pytest

from sonar.core.model import default_config
from sonar.engine.ducking import Ducker, duck_targets, next_depth

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
    for _ in range(10):  # 100 ms release süresi 500 ms'lik zarfın beşte biri
        depth = next_depth(
            depth, speaking=False, depth_db=-12, attack_ms=100, release_ms=500, dt=0.01
        )
    assert depth == pytest.approx(0.8)


def test_depth_never_leaves_the_unit_range():
    depth = next_depth(1.0, speaking=True, depth_db=-12, attack_ms=1, release_ms=1, dt=10)
    assert depth == 1.0
    depth = next_depth(0.0, speaking=False, depth_db=-12, attack_ms=1, release_ms=1, dt=10)
    assert depth == 0.0


# --------------------------------------------------------------------------- hedefler


def test_empty_target_list_means_every_other_channel():
    config = default_config()
    triggers, targets = duck_targets(config)
    assert triggers == {"chat"}
    assert targets == {"game", "media", "aux"}


def test_a_trigger_is_never_its_own_target():
    config = default_config()
    config.ducking.target_channels = ["chat", "media"]
    _, targets = duck_targets(config)
    assert targets == {"media"}


def test_unknown_channels_are_ignored():
    config = default_config()
    config.ducking.trigger_channels = ["chat", "yok"]
    triggers, _ = duck_targets(config)
    assert triggers == {"chat"}


# --------------------------------------------------------------------------- döngü


@pytest.fixture
def config():
    cfg = default_config()
    cfg.ducking.enabled = True
    cfg.ducking.reduction_db = -12.0
    cfg.ducking.threshold_db = -40.0
    cfg.ducking.attack_ms = 100.0
    cfg.ducking.hold_ms = 200.0
    cfg.ducking.release_ms = 400.0
    return cfg


def test_disabled_ducking_produces_no_gains(config):
    config.ducking.enabled = False
    assert Ducker().step(config, {"chat": 0.0}, 0.05) == {}


def test_a_loud_trigger_pulls_the_others_down(config):
    ducker = Ducker()
    for _ in range(4):  # 4 × 25 ms = 100 ms = tam attack
        gains = ducker.step(config, {"chat": -10.0}, 0.025)
    assert gains["media"] == pytest.approx(0.251, abs=0.01)  # -12 dB
    assert "chat" not in gains, "tetikleyici kendini kısmaz"


def test_silence_below_the_threshold_never_ducks(config):
    ducker = Ducker()
    for _ in range(10):
        gains = ducker.step(config, {"chat": -60.0}, 0.05)
    assert gains["media"] == pytest.approx(1.0)


def test_hold_keeps_the_duck_down_between_words(config):
    ducker = Ducker()
    for _ in range(4):
        ducker.step(config, {"chat": -10.0}, 0.025)
    assert ducker.depth == pytest.approx(1.0)

    # 100 ms sessizlik: hold 200 ms olduğu için hâlâ inik olmalı.
    for _ in range(4):
        ducker.step(config, {"chat": -80.0}, 0.025)
    assert ducker.depth == pytest.approx(1.0), "hold bitmeden çıkmamalı"

    # Hold bitti; release başlıyor.
    for _ in range(8):
        ducker.step(config, {"chat": -80.0}, 0.025)
    assert ducker.depth < 1.0


def test_reset_clears_the_envelope(config):
    ducker = Ducker()
    ducker.step(config, {"chat": -10.0}, 0.05)
    ducker.reset()
    assert ducker.depth == 0.0
    assert ducker.gains == {}
