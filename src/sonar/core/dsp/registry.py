"""Desteklenen DSP eklentilerinin kataloğu.

Eklenti meta verisini çalışma zamanında TTL ayrıştırarak öğrenmek yerine **kürasyonlu statik
bir katalog** tutuyoruz. Sebep: yalnızca birkaç eklenti kullanıyoruz, hepsinin portlarını
biliyoruz, ve statik katalog birim testlerle doğrulanabiliyor — bir lilv bağımlılığı ve
açılışta yüzlerce dosya okumak gerekmiyor.

Buradaki tüm değerler eklentilerin kendi TTL dosyalarından (LSP) ve LADSPA descriptor'ından
(DeepFilterNet) okunarak doğrulanmıştır.

**Dikkat:** LSP'nin kazanç portları (`g_N`, `mk`, `gt`, `al`, `th` …) **lineer** kazançtır,
dB değil. Dönüşüm `core.dsp.params` içinde yapılır.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path

__all__ = [
    "LADSPA_SEARCH_PATH",
    "LV2_SEARCH_PATH",
    "PLUGINS",
    "PluginKind",
    "PluginSpec",
    "PortSpec",
    "available_plugins",
    "eq_analyzer_ports",
    "eq_plugin_for",
    "hrtf_file",
    "is_available",
    "plugin",
    "plugin_reference",
    "sofa_available",
]


class PluginKind(StrEnum):
    LV2 = "lv2"
    LADSPA = "ladspa"
    #: PipeWire'ın kendi `filter-graph` eklentileri (`copy`, `mixer`, `linear`).
    #: Kurulum gerektirmiyor, PipeWire varsa vardır.
    BUILTIN = "builtin"
    #: SOFA/HRTF `spatializer`. `libspa-filter-graph-plugin-sofa.so` ve bir `.sofa`
    #: dosyası gerekiyor; ikisi de yoksa aşama zincirden düşer.
    SOFA = "sofa"


@dataclass(frozen=True, slots=True)
class PortSpec:
    """Bir kontrol portunun sınırları. `default` eklentinin kendi varsayılanıdır."""

    symbol: str
    label: str
    minimum: float
    maximum: float
    default: float
    unit: str = ""
    logarithmic: bool = False
    integer: bool = False

    def clamp(self, value: float) -> float:
        return min(max(value, self.minimum), self.maximum)


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """Zincire yerleştirilebilir bir eklenti."""

    key: str
    kind: PluginKind
    #: LV2 için URI, LADSPA için paylaşılan kütüphanenin dosya adı.
    uri: str
    #: Yalnızca LADSPA: kütüphane içindeki eklenti etiketi.
    label: str = ""
    audio_in: tuple[str, ...] = ()
    audio_out: tuple[str, ...] = ()
    ports: dict[str, PortSpec] = field(default_factory=dict)
    #: Bu eklenti çok bandlıysa desteklediği band sayısı.
    band_capacity: int = 0

    @property
    def channels(self) -> int:
        return len(self.audio_in)

    def port(self, symbol: str) -> PortSpec | None:
        return self.ports.get(symbol)

    def clamp(self, symbol: str, value: float) -> float:
        spec = self.ports.get(symbol)
        return spec.clamp(value) if spec else value


def _ports(*rows: tuple) -> dict[str, PortSpec]:
    """`(symbol, label, min, max, default, unit, log, int)` demetlerinden port sözlüğü."""
    out: dict[str, PortSpec] = {}
    for row in rows:
        symbol, label, lo, hi, dflt = row[:5]
        unit = row[5] if len(row) > 5 else ""
        log = bool(row[6]) if len(row) > 6 else False
        integer = bool(row[7]) if len(row) > 7 else False
        out[symbol] = PortSpec(symbol, label, lo, hi, dflt, unit, log, integer)
    return out


# --------------------------------------------------------------------------- LSP: EQ

#: LSP'nin band varsayılan frekansları: ISO tercih edilen frekanslar (R10, 1/3 oktav).
#: `x32` bu serinin tamamını, `x16` her ikincisini, `x8` her dördüncüsünü kullanır.
_ISO_R10_SERIES: tuple[float, ...] = (
    16.0, 20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 80.0,
    100.0, 125.0, 160.0, 200.0, 250.0, 315.0, 400.0, 500.0,
    630.0, 800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0,
    4000.0, 5000.0, 6300.0, 8000.0, 10_000.0, 12_500.0, 16_000.0, 20_000.0,
)  # fmt: skip


def _band_default_freqs(bands: int) -> tuple[float, ...]:
    """`x8`/`x16`/`x32` varyantlarının band varsayılan frekansları."""
    stride = 32 // bands
    return _ISO_R10_SERIES[::stride][:bands]


#: Her banda ait port şablonları. `{n}` band indeksiyle, frekans varsayılanı ise
#: `_band_default_freqs()` ile doldurulur.
_EQ_BAND_PORTS: tuple[tuple, ...] = (
    ("ft_{n}", "Filtre tipi {n}", 0, 11, 0, "", False, True),
    ("fm_{n}", "Filtre modeli {n}", 0, 6, 0, "", False, True),
    ("s_{n}", "Eğim {n}", 0, 3, 0, "", False, True),
    ("f_{n}", "Frekans {n}", 10.0, 24_000.0, None, "hz", True),
    ("g_{n}", "Kazanç {n}", 0.015850, 63.095749, 1.0, "", True),
    ("q_{n}", "Q {n}", 0.0, 100.0, 0.0),
    ("xs_{n}", "Solo {n}", 0, 1, 0, "", False, True),
    ("xm_{n}", "Sustur {n}", 0, 1, 0, "", False, True),
)

_EQ_GLOBAL_PORTS = _ports(
    ("enabled", "Etkin", 0, 1, 1, "", False, True),
    ("mode", "Ekolayzer modu", 0, 3, 0, "", False, True),
    ("g_in", "Giriş kazancı", 0.0, 10.0, 1.0, "", True),
    ("g_out", "Çıkış kazancı", 0.0, 10.0, 1.0, "", True),
    ("bal", "Denge", -100.0, 100.0, 0.0, "pc"),
)


#: Spektrum analizörü anahtarları — giriş / çıkış / dönüş FFT'si. Üçü de eklentide
#: **varsayılan olarak açık** gelir ve bypass'ta bile çalışırlar: ölçümde altı analizör
#: kapatıldığında altı kanallık grafın boştaki CPU'su %16.1'den %4.4'e düştü. Bize hiçbiri
#: gerekmiyor, EQ eğrisini kendimiz numpy ile çiziyoruz (`core.dsp.response`).
#: Stereo varyantta `_l`/`_r` ekli, mono varyantta eksiz — bu yüzden port adları kanal
#: sayısına göre üretiliyor.
_EQ_ANALYZER_PREFIXES = ("ife", "ofe", "rfe")


def eq_analyzer_ports(spec: PluginSpec) -> tuple[str, ...]:
    """EQ eklentisinin FFT analizör anahtarları. Hepsi 0 yazılmalı."""
    return tuple(
        symbol
        for symbol in spec.ports
        if symbol.split("_")[0] in _EQ_ANALYZER_PREFIXES and not symbol[0].isdigit()
    )


def _eq_spec(bands: int, channels: int) -> PluginSpec:
    suffix = "stereo" if channels == 2 else "mono"
    ports = dict(_EQ_GLOBAL_PORTS)
    for prefix in _EQ_ANALYZER_PREFIXES:
        for symbol in (f"{prefix}_l", f"{prefix}_r") if channels == 2 else (prefix,):
            ports[symbol] = PortSpec(symbol, f"Analizör {symbol}", 0, 1, 1, "", False, True)
    freqs = _band_default_freqs(bands)
    for n in range(bands):
        for row in _EQ_BAND_PORTS:
            sym = row[0].format(n=n)
            # Frekans varsayılanı banda göre değişir; şablonda `None` bırakılmıştı.
            default = freqs[n] if row[4] is None else row[4]
            ports[sym] = PortSpec(
                sym, row[1].format(n=n), row[2], row[3], default,
                row[5] if len(row) > 5 else "",
                bool(row[6]) if len(row) > 6 else False,
                bool(row[7]) if len(row) > 7 else False,
            )  # fmt: skip
    return PluginSpec(
        key=f"lsp_para_eq_x{bands}_{suffix}",
        kind=PluginKind.LV2,
        uri=f"http://lsp-plug.in/plugins/lv2/para_equalizer_x{bands}_{suffix}",
        audio_in=("in_l", "in_r") if channels == 2 else ("in",),
        audio_out=("out_l", "out_r") if channels == 2 else ("out",),
        ports=ports,
        band_capacity=bands,
    )


# --------------------------------------------------------------------------- LSP: dinamikler


def _dyn_spec(name: str, channels: int, ports: dict[str, PortSpec]) -> PluginSpec:
    suffix = "stereo" if channels == 2 else "mono"
    return PluginSpec(
        key=f"lsp_{name}_{suffix}",
        kind=PluginKind.LV2,
        uri=f"http://lsp-plug.in/plugins/lv2/{name}_{suffix}",
        audio_in=("in_l", "in_r") if channels == 2 else ("in",),
        audio_out=("out_l", "out_r") if channels == 2 else ("out",),
        ports=ports,
    )


_GATE_PORTS = _ports(
    ("enabled", "Etkin", 0, 1, 1, "", False, True),
    ("gt", "Eşik", 0.000016, 1.0, 0.0631, "", True),
    ("gz", "Bölge genişliği", 0.001, 1.0, 0.50118, "", True),
    ("gr", "Kısma", 0.000251, 3981.072998, 0.0631, "", True),
    ("gh", "Histerezis", 0, 1, 0, "", False, True),
    ("at", "Atak", 0.0, 2000.0, 20.0, "ms", True),
    ("rt", "Bırakma", 0.0, 5000.0, 100.0, "ms", True),
    ("mk", "Makyaj kazancı", 0.001, 1000.0, 1.0, "", True),
    ("shpf", "Yan zincir HPF", 10.0, 20_000.0, 10.0, "hz", True),
    ("slpf", "Yan zincir LPF", 10.0, 20_000.0, 20_000.0, "hz", True),
)

_COMP_PORTS = _ports(
    ("enabled", "Etkin", 0, 1, 1, "", False, True),
    ("al", "Eşik", 0.001, 1.0, 0.25119, "", True),
    ("cr", "Oran", 1.0, 100.0, 4.0, "", True),
    ("kn", "Diz", 0.0631, 1.0, 0.50118, "", True),
    ("at", "Atak", 0.0, 2000.0, 20.0, "ms", True),
    ("rt", "Bırakma", 0.0, 5000.0, 100.0, "ms", True),
    ("mk", "Makyaj kazancı", 0.001, 1000.0, 1.0, "", True),
    ("scr", "Yan zincir tepkisi", 0.0, 250.0, 10.0, "ms", True),
)

_LIMITER_PORTS = _ports(
    ("enabled", "Etkin", 0, 1, 1, "", False, True),
    ("th", "Tavan", 0.003981, 1.0, 1.0, "", True),
    ("lk", "İleri bakış", 0.1, 20.0, 5.0, "ms", True),
    ("at", "Atak", 0.25, 20.0, 5.0, "ms", True),
    ("rt", "Bırakma", 0.25, 20.0, 5.0, "ms", True),
    ("g_in", "Giriş kazancı", 0.0, 1000.0, 1.0, "", True),
    ("g_out", "Çıkış kazancı", 0.0, 1000.0, 1.0, "", True),
    # Bu ikisi eklentide varsayılan olarak AÇIK gelir ve `th`'yi tavan olmaktan çıkarır;
    # `params._STAGE_FIXED` ikisini de 0'a sabitler. Ayrıntı: .plan/02-confgen.md
    ("boost", "Kazanç yükseltme", 0, 1, 1, "", False, True),
    ("alr", "Otomatik seviye düzenleme", 0, 1, 1, "", False, True),
)


# --------------------------------------------------------------------------- DeepFilterNet

_DF_CONTROL_PORTS = _ports(
    ("Attenuation Limit (dB)", "Gürültü azaltma sınırı", 0.0, 100.0, 100.0, "db"),
    ("Min processing threshold (dB)", "Asgari işleme eşiği", -15.0, 35.0, -15.0, "db"),
    ("Max ERB processing threshold (dB)", "Azami ERB eşiği", -15.0, 35.0, 35.0, "db"),
    ("Max DF processing threshold (dB)", "Azami DF eşiği", -15.0, 35.0, 35.0, "db"),
    ("Min Processing Buffer (frames)", "Asgari işleme tamponu", 0.0, 10.0, 0.0, "", False, True),
    ("Post Filter Beta", "Son filtre beta", 0.0, 0.05, 0.0),
)

_DEEPFILTER_MONO = PluginSpec(
    key="deepfilter_mono",
    kind=PluginKind.LADSPA,
    uri="libdeep_filter_ladspa.so",
    label="deep_filter_mono",
    audio_in=("Audio In",),
    audio_out=("Audio Out",),
    ports=_DF_CONTROL_PORTS,
)

_DEEPFILTER_STEREO = PluginSpec(
    key="deepfilter_stereo",
    kind=PluginKind.LADSPA,
    uri="libdeep_filter_ladspa.so",
    label="deep_filter_stereo",
    audio_in=("Audio In L", "Audio In R"),
    audio_out=("Audio Out L", "Audio Out R"),
    ports=_DF_CONTROL_PORTS,
)


# --------------------------------------------------------------------------- katalog

PLUGINS: dict[str, PluginSpec] = {}
for _bands in (8, 16, 32):
    for _ch in (1, 2):
        _spec = _eq_spec(_bands, _ch)
        PLUGINS[_spec.key] = _spec
for _name, _ports_map in (
    ("gate", _GATE_PORTS),
    ("compressor", _COMP_PORTS),
    ("limiter", _LIMITER_PORTS),
):
    for _ch in (1, 2):
        _spec = _dyn_spec(_name, _ch, _ports_map)
        PLUGINS[_spec.key] = _spec
PLUGINS[_DEEPFILTER_MONO.key] = _DEEPFILTER_MONO
PLUGINS[_DEEPFILTER_STEREO.key] = _DEEPFILTER_STEREO

del _bands, _ch, _spec, _name, _ports_map


#: Arayüzde sunulan band sayısı → kullanılacak LSP EQ varyantının band kapasitesi.
_BAND_COUNT_TO_CAPACITY = {5: 8, 8: 8, 10: 16, 16: 16, 32: 32}


def plugin(key: str) -> PluginSpec:
    """Katalogdan bir eklenti döndürür."""
    try:
        return PLUGINS[key]
    except KeyError:
        raise KeyError(f"katalogda böyle bir eklenti yok: {key}") from None


def eq_plugin_for(band_count: int, channels: int = 2) -> PluginSpec:
    """İstenen band sayısını karşılayan en küçük LSP EQ varyantını döndürür."""
    capacity = _BAND_COUNT_TO_CAPACITY.get(band_count)
    if capacity is None:
        capacity = next((c for c in (8, 16, 32) if c >= band_count), 32)
    suffix = "stereo" if channels == 2 else "mono"
    return plugin(f"lsp_para_eq_x{capacity}_{suffix}")


# --------------------------------------------------------------------------- kurulu mu?


def _search_path(env: str, defaults: tuple[str, ...]) -> tuple[Path, ...]:
    raw = os.environ.get(env)
    parts = raw.split(":") if raw else list(defaults)
    return tuple(Path(p).expanduser() for p in parts if p)


LV2_SEARCH_PATH = _search_path(
    "LV2_PATH", ("~/.lv2", "/usr/local/lib/lv2", "/usr/lib/lv2", "/usr/lib64/lv2")
)
LADSPA_SEARCH_PATH = _search_path(
    "LADSPA_PATH", ("~/.ladspa", "/usr/local/lib/ladspa", "/usr/lib/ladspa", "/usr/lib64/ladspa")
)


@cache
def _installed_lv2_uris() -> frozenset[str]:
    """Kurulu tüm LV2 eklentilerinin URI'leri. Yalnızca `manifest.ttl` dosyaları taranır."""
    uris: set[str] = set()
    for root in LV2_SEARCH_PATH:
        if not root.is_dir():
            continue
        for manifest in root.glob("*.lv2/manifest.ttl"):
            try:
                uris |= extract_ttl_uris(manifest.read_text(errors="replace"))
            except OSError:
                continue
    return frozenset(uris)


