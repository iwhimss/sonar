from __future__ import annotations

import json

import pytest

from sonar.core.importers import (
    ProfileImportError,
    detect_format,
    export_autoeq,
    export_profile,
    import_any,
    parse_apo,
    parse_autoeq,
    parse_easyeffects,
    parse_sonarprofile,
)
from sonar.core.model import EqBandType, default_profile

AUTOEQ = """\
Preamp: -6.2 dB
Filter 1: ON LSC Fc 105 Hz Gain 4.5 dB Q 0.70
Filter 2: ON PK Fc 1200 Hz Gain -3.1 dB Q 1.41
Filter 3: ON HSC Fc 10000 Hz Gain 2.0 dB Q 0.70
"""

APO = """\
Preamp: -3.0 dB
Filter 1: ON PK Fc 60 Hz Gain 5.0 dB Q 1.00
Filter 2: OFF PK Fc 500 Hz Gain -2.0 dB Q 2.00
Filter 3: ON HP Fc 30 Hz Q 0.71
"""

EASYEFFECTS = json.dumps(
    {
        "output": {
            "equalizer": {
                "input-gain": -2.0,
                "left": {
                    "band0": {"type": "Bell", "frequency": 100.0, "gain": 3.0, "q": 1.2},
                    "band1": {"type": "Hi-shelf", "frequency": 8000.0, "gain": -2.0, "q": 0.7},
                    "band2": {"type": "Off", "frequency": 500.0, "gain": 9.0, "q": 1.0},
                },
            }
        }
    }
)


# --------------------------------------------------------------------------- AutoEQ / APO


def test_autoeq_round_trip():
    result = parse_autoeq(AUTOEQ, "HD650")
    assert result.source == "autoeq"
    assert result.profile.name == "HD650"
    assert result.profile.eq.enabled is True
    assert result.profile.eq.preamp_db == -6.2

    bands = result.profile.eq.active_bands()
    assert bands[0].freq == 105.0
    assert bands[0].band_type is EqBandType.LOW_SHELF
    assert bands[1].gain_db == -3.1
    assert bands[2].band_type is EqBandType.HIGH_SHELF


def test_bands_are_sorted_by_frequency():
    text = "Filter 1: ON PK Fc 8000 Hz Gain 1 dB Q 1\nFilter 2: ON PK Fc 100 Hz Gain 1 dB Q 1\n"
    freqs = [b.freq for b in parse_autoeq(text).profile.eq.active_bands()[:2]]
    assert freqs == [100.0, 8000.0]


def test_disabled_filter_is_kept_but_marked_off():
    result = parse_apo(APO)
    disabled = [b for b in result.profile.eq.active_bands() if not b.enabled]
    assert len(disabled) == 1
    assert disabled[0].freq == 500.0


def test_filter_without_a_gain_defaults_to_zero():
    """High-pass satırlarında `Gain` alanı yoktur."""
    band = next(b for b in parse_apo(APO).profile.eq.active_bands() if b.freq == 30.0)
    assert band.band_type is EqBandType.HIGH_PASS
    assert band.gain_db == 0.0


def test_unknown_filter_type_is_skipped():
    text = "Filter 1: ON XYZ Fc 100 Hz Gain 3 dB Q 1\nFilter 2: ON PK Fc 200 Hz Gain 1 dB Q 1\n"
    assert len(parse_autoeq(text).profile.eq.active_bands()) >= 1
    assert all(b.freq != 100.0 for b in parse_autoeq(text).profile.eq.active_bands() if b.enabled)


def test_file_without_filters_is_an_error():
    with pytest.raises(ProfileImportError, match="bandı bulunamadı"):
        parse_autoeq("Preamp: -3.0 dB\n")


def test_export_round_trips_through_autoeq():
    original = parse_autoeq(AUTOEQ, "HD650").profile
    again = parse_autoeq(export_autoeq(original), "HD650").profile
    for a, b in zip(original.eq.active_bands()[:3], again.eq.active_bands()[:3], strict=True):
        assert a.freq == pytest.approx(b.freq)
        assert a.gain_db == pytest.approx(b.gain_db, abs=0.05)
        assert a.band_type is b.band_type
    assert again.eq.preamp_db == pytest.approx(original.eq.preamp_db)


# --------------------------------------------------------------------------- band sayısı


def test_band_count_rounds_up_to_a_supported_size():
    """Zincirin kapasitesi 8/16/32; 3 band 5'lik bir profile sığar."""
    assert parse_autoeq(AUTOEQ).profile.eq.band_count == 5


