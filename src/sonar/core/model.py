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
    "DEFAULT_OUTPUT_BUS",
    "SCHEMA_VERSION",
    "STREAM_BUS",
    "BusKind",
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

SCHEMA_VERSION = 3

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


class BusKind(StrEnum):
    """Bir miks yolunun türü.

    `OUTPUT` bir fiziksel cihaza çıkar ve birden fazla olabilir — kullanıcı Game'i
    hoparlöre, Media'yı kulaklığa gönderebilsin diye (Faz 20). Her birinin kendi
    master fader'ı, DSP'si ve profili var.

    `STREAM` tektir: OBS'in gördüğü sanal giriş cihazı. Her kanal ona **ayrıca** ve
    her zaman gönderir; hangi çıkışa gittiğinden bağımsız.
    """

    OUTPUT = "output"
    STREAM = "stream"


#: İlk kurulumda oluşturulan çıkış bus'ının kimliği. Kod hiçbir yerde "personal"
#: olduğunu varsaymaz; kullanıcı onu silip başkasını varsayılan yapabilir.
DEFAULT_OUTPUT_BUS = "personal"

#: Yayın bus'ının kimliği. Tek olduğu için sabit.
STREAM_BUS = "stream"


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
    #: Bus kimliği → gönderi seviyesi. Yayın bus'ı dâhil **her** bus için bir giriş
    #: bulunur; eksikse `send()` varsayılanını üretir.
    sends: dict[str, BusSend] = field(default_factory=dict)
    #: Kanalın hangi çıkış bus'ına gittiği. Yalnızca bu bus'ın gönderisi açık kalır;
    #: diğer çıkış bus'larının gönderileri susturulur. Değiştirmek grafı yeniden
    #: kurmaz, yalnızca bir mute yazımıdır.
    output_bus: str = DEFAULT_OUTPUT_BUS
    #: OBS'e kanal başına ayrı track vermek için `_fx` çıkışını sanal bir **giriş
    #: cihazı** olarak yayınla. Varsayılan kapalı: açıkken her çıkış kanalı sistemin
    #: mikrofon listesinde görünür ve "Media neden mikrofon?" sorusuna yol açar.
    #: SteelSeries GG'de de yalnızca birleşik Stream Mix vardı.
    stream_source: bool = False

    def send(self, bus_id: str) -> BusSend:
        """Bu kanalın bir bus'a gönderisi. Yoksa nötr bir tane üretilip saklanır."""
        send = self.sends.get(bus_id)
        if send is None:
            send = BusSend()
            self.sends[bus_id] = send
        return send

    @property
    def stream(self) -> BusSend:
        """Yayın gönderisi — sık kullanıldığı için kısayol."""
        return self.send(STREAM_BUS)

    @property
    def output(self) -> BusSend:
        """Kanalın **seçili** çıkış bus'ına gönderisi; mikserdeki kulaklık fader'ı."""
        return self.send(self.output_bus)

    @property
    def sink_node(self) -> str:
        """Uygulamaların çaldığı sink node adı."""
        return f"sonar_{self.id}"

    @property
    def fx_node(self) -> str:
        """DSP sonrası çıkış. `stream_source` açıkken ayrıca sanal bir kaynaktır."""
        return f"sonar_{self.id}_fx"

    def loopback_node(self, bus_id: str) -> str:
        """Fader'ın uygulandığı loopback node adı."""
        return f"sonar_{self.id}_to_{bus_id}"


@dataclass(slots=True)
class MasterBus:
    """Bir miks yolu: bir çıkış cihazı ya da yayın miksi."""

    id: str
    name: str
    kind: BusKind = BusKind.OUTPUT
    device: str = ""  # boş = sistem varsayılanı
    volume: float = 1.0
    muted: bool = False
    active_profile: str = "Default"
    order: int = 0

    @property
    def sink_node(self) -> str:
        return f"sonar_{self.id}"

    @property
    def out_node(self) -> str:
        """Bus'ın çıkış node'u: çıkış bus'larında fiziksel cihaza giden akış,
        yayın bus'ında OBS'in gördüğü sanal kaynak."""
        return f"sonar_{self.id}_out"

    @property
    def is_stream(self) -> bool:
        return self.kind is BusKind.STREAM


