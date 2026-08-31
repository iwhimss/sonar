from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from sonar.core.model import default_config
from sonar.engine.meters import (
    CLIP_HOLD_S,
    FLOOR_DB,
    Level,
    MeterManager,
    MeterSource,
    PeakHold,
    analyse,
    meter_sources,
    to_db,
)

# --------------------------------------------------------------------------- dB dönüşümü


def test_full_scale_is_zero_db():
    assert to_db(1.0) == pytest.approx(0.0)


def test_half_scale_is_minus_six_db():
    assert to_db(0.5) == pytest.approx(-6.02, abs=0.01)


def test_silence_hits_the_floor():
    assert to_db(0.0) == FLOOR_DB
    assert to_db(1e-9) == FLOOR_DB


def test_negative_input_is_treated_as_silence():
    assert to_db(-1.0) == FLOOR_DB


# --------------------------------------------------------------------------- analiz


def test_sine_peak_and_rms():
    """Sinüsün RMS'i tepesinin 1/√2'si — tam 3.01 dB altında."""
    t = np.arange(8000) / 8000.0
    block = (0.5 * np.sin(2 * np.pi * 100 * t)).astype(np.float32)
    peak_db, rms_db, clipped = analyse(block)
    assert peak_db == pytest.approx(-6.02, abs=0.05)
    assert rms_db == pytest.approx(-9.03, abs=0.05)
    assert clipped is False


def test_silence_reads_the_floor():
    peak_db, rms_db, clipped = analyse(np.zeros(160, dtype=np.float32))
    assert (peak_db, rms_db, clipped) == (FLOOR_DB, FLOOR_DB, False)


def test_empty_block_is_safe():
    assert analyse(np.array([], dtype=np.float32)) == (FLOOR_DB, FLOOR_DB, False)


def test_clip_is_detected():
    block = np.array([0.1, 1.0, -0.2], dtype=np.float32)
    _peak, _rms, clipped = analyse(block)
    assert clipped is True


def test_nan_and_inf_do_not_poison_the_meter():
    """Bozuk bir tampon metreyi NaN'a kilitlememeli."""
    block = np.array([0.5, np.nan, np.inf, -0.5], dtype=np.float32)
    peak_db, rms_db, _clipped = analyse(block)
    assert np.isfinite(peak_db) and np.isfinite(rms_db)
    assert peak_db == pytest.approx(-6.02, abs=0.05)


# --------------------------------------------------------------------------- peak-hold


def test_hold_keeps_the_peak_then_decays():
    hold = PeakHold(hold_s=1.5, decay_db_per_s=20.0)
    assert hold.update(-10.0, 0.0) == -10.0
    assert hold.update(-40.0, 1.0) == -10.0, "tutma süresi içinde düşmemeli"
    assert hold.update(-40.0, 2.0) == pytest.approx(-20.0), "0.5 s düşüş = 10 dB"


def test_hold_rises_immediately():
    hold = PeakHold()
    hold.update(-30.0, 0.0)
    assert hold.update(-5.0, 0.1) == -5.0


def test_hold_never_goes_below_the_floor():
    hold = PeakHold(hold_s=0.0, decay_db_per_s=20.0)
    hold.update(-10.0, 0.0)
    assert hold.update(FLOOR_DB, 100.0) == FLOOR_DB


# --------------------------------------------------------------------------- ölçüm noktaları


def test_meter_sources_cover_every_channel_bus_and_mic():
    sources = meter_sources(default_config())
    assert set(sources) == {
        "sonar_game_fx",
        "sonar_chat_fx",
        "sonar_media_fx",
        "sonar_aux_fx",
        "sonar_personal",
        "sonar_stream",
        "sonar_mic",
        "sonar_stream_mic",
    }


def test_only_buses_capture_the_monitor():
    """`_fx` ve mikrofonlar birer kaynak; bus'lar sink olduğu için monitörleri alınır."""
    sources = meter_sources(default_config())
    assert sources["sonar_personal"] is True
    assert sources["sonar_stream"] is True
    assert sources["sonar_game_fx"] is False
    assert sources["sonar_mic"] is False


def test_capture_command_shape():
    source = MeterSource("sonar_game_fx")
    assert source.command == [
        "pw-cat", "--record", "--target", "sonar_game_fx",
        "--latency", "500ms",
        "--rate", "8000", "--channels", "1", "--format", "f32", "-",
    ]  # fmt: skip