_PREFIX_RE = re.compile(r"@prefix\s+([A-Za-z_][\w.-]*)?:\s*<([^>]*)>\s*\.")
_ANGLE_URI_RE = re.compile(r"<([^>\s]*)>")
_CURIE_RE = re.compile(r"\b([A-Za-z_][\w.-]*):([A-Za-z_][\w.\-]*)")


def extract_ttl_uris(text: str) -> set[str]:
    """Bir Turtle belgesinde geçen mutlak URI'leri toplar.

    Tam bir Turtle ayrıştırıcısı değil — sadece bir eklenti URI'sinin manifest'te geçip
    geçmediğini anlamamıza yeter. İki yazım biçimini de karşılar: açık ``<http://...>``
    ve öntakı kısaltması. LSP ikincisini kullanır::

        @prefix plug: <http://lsp-plug.in/plugins/lv2/> .
        plug:para_equalizer_x16_stereo a lv2:Plugin ;

    Özne/nesne konumu ayırt edilmez; aradığımız URI'ler o kadar özgüldür ki yanlış pozitif
    pratikte imkânsızdır.
    """
    prefixes = {(m.group(1) or ""): m.group(2) for m in _PREFIX_RE.finditer(text)}
    uris = {m.group(1) for m in _ANGLE_URI_RE.finditer(text) if "://" in m.group(1)}

    # Kısaltmaları ararken açı parantezli URI'lerin içine bakmayalım (`http:` gibi sahte
    # eşleşmeler üretirler) ve yorum satırlarını atlayalım.
    for line in _ANGLE_URI_RE.sub(" ", text).splitlines():
        code = line.split("#", 1)[0]
        if code.lstrip().startswith("@prefix"):
            continue
        for match in _CURIE_RE.finditer(code):
            base = prefixes.get(match.group(1))
            if base:
                uris.add(base + match.group(2))
    return uris


