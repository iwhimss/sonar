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
    "CHAIN_ORDER",
    "DEFAULT_OUTPUT_BUS",
    "DYNAMIC_STAGES",
    "MIC_ONLY_STAGES",
    "PLAYBACK_ONLY_STAGES",
    "SCHEMA_VERSION",
    "STREAM_BUS",
    "BusKind",
    "BusSend",
    "Channel",
    "ChatMixConfig",
    "DuckingConfig",
    "EffectSlot",
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
    "StreamDirection",
    "default_band_frequencies",
    "default_band_q",
    "default_config",
    "default_profile",
]

SCHEMA_VERSION = 6

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
    EXPANDER = "expander"
    EQ = "eq"
    COMP = "comp"
    DEESSER = "deesser"
    MAXIMIZER = "maximizer"
    BASS_ENHANCER = "bass"
    EXCITER = "exciter"
    LOUDNESS = "loudness"
    STEREO_TOOLS = "stereo"
    DELAY = "delay"
    REVERB = "reverb"
    SPATIAL = "spatial"
    BOOST = "boost"
    LIMITER = "lim"


#: Efekt eklerken kullanılan **varsayılan** sıralama ve arayüzdeki listenin düzeni.
#:
#: Şema 7'den beri gerçek sıra kullanıcınındır (`Profile.effects`); bu demet yalnızca
#: "efekt ekle" listesinin sırasını ve şema 6 → 7 göçünün sırasını belirliyor.
#:
#: Spatial ve Boost, limiter'ın **öncesinde**: ikisi de sinyali büyütebiliyor ve
#: limiter son savunma hattı olarak kalmalı. Spatial'ın boost'tan önce olması da
#: bilinçli — HRTF'in kendi kazanç kaybını boost telafi edebilsin.
CHAIN_ORDER: tuple[FilterStage, ...] = (
    FilterStage.DEEPFILTER,
    FilterStage.GATE,
    FilterStage.EXPANDER,
    FilterStage.EQ,
    FilterStage.COMP,
    FilterStage.DEESSER,
    FilterStage.BASS_ENHANCER,
    FilterStage.EXCITER,
    FilterStage.STEREO_TOOLS,
    FilterStage.DELAY,
    FilterStage.REVERB,
    FilterStage.SPATIAL,
    FilterStage.LOUDNESS,
    FilterStage.BOOST,
    FilterStage.MAXIMIZER,
    FilterStage.LIMITER,
)

#: EQ dışındaki, `FilterState` ile temsil edilen aşamalar.
DYNAMIC_STAGES: tuple[FilterStage, ...] = (
    FilterStage.DEEPFILTER,
    FilterStage.GATE,
    FilterStage.COMP,
    FilterStage.SPATIAL,
    FilterStage.BOOST,
    FilterStage.LIMITER,
)

#: Yalnızca oynatma zincirlerinde anlamlı aşamalar. Mikrofonda kulaklık simülasyonu
#: yapmanın karşılığı yok.
PLAYBACK_ONLY_STAGES: tuple[FilterStage, ...] = (FilterStage.SPATIAL,)

#: Yalnızca mikrofon zincirlerinde anlamlı aşamalar. DeepFilterNet bir **gürültü**
#: engelleyici; oynatma zincirinde işi yok ve pahalı (ölçüldü: mikrofon kullanımdayken
#: +%43 CPU).
MIC_ONLY_STAGES: tuple[FilterStage, ...] = (FilterStage.DEEPFILTER,)


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