def test_capture_asks_for_a_large_buffer():
    """Ölçüldü: `pw-cat` CPU'sunu üçte bire indiriyor, tepki gecikmesini değiştirmiyor."""
    assert "--latency" in MeterSource("x").command


def test_sink_capture_adds_the_flag():
    assert "stream.capture.sink=true" in MeterSource("sonar_personal", capture_sink=True).command


# --------------------------------------------------------------------------- MeterSource


def test_feed_updates_the_level():
    source = MeterSource("x")
    source.feed(np.full(160, 0.5, dtype=np.float32), now=0.0)
    level = source.level(now=0.0)
    assert level.peak_db == pytest.approx(-6.02, abs=0.05)
    assert level.rms_db == pytest.approx(-6.02, abs=0.05)
    assert level.silent is False


def test_clip_flag_holds_then_clears():
    source = MeterSource("x")
    source.feed(np.array([1.0], dtype=np.float32), now=0.0)
    assert source.level(now=0.5).clipped is True
    assert source.level(now=CLIP_HOLD_S + 0.1).clipped is False


def test_level_falls_back_to_silence():
    source = MeterSource("x")
    source.feed(np.zeros(160, dtype=np.float32), now=0.0)
    assert source.level(now=0.0).silent is True


def test_stop_resets_the_state():
    source = MeterSource("x")
    source.feed(np.full(160, 0.5, dtype=np.float32), now=0.0)
    source.stop()
    assert source.level().silent is True


# --------------------------------------------------------------------------- MeterManager


class FakeSource:
    instances: ClassVar[list[FakeSource]] = []

    def __init__(self, node: str, capture_sink: bool) -> None:
        self.node = node
        self.capture_sink = capture_sink
        self.started = 0
        self.stopped = 0
        FakeSource.instances.append(self)

    def start(self):
        self.started += 1

    def stop(self, timeout: float = 2.0):
        self.stopped += 1

    def level(self, now=None):
        return Level(-12.0, -15.0, -12.0, False)


@pytest.fixture
def manager():
    FakeSource.instances = []
    mgr = MeterManager(interval=0, source_factory=FakeSource)
    mgr.configure(meter_sources(default_config()))
    return mgr


def test_nothing_runs_without_subscribers(manager):
    """Daemon tek başınayken tek bir ölçüm süreci bile açılmamalı."""
    assert manager.running is False
    assert manager.levels() == {}
    assert FakeSource.instances == []


def test_first_subscriber_starts_the_sources(manager):
    manager.subscribe()
    assert manager.running is True
    assert len(manager.nodes) == 8
    assert all(s.started == 1 for s in FakeSource.instances)


def test_second_subscriber_does_not_restart(manager):
    manager.subscribe()
    count = len(FakeSource.instances)
    manager.subscribe()
    assert manager.subscribers == 2
    assert len(FakeSource.instances) == count


def test_last_unsubscribe_stops_everything(manager):
    manager.subscribe()
    manager.subscribe()
    manager.unsubscribe()
    assert manager.running is True, "hâlâ bir abone var"
    manager.unsubscribe()
    assert manager.running is False
    assert all(s.stopped == 1 for s in FakeSource.instances)


def test_unsubscribe_never_goes_negative(manager):
    assert manager.unsubscribe() == 0
    assert manager.unsubscribe() == 0


def test_levels_are_reported_per_node(manager):
    manager.subscribe()
    levels = manager.levels()
    assert set(levels) == set(manager.nodes)
    assert levels["sonar_game_fx"].peak_db == -12.0


def test_reconfigure_while_running_restarts_sources(manager):
    """Graf yeniden kurulunca ölçüm noktaları da yeniden bağlanmalı."""
    manager.subscribe()
    first = list(FakeSource.instances)
    manager.configure({"sonar_yeni_fx": False})
    assert all(s.stopped == 1 for s in first)
    assert manager.nodes == ("sonar_yeni_fx",)


def test_reconfigure_while_idle_starts_nothing(manager):
    manager.configure({"sonar_yeni_fx": False})
    assert manager.running is False
    assert FakeSource.instances == []


def test_stop_clears_subscribers(manager):
    manager.subscribe()
    manager.stop()
    assert manager.subscribers == 0
    assert manager.running is False
