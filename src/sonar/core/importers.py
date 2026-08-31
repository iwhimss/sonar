"""Dış EQ formatlarını Sonar profiline çevirir, geri yazar.

Desteklenenler:

* **`.sonarprofile`** — kendi formatımız (profil JSON'u + şema sürümü)
* **AutoEQ `ParametricEQ.txt`** — kulaklık düzeltme eğrilerinin fiili standardı,
  binlerce kulaklık için hazır dosya var
* **Equalizer APO `config.txt`** — Windows'tan taşıma
* **EasyEffects preset `.json`** — aynı makinedeki diğer araçtan taşıma

## Neden band sayısı yuvarlanıyor

Sonar'ın grafı sabit kapasiteli bir LSP `para_equalizer` taşıyor (8/16/32). İçe aktarılan
dosya 7 band içeriyorsa 10 bandlık zincire sığar; 20 band içeriyorsa 32'ye çıkılır. Fazla
band **atılmaz**, desteklenen en küçük kapasiteye yükseltilir; hiçbiri sığmazsa (32'den
fazla) en zayıf kazançlı bandlar düşer ve çağıran tarafa kaç bandın atıldığı bildirilir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sonar.core.model import (
    SCHEMA_VERSION,
    SUPPORTED_BAND_COUNTS,
    EqBand,
    EqBandType,
    Profile,
    default_profile,
)
from sonar.core.serde import from_jsonable, to_jsonable

__all__ = [
    "ImportResult",
    "ProfileImportError",
    "detect_format",
    "export_autoeq",
    "export_profile",
    "import_any",
    "parse_apo",
    "parse_autoeq",
    "parse_easyeffects",
    "parse_sonarprofile",
]


class ProfileImportError(Exception):
    """Dosya tanınmadı veya okunamadı."""


@dataclass(frozen=True, slots=True)
class ImportResult:
    profile: Profile
    source: str
    dropped: int = 0
    warnings: tuple[str, ...] = ()


#: AutoEQ / APO filtre adlarını bizim tiplerimize eşler.
_TYPE_MAP = {
    "PK": EqBandType.PEAK,
    "PEQ": EqBandType.PEAK,
    "MODAL": EqBandType.PEAK,
    "LS": EqBandType.LOW_SHELF,
    "LSC": EqBandType.LOW_SHELF,
    "HS": EqBandType.HIGH_SHELF,
    "HSC": EqBandType.HIGH_SHELF,
    "LP": EqBandType.LOW_PASS,
    "LPQ": EqBandType.LOW_PASS,
    "HP": EqBandType.HIGH_PASS,
    "HPQ": EqBandType.HIGH_PASS,
    "NO": EqBandType.NOTCH,
    "AP": EqBandType.ALLPASS,
    "BP": EqBandType.BANDPASS,
}

# "Filter 1: ON PK Fc 105 Hz Gain -2.5 dB Q 0.70"
_FILTER_RE = re.compile(
    r"^\s*Filter\s+\d+\s*:\s*(?P<state>ON|OFF)\s+(?P<kind>[A-Z]+)"
    r"(?:\s+Fc\s+(?P<freq>[\d.]+)\s*Hz)?"
    r"(?:\s+Gain\s+(?P<gain>-?[\d.]+)\s*dB)?"
    r"(?:\s+Q\s+(?P<q>[\d.]+))?",
    re.IGNORECASE,
)
_PREAMP_RE = re.compile(r"^\s*Preamp\s*:\s*(-?[\d.]+)\s*dB", re.IGNORECASE)


def _fit_band_count(count: int) -> tuple[int, int]:
    """`(kullanılacak band sayısı, düşen band sayısı)`."""
    for supported in SUPPORTED_BAND_COUNTS:
        if count <= supported:
            return supported, 0
    largest = SUPPORTED_BAND_COUNTS[-1]
    return largest, count - largest


def _build(name: str, bands: list[EqBand], preamp_db: float, source: str) -> ImportResult:
    warnings: list[str] = []
    if not bands:
        raise ProfileImportError("dosyada hiç EQ bandı bulunamadı")

    # 32'den fazlaysa en zayıf kazançlılar düşer — en az duyulacak olanlar.
    band_count, dropped = _fit_band_count(len(bands))
    if dropped:
        bands = sorted(bands, key=lambda b: -abs(b.gain_db))[:band_count]
        bands.sort(key=lambda b: b.freq)
        warnings.append(
            f"{dropped} band sığmadı ve en zayıf kazançlı olanlar atıldı "
            f"(en fazla {band_count} band destekleniyor)"
        )

    profile = default_profile(name, band_count=band_count)
    profile.eq.enabled = True
    profile.eq.preamp_db = preamp_db
    for index in range(band_count):
        if index < len(bands):
            profile.eq.bands[index] = bands[index].clamped()
        else:
            # Kullanılmayan bandlar kapatılır; aksi hâlde varsayılan frekanslar kalır.
            profile.eq.bands[index].band_type = EqBandType.OFF
            profile.eq.bands[index].gain_db = 0.0
    return ImportResult(profile, source, dropped, tuple(warnings))


# --------------------------------------------------------------------------- AutoEQ / APO


def parse_autoeq(text: str, name: str = "AutoEQ") -> ImportResult:
    """AutoEQ `ParametricEQ.txt`. Biçim APO ile aynı; ayrı isim okunabilirlik için."""
    return _parse_filter_lines(text, name, "autoeq")


def parse_apo(text: str, name: str = "Equalizer APO") -> ImportResult:
    return _parse_filter_lines(text, name, "apo")


def _parse_filter_lines(text: str, name: str, source: str) -> ImportResult:
    bands: list[EqBand] = []
    preamp = 0.0
    for line in text.splitlines():
        preamp_match = _PREAMP_RE.match(line)
        if preamp_match:
            preamp = float(preamp_match.group(1))
            continue
        match = _FILTER_RE.match(line)
        if not match:
            continue
        kind = _TYPE_MAP.get(match.group("kind").upper())
        if kind is None:
            continue
        freq = match.group("freq")
        if freq is None:
            continue
        bands.append(
            EqBand(
                freq=float(freq),
                gain_db=float(match.group("gain") or 0.0),
                q=float(match.group("q") or 0.707),
                band_type=kind,
                enabled=match.group("state").upper() == "ON",
            )
        )
    bands.sort(key=lambda b: b.freq)
    return _build(name, bands, preamp, source)


def export_autoeq(profile: Profile) -> str:
    """AutoEQ / APO metin biçimi — başka araçlara taşımak için."""
    reverse = {
        v: k
        for k, v in (
            ("PK", EqBandType.PEAK),
            ("LSC", EqBandType.LOW_SHELF),
            ("HSC", EqBandType.HIGH_SHELF),
            ("LP", EqBandType.LOW_PASS),
            ("HP", EqBandType.HIGH_PASS),
            ("NO", EqBandType.NOTCH),
            ("AP", EqBandType.ALLPASS),
            ("BP", EqBandType.BANDPASS),
        )
    }
    lines = [f"Preamp: {profile.eq.preamp_db:.1f} dB"]
    for index, band in enumerate(profile.eq.active_bands(), start=1):
        if band.band_type is EqBandType.OFF:
            continue
        kind = reverse.get(band.band_type, "PK")
        lines.append(
            f"Filter {index}: {'ON' if band.enabled else 'OFF'} {kind} "
            f"Fc {band.freq:g} Hz Gain {band.gain_db:.1f} dB Q {band.q:.2f}"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- EasyEffects


def parse_easyeffects(text: str, name: str = "EasyEffects") -> ImportResult:
    """EasyEffects preset'inin EQ bölümü.

    Yapı: `{"output": {"equalizer": {"left": {"band0": {...}}, ...}}}`. Yalnızca sol kanal
    okunuyor; EasyEffects varsayılan olarak iki kanalı eşitler ve bizim EQ'muz zaten
    kanalları ayırmıyor.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProfileImportError("EasyEffects preset'i ayrıştırılamadı") from error

    equalizer = None
    for section in ("output", "input"):
        candidate = (data.get(section) or {}).get("equalizer")
        if candidate:
            equalizer = candidate
            break
    if equalizer is None:
        raise ProfileImportError("preset içinde ekolayzer bölümü yok")

    channel = equalizer.get("left") or equalizer.get("right") or {}
    bands: list[EqBand] = []
    for key, raw in channel.items():
        if not key.startswith("band") or not isinstance(raw, dict):
            continue
        kind = {
            "Bell": EqBandType.PEAK,
            "Lo-shelf": EqBandType.LOW_SHELF,
            "Hi-shelf": EqBandType.HIGH_SHELF,
            "Lo-pass": EqBandType.LOW_PASS,
            "Hi-pass": EqBandType.HIGH_PASS,
            "Notch": EqBandType.NOTCH,
            "Allpass": EqBandType.ALLPASS,
            "Bandpass": EqBandType.BANDPASS,
            "Off": EqBandType.OFF,
        }.get(str(raw.get("type", "Bell")), EqBandType.PEAK)
        if kind is EqBandType.OFF:
            continue
        try:
            bands.append(
                EqBand(
                    freq=float(raw.get("frequency", 1000.0)),
                    gain_db=float(raw.get("gain", 0.0)),
                    q=float(raw.get("q", 1.0)) or 1.0,
                    band_type=kind,
                    enabled=str(raw.get("mode", "RLC (BT)")).lower() != "off",
                )
            )
        except (TypeError, ValueError):
            continue
    bands.sort(key=lambda b: b.freq)
    preamp = float((data.get("output") or {}).get("equalizer", {}).get("input-gain", 0.0) or 0.0)
    return _build(name, bands, preamp, "easyeffects")