class StreamDirection(StrEnum):
    """Bir akışın yönü.

    `OUT` uygulamanın **çaldığı** ses (kanal sink'ine gider), `IN` uygulamanın
    **dinlediği** mikrofon (Sonar giriş zincirinden beslenir). Discord ikisine de
    sahiptir; kullanıcı ikisini ayrı ayrı yönlendirebilmeli (Faz 21).
    """

    OUT = "out"
    IN = "in"


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
class DuckingConfig:
    """Smart Volume: **bu profilin kanalı** konuşurken diğerlerini kıs.

    SteelSeries GG'deki "Smart Volume". Bir DSP aşaması değil, daemon tarafında bir
    zarf takipçisi — nedeni `engine.ducking` başlığında.

    Profilin içinde duruyor (şema 4): tetikleyici, profili taşıyan kanalın kendisi.
    Böylece "Chat'in oyun profilinde açık, müzik profilinde kapalı" gibi bir ayrım
    mümkün oluyor. Önce ayarlarda tek bir global blok olarak duruyordu ve hangi kanalın
    tetikleyici olduğu ayrıca seçiliyordu.
    """

    enabled: bool = False
    #: Kısılacak kanallar. **Boş = bu kanal dışındaki her çıkış kanalı.**
    target_channels: list[str] = field(default_factory=list)
    #: Tam indirim miktarı (negatif dB).
    reduction_db: float = -12.0
    #: Kanalın "konuşuyor" sayılması için gereken tepe seviye.
    threshold_db: float = -40.0
    attack_ms: float = 80.0
    #: Sustuktan sonra inik kalınan süre. Olmazsa cümle aralarında ses pompalıyor.
    hold_ms: float = 400.0
    release_ms: float = 800.0


