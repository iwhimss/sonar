from __future__ import annotations

import ctypes
import re
from pathlib import Path

import pytest

from sonar.core.dsp import registry
from sonar.core.model import SUPPORTED_BAND_COUNTS

# --------------------------------------------------------------------------- katalog tutarlılığı


def test_catalog_keys_match_specs():
    for key, spec in registry.PLUGINS.items():
        assert spec.key == key


def test_every_plugin_has_matching_io():
    for spec in registry.PLUGINS.values():
        assert len(spec.audio_in) == len(spec.audio_out) >= 1


def test_port_defaults_are_inside_their_range():
    for spec in registry.PLUGINS.values():
        for port in spec.ports.values():
            assert port.minimum <= port.default <= port.maximum, f"{spec.key}:{port.symbol}"


def test_clamp_respects_bounds():
    spec = registry.plugin("lsp_gate_stereo")
    assert spec.clamp("at", -5.0) == 0.0
    assert spec.clamp("at", 1e9) == 2000.0
    assert spec.clamp("bilinmeyen_port", 1234.0) == 1234.0


def test_unknown_plugin_raises():
    with pytest.raises(KeyError, match="katalogda böyle bir eklenti yok"):
        registry.plugin("yok_böyle")


@pytest.mark.parametrize("band_count", SUPPORTED_BAND_COUNTS)
def test_eq_variant_covers_requested_bands(band_count):
    spec = registry.eq_plugin_for(band_count)
    assert spec.band_capacity >= band_count
    assert f"ft_{band_count - 1}" in spec.ports


def test_eq_capacity_is_fixed_at_the_largest_variant():
    """Kapasite band sayısından bağımsız: band eklemek grafı yeniden kurmasın diye.

    Bedeli ölçüldü (altı zincir, ses akarken): x16 %11.6, x32 %12.0 — kullanılmayan
    bandlar `ft = 0` ile kapalı ve analizörler zaten kapalı olduğu için neredeyse bedava.
    """
    for count in (5, 10, 16, 32):
        assert registry.eq_plugin_for(count).band_capacity == registry.EQ_CAPACITY


def test_mono_variants_exist():
    assert registry.eq_plugin_for(10, channels=1).channels == 1
    assert registry.plugin("lsp_gate_mono").channels == 1
    assert registry.plugin("deepfilter_mono").channels == 1


def test_eq_has_all_per_band_ports():
    spec = registry.plugin("lsp_para_eq_x16_stereo")
    for index in range(16):
        for prefix in ("ft", "fm", "s", "f", "g", "q", "xs", "xm"):
            assert f"{prefix}_{index}" in spec.ports


# --------------------------------------------------------------------------- kurulu mu?


def test_availability_probe_runs():
    result = registry.available_plugins()
    assert set(result) == set(registry.PLUGINS)
    assert all(isinstance(v, bool) for v in result.values())


def test_unknown_plugin_is_not_available():
    assert registry.is_available("yok_böyle") is False


def test_search_path_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "LADSPA_SEARCH_PATH", (tmp_path,))
    registry.clear_cache()
    assert registry.is_available("deepfilter_stereo") is False
    (tmp_path / "libdeep_filter_ladspa.so").write_bytes(b"")
    registry.clear_cache()
    assert registry.is_available("deepfilter_stereo") is True
    registry.clear_cache()


# --------------------------------------------------------------------------- gerçek sisteme karşı
#
# Bu testler statik kataloğun kurulu eklentilerle hâlâ örtüştüğünü doğrular. Eklenti kurulu
# değilse atlanır — CI'da veya farklı bir makinede paketin yokluğu hata sayılmamalı.


def _lsp_ttl(name: str) -> Path | None:
    for root in registry.LV2_SEARCH_PATH:
        candidate = root / "lsp-plugins.lv2" / f"{name}.ttl"
        if candidate.is_file():
            return candidate
    return None


def _ttl_ports(path: Path) -> dict[str, dict[str, float]]:
    text = path.read_text(errors="replace")
    out: dict[str, dict[str, float]] = {}
    for block in re.split(r"\]\s*,\s*\[", text):
        match = re.search(r'lv2:symbol "([^"]+)"', block)
        if not match:
            continue
        values: dict[str, float] = {}
        for field in ("minimum", "maximum", "default"):
            found = re.search(rf"lv2:{field}\s+(-?[\d.eE+-]+)", block)
            if found:
                values[field] = float(found.group(1))
        out[match.group(1)] = values
    return out


@pytest.mark.parametrize(
    ("key", "ttl"),
    [
        ("lsp_para_eq_x16_stereo", "para_equalizer_x16_stereo"),
        ("lsp_gate_stereo", "gate_stereo"),
        ("lsp_compressor_stereo", "compressor_stereo"),
        ("lsp_limiter_stereo", "limiter_stereo"),
    ],
)
def test_catalog_matches_installed_ttl(key, ttl):
    path = _lsp_ttl(ttl)
    if path is None:
        pytest.skip(f"lsp-plugins kurulu değil ({ttl})")

    actual = _ttl_ports(path)
    spec = registry.plugin(key)
    for symbol, port in spec.ports.items():
        assert symbol in actual, f"{key}: '{symbol}' portu eklentide yok"
        real = actual[symbol]
        for field, ours in (
            ("minimum", port.minimum),
            ("maximum", port.maximum),
            ("default", port.default),
        ):
            if field not in real:
                continue
            assert ours == pytest.approx(real[field], rel=1e-4), (
                f"{key}:{symbol}.{field} — katalog {ours}, eklenti {real[field]}"
            )