# --------------------------------------------------------------------------- kendi formatımız


def export_profile(profile: Profile) -> str:
    """`.sonarprofile` — şema sürümlü, insan okunabilir JSON."""
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "sonar-profile",
            "profile": to_jsonable(profile),
        },
        ensure_ascii=False,
        indent=2,
    )


def parse_sonarprofile(text: str, name: str | None = None) -> ImportResult:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProfileImportError("dosya geçerli JSON değil") from error
    payload = data.get("profile") if isinstance(data, dict) else None
    if payload is None:
        raise ProfileImportError("dosya bir Sonar profili değil")
    version = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        raise ProfileImportError(f"dosya daha yeni bir sürümden ({version})")
    profile = from_jsonable(Profile, payload)
    if name:
        profile.name = name
    return ImportResult(profile, "sonarprofile")


# --------------------------------------------------------------------------- otomatik seçim


def detect_format(text: str) -> str:
    """İçeriğe bakarak biçimi tahmin eder. Uzantıya güvenmiyoruz."""
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return "unknown"
        if isinstance(data, dict) and data.get("kind") == "sonar-profile":
            return "sonarprofile"
        if isinstance(data, dict) and ("output" in data or "input" in data):
            return "easyeffects"
        return "unknown"
    if _FILTER_RE.search(text) or _PREAMP_RE.search(text):
        return "autoeq"
    return "unknown"


def import_any(text: str, name: str | None = None) -> ImportResult:
    """Biçimi kendi bulup içe aktarır."""
    kind = detect_format(text)
    if kind == "sonarprofile":
        return parse_sonarprofile(text, name)
    if kind == "easyeffects":
        return parse_easyeffects(text, name or "EasyEffects")
    if kind == "autoeq":
        return parse_autoeq(text, name or "AutoEQ")
    raise ProfileImportError(
        "dosya biçimi tanınmadı (AutoEQ/APO, EasyEffects veya .sonarprofile bekleniyor)"
    )
