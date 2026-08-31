from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6.QtQuick")

from sonar.core.model import EqBandType
from sonar.gui.eqcurve import NODE_COLORS, eq_from_json


def payload(**overrides) -> str:
    data = {
        "enabled": True,
        "band_count": 2,
        "preamp_db": -1.5,
        "bands": [
            {
                "freq": 100.0,
                "gain_db": 6.0,
                "q": 1.4,
                "band_type": "peak",
                "slope": 0,
                "enabled": True,
            },
            {
                "freq": 4000.0,
                "gain_db": -3.0,
                "q": 2.0,
                "band_type": "high_shelf",
                "slope": 1,
                "enabled": False,
            },
        ],
    }
    data.update(overrides)
    return json.dumps(data)


def test_round_trip():
    eq = eq_from_json(payload())
    assert eq.enabled is True
    assert eq.band_count == 2
    assert eq.preamp_db == -1.5
    assert eq.bands[0].freq == 100.0
    assert eq.bands[1].band_type is EqBandType.HIGH_SHELF
    assert eq.bands[1].enabled is False
    assert eq.bands[1].slope == 1


def test_empty_payload_is_a_flat_eq():
    for text in ("", "{}", "bu json değil"):
        eq = eq_from_json(text)
        assert eq.enabled is False
        assert eq.bands == []


def test_broken_band_is_skipped_not_fatal():
    """Tek bozuk band tüm eğriyi düşürmemeli."""
    eq = eq_from_json(
        json.dumps(
            {
                "enabled": True,
                "bands": [
                    {"freq": "abc"},
                    {"freq": 1000.0, "gain_db": 3.0, "band_type": "peak"},
                ],
            }
        )
    )
    assert len(eq.bands) == 1
    assert eq.bands[0].freq == 1000.0


def test_unknown_band_type_is_skipped():
    eq = eq_from_json(json.dumps({"enabled": True, "bands": [{"freq": 1.0, "band_type": "yok"}]}))
    assert eq.bands == []


def test_band_count_defaults_to_the_band_list_length():
    eq = eq_from_json(json.dumps({"bands": [{"freq": 100.0}, {"freq": 200.0}]}))
    assert eq.band_count == 2


def test_node_colours_are_distinct():
    assert len(set(NODE_COLORS)) == len(NODE_COLORS)


# --------------------------------------------------------------------------- koordinatlar
#
# Öğe bir QGuiApplication istiyor; testlerin geri kalanı QCoreApplication kurduğu için
# ayrı süreçte çalıştırılıyor (aynı süreçte ikisi bir arada Qt'yi abort ettiriyor).


def test_coordinate_mapping_round_trips():
    import os
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        """
        from PySide6.QtGui import QGuiApplication
        app = QGuiApplication([])
        from sonar.gui.eqcurve import EqCurve
        import json

        curve = EqCurve()
        curve.setWidth(800); curve.setHeight(300)
        curve.eq = json.dumps({"enabled": True, "band_count": 2, "bands": [
            {"freq": 100.0, "gain_db": 6.0, "q": 1.4, "band_type": "peak",
             "slope": 0, "enabled": True},
            {"freq": 4000.0, "gain_db": -3.0, "q": 2.0, "band_type": "peak",
             "slope": 0, "enabled": True}]})

        assert abs(curve.freqForX(curve.xForFreq(1000.0)) - 1000.0) < 0.5
        assert abs(curve.gainForY(curve.yForGain(6.0)) - 6.0) < 0.01
        # 0 dB tam ortada
        assert abs(curve.yForGain(0.0) - 150.0) < 0.01
        # aralık dışı değerler kırpılıyor
        assert curve.xForFreq(1.0) == 0.0
        assert curve.xForFreq(99999.0) == 800.0
        # isabet testi
        assert curve.bandAt(curve.xForFreq(4000.0), curve.yForGain(-3.0)) == 1
        assert curve.bandAt(5.0, 5.0) == -1
        # boyutsuz öğe çökmemeli
        empty = EqCurve()
        assert empty.freqForX(10.0) > 0
        assert empty.gainForY(10.0) == 0.0
        print("OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=False,
    )
    assert "OK" in result.stdout, result.stdout + result.stderr
