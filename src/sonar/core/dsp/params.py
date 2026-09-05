"""Profil değerlerini eklenti port değerlerine çevirir.

Model katmanı parametreleri insan birimlerinde tutar (dB, ms, oran); LSP eklentileri ise
kazançları **lineer** ister. Bu modül aradaki tek dönüşüm noktasıdır ve canlı parametre
yazımının tek kaynağıdır: `profile_to_params()` bir profili doğrudan
``{"eq:g_3": 1.6788, "gate:at": 10.0, ...}`` biçimine indirger; `engine.control` bunu
olduğu gibi `pw-cli`'ye verir.

Anahtar biçimi ``"<slot>:<port>"`` — slot kimlikleri profildeki `EffectSlot.slot`
değerleridir ve `engine.confgen`'in ürettiği `filter.graph` node adlarıyla birebir
aynıdır. Şema 7'ye kadar bu ad aşamanın kendisiydi (`eq`, `gate`); artık aynı efektten
birden fazla eklenebildiği için slot kimliği (`comp`, `comp2`).
"""

from __future__ import annotations

import math

from sonar.core.dsp import registry
from sonar.core.model import (
    EffectSlot,
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


def param_key(slot: str, port: str) -> str:
    """``"eq:g_3"`` biçiminde canlı yazım anahtarı üretir."""
    return f"{slot}:{port}"


# --------------------------------------------------------------------------- EQ


def eq_params(eq: EqState, capacity: int, *, slot: str = "eq") -> dict[str, float]:
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
    return {param_key(slot, port): value for port, value in out.items()}


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
#: Kullanıcıya yüzde gösterilen, eklentide 0–1 (ya da 0–n) oranı olan portlar.
_PERCENT = "percent"

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
    # --- EasyEffects karşılıkları -------------------------------------------
    FilterStage.EXPANDER: {
        "threshold_db": ("al", _TO_LINEAR),
        "knee_db": ("kn", _TO_LINEAR),
        "attack_ms": ("at", _DIRECT),
        "release_ms": ("rt", _DIRECT),
        "makeup_db": ("mk", _TO_LINEAR),
    },
    FilterStage.DEESSER: {
        "threshold_db": ("threshold", _TO_LINEAR),
        "ratio": ("ratio", _DIRECT),
        "split_hz": ("f1_freq", _DIRECT),
        "makeup_db": ("makeup", _TO_LINEAR),
    },
    FilterStage.BASS_ENHANCER: {
        "amount": ("amount", _DIRECT),
        "harmonics": ("drive", _DIRECT),
        "scope_hz": ("freq", _DIRECT),
    },
    FilterStage.EXCITER: {
        "amount": ("amount", _DIRECT),
        "harmonics": ("drive", _DIRECT),
        "scope_hz": ("freq", _DIRECT),
    },
    FilterStage.STEREO_TOOLS: {
        "width": ("slev", _PERCENT),
        "mid_db": ("mlev", _TO_LINEAR),
        "balance": ("balance_out", _PERCENT),
        "base": ("stereo_base", _PERCENT),
    },
    FilterStage.DELAY: {
        "time_ms": ("time", _DIRECT),
        "drywet": ("drywet", _DIRECT),
    },
    FilterStage.REVERB: {
        "decay_s": ("decay_time", _DIRECT),
        "room_size": ("room_size", _DIRECT),
        "wet": ("amount", _DIRECT),
        "predelay_ms": ("predelay", _DIRECT),
        "damp_hz": ("hf_damp", _DIRECT),
    },
    FilterStage.LOUDNESS: {
        "volume_db": ("volume", _DIRECT),
    },
    FilterStage.MAXIMIZER: {
        "ceiling_db": ("Threshold", _DIRECT),
        "gain_db": ("Input Gain", _DIRECT),
        "release_ms": ("Release", _DIRECT),
    },
}

