"""Profil değerlerini eklenti port değerlerine çevirir.

Model katmanı parametreleri insan birimlerinde tutar (dB, ms, oran); LSP eklentileri ise
kazançları **lineer** ister. Bu modül aradaki tek dönüşüm noktasıdır ve canlı parametre
yazımının tek kaynağıdır: `profile_to_params()` bir profili doğrudan
``{"eq:g_3": 1.6788, "gate:at": 10.0, ...}`` biçimine indirger; `engine.control` bunu
olduğu gibi `pw-cli`'ye verir.

Anahtar biçimi ``"<aşama>:<port>"`` — aşama adları `FilterStage` değerleridir ve
`engine.confgen`'in ürettiği `filter.graph` node adlarıyla birebir aynıdır.
"""

from __future__ import annotations

import math

from sonar.core.dsp import registry
from sonar.core.model import (
    CHAIN_ORDER,
    EqBand,
    EqBandType,
    EqState,
    FilterStage,
    FilterState,
    Profile,
)

__all__ = [
    "BAND_TYPE_TO_LSP",
    "MULTI_NODE_STAGES",
    "SILENCE_DB",
    "db_to_linear",
    "eq_bypass_ports",
    "linear_to_db",
    "multi_stage_params",
    "param_key",
    "profile_to_params",
    "stage_bypass_ports",
    "stage_params",
]

#: Bunun altındaki dB değerleri "sessizlik" sayılır; lineer 0'a eşlenir.
SILENCE_DB = -120.0

#: LSP `ft_N` enum'u (para_equalizer TTL'inden doğrulandı).
BAND_TYPE_TO_LSP: dict[EqBandType, int] = {
    EqBandType.OFF: 0,
    EqBandType.PEAK: 1,  # Bell
    EqBandType.HIGH_PASS: 2,  # Hi-pass
    EqBandType.HIGH_SHELF: 3,  # Hi-shelf
    EqBandType.LOW_PASS: 4,  # Lo-pass
    EqBandType.LOW_SHELF: 5,  # Lo-shelf
    EqBandType.NOTCH: 6,
    EqBandType.ALLPASS: 8,
    EqBandType.BANDPASS: 9,
}

#: LSP `fm_N` filtre modeli. 6 = "APO (DR)", yani Equalizer APO'nun doğrudan biquad modeli.
#: Bunu seçiyoruz çünkü RBJ cookbook formülleriyle birebir örtüşür — böylece arayüzde
#: çizdiğimiz eğri (`core.dsp.response`) kulağın duyduğuyla aynı olur.
LSP_FILTER_MODEL_APO = 6

#: LSP EQ'nun genel modu: 0 = IIR.
LSP_EQ_MODE_IIR = 0


# --------------------------------------------------------------------------- dB ↔ lineer


def db_to_linear(db: float) -> float:
    """Desibeli lineer kazanca çevirir. `SILENCE_DB` altı 0 döndürür."""
    if db <= SILENCE_DB:
        return 0.0
    return 10.0 ** (db / 20.0)


def linear_to_db(linear: float) -> float:
    """Lineer kazancı desibele çevirir. Sıfır ve negatif için `SILENCE_DB` döndürür."""
    if linear <= 0.0:
        return SILENCE_DB
    return 20.0 * math.log10(linear)


def param_key(stage: FilterStage, port: str) -> str:
    """``"eq:g_3"`` biçiminde canlı yazım anahtarı üretir."""
    return f"{stage.value}:{port}"


# --------------------------------------------------------------------------- EQ


def eq_params(eq: EqState, capacity: int) -> dict[str, float]:
    """Ekolayzer durumunu LSP port değerlerine çevirir.

    `capacity` kullanılan eklentinin band kapasitesidir (8/16/32). Kullanılmayan bandlar
    `ft = 0` (Off) yapılarak devre dışı bırakılır — böylece zincirin topolojisi
    band sayısı değişse bile sabit kalır.
    """
    spec = registry.plugin(f"lsp_para_eq_x{capacity}_stereo")
    out: dict[str, float] = {
        "enabled": 1.0 if eq.enabled else 0.0,
        "mode": float(LSP_EQ_MODE_IIR),
        "g_in": db_to_linear(eq.preamp_db),
        "g_out": 1.0,
        **dict.fromkeys(registry.eq_analyzer_ports(spec), 0.0),
    }
    bands = eq.active_bands()
    for index in range(capacity):
        band = bands[index] if index < len(bands) else None
        out.update(_band_params(index, band, spec))
    return {param_key(FilterStage.EQ, port): value for port, value in out.items()}