@dataclass(slots=True)
class MicChain:
    """Bir mikrofon işleme zinciri ve ondan doğan sanal kaynak."""

    id: str  # ilk kurulumda "mic" ve "stream_mic"; kullanıcı yenisini ekleyebilir
    name: str
    color: str = "#F2A73B"
    icon: str = "mic"
    order: int = 0
    builtin: bool = False
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
    #: Virgülle birden fazla kanal verilebilir ("chat,media"). Yeni bir alan eklemek yerine
    #: aynı alan çoğullaştırıldı: eski yapılandırmalar olduğu gibi okunmaya devam ediyor.
    left_channel: str = "game"
    right_channel: str = "chat"
    floor_db: float = -40.0  # uçtaki kanalın kaç dB kısılacağı

    def left(self) -> list[str]:
        return _split_channels(self.left_channel)

    def right(self) -> list[str]:
        return _split_channels(self.right_channel)


def _split_channels(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


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
    #: Hedef → sıralı favori profil adları. Sıra listenin kendisi; sayı sınırı yok.
    #: Şema 1'de bu bilgi profil dosyalarındaki `favorite_slot` alanında (9 slot) duruyordu.
    favorites: dict[str, list[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------ arama yardımcıları

    def channel(self, channel_id: str) -> Channel | None:
        return next((c for c in self.channels if c.id == channel_id), None)

    def bus(self, bus_id: str) -> MasterBus | None:
        """Bilinmeyen id'de `None` — `channel()` ve `mic()` ile aynı davranış."""
        return next((b for b in self.buses if b.id == bus_id), None)

    def ordered_buses(self) -> list[MasterBus]:
        """Conf üretimi buna bağlı: sıra deterministik olmalı."""
        return sorted(self.buses, key=lambda b: (b.order, b.id))

    def output_buses(self) -> list[MasterBus]:
        """Fiziksel cihaza çıkan bus'lar — mikserdeki master şeritleri."""
        return [b for b in self.ordered_buses() if not b.is_stream]

    def stream_bus(self) -> MasterBus | None:
        return next((b for b in self.buses if b.is_stream), None)

    def default_output_bus(self) -> MasterBus | None:
        """Kanalların düşeceği çıkış. `personal` yoksa ilk çıkış bus'ı."""
        return self.bus(DEFAULT_OUTPUT_BUS) or next(iter(self.output_buses()), None)

    def output_bus_of(self, channel: Channel) -> MasterBus | None:
        """Kanalın gerçekten bağlı olduğu çıkış — seçtiği bus silinmişse varsayılan."""
        return self.bus(channel.output_bus) or self.default_output_bus()

    def ensure_sends(self) -> None:
        """Her kanalın her bus'a bir gönderisi olsun.

        `Channel.send()` eksik olanı zaten üretiyor, ama o tembel yol yalnızca bellekte
        çalışıyor: `config.toml`'da ve arayüzün gördüğü JSON'da gönderi görünmüyordu.
        Yükleme ve bus ekleme sonrasında bir kez çağrılır.
        """
        bus_ids = [bus.id for bus in self.buses]
        for channel in self.channels:
            for bus_id in bus_ids:
                channel.send(bus_id)
            # Silinmiş bir bus'ın gönderisi artılıp durmasın.
            for stale in [b for b in channel.sends if b not in bus_ids]:
                del channel.sends[stale]

    def next_bus_order(self) -> int:
        return max((b.order for b in self.buses), default=-1) + 1

    def mic(self, mic_id: str) -> MicChain | None:
        return next((m for m in self.mic_chains if m.id == mic_id), None)

    def ordered_channels(self) -> list[Channel]:
        return sorted(self.channels, key=lambda c: (c.order, c.id))

    def ordered_mics(self) -> list[MicChain]:
        return sorted(self.mic_chains, key=lambda m: (m.order, m.id))

    def next_mic_order(self) -> int:
        return max((m.order for m in self.mic_chains), default=-1) + 1

    def favorites_of(self, target: str) -> list[str]:
        return list(self.favorites.get(target, []))

    def profile_targets(self) -> list[str]:
        """Profil tutabilen her şeyin kimliği — kanallar, mikrofonlar ve bus'lar."""
        return (
            [c.id for c in self.ordered_channels()]
            + [m.id for m in self.mic_chains]
            + [b.id for b in self.ordered_buses()]
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
#: İlk kurulumda yazılan yönlendirme kuralları: `(anahtar, desen, kanal, regex mi)`.
#: Hepsi öneridir — kullanıcı arayüzden veya `config.toml`'dan düzenleyebilir.
SUGGESTED_RULES: tuple[tuple[MatchKey, str, str, bool], ...] = (
    (MatchKey.BINARY, "Discord", "chat", False),
    (MatchKey.BINARY, "discord", "chat", False),
    (MatchKey.BINARY, "vesktop", "chat", False),
    (MatchKey.BINARY, "TeamSpeak3", "chat", False),
    (MatchKey.BINARY, "mumble", "chat", False),
    (MatchKey.APP_NAME, "WEBRTC VoiceEngine", "chat", False),
    (MatchKey.BINARY, "firefox", "media", False),
    (MatchKey.BINARY, "chrome", "media", False),
    (MatchKey.BINARY, "chromium", "media", False),
    (MatchKey.BINARY, "brave", "media", False),
    (MatchKey.BINARY, "spotify", "media", False),
    (MatchKey.BINARY, "mpv", "media", False),
    (MatchKey.BINARY, "vlc", "media", False),
    # Oyunlar: Proton/Wine altındaki süreçler ve Steam'in kendi başlattığı binary'ler.
    # Bunlar sezgisel; yanlış yakalarsa kullanıcı kuralı silebilir.
    (MatchKey.BINARY, r"\.exe$", "game", True),
    (MatchKey.BINARY, r"^wine", "game", True),
    (MatchKey.BINARY, r"^steam_app_", "game", True),
)


def default_config() -> SonarConfig:
    """İlk çalıştırmada yazılan yapılandırma."""
    channels = [
        Channel(id=cid, name=name, color=color, icon=icon, order=i, builtin=True)
        for i, (cid, name, color, icon) in enumerate(BUILTIN_CHANNELS)
    ]
    buses = [
        MasterBus(id=DEFAULT_OUTPUT_BUS, name="Personal Mix", kind=BusKind.OUTPUT, order=0),
        MasterBus(id=STREAM_BUS, name="Stream Mix", kind=BusKind.STREAM, order=1),
    ]
    mics = [
        MicChain(id="mic", name="Mic", order=0, builtin=True),
        MicChain(id="stream_mic", name="Stream Mic", color="#C77DFF", order=1, builtin=True),
    ]
    rules = [
        RoutingRule(match_key=key, pattern=pattern, channel_id=channel, is_regex=is_regex)
        for key, pattern, channel, is_regex in SUGGESTED_RULES
    ]
    config = SonarConfig(channels=channels, buses=buses, mic_chains=mics, rules=rules)
    config.ensure_sends()
    return config


#: Türkçe (ve yaygın Latin) harflerin ASCII karşılıkları. Bunlar olmadan "Hoparlör"
#: `hoparl_r` oluyordu: kimlik node adına giriyor ve kullanıcıya da gösteriliyor.
_TRANSLITERATE = str.maketrans(
    {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i",
        "û": "u", "é": "e", "è": "e", "á": "a", "ñ": "n", "ä": "a", "å": "a", "ø": "o",
        "æ": "ae", "ß": "ss",
    }
)  # fmt: skip


def slugify(name: str) -> str:
    """Kullanıcının verdiği adı güvenli bir kimliğe çevirir.

    Kimlik PipeWire node adına giriyor (`sonar_<id>`), yani ASCII kalmalı. Türkçe
    harfler **düşürülmüyor, çevriliyor**: "Hoparlör" → `hoparlor`.
    """
    folded = name.strip().casefold().translate(_TRANSLITERATE)
    slug = _SLUG_RE.sub("_", folded.replace(" ", "_")).strip("_")
    return slug or "kanal"
