"""Efekt kataloğunun **arayüz** tarafı: kategoriler ve parametre meta verisi.

`registry` eklentilerin port tablosunu tutuyor (sınırlar eklentinin kendi TTL'inden),
`params` Sonar adlarını port sembollerine çeviriyor. Burada üçüncü parça var: bir
parametrenin kullanıcıya **nasıl gösterileceği** — hangi aralıkta, hangi birimle, kaç
ondalıkla.

Bu bilgi şema 6'ya kadar `ChannelFx.qml` içinde elle yazılıydı ve her yeni efekt QML
yazmayı gerektiriyordu. Buraya taşınınca arayüz genel oldu: panel de, parametre satırı da
bu listeden çiziliyor, `sonar-cli` aynı listeyi okuyor ve çeviri anahtarları tek yerden
üretiliyor (`param.<efekt>.<ad>`).

**Aralıklar eklentinin sınırları değil, kullanıcıya makul geleni.** Eklenti `amount`
portuna 0–64 izin veriyor olabilir; kaydırıcıyı 64'e kadar açmak onu kullanılmaz yapar.
Yazılan değer yine de `PluginSpec.clamp` ile eklentinin sınırına kırpılıyor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sonar.core.model import CHAIN_ORDER, DEFAULT_FILTER_PARAMS, FilterStage

__all__ = ["CATEGORIES", "EFFECTS", "EffectSpec", "ParamSpec", "effect_spec", "params_of"]


class Category(StrEnum):
    """"Efekt ekle" listesindeki gruplar."""

    DYNAMICS = "dynamics"
    TONE = "tone"
    SPACE = "space"
    UTILITY = "utility"


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Bir parametrenin arayüzdeki hâli."""

    name: str
    minimum: float
    maximum: float
    unit: str = ""
    decimals: int = 1

    @property
    def default(self) -> float:
        return 0.0


@dataclass(frozen=True, slots=True)
class EffectSpec:
    kind: FilterStage
    category: Category
    params: tuple[ParamSpec, ...]
    #: Kullanıcıya gösterilecek kısa açıklama anahtarı; boşsa gösterilmiyor.
    hint: str = ""


def _p(name: str, minimum: float, maximum: float, unit: str = "", decimals: int = 1) -> ParamSpec:
    return ParamSpec(name, minimum, maximum, unit, decimals)