def _band_params(index: int, band: EqBand | None, spec: registry.PluginSpec) -> dict[str, float]:
    if band is None or not band.enabled:
        return {f"ft_{index}": 0.0}
    band = band.clamped()
    return {
        f"ft_{index}": float(BAND_TYPE_TO_LSP.get(band.band_type, 1)),
        f"fm_{index}": float(LSP_FILTER_MODEL_APO),
        f"s_{index}": float(band.slope),
        f"f_{index}": spec.clamp(f"f_{index}", band.freq),
        f"g_{index}": spec.clamp(f"g_{index}", db_to_linear(band.gain_db)),
        f"q_{index}": spec.clamp(f"q_{index}", band.q),
        f"xs_{index}": 0.0,
        f"xm_{index}": 0.0,
    }


# --------------------------------------------------------------------------- dinamik aşamalar

#: Her aşama için: Sonar parametre adı → (port sembolü, dönüşüm).
#: Dönüşüm `None` ise değer doğrudan geçer.
_TO_LINEAR = "linear"
_DIRECT = "direct"
_BOOL = "bool"

_STAGE_PORT_MAP: dict[FilterStage, dict[str, tuple[str, str]]] = {
    FilterStage.GATE: {
        "threshold_db": ("gt", _TO_LINEAR),
        "zone_db": ("gz", _TO_LINEAR),
        "reduction_db": ("gr", _TO_LINEAR),
        "attack_ms": ("at", _DIRECT),
        "release_ms": ("rt", _DIRECT),
        "makeup_db": ("mk", _TO_LINEAR),
        "hysteresis": ("gh", _BOOL),
    },
    FilterStage.COMP: {
        "threshold_db": ("al", _TO_LINEAR),
        "ratio": ("cr", _DIRECT),
        "attack_ms": ("at", _DIRECT),
        "release_ms": ("rt", _DIRECT),
        "knee_db": ("kn", _TO_LINEAR),
        "makeup_db": ("mk", _TO_LINEAR),
    },
    FilterStage.LIMITER: {
        "ceiling_db": ("th", _TO_LINEAR),
        "lookahead_ms": ("lk", _DIRECT),
        "attack_ms": ("at", _DIRECT),
        "release_ms": ("rt", _DIRECT),
    },
    FilterStage.DEEPFILTER: {
        "attenuation_db": ("Attenuation Limit (dB)", _DIRECT),
        "post_filter_beta": ("Post Filter Beta", _DIRECT),
        "min_buffer_frames": ("Min Processing Buffer (frames)", _DIRECT),
    },
}

#: Aşamanın kapalı olduğunda yazılacak portlar. Topoloji değişmediği için bypass böyle yapılır.
_STAGE_BYPASS: dict[FilterStage, dict[str, float]] = {
    FilterStage.GATE: {"enabled": 0.0},
    FilterStage.COMP: {"enabled": 0.0},
    FilterStage.LIMITER: {"enabled": 0.0},
    # DeepFilterNet'te `enabled` portu yok; sıfır azaltma sınırı fiilen bypass demektir.
    FilterStage.DEEPFILTER: {"Attenuation Limit (dB)": 0.0},
}

#: Aşama **açıkken** her zaman sabitlenen portlar.
#:
#: LSP limiter varsayılan olarak `boost` (Gain boost) ve `alr` (Automatic Level Regulation)
#: açık gelir. Bu hâliyle `th` bir tavan değil, sinyali 0 dBFS'e taşıyan bir hedef seviyedir:
#: ölçümde `th = -30 dB` verilen bir limiter, -20 dBFS'lik girişi **yükseltti**. İkisi de
#: kapatıldığında `th` tam olarak tavan oluyor (-30 dB → -30.01 dBFS ölçüldü). Kullanıcı
#: "limiter aç" dediğinde sesin yükselmesi beklenmedik olurdu, bu yüzden sabitliyoruz.
_STAGE_FIXED: dict[FilterStage, dict[str, float]] = {
    FilterStage.LIMITER: {"boost": 0.0, "alr": 0.0},
}


#: Kanal başına (ya da alt graf hâlinde) birden çok node'a yayılan aşamalar.
#: Bunların parametreleri `"<aşama>:<port>"` kalıbına girmiyor; her node'un kendi adı var,
#: bu yüzden ayrı bir üretici kullanıyorlar (`multi_stage_params`).
MULTI_NODE_STAGES: tuple[FilterStage, ...] = (FilterStage.SPATIAL, FilterStage.BOOST)