def test_installed_eq_audio_ports_exist():
    path = _lsp_ttl("para_equalizer_x16_stereo")
    if path is None:
        pytest.skip("lsp-plugins kurulu değil")
    symbols = set(_ttl_ports(path))
    spec = registry.plugin("lsp_para_eq_x16_stereo")
    assert set(spec.audio_in) <= symbols
    assert set(spec.audio_out) <= symbols


def test_deepfilter_catalog_matches_the_real_library():
    library = None
    for root in registry.LADSPA_SEARCH_PATH:
        candidate = root / "libdeep_filter_ladspa.so"
        if candidate.is_file():
            library = candidate
            break
    if library is None:
        pytest.skip("deepfilter-ladspa kurulu değil")

    for spec in (registry.plugin("deepfilter_mono"), registry.plugin("deepfilter_stereo")):
        descriptor = _ladspa_descriptor(library, spec.label)
        assert descriptor is not None, f"{spec.label} kütüphanede yok"
        names, hints = descriptor
        assert list(spec.audio_in) + list(spec.audio_out) == names[: len(spec.audio_in) * 2]
        for symbol, port in spec.ports.items():
            assert symbol in hints, f"{spec.label}: '{symbol}' portu yok"
            low, high = hints[symbol]
            assert port.minimum == pytest.approx(low)
            assert port.maximum == pytest.approx(high)


class _LadspaHint(ctypes.Structure):
    _fields_ = [
        ("HintDescriptor", ctypes.c_int),
        ("LowerBound", ctypes.c_float),
        ("UpperBound", ctypes.c_float),
    ]


class _LadspaDescriptor(ctypes.Structure):
    _fields_ = [
        ("UniqueID", ctypes.c_ulong),
        ("Label", ctypes.c_char_p),
        ("Properties", ctypes.c_int),
        ("Name", ctypes.c_char_p),
        ("Maker", ctypes.c_char_p),
        ("Copyright", ctypes.c_char_p),
        ("PortCount", ctypes.c_ulong),
        ("PortDescriptors", ctypes.POINTER(ctypes.c_int)),
        ("PortNames", ctypes.POINTER(ctypes.c_char_p)),
        ("PortRangeHints", ctypes.POINTER(_LadspaHint)),
        ("ImplementationData", ctypes.c_void_p),
    ]


def _ladspa_descriptor(library: Path, label: str):
    """`(port adları, {kontrol portu: (alt, üst)})` döndürür."""
    lib = ctypes.CDLL(str(library))
    lib.ladspa_descriptor.restype = ctypes.POINTER(_LadspaDescriptor)
    lib.ladspa_descriptor.argtypes = [ctypes.c_ulong]
    index = 0
    while pointer := lib.ladspa_descriptor(index):
        descriptor = pointer.contents
        if descriptor.Label.decode() == label:
            names = [descriptor.PortNames[i].decode() for i in range(descriptor.PortCount)]
            hints = {
                names[i]: (
                    descriptor.PortRangeHints[i].LowerBound,
                    descriptor.PortRangeHints[i].UpperBound,
                )
                for i in range(descriptor.PortCount)
                if descriptor.PortDescriptors[i] & 0x4  # LADSPA_PORT_CONTROL
            }
            return names, hints
        index += 1
    return None


# --------------------------------------------------------------------------- Turtle URI çıkarımı


def test_extract_expands_prefix_abbreviations():
    """LSP manifest'i kısaltma kullanır; tam URI aramak yeterli değil (bu hata yaşandı)."""
    ttl = (
        "@prefix lv2:  <http://lv2plug.in/ns/lv2core#> .\n"
        "@prefix plug: <http://lsp-plug.in/plugins/lv2/> .\n"
        "\n"
        "plug:para_equalizer_x16_stereo\n"
        "\ta lv2:Plugin ;\n"
        "\tlv2:binary <lsp-plugins-lv2.so> .\n"
    )
    uris = registry.extract_ttl_uris(ttl)
    assert "http://lsp-plug.in/plugins/lv2/para_equalizer_x16_stereo" in uris


def test_extract_handles_explicit_uris():
    ttl = "<http://example.org/thing> a lv2:Plugin .\n"
    assert "http://example.org/thing" in registry.extract_ttl_uris(ttl)


def test_extract_ignores_comments_and_relative_paths():
    ttl = (
        "@prefix plug: <http://lsp-plug.in/plugins/lv2/> .\n"
        "# plug:kapali_eklenti\n"
        "plug:acik a lv2:Plugin ; rdfs:seeAlso <acik.ttl> .\n"
    )
    uris = registry.extract_ttl_uris(ttl)
    assert "http://lsp-plug.in/plugins/lv2/acik" in uris
    assert "http://lsp-plug.in/plugins/lv2/kapali_eklenti" not in uris
    assert not any(u.endswith("acik.ttl") for u in uris)


def test_extract_does_not_invent_uris_from_unknown_prefixes():
    assert registry.extract_ttl_uris("bilinmeyen:sey a lv2:Plugin .") == set()


@pytest.mark.parametrize(
    "key",
    [
        "lsp_para_eq_x8_stereo",
        "lsp_para_eq_x16_stereo",
        "lsp_para_eq_x32_stereo",
        "lsp_gate_stereo",
        "lsp_compressor_stereo",
        "lsp_limiter_stereo",
    ],
)
def test_installed_lsp_plugins_are_detected(key):
    """`lsp-plugins` kuruluysa katalog onu görebilmeli."""
    if _lsp_ttl("para_equalizer_x16_stereo") is None:
        pytest.skip("lsp-plugins kurulu değil")
    assert registry.is_available(key) is True