@pytest.mark.parametrize(("count", "expected"), [(3, 5), (7, 10), (12, 16), (20, 32)])
def test_band_count_steps(count, expected):
    lines = [f"Filter {i}: ON PK Fc {100 * (i + 1)} Hz Gain 1 dB Q 1" for i in range(count)]
    assert parse_autoeq("\n".join(lines)).profile.eq.band_count == expected


def test_too_many_bands_drops_the_weakest_and_warns():
    lines = [
        f"Filter {i}: ON PK Fc {50 + i * 100} Hz Gain {0.1 if i > 5 else 9.0} dB Q 1"
        for i in range(40)
    ]
    result = parse_autoeq("\n".join(lines))
    assert result.profile.eq.band_count == 32
    assert result.dropped == 8
    assert result.warnings and "sığmadı" in result.warnings[0]
    # Güçlü bandlar korunmuş olmalı.
    assert any(abs(b.gain_db) > 5 for b in result.profile.eq.active_bands())


def test_unused_bands_are_switched_off():
    """Aksi hâlde varsayılan frekanslar profile sızar ve eğri yanlış görünür."""
    result = parse_autoeq(AUTOEQ)
    extra = result.profile.eq.active_bands()[3:]
    assert all(b.band_type is EqBandType.OFF for b in extra)


# --------------------------------------------------------------------------- EasyEffects


def test_easyeffects_import():
    result = parse_easyeffects(EASYEFFECTS)
    assert result.source == "easyeffects"
    bands = result.profile.eq.active_bands()
    assert bands[0].freq == 100.0
    assert bands[0].band_type is EqBandType.PEAK
    assert bands[1].band_type is EqBandType.HIGH_SHELF
    assert result.profile.eq.preamp_db == -2.0


def test_easyeffects_off_bands_are_skipped():
    assert len(parse_easyeffects(EASYEFFECTS).profile.eq.active_bands()) >= 2
    freqs = [b.freq for b in parse_easyeffects(EASYEFFECTS).profile.eq.active_bands()[:2]]
    assert 500.0 not in freqs


def test_easyeffects_without_an_equalizer_is_an_error():
    with pytest.raises(ProfileImportError, match="ekolayzer"):
        parse_easyeffects(json.dumps({"output": {"compressor": {}}}))


def test_broken_json_is_an_error():
    with pytest.raises(ProfileImportError):
        parse_easyeffects("{ bozuk")


# --------------------------------------------------------------------------- kendi formatımız


def test_sonarprofile_round_trip():
    profile = default_profile("CS2")
    profile.eq.enabled = True
    profile.eq.bands[2].gain_db = 6.0
    text = export_profile(profile)
    back = parse_sonarprofile(text).profile
    assert back.name == "CS2"
    assert back.eq.bands[2].gain_db == 6.0


def test_sonarprofile_rejects_a_newer_schema():
    text = json.dumps({"schema_version": 99, "kind": "sonar-profile", "profile": {}})
    with pytest.raises(ProfileImportError, match="daha yeni"):
        parse_sonarprofile(text)


def test_sonarprofile_rejects_a_foreign_file():
    with pytest.raises(ProfileImportError, match="Sonar profili değil"):
        parse_sonarprofile(json.dumps({"hello": 1}))


def test_sonarprofile_name_can_be_overridden():
    text = export_profile(default_profile("Eski"))
    assert parse_sonarprofile(text, "Yeni").profile.name == "Yeni"


# --------------------------------------------------------------------------- otomatik seçim
#
# Uzantıya güvenmiyoruz: kullanıcı dosyayı indirirken adı değişmiş olabilir.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (AUTOEQ, "autoeq"),
        (APO, "autoeq"),
        (EASYEFFECTS, "easyeffects"),
        (export_profile(default_profile("X")), "sonarprofile"),
        ("merhaba dünya", "unknown"),
        ("{ bozuk json", "unknown"),
        ('{"başka": "json"}', "unknown"),
    ],
)
def test_format_detection(text, expected):
    assert detect_format(text) == expected


def test_import_any_dispatches():
    assert import_any(AUTOEQ).source == "autoeq"
    assert import_any(EASYEFFECTS).source == "easyeffects"
    assert import_any(export_profile(default_profile("X"))).source == "sonarprofile"


def test_import_any_rejects_an_unknown_file():
    with pytest.raises(ProfileImportError, match="tanınmadı"):
        import_any("bu bir EQ dosyası değil")