@cache
def _ladspa_library(filename: str) -> Path | None:
    for root in LADSPA_SEARCH_PATH:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return None


def plugin_reference(spec: PluginSpec) -> str:
    """`filter.graph` içindeki `plugin` alanına yazılacak değer.

    LV2 için URI. LADSPA için **mutlak yol**: daemon `systemd --user` altında çalışırken
    kullanıcının kabuğundaki `LADSPA_PATH` miras alınmaz, çıplak dosya adı bulunamayabilir.
    Kütüphane hiç bulunamazsa çıplak ad döner — hata mesajı o zaman anlaşılır olur.
    """
    if spec.kind is PluginKind.LV2:
        return spec.uri
    found = _ladspa_library(spec.uri)
    return str(found) if found else spec.uri


def is_available(key: str) -> bool:
    """Eklenti bu sistemde gerçekten kurulu mu?"""
    spec = PLUGINS.get(key)
    if spec is None:
        return False
    if spec.kind is PluginKind.LV2:
        return spec.uri in _installed_lv2_uris()
    return _ladspa_library(spec.uri) is not None


def available_plugins() -> dict[str, bool]:
    """Katalogdaki her eklentinin kurulu olup olmadığı."""
    return {key: is_available(key) for key in PLUGINS}


def clear_cache() -> None:
    """Eklenti tarama önbelleğini boşaltır (paket kurulumundan sonra çağrılır)."""
    _installed_lv2_uris.cache_clear()
    _ladspa_library.cache_clear()
    hrtf_file.cache_clear()
    sofa_available.cache_clear()