#: Volume Boost'un üst sınırı. Limiter'dan önce durduğu için kırpma üretmiyor ama
#: sınırsız bırakmak kullanıcıya kendini sağır etme imkânı verirdi.
MAX_BOOST_DB = 12.0

#: Crossfeed sızıntı kazancının uçları. Alt uç ("Performans") yön algısını korumak için
#: kasten düşük; üst uç ("Sürükleyicilik") -4.4 dB, gerçek hoparlörlerdekine yakın.
SPATIAL_BLEED_MIN = 0.12
SPATIAL_BLEED_MAX = 0.60

#: Kafa gölgesinin kesim frekansı. Sürükleyicilik ucunda daha erken kesiliyor.
SPATIAL_CUTOFF_MAX_HZ = 1600.0
SPATIAL_CUTOFF_MIN_HZ = 700.0

#: Kulaklar arası gecikme. Gerçek bir stereo üçgeninde 0.2–0.3 ms.
SPATIAL_DELAY_MIN_S = 0.00015
SPATIAL_DELAY_MAX_S = 0.0008


def multi_stage_params(
    stage: FilterStage, state: FilterState, channels: int = 2
) -> dict[str, float]:
    """Çok node'lu aşamaların port değerleri; anahtarlar tam nitelikli (`"boost_l:Mult"`)."""
    if stage is FilterStage.BOOST:
        return _boost_params(state, channels)
    if stage is FilterStage.SPATIAL:
        return _spatial_params(state)
    raise ValueError(f"{stage} çok node'lu bir aşama değil")


def _boost_names(channels: int) -> tuple[str, ...]:
    return ("boost",) if channels == 1 else ("boost_l", "boost_r")


def _boost_params(state: FilterState, channels: int) -> dict[str, float]:
    """PipeWire `linear`: `Out = In * Mult + Add`. Bypass `Mult = 1.0`."""
    defaults = _default_params(FilterStage.BOOST)
    gain_db = state.params.get("gain_db", defaults["gain_db"]) if state.enabled else 0.0
    gain_db = min(max(float(gain_db), 0.0), MAX_BOOST_DB)
    mult = db_to_linear(gain_db)
    out: dict[str, float] = {}
    for name in _boost_names(channels):
        out[f"{name}:Mult"] = mult
        out[f"{name}:Add"] = 0.0
    return out


def _spatial_params(state: FilterState) -> dict[str, float]:
    """Crossfeed ayarları → gecikme, alçak geçiren kesim ve sızıntı kazancı.

    Kullanıcıya iki kaydırıcı gösteriliyor (SteelSeries'teki gibi):

    * **Performans ↔ Sürükleyicilik** (`immersion`, 0–100): ne kadar sızıntı ve ne kadar
      "yumuşak". Performans ucunda sızıntı az ve tizleri daha çok geçiyor → yön algısı
      keskin kalır, rekabetçi FPS için tercih edilen bu. Sürükleyicilik ucunda sızıntı
      artıyor ve daha erken kesiliyor → sahne genişler, hikâye oyunları ve film için.
    * **Mesafe** (`distance`, 0–100): sanal hoparlörlerin uzaklığı, yani kulaklar arası
      gecikme. Gerçek bir stereo üçgeninde bu 0.2–0.3 ms; daha uzun değerler sahneyi
      büyütüyor.

    Bypass mikserde: sızıntı kazancı 0 → çıkış girişe **birebir** eşit.
    """
    defaults = _default_params(FilterStage.SPATIAL)
    if not state.enabled:
        return {"spatial_mix_l:Gain 2": 0.0, "spatial_mix_r:Gain 2": 0.0}

    immersion = _unit(state.params.get("immersion", defaults["immersion"]))
    distance = _unit(state.params.get("distance", defaults["distance"]))

    bleed = SPATIAL_BLEED_MIN + immersion * (SPATIAL_BLEED_MAX - SPATIAL_BLEED_MIN)
    cutoff = SPATIAL_CUTOFF_MAX_HZ + immersion * (SPATIAL_CUTOFF_MIN_HZ - SPATIAL_CUTOFF_MAX_HZ)
    delay = SPATIAL_DELAY_MIN_S + distance * (SPATIAL_DELAY_MAX_S - SPATIAL_DELAY_MIN_S)

    return {
        "spatial_mix_l:Gain 1": 1.0,
        "spatial_mix_r:Gain 1": 1.0,
        "spatial_mix_l:Gain 2": bleed,
        "spatial_mix_r:Gain 2": bleed,
        "spatial_delay_l:Delay (s)": delay,
        "spatial_delay_r:Delay (s)": delay,
        "spatial_lp_l:Freq": cutoff,
        "spatial_lp_r:Freq": cutoff,
        "spatial_lp_l:Q": 0.707,
        "spatial_lp_r:Q": 0.707,
    }