#: Aşamanın kapalı olduğunda yazılacak portlar. Topoloji değişmediği için bypass böyle yapılır.
_STAGE_BYPASS: dict[FilterStage, dict[str, float]] = {
    FilterStage.GATE: {"enabled": 0.0},
    FilterStage.COMP: {"enabled": 0.0},
    FilterStage.LIMITER: {"enabled": 0.0},
    FilterStage.EXPANDER: {"enabled": 0.0},
    FilterStage.DELAY: {"enabled": 0.0},
    FilterStage.LOUDNESS: {"enabled": 0.0},
    # DeepFilterNet'te `enabled` portu yok; sıfır azaltma sınırı fiilen bypass demektir.
    FilterStage.DEEPFILTER: {"Attenuation Limit (dB)": 0.0},
    # Calf'ın `bypass` portu 1 = kapalı (LSP'nin `enabled`'ının tersi).
    FilterStage.DEESSER: {"bypass": 1.0},
    FilterStage.BASS_ENHANCER: {"bypass": 1.0},
    FilterStage.EXCITER: {"bypass": 1.0},
    FilterStage.STEREO_TOOLS: {"bypass": 1.0},
    # Calf Reverb'de `bypass` yok; `on` (Active) portu 0 olunca devre dışı.
    FilterStage.REVERB: {"on": 0.0},
    # ZaMaximX2'de bypass portu **yok**: tavan 0 dB ve kazanç 0 dB iken şeffaf.
    FilterStage.MAXIMIZER: {"Threshold": 0.0, "Input Gain": 0.0, "Release": 30.0},
}

#: `enabled = 1` yazılmayacak aşamalar: ya öyle bir portları yok, ya da bypass'ları
#: başka bir portla yapılıyor ve açılışta o portun **gerçek** değeri yazılmalı.
_NO_ENABLED_PORT: frozenset[FilterStage] = frozenset(
    {
        FilterStage.DEEPFILTER,
        FilterStage.MAXIMIZER,
        FilterStage.DEESSER,
        FilterStage.BASS_ENHANCER,
        FilterStage.EXCITER,
        FilterStage.STEREO_TOOLS,
        FilterStage.REVERB,
    }
)

#: Aşama açıkken bypass portunun alacağı **ters** değer.
_STAGE_ACTIVE: dict[FilterStage, dict[str, float]] = {
    FilterStage.DEESSER: {"bypass": 0.0},
    FilterStage.BASS_ENHANCER: {"bypass": 0.0},
    FilterStage.EXCITER: {"bypass": 0.0},
    FilterStage.STEREO_TOOLS: {"bypass": 0.0},
    FilterStage.REVERB: {"on": 1.0},
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
    stage: FilterStage, state: FilterState, channels: int = 2, slot: str = ""
) -> dict[str, float]:
    """Çok node'lu aşamaların port değerleri; anahtarlar tam nitelikli (`"boost_l:Mult"`)."""
    slot = slot or stage.value
    if stage is FilterStage.BOOST:
        return _boost_params(slot, state, channels)
    if stage is FilterStage.SPATIAL:
        return _spatial_params(slot, state)
    raise ValueError(f"{stage} çok node'lu bir aşama değil")


def _boost_names(slot: str, channels: int) -> tuple[str, ...]:
    return (slot,) if channels == 1 else (f"{slot}_l", f"{slot}_r")


def _boost_params(slot: str, state: FilterState, channels: int) -> dict[str, float]:
    """PipeWire `linear`: `Out = In * Mult + Add`. Bypass `Mult = 1.0`."""
    defaults = _default_params(FilterStage.BOOST)
    gain_db = state.params.get("gain_db", defaults["gain_db"]) if state.enabled else 0.0
    gain_db = min(max(float(gain_db), 0.0), MAX_BOOST_DB)
    mult = db_to_linear(gain_db)
    out: dict[str, float] = {}
    for name in _boost_names(slot, channels):
        out[f"{name}:Mult"] = mult
        out[f"{name}:Add"] = 0.0
    return out