# --------------------------------------------------------------------------- SOFA / HRTF

#: `spatializer` eklentisini taşıyan SPA modülü. PipeWire libmysofa olmadan
#: derlenmişse bu dosya yoktur ve Spatial Audio aşaması zincirden düşer.
SOFA_PLUGIN_PATHS: tuple[Path, ...] = (
    Path("/usr/lib/spa-0.2/filter-graph/libspa-filter-graph-plugin-sofa.so"),
    Path("/usr/lib64/spa-0.2/filter-graph/libspa-filter-graph-plugin-sofa.so"),
)

#: Aranacak HRTF dosyaları, tercih sırasıyla. `default.sofa` libmysofa'nın kendi
#: gömülü seti; MIT KEMAR daha ayrıntılı ama her kurulumda yok.
HRTF_SEARCH_PATH: tuple[Path, ...] = (
    Path("/usr/share/libmysofa/default.sofa"),
    Path("/usr/share/libmysofa/MIT_KEMAR_normal_pinna.sofa"),
    Path("/usr/share/sofa/default.sofa"),
)


@cache
def hrtf_file() -> str:
    """Kullanılacak HRTF dosyasının yolu; hiçbiri yoksa boş dize.

    Boş dönmesi Spatial Audio aşamasının kurulamayacağı anlamına gelir; `plan_chain`
    onu zincirden düşürür ve arayüz "eklenti kurulu değil" yolunu kullanır.
    """
    for candidate in HRTF_SEARCH_PATH:
        if candidate.is_file():
            return str(candidate)
    return ""


@cache
def sofa_available() -> bool:
    """SOFA eklentisi ve bir HRTF dosyası var mı?"""
    return bool(hrtf_file()) and any(path.is_file() for path in SOFA_PLUGIN_PATHS)