def _unit(value: float) -> float:
    """0–100 aralığındaki kullanıcı değerini 0–1'e indirger."""
    return min(max(float(value), 0.0), 100.0) / 100.0


def stage_bypass_ports(stage: FilterStage) -> dict[str, float]:
    """Aşamayı fiilen devre dışı bırakan port değerleri (anahtarlar önekSİZ).

    `graph.conf`'a yazılacak başlangıç değerleri de budur: zincir bypass'ta doğar, gerçek
    profil açılışta canlı yazımla uygulanır.
    """
    if stage is FilterStage.EQ:
        return {"enabled": 0.0}
    return dict(_STAGE_BYPASS[stage])


def eq_bypass_ports(spec: registry.PluginSpec) -> dict[str, float]:
    """EQ'nun bypass başlangıç değerleri — analizörler dâhil.

    Analizörleri kapatmak sadece bir optimizasyon değil, **zorunlu**: LSP'nin FFT'leri
    varsayılan olarak açık ve `enabled = 0` iken de çalışıyorlar. Ölçüm: altı kanallık
    grafın boştaki CPU'su %16.1 → %4.4 (bkz. .plan/02-confgen.md).
    """
    return {"enabled": 0.0, **dict.fromkeys(registry.eq_analyzer_ports(spec), 0.0)}


def stage_params(
    stage: FilterStage, state: FilterState, spec: registry.PluginSpec | None = None
) -> dict[str, float]:
    """Tek bir dinamik aşamanın port değerlerini üretir."""
    if stage is FilterStage.EQ:
        raise ValueError("EQ için eq_params() kullanın")
    mapping = _STAGE_PORT_MAP[stage]

    if not state.enabled:
        ports = dict(_STAGE_BYPASS[stage])
    else:
        ports = {} if stage is FilterStage.DEEPFILTER else {"enabled": 1.0}
        ports.update(_STAGE_FIXED.get(stage, {}))
        defaults = _default_params(stage)
        for name, (port, kind) in mapping.items():
            value = state.params.get(name, defaults.get(name, 0.0))
            ports[port] = _convert(value, kind)

    if spec is not None:
        ports = {port: spec.clamp(port, value) for port, value in ports.items()}
    return {param_key(stage, port): value for port, value in ports.items()}


def _convert(value: float, kind: str) -> float:
    if kind is _TO_LINEAR or kind == _TO_LINEAR:
        return db_to_linear(value)
    if kind == _BOOL:
        return 1.0 if value else 0.0
    return float(value)


def _default_params(stage: FilterStage) -> dict[str, float]:
    from sonar.core.model import DEFAULT_FILTER_PARAMS

    return DEFAULT_FILTER_PARAMS[stage]


# --------------------------------------------------------------------------- profil


def profile_to_params(
    profile: Profile,
    *,
    stages: tuple[FilterStage, ...] = CHAIN_ORDER,
    channels: int = 2,
) -> dict[str, float]:
    """Bir profili canlı yazıma hazır düz parametre sözlüğüne indirger.

    `stages` zincirde gerçekten bulunan aşamalardır — kurulu olmayan bir eklenti
    zincirden çıkarıldığında `confgen` onu bu listeden de düşürür, böylece var olmayan
    bir node'a parametre yazmaya çalışmayız.
    """
    out: dict[str, float] = {}
    for stage in stages:
        if stage is FilterStage.EQ:
            capacity = registry.eq_plugin_for(profile.eq.band_count, channels).band_capacity
            out.update(eq_params(profile.eq, capacity))
        elif stage in MULTI_NODE_STAGES:
            out.update(multi_stage_params(stage, profile.filter(stage), channels))
        else:
            spec = _dynamic_spec(stage, channels)
            out.update(stage_params(stage, profile.filter(stage), spec))
    return out


def _dynamic_spec(stage: FilterStage, channels: int) -> registry.PluginSpec | None:
    suffix = "stereo" if channels == 2 else "mono"
    key = {
        FilterStage.GATE: f"lsp_gate_{suffix}",
        FilterStage.COMP: f"lsp_compressor_{suffix}",
        FilterStage.LIMITER: f"lsp_limiter_{suffix}",
        FilterStage.DEEPFILTER: f"deepfilter_{suffix}",
    }.get(stage)
    return registry.PLUGINS.get(key) if key else None