def _spatial_params(slot: str, state: FilterState) -> dict[str, float]:
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
        return {f"{slot}_mix_l:Gain 2": 0.0, f"{slot}_mix_r:Gain 2": 0.0}

    immersion = _unit(state.params.get("immersion", defaults["immersion"]))
    distance = _unit(state.params.get("distance", defaults["distance"]))

    bleed = SPATIAL_BLEED_MIN + immersion * (SPATIAL_BLEED_MAX - SPATIAL_BLEED_MIN)
    cutoff = SPATIAL_CUTOFF_MAX_HZ + immersion * (SPATIAL_CUTOFF_MIN_HZ - SPATIAL_CUTOFF_MAX_HZ)
    delay = SPATIAL_DELAY_MIN_S + distance * (SPATIAL_DELAY_MAX_S - SPATIAL_DELAY_MIN_S)

    return {
        f"{slot}_mix_l:Gain 1": 1.0,
        f"{slot}_mix_r:Gain 1": 1.0,
        f"{slot}_mix_l:Gain 2": bleed,
        f"{slot}_mix_r:Gain 2": bleed,
        f"{slot}_delay_l:Delay (s)": delay,
        f"{slot}_delay_r:Delay (s)": delay,
        f"{slot}_lp_l:Freq": cutoff,
        f"{slot}_lp_r:Freq": cutoff,
        f"{slot}_lp_l:Q": 0.707,
        f"{slot}_lp_r:Q": 0.707,
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
    stage: FilterStage,
    state: FilterState,
    spec: registry.PluginSpec | None = None,
    slot: str = "",
) -> dict[str, float]:
    """Tek bir dinamik aşamanın port değerlerini üretir."""
    if stage is FilterStage.EQ:
        raise ValueError("EQ için eq_params() kullanın")
    mapping = _STAGE_PORT_MAP[stage]

    if not state.enabled:
        ports = dict(_STAGE_BYPASS[stage])
    else:
        ports = {} if stage in _NO_ENABLED_PORT else {"enabled": 1.0}
        ports.update(_STAGE_ACTIVE.get(stage, {}))
        ports.update(_STAGE_FIXED.get(stage, {}))
        defaults = _default_params(stage)
        for name, (port, kind) in mapping.items():
            value = state.params.get(name, defaults.get(name, 0.0))
            ports[port] = _convert(value, kind)

    if spec is not None:
        ports = {port: spec.clamp(port, value) for port, value in ports.items()}
    return {param_key(slot or stage.value, port): value for port, value in ports.items()}


def _convert(value: float, kind: str) -> float:
    if kind == _TO_LINEAR:
        return db_to_linear(value)
    if kind == _BOOL:
        return 1.0 if value else 0.0
    if kind == _PERCENT:
        return float(value) / 100.0
    return float(value)


def _default_params(stage: FilterStage) -> dict[str, float]:
    from sonar.core.model import DEFAULT_FILTER_PARAMS

    return DEFAULT_FILTER_PARAMS[stage]


# --------------------------------------------------------------------------- profil


def profile_to_params(
    profile: Profile,
    *,
    slots: tuple[EffectSlot, ...] | None = None,
    channels: int = 2,
) -> dict[str, float]:
    """Bir profili canlı yazıma hazır düz parametre sözlüğüne indirger.

    `slots` zincirde gerçekten bulunan efektlerdir — kurulu olmayan bir eklenti zincirden
    çıkarıldığında `chain.plan_chain` onu düşürür ve `confgen` bu listeyi ona göre verir,
    böylece var olmayan bir node'a parametre yazmaya çalışmayız.
    """
    out: dict[str, float] = {}
    for effect in profile.effects if slots is None else slots:
        state = profile.state(effect.slot)
        if effect.kind is FilterStage.EQ:
            capacity = registry.eq_plugin_for(profile.eq.band_count, channels).band_capacity
            out.update(eq_params(profile.eq, capacity, slot=effect.slot))
        elif effect.kind in MULTI_NODE_STAGES:
            out.update(multi_stage_params(effect.kind, state, channels, slot=effect.slot))
        else:
            spec = _dynamic_spec(effect.kind, channels)
            out.update(stage_params(effect.kind, state, spec, slot=effect.slot))
    return out


def _dynamic_spec(stage: FilterStage, channels: int) -> registry.PluginSpec | None:
    suffix = "stereo" if channels == 2 else "mono"
    key = _PLUGIN_KEYS.get(stage, "").format(suffix=suffix)
    return registry.PLUGINS.get(key) if key else None


#: Aşama → eklenti anahtarı şablonu. Tek kaynak: `chain._plugin_key` de bunu okuyor,
#: yoksa iki yerde birbirinden habersiz iki eşleme olurdu.
_PLUGIN_KEYS: dict[FilterStage, str] = {
    FilterStage.GATE: "lsp_gate_{suffix}",
    FilterStage.COMP: "lsp_compressor_{suffix}",
    FilterStage.LIMITER: "lsp_limiter_{suffix}",
    FilterStage.DEEPFILTER: "deepfilter_{suffix}",
    FilterStage.EXPANDER: "lsp_expander_stereo",
    FilterStage.DELAY: "lsp_comp_delay_stereo",
    FilterStage.LOUDNESS: "lsp_loud_comp_stereo",
    FilterStage.DEESSER: "calf_deesser",
    FilterStage.BASS_ENHANCER: "calf_bassenhancer",
    FilterStage.EXCITER: "calf_exciter",
    FilterStage.REVERB: "calf_reverb",
    FilterStage.STEREO_TOOLS: "calf_stereotools",
    FilterStage.MAXIMIZER: "zam_maximizer_stereo",
}