@dataclass(slots=True)
class EffectSlot:
    """Zincire yerleştirilmiş **bir** efekt.

    Şema 7'ye kadar zincir sabitti: `CHAIN_ORDER`'daki yedi aşama her profilde vardı ve
    "kapalı" olanlar bypass'ta duruyordu. Kullanıcı EasyEffects'teki gibi *"diğer
    ayarları kendim ekleyeyim, ekledikçe görünsün"* isteyince zincir bir **liste** oldu.

    `slot` grafın içindeki node adı ve profil içinde benzersiz: aynı efektten iki tane
    eklenebiliyor (`comp1`, `comp2`). Canlı parametre anahtarı `"<slot>:<port>"`, yani
    şema 6'daki `"eq:g_3"` deseninin aynısı — yalnızca ad artık slot kimliği.
    """

    kind: FilterStage = FilterStage.EQ
    slot: str = "eq"
    enabled: bool = True
    #: Sonar'ın kendi parametre adları (`threshold_db`, `attack_ms`, …), port sembolleri
    #: değil. Eşleme `core.dsp.params` içinde.
    params: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Profile:
    """Bir kanalın tüm DSP durumu. Kanal başına birden fazla profil kaydedilebilir."""

    name: str = "Default"
    eq: EqState = field(default_factory=EqState)
    #: Zincirdeki efektler, **sinyal sırasıyla**. Kullanıcı sürükleyerek diziyor.
    effects: list[EffectSlot] = field(default_factory=list)
    #: Smart Volume — bu kanal konuşurken diğerlerini kıs. Şema 4'te ayarlardan buraya
    #: taşındı: kullanıcı her profilde ayrı olmasını istedi.
    ducking: DuckingConfig = field(default_factory=DuckingConfig)

    def slot(self, slot_id: str) -> EffectSlot | None:
        return next((e for e in self.effects if e.slot == slot_id), None)

    def state(self, slot_id: str) -> FilterState:
        """Slotun `FilterState` görünümü — `core.dsp.params` bu biçimi bekliyor.

        EQ'nun aç/kapa durumu `profile.eq.enabled`'da duruyor (eğri, bandlar ve içe/dışa
        aktarma hep oradan okuyor); slotun kendi bayrağı EQ için yok sayılıyor.
        """
        effect = self.slot(slot_id)
        if effect is None:
            return FilterState(enabled=False, params={})
        enabled = self.eq.enabled if effect.kind is FilterStage.EQ else effect.enabled
        defaults = DEFAULT_FILTER_PARAMS.get(effect.kind, {})
        return FilterState(enabled=enabled, params={**defaults, **effect.params})

    def next_slot_id(self, kind: FilterStage) -> str:
        """Bu profilde benzersiz bir node adı üretir: `comp`, `comp2`, `comp3` …"""
        used = {e.slot for e in self.effects}
        if kind.value not in used:
            return kind.value
        index = 2
        while f"{kind.value}{index}" in used:
            index += 1
        return f"{kind.value}{index}"


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
        """Kanalın çıkış gönderisi; mikserdeki kulaklık fader'ı."""
        return self.send(DEFAULT_OUTPUT_BUS)

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
    #: Mikrofonu yayın miksine de gönder.
    #:
    #: Test turu 4'te varsayılan **açık** oldu. Gerekçe ölçüldü: resmî OBS kurulumu
    #: tek kaynak (yayın miksinin monitörü) ve o kaynakta mikrofon yoksa yayında ses
    #: duyulmuyor. Kapalıyken mikrofonun yayın fader'ı da hiçbir şey yapmıyor gibi
    #: görünüyordu — kullanıcının üçüncü turda bildirdiği hata buydu.
    #:
    #: OBS'e ayrı bir mikrofon kaynağı ekleyenler bunu kapatmalı; açık bırakırlarsa
    #: ses iki kez gider. `api.stream_setup()` bu durumu tespit edip uyarıyor.
    send_to_stream_bus: bool = True

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
    #: Kuralın hangi yöndeki akışa baktığı. `out` uygulamanın çaldığı ses, `in` onun
    #: dinlediği mikrofon. Aynı uygulamanın ikisi için ayrı kuralı olabilir — Discord
    #: örneği tam olarak bu. Eski kurallar `out` olarak okunur (alan varsayılanı).
    direction: StreamDirection = StreamDirection.OUT

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
    #: Hiçbir kurala uymayan **mikrofon** akışının bağlanacağı giriş zinciri.
    default_mic_chain: str = "mic"
    default_band_count: int = 10
    start_minimized: bool = False
    #: ChatMix'i ne sürüyor. `auto` = kulaklık tekeri okunabiliyorsa o, yoksa slider.
    #: Teker yönetirken slider salt okunur olur; iki kaynağın birbirini ezmesi
    #: kullanıcının istemediği şeydi.
    chatmix_source: str = "auto"
    #: Donanım tekerinin yönünü ters çevir.
    #:
    #: Rapor iki kazanç veriyor (`headset.decode_chatmix`) ama hangi ucun Game hangisinin
    #: Chat olduğu kayıttan çıkmıyor — kullanıcının tekeri hangi yöne çevirdiğini bilmenin
    #: yolu yok. Ters geliyorsa tek anahtarla düzeliyor; tahmin edip yanlış yapmaktansa
    #: kullanıcının bir kez söylemesi daha iyi.
    chatmix_invert: bool = False
    #: Arayüz dili. `sonar.core.i18n.LANGUAGES` içindeki kodlardan biri.
    #:
    #: Yalnızca **gösterilen** metinleri etkiler. Kanal ve bus adları (dolayısıyla
    #: PipeWire cihaz açıklamaları) kullanıcı verisidir ve dile göre değişmez —
    #: değişseydi OBS'te seçili aygıt her dil değişiminde kaybolurdu.
    language: str = "tr"
    #: Sanal kanallar kuruldu mu.
    #:
    #: `False` iken daemon D-Bus'ta ayakta durur ama PipeWire'a **hiç** dokunmaz:
    #: graf kurulmaz, varsayılan çıkış devralınmaz, ChatMix tekeri okunmaz. Kurulum
    #: kullanıcının karşılama ekranındaki düğmesine basmasıyla olur (`api.provision`).
    #: Kaldırıcı bunu `False`'a döndürerek sistemi Sonar hiç kurulmamış hâle getirir.
    provisioned: bool = False


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
        """Fiziksel cihaza çıkan bus'lar.

        Bir dönem birden fazla olabiliyordu (kanal başına ayrı cihaz); kullanıcı
        karışıklık ürettiği için geri alındı ve liste artık tek elemanlı. `MasterBus.kind`
        yine de duruyor: yayın bus'ını çıkıştan ayıran alan o.
        """
        return [b for b in self.ordered_buses() if not b.is_stream]

    def stream_bus(self) -> MasterBus | None:
        return next((b for b in self.buses if b.is_stream), None)

    def default_output_bus(self) -> MasterBus | None:
        """Kanalların düşeceği çıkış. `personal` yoksa ilk çıkış bus'ı."""
        return self.bus(DEFAULT_OUTPUT_BUS) or next(iter(self.output_buses()), None)

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
    #: Spatial Audio (crossfeed): kulaklar arası sızıntı. `immersion` sızıntının
    #: miktarını ve yumuşaklığını, `distance` gecikmesini belirliyor — ikisi de 0–100.
    FilterStage.SPATIAL: {
        "immersion": 50.0,
        "distance": 40.0,
    },
    #: Volume Boost: limiter'dan önce uygulanan düz kazanç.
    FilterStage.BOOST: {"gain_db": 6.0},
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
    # --- EasyEffects karşılıkları (test turu 6) -----------------------------
    #: Genişletici: kompresörün tersi. Eşiğin **altındaki** sessizliği daha da kısar.
    FilterStage.EXPANDER: {
        "threshold_db": -30.0,
        "knee_db": -6.0,
        "attack_ms": 20.0,
        "release_ms": 100.0,
        "makeup_db": 0.0,
    },
    #: De-esser: "s" seslerinin tizdeki sertliğini alır.
    FilterStage.DEESSER: {
        "threshold_db": -18.0,
        "ratio": 3.0,
        "split_hz": 6000.0,
        "makeup_db": 0.0,
    },
    #: Bas zenginleştirici: alt uca harmonik ekler, gerçek bas eklemeden "dolgun" yapar.
    FilterStage.BASS_ENHANCER: {
        "amount": 1.0,
        "harmonics": 8.5,
        "scope_hz": 100.0,
    },
    #: Exciter: aynı iş, tiz uçta. Kayıtta kaybolan parlaklığı geri verir.
    FilterStage.EXCITER: {
        "amount": 1.0,
        "harmonics": 8.5,
        "scope_hz": 7500.0,
    },
    #: Stereo araçları: sahne genişliği, orta/yan dengesi.
    FilterStage.STEREO_TOOLS: {
        "width": 100.0,
        "mid_db": 0.0,
        "balance": 0.0,
        "base": 0.0,
    },
    #: Gecikme: iki kanala da aynı gecikme. Kuru/ıslak karışımı ne kadar duyulacağını
    #: belirliyor; %100 tamamen gecikmiş sinyal demek.
    FilterStage.DELAY: {
        "time_ms": 20.0,
        "drywet": 50.0,
    },
    #: Reverb: oda simülasyonu.
    FilterStage.REVERB: {
        "decay_s": 1.5,
        "room_size": 2.0,
        "wet": 0.25,
        "predelay_ms": 0.0,
        "damp_hz": 5000.0,
    },
    #: Loudness: düşük seviyede dinlerken kaybolan bas ve tizi eşit-gürlük eğrisine göre
    #: geri verir. `volume_db` **dinlediğiniz** seviyedir, bir kazanç değil.
    FilterStage.LOUDNESS: {
        "volume_db": 0.0,
    },
    #: Maximizer: limiter'ın "yükselt ve tavana yasla" hâli. Tavan 0 dB ve kazanç 0 dB
    #: iken şeffaf — eklentinin bypass portu yok.
    FilterStage.MAXIMIZER: {
        "ceiling_db": -1.0,
        "gain_db": 0.0,
        "release_ms": 30.0,
    },
}


def default_profile(name: str = "Default", band_count: int = 10) -> Profile:
    """Düz EQ'lu, **başka hiçbir efekti olmayan** profil.

    Şema 6'ya kadar yedi aşamanın hepsi (kapalı hâlde) profilin içindeydi ve arayüzde
    hepsi görünüyordu. Kullanıcının isteği: *"Profil ayarlarına girince sadece ekolayzer
    ayarı gözüksün. Diğer ayarları tıpkı EasyEffects programındaki gibi kullanıcı kendisi
    eklesin."*
    """
    freqs = default_band_frequencies(band_count)
    q = default_band_q(band_count)
    bands = [EqBand(freq=f, gain_db=0.0, q=q, band_type=EqBandType.PEAK) for f in freqs]
    return Profile(
        name=name,
        eq=EqState(enabled=False, band_count=band_count, preamp_db=0.0, bands=bands),
        effects=[EffectSlot(kind=FilterStage.EQ, slot=FilterStage.EQ.value, enabled=False)],
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