#: Katalog. Sıra `CHAIN_ORDER` ile aynı; "efekt ekle" listesi bu sırada çiziliyor.
EFFECTS: dict[FilterStage, EffectSpec] = {
    FilterStage.DEEPFILTER: EffectSpec(
        FilterStage.DEEPFILTER,
        Category.UTILITY,
        (
            _p("attenuation_db", 0, 100, "dB", 0),
            _p("post_filter_beta", 0, 0.05, "", 3),
        ),
        hint="fx.df.hint",
    ),
    FilterStage.GATE: EffectSpec(
        FilterStage.GATE,
        Category.DYNAMICS,
        (
            _p("threshold_db", -80, 0, "dB"),
            _p("attack_ms", 0, 200, "ms"),
            _p("release_ms", 5, 1000, "ms"),
            _p("reduction_db", -80, 0, "dB"),
        ),
    ),
    FilterStage.EXPANDER: EffectSpec(
        FilterStage.EXPANDER,
        Category.DYNAMICS,
        (
            _p("threshold_db", -80, 0, "dB"),
            _p("knee_db", -24, 0, "dB"),
            _p("attack_ms", 0, 200, "ms"),
            _p("release_ms", 5, 1000, "ms"),
            _p("makeup_db", 0, 24, "dB"),
        ),
        hint="fx.expander.hint",
    ),
    FilterStage.COMP: EffectSpec(
        FilterStage.COMP,
        Category.DYNAMICS,
        (
            _p("threshold_db", -60, 0, "dB"),
            _p("ratio", 1, 20, ": 1"),
            _p("attack_ms", 0, 200, "ms"),
            _p("release_ms", 5, 1000, "ms"),
            _p("makeup_db", 0, 24, "dB"),
        ),
    ),
    FilterStage.DEESSER: EffectSpec(
        FilterStage.DEESSER,
        Category.DYNAMICS,
        (
            _p("threshold_db", -60, 0, "dB"),
            _p("ratio", 1, 20, ": 1"),
            _p("split_hz", 2000, 16000, "Hz", 0),
            _p("makeup_db", 0, 24, "dB"),
        ),
        hint="fx.deesser.hint",
    ),
    FilterStage.BASS_ENHANCER: EffectSpec(
        FilterStage.BASS_ENHANCER,
        Category.TONE,
        (
            _p("amount", 0, 10, "", 2),
            _p("harmonics", 0.1, 10, "", 1),
            _p("scope_hz", 10, 250, "Hz", 0),
        ),
        hint="fx.bass.hint",
    ),
    FilterStage.EXCITER: EffectSpec(
        FilterStage.EXCITER,
        Category.TONE,
        (
            _p("amount", 0, 10, "", 2),
            _p("harmonics", 0.1, 10, "", 1),
            _p("scope_hz", 2000, 12000, "Hz", 0),
        ),
        hint="fx.exciter.hint",
    ),
    FilterStage.STEREO_TOOLS: EffectSpec(
        FilterStage.STEREO_TOOLS,
        Category.SPACE,
        (
            _p("width", 0, 200, "%", 0),
            _p("mid_db", -12, 12, "dB"),
            _p("balance", -100, 100, "%", 0),
            _p("base", -100, 100, "%", 0),
        ),
        hint="fx.stereo.hint",
    ),
    FilterStage.DELAY: EffectSpec(
        FilterStage.DELAY,
        Category.SPACE,
        (
            _p("time_ms", 0, 500, "ms", 0),
            _p("drywet", 0, 100, "%", 0),
        ),
    ),
    FilterStage.REVERB: EffectSpec(
        FilterStage.REVERB,
        Category.SPACE,
        (
            _p("decay_s", 0.4, 15, "s", 2),
            _p("room_size", 0, 5, "", 0),
            _p("wet", 0, 1, "", 2),
            _p("predelay_ms", 0, 500, "ms", 0),
            _p("damp_hz", 2000, 20000, "Hz", 0),
        ),
    ),
    FilterStage.SPATIAL: EffectSpec(
        FilterStage.SPATIAL,
        Category.SPACE,
        (
            _p("immersion", 0, 100, "", 0),
            _p("distance", 0, 100, "", 0),
        ),
        hint="fx.spatial.hint",
    ),
    FilterStage.LOUDNESS: EffectSpec(
        FilterStage.LOUDNESS,
        Category.TONE,
        (_p("volume_db", -60, 0, "dB"),),
        hint="fx.loudness.hint",
    ),
    FilterStage.BOOST: EffectSpec(
        FilterStage.BOOST,
        Category.UTILITY,
        (_p("gain_db", 0, 12, "dB"),),
        hint="fx.boost.hint",
    ),
    FilterStage.MAXIMIZER: EffectSpec(
        FilterStage.MAXIMIZER,
        Category.DYNAMICS,
        (
            _p("ceiling_db", -30, 0, "dB"),
            _p("gain_db", -20, 20, "dB"),
            _p("release_ms", 1, 100, "ms", 0),
        ),
        hint="fx.maximizer.hint",
    ),
    FilterStage.LIMITER: EffectSpec(
        FilterStage.LIMITER,
        Category.DYNAMICS,
        (
            _p("ceiling_db", -24, 0, "dB"),
            _p("lookahead_ms", 0.1, 20, "ms"),
            _p("release_ms", 0.25, 20, "ms"),
        ),
    ),
    FilterStage.EQ: EffectSpec(FilterStage.EQ, Category.TONE, ()),
}

#: Kategorilerin arayüzdeki sırası.
CATEGORIES: tuple[Category, ...] = (
    Category.DYNAMICS,
    Category.TONE,
    Category.SPACE,
    Category.UTILITY,
)


def effect_spec(kind: FilterStage) -> EffectSpec:
    return EFFECTS[kind]


def params_of(kind: FilterStage) -> list[dict]:
    """Bir efektin parametreleri, arayüzün beklediği sözlük biçiminde."""
    spec = EFFECTS.get(kind)
    if spec is None:
        return []
    defaults = DEFAULT_FILTER_PARAMS.get(kind, {})
    return [
        {
            "name": param.name,
            "label": f"param.{kind.value}.{param.name}",
            "from": param.minimum,
            "to": param.maximum,
            "unit": param.unit,
            "digits": param.decimals,
            "fallback": defaults.get(param.name, 0.0),
        }
        for param in spec.params
    ]


def _check_catalog() -> None:
    """Katalog ile modelin uyumu — içe aktarma anında.

    Bir efekti `CHAIN_ORDER`'a ekleyip burada tanımlamayı unutmak, arayüzde parametresiz
    bir panel demekti; parametre adını yanlış yazmak ise sessizce çalışmayan bir
    kaydırıcı. İkisi de test beklemeden burada patlıyor.
    """
    for kind in CHAIN_ORDER:
        spec = EFFECTS.get(kind)
        if spec is None:
            raise RuntimeError(f"efekt kataloğunda eksik: {kind.value}")
        defaults = DEFAULT_FILTER_PARAMS.get(kind, {})
        unknown = {p.name for p in spec.params} - set(defaults)
        if unknown:
            raise RuntimeError(f"{kind.value}: tanımsız parametre {sorted(unknown)}")


_check_catalog()
