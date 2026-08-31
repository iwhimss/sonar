"""Sonar'ın veri modeli.

Bu modül **saf**tır: PipeWire'a, dosya sistemine ve Qt'ye bağımlı değildir, yan etkisi yoktur.
Daemon, GUI ve CLI aynı nesneleri kullanır.

Önemli tasarım kararı: filtre parametreleri burada **insan birimlerinde** (dB, ms, oran)
tutulur — eklentinin port birimlerinde değil. Dönüşüm `core.dsp.params` katmanında yapılır.
Böylece yapılandırma dosyası kullanılan LV2 eklentisinden bağımsız kalır; ileride DSP arka ucu
değişirse kullanıcının profilleri geçerliliğini korur.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "SCHEMA_VERSION",
    "BusId",
    "BusSend",
    "Channel",
    "ChatMixConfig",
    "EqBand",
    "EqBandType",
    "EqState",
    "FilterStage",
    "FilterState",
    "MasterBus",
    "MatchKey",
    "MicChain",
    "Profile",
    "RoutingRule",
    "Settings",
    "SonarConfig",
    "default_band_frequencies",
    "default_band_q",
    "default_config",
    "default_profile",
]

SCHEMA_VERSION = 1

#: Varsayılan EQ bandlarının yayıldığı aralık. 31.25 Hz – 16 kHz tam 9 oktav olduğu için
#: 10 bandda tam oktav aralıklı klasik grafik ekolayzer frekansları çıkar.
EQ_FREQ_MIN = 31.25
EQ_FREQ_MAX = 16_000.0

#: Arayüzde sunulan band sayıları. Her biri bir LSP `para_equalizer_xN` varyantına eşlenir.
SUPPORTED_BAND_COUNTS = (5, 10, 16, 32)

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


# --------------------------------------------------------------------------- sabit listeler


class FilterStage(StrEnum):
    """DSP zincirindeki aşamalar. Değerler zincirdeki node adlarıyla birebir aynıdır."""

    DEEPFILTER = "df"
    GATE = "gate"
    EQ = "eq"
    COMP = "comp"
    LIMITER = "lim"


#: Zincirdeki sıralama — sinyal bu sırayla akar.
CHAIN_ORDER: tuple[FilterStage, ...] = (
    FilterStage.DEEPFILTER,
    FilterStage.GATE,
    FilterStage.EQ,
    FilterStage.COMP,
    FilterStage.LIMITER,
)

#: EQ dışındaki, `FilterState` ile temsil edilen aşamalar.
DYNAMIC_STAGES: tuple[FilterStage, ...] = (
    FilterStage.DEEPFILTER,
    FilterStage.GATE,
    FilterStage.COMP,
    FilterStage.LIMITER,
)


class BusId(StrEnum):
    """İki miks yolu: kullanıcının kulaklığı ve yayın."""

    PERSONAL = "personal"
    STREAM = "stream"


class EqBandType(StrEnum):
    """EQ band filtre tipleri (LSP `ft_N` enum'una eşlenir)."""

    OFF = "off"
    PEAK = "peak"
    LOW_SHELF = "low_shelf"
    HIGH_SHELF = "high_shelf"
    LOW_PASS = "low_pass"
    HIGH_PASS = "high_pass"
    NOTCH = "notch"
    ALLPASS = "allpass"
    BANDPASS = "bandpass"


class MatchKey(StrEnum):
    """Bir yönlendirme kuralının hangi akış özelliğine baktığı."""

    BINARY = "binary"  # application.process.binary — en güvenilir
    APP_NAME = "app_name"  # application.name
    MEDIA_NAME = "media_name"  # media.name

    @property
    def priority(self) -> int:
        """Küçük sayı = daha güvenilir eşleşme."""
        return {"binary": 0, "app_name": 1, "media_name": 2}[self.value]


# --------------------------------------------------------------------------- filtreler


@dataclass(slots=True)
class EqBand:
    """Tek bir parametrik EQ bandı."""

    freq: float
    gain_db: float = 0.0
    q: float = 1.41
    band_type: EqBandType = EqBandType.PEAK
    slope: int = 0  # LSP `s_N`: 0=x1, 1=x2, 2=x3, 3=x4
    enabled: bool = True

    def clamped(self) -> EqBand:
        """Değerleri makul aralıklara kırpılmış bir kopya döndürür."""
        return EqBand(
            freq=min(max(self.freq, 10.0), 24_000.0),
            gain_db=min(max(self.gain_db, -36.0), 36.0),
            q=min(max(self.q, 0.05), 100.0),
            band_type=self.band_type,
            slope=min(max(self.slope, 0), 3),
            enabled=self.enabled,
        )


@dataclass(slots=True)
class EqState:
    """Bir profilin ekolayzer durumu."""

    enabled: bool = False
    band_count: int = 10
    preamp_db: float = 0.0
    bands: list[EqBand] = field(default_factory=list)

    def active_bands(self) -> list[EqBand]:
        """Yalnızca `band_count` kadarını döndürür (fazlası kullanıcı geçmişinde saklı kalır)."""
        return self.bands[: self.band_count]


@dataclass(slots=True)
class FilterState:
    """EQ dışındaki bir aşamanın durumu.

    `params` anahtarları Sonar'ın kendi isimleridir (`threshold_db`, `attack_ms`, …),
    eklenti port sembolleri değil. Eşleme `core.dsp.params` içindedir.
    """

    enabled: bool = False
    params: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Profile:
    """Bir kanalın tüm DSP durumu. Kanal başına birden fazla profil kaydedilebilir."""

    name: str = "Default"
    eq: EqState = field(default_factory=EqState)
    filters: dict[FilterStage, FilterState] = field(default_factory=dict)
    favorite_slot: int | None = None

    def filter(self, stage: FilterStage) -> FilterState:
        """Aşamanın durumunu döndürür; tanımlı değilse varsayılanı üretir."""
        state = self.filters.get(stage)
        if state is None:
            state = FilterState(enabled=False, params=dict(DEFAULT_FILTER_PARAMS[stage]))
            self.filters[stage] = state
        return state


# --------------------------------------------------------------------------- kanallar & bus'lar


@dataclass(slots=True)
class BusSend:
    """Bir kanalın bir miks yoluna gönderdiği seviye."""

    volume: float = 1.0
    muted: bool = False


@dataclass(slots=True)
class Channel:
    """Uygulamaların ses çaldığı bir sanal kanal."""

    id: str
    name: str
    color: str
    icon: str = "speaker"
    order: int = 0
    builtin: bool = False
    active_profile: str = "Default"
    personal: BusSend = field(default_factory=BusSend)
    stream: BusSend = field(default_factory=BusSend)

    def send(self, bus: BusId) -> BusSend:
        return self.personal if bus is BusId.PERSONAL else self.stream

    @property
    def sink_node(self) -> str:
        """Uygulamaların çaldığı sink node adı."""
        return f"sonar_{self.id}"

    @property
    def fx_node(self) -> str:
        """DSP sonrası sanal kaynak — OBS bunu yakalar."""
        return f"sonar_{self.id}_fx"

    def loopback_node(self, bus: BusId) -> str:
        """Fader'ın uygulandığı loopback node adı."""
        return f"sonar_{self.id}_to_{bus.value}"


@dataclass(slots=True)
class MasterBus:
    """Kişisel veya yayın miks yolu."""

    id: BusId
    name: str
    device: str = ""  # boş = sistem varsayılanı
    volume: float = 1.0
    muted: bool = False
    active_profile: str = "Default"

    @property
    def sink_node(self) -> str:
        return f"sonar_{self.id.value}"


@dataclass(slots=True)
class MicChain:
    """Bir mikrofon işleme zinciri ve ondan doğan sanal kaynak."""

    id: str  # "mic" veya "stream_mic"
    name: str
    source_device: str = ""  # boş = sistem varsayılanı
    active_profile: str = "Default"
    volume: float = 1.0
    muted: bool = False
    #: Yalnızca `stream_mic` için: ayrı bir zincir kurmak yerine `mic` zincirinden beslen.
    share_chain_with_mic: bool = False
    #: Yan ton — kendi sesini kulaklıktan duyma.
    monitor_enabled: bool = False
    monitor_volume: float = 0.5
    #: Mikrofonu yayın miksine de gönder (OBS ayrı kaynak kullanıyorsa gereksizdir).
    send_to_stream_bus: bool = False

    @property
    def source_node(self) -> str:
        return f"sonar_{self.id}"


# --------------------------------------------------------------------------- yönlendirme


@dataclass(slots=True)
class RoutingRule:
    """Bir uygulamayı bir kanala bağlayan kural."""

    match_key: MatchKey
    pattern: str
    channel_id: str
    is_regex: bool = False
    enabled: bool = True

    def matches(self, value: str) -> bool:
        """`value` bu kurala uyuyor mu? Hatalı regex sessizce eşleşmez sayılır."""
        if not self.enabled or not value:
            return False
        if self.is_regex:
            try:
                return re.search(self.pattern, value, re.IGNORECASE) is not None
            except re.error:
                return False
        return value.casefold() == self.pattern.casefold()

    @property
    def specificity(self) -> int:
        """Aynı öncelikteki kurallar arasında daha uzun desen kazanır."""
        return len(self.pattern)


@dataclass(slots=True)
class ChatMixConfig:
    """Tek slider ile iki kanal arasında denge kurar. Yalnızca kişisel miksi etkiler."""

    enabled: bool = True
    value: float = 50.0  # 0 = tamamen sol, 50 = nötr, 100 = tamamen sağ
    left_channel: str = "game"
    right_channel: str = "chat"
    floor_db: float = -40.0  # uçtaki kanalın kaç dB kısılacağı


@dataclass(slots=True)
class Settings:
    """Kanal dışı genel ayarlar."""

    #: Sistem varsayılan çıkışını Sonar'a devret. Kapalıyken hiçbir sistem ayarına dokunulmaz.
    take_over_default_sink: bool = False
    sample_rate: int = 48_000
    #: Hiçbir kurala uymayan uygulamanın gideceği kanal.
    default_channel: str = "media"
    default_band_count: int = 10
    start_minimized: bool = False


# --------------------------------------------------------------------------- kök


@dataclass(slots=True)
class SonarConfig:
    """Kalıcı yapılandırmanın kökü. Profiller ayrı dosyalarda tutulur."""

    schema_version: int = SCHEMA_VERSION
    channels: list[Channel] = field(default_factory=list)
    buses: list[MasterBus] = field(default_factory=list)
    mic_chains: list[MicChain] = field(default_factory=list)
    rules: list[RoutingRule] = field(default_factory=list)
    chatmix: ChatMixConfig = field(default_factory=ChatMixConfig)
    settings: Settings = field(default_factory=Settings)

    # ------------------------------------------------------------------ arama yardımcıları

    def channel(self, channel_id: str) -> Channel | None:
        return next((c for c in self.channels if c.id == channel_id), None)

    def bus(self, bus_id: BusId | str) -> MasterBus | None:
        """Bilinmeyen id'de `None` — `channel()` ve `mic()` ile aynı davranış.

        Eskiden `BusId(bus_id)` doğrudan çağrılıyor ve bilinmeyen bir ad `ValueError`
        yükseltiyordu; imza `| None` dediği hâlde. "Bu ad bir kanal mı, bus mu?" diye
        yoklayan her çağrı yeri patlıyordu.
        """
        if isinstance(bus_id, str):
            try:
                key = BusId(bus_id)
            except ValueError:
                return None
        else:
            key = bus_id
        return next((b for b in self.buses if b.id is key), None)

    def mic(self, mic_id: str) -> MicChain | None:
        return next((m for m in self.mic_chains if m.id == mic_id), None)

    def ordered_channels(self) -> list[Channel]:
        return sorted(self.channels, key=lambda c: (c.order, c.id))

    def profile_targets(self) -> list[str]:
        """Profil tutabilen her şeyin kimliği — kanallar, mikrofonlar ve bus'lar."""
        return (
            [c.id for c in self.ordered_channels()]
            + [m.id for m in self.mic_chains]
            + [b.id.value for b in self.buses]
        )

    def next_channel_order(self) -> int:
        return max((c.order for c in self.channels), default=-1) + 1


# --------------------------------------------------------------------------- varsayılanlar


def default_band_frequencies(count: int) -> list[float]:
    """`count` band için logaritmik aralıklı merkez frekansları."""
    if count < 1:
        return []
    if count == 1:
        return [1000.0]
    ratio = (EQ_FREQ_MAX / EQ_FREQ_MIN) ** (1 / (count - 1))
    return [round(EQ_FREQ_MIN * ratio**i, 2) for i in range(count)]


def default_band_q(count: int) -> float:
    """Komşu bandlar arasındaki mesafeye göre birbirini tamamlayan Q değeri.

    Bant genişliği `n` oktav olan bir çan filtresi için standart formül:
    ``Q = sqrt(2^n) / (2^n - 1)``. Tam oktav aralıkta (10 band) 1.414 çıkar.
    """
    if count < 2:
        return 1.41
    ratio = (EQ_FREQ_MAX / EQ_FREQ_MIN) ** (1 / (count - 1))
    octaves = math.log2(ratio)
    return round(math.sqrt(2**octaves) / (2**octaves - 1), 4)


#: Her dinamik aşamanın insan birimli varsayılan parametreleri.
DEFAULT_FILTER_PARAMS: dict[FilterStage, dict[str, float]] = {
    FilterStage.DEEPFILTER: {
        "attenuation_db": 40.0,  # 0 = etkisiz, 100 = azami temizlik
        "post_filter_beta": 0.02,
        "min_buffer_frames": 0.0,
    },
    FilterStage.GATE: {
        "threshold_db": -40.0,
        "zone_db": -6.0,  # eşiğin altındaki geçiş bölgesi (histerezis genişliği)
        "reduction_db": -24.0,  # kapalıyken uygulanan kısma
        "attack_ms": 10.0,
        "release_ms": 100.0,
        "makeup_db": 0.0,
        "hysteresis": 0.0,
    },
    FilterStage.COMP: {
        "threshold_db": -18.0,
        "ratio": 4.0,
        "attack_ms": 5.0,
        "release_ms": 120.0,
        "knee_db": -6.0,
        "makeup_db": 0.0,
    },
    FilterStage.LIMITER: {
        "ceiling_db": -1.0,
        "lookahead_ms": 5.0,
        "attack_ms": 5.0,
        "release_ms": 5.0,
    },
}


def default_profile(name: str = "Default", band_count: int = 10) -> Profile:
    """Düz EQ ve tüm filtreleri kapalı bir profil."""
    freqs = default_band_frequencies(band_count)
    q = default_band_q(band_count)
    bands = [EqBand(freq=f, gain_db=0.0, q=q, band_type=EqBandType.PEAK) for f in freqs]
    return Profile(
        name=name,
        eq=EqState(enabled=False, band_count=band_count, preamp_db=0.0, bands=bands),
        filters={
            stage: FilterState(enabled=False, params=dict(params))
            for stage, params in DEFAULT_FILTER_PARAMS.items()
        },
    )


#: Kanal kimliği → (görünen ad, aksan rengi, ikon). Renkler `.plan/07-gui-mixer.md`'deki palet.
BUILTIN_CHANNELS: tuple[tuple[str, str, str, str], ...] = (
    ("game", "Game", "#22C58B", "gamepad"),
    ("chat", "Chat", "#3B9EFF", "chat"),
    ("media", "Media", "#F0479A", "play"),
    ("aux", "Aux", "#8B95A5", "speaker"),
)

#: İlk kurulumda önerilen yönlendirme kuralları.
SUGGESTED_RULES: tuple[tuple[MatchKey, str, str], ...] = (
    (MatchKey.BINARY, "Discord", "chat"),
    (MatchKey.BINARY, "discord", "chat"),
    (MatchKey.BINARY, "vesktop", "chat"),
    (MatchKey.BINARY, "TeamSpeak3", "chat"),
    (MatchKey.BINARY, "mumble", "chat"),
    (MatchKey.APP_NAME, "WEBRTC VoiceEngine", "chat"),
    (MatchKey.BINARY, "firefox", "media"),
    (MatchKey.BINARY, "chrome", "media"),
    (MatchKey.BINARY, "chromium", "media"),
    (MatchKey.BINARY, "brave", "media"),
    (MatchKey.BINARY, "spotify", "media"),
    (MatchKey.BINARY, "mpv", "media"),
    (MatchKey.BINARY, "vlc", "media"),
)


def default_config() -> SonarConfig:
    """İlk çalıştırmada yazılan yapılandırma."""
    channels = [
        Channel(id=cid, name=name, color=color, icon=icon, order=i, builtin=True)
        for i, (cid, name, color, icon) in enumerate(BUILTIN_CHANNELS)
    ]
    buses = [
        MasterBus(id=BusId.PERSONAL, name="Personal Mix"),
        MasterBus(id=BusId.STREAM, name="Stream Mix"),
    ]
    mics = [
        MicChain(id="mic", name="Mic"),
        MicChain(id="stream_mic", name="Stream Mic", share_chain_with_mic=False),
    ]
    rules = [
        RoutingRule(match_key=key, pattern=pattern, channel_id=channel)
        for key, pattern, channel in SUGGESTED_RULES
    ]
    return SonarConfig(channels=channels, buses=buses, mic_chains=mics, rules=rules)


def slugify(name: str) -> str:
    """Kullanıcının verdiği adı güvenli bir kanal kimliğine çevirir."""
    slug = _SLUG_RE.sub("_", name.strip().casefold().replace(" ", "_")).strip("_")
    return slug or "kanal"
