"""DSP zincirinden PipeWire `filter.graph` sözlüğü üretir.

Zincirin topolojisi **sabittir** — bir efekti açıp kapatmak grafı değiştirmez, yalnızca o
aşamanın bypass portuna yazar (bkz. `params.stage_params`). Böylece profil değiştirmek veya
bir filtreyi kapatmak `graph.conf`'u değiştirmez, dolayısıyla süreci yeniden başlatmaz.

Tek istisna: eklenti sistemde **kurulu değilse** o aşama zincirden tamamen çıkarılır ve
linkler yeniden bağlanır. Bu yapısal bir farktır ve conf'a yansır.

Node adları `FilterStage` değerleriyle birebir aynıdır (`df`, `gate`, `eq`, `comp`, `lim`),
çünkü canlı parametre anahtarları `"<node>:<port>"` biçimindedir: `"eq:g_3"`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sonar.core.dsp import registry
from sonar.core.dsp.params import eq_bypass_ports, stage_bypass_ports
from sonar.core.model import CHAIN_ORDER, FilterStage

__all__ = ["ChainPlan", "StageBlock", "build_chain", "plan_chain", "stage_block"]


@dataclass(frozen=True, slots=True)
class StageBlock:
    """Bir aşamanın graf karşılığı: bir ya da **birden çok** node.

    Aşamaların çoğu tek bir eklenti node'u (`gate`, `eq`, …) ve bu sınıf onların da
    kapsayıcısı. Ama Spatial Audio altı node'dan oluşan bir alt graf, Volume Boost ise
    kanal başına bir node — PipeWire'ın `linear` ve `spatializer` eklentileri **mono**.

    `audio_in` / `audio_out` dışarıya açılan portlar, kanal sırasıyla ve
    `"node:port"` biçiminde tam nitelikli.
    """

    nodes: tuple[dict, ...]
    audio_in: tuple[str, ...]
    audio_out: tuple[str, ...]
    links: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class ChainPlan:
    """Bir zincirin çözülmüş hâli: hangi aşamalar var, her biri hangi eklentiyle."""

    stages: tuple[FilterStage, ...]
    plugins: dict[FilterStage, registry.PluginSpec]
    channels: int
    skipped: tuple[FilterStage, ...]

    @property
    def eq_capacity(self) -> int:
        """EQ eklentisinin band kapasitesi; EQ yoksa 0."""
        spec = self.plugins.get(FilterStage.EQ)
        return spec.band_capacity if spec else 0


def plan_chain(
    stages: tuple[FilterStage, ...] = CHAIN_ORDER,
    *,
    channels: int = 2,
    band_count: int = 10,
    require_installed: bool = True,
    spatial: bool = False,
) -> ChainPlan:
    """İstenen aşamalardan kurulabilir olanları seçer.

    `require_installed` yalnızca testlerde kapatılır; çalışma zamanında eksik eklenti
    zincirden düşmelidir, aksi hâlde `pipewire -c` grafı hiç kuramaz.
    """
    if channels not in (1, 2):
        raise ValueError(f"kanal sayısı 1 veya 2 olmalı, {channels} verildi")

    kept: list[FilterStage] = []
    skipped: list[FilterStage] = []
    plugins: dict[FilterStage, registry.PluginSpec] = {}

    for stage in CHAIN_ORDER:
        if stage not in stages:
            continue
        # Boost ve Spatial bir LV2/LADSPA eklentisine dayanmıyor; katalogda yoklar.
        if stage is FilterStage.BOOST:
            kept.append(stage)
            continue
        if stage is FilterStage.SPATIAL:
            # Yapısal: yalnızca hedef açıkça istediğinde kuruluyor. Konvolver bypass'ta
            # da CPU yiyor (ölçüldü: boşta %0.0 → %14.4), bu yüzden kapalıyken grafta
            # hiç bulunmuyor. Mono zincirde (mikrofon) anlamsız; SOFA yoksa kurulamaz.
            if (
                not spatial
                or channels != 2
                or (require_installed and not registry.sofa_available())
            ):
                skipped.append(stage)
            else:
                kept.append(stage)
            continue
        key = _plugin_key(stage, channels, band_count)
        if require_installed and not registry.is_available(key):
            skipped.append(stage)
            continue
        plugins[stage] = registry.plugin(key)
        kept.append(stage)

    return ChainPlan(tuple(kept), plugins, channels, tuple(skipped))


def build_chain(plan: ChainPlan) -> dict:
    """`ChainPlan`'ı PipeWire `filter.graph` sözlüğüne çevirir.

    Boş bir zincir (hiçbir eklenti kurulu değil) için `None` yerine, aşamaları olmayan bir
    graf döndürmek anlamsız olurdu — çağıran taraf `plan.stages` boşsa filter-chain yerine
    düz bir loopback kurmalıdır. Bu durumda `ValueError` atılır.
    """
    if not plan.stages:
        raise ValueError("zincirde hiç aşama yok; filter-chain yerine loopback kullanın")

    blocks = [stage_block(stage, plan, plan.channels) for stage in plan.stages]

    nodes: list[dict] = []
    links: list[dict] = []
    for block in blocks:
        nodes.extend(block.nodes)
    # Link sırası: her bloğun kendi iç linkleri, sonra bir sonrakine geçiş. Tek node'lu
    # aşamalarda iç link yok, yani bu sıra eski `pairwise` düzeniyle birebir aynı —
    # mevcut altın conf byte olarak değişmiyor.
    for index, block in enumerate(blocks):
        links.extend(block.links)
        if index + 1 < len(blocks):
            nxt = blocks[index + 1]
            for channel in range(plan.channels):
                links.append({"output": block.audio_out[channel], "input": nxt.audio_in[channel]})

    graph: dict = {
        "nodes": nodes,
        "inputs": list(blocks[0].audio_in),
        "outputs": list(blocks[-1].audio_out),
    }
    if links:
        graph["links"] = links
    return graph


def stage_block(stage: FilterStage, plan: ChainPlan, channels: int) -> StageBlock:
    """Bir aşamanın node'ları, iç linkleri ve dışarı açılan portları."""
    if stage is FilterStage.SPATIAL:
        return _spatial_block(channels)
    if stage is FilterStage.BOOST:
        return _boost_block(channels)
    spec = plan.plugins[stage]
    return StageBlock(
        nodes=(_node(stage, spec),),
        audio_in=tuple(f"{stage.value}:{p}" for p in spec.audio_in[:channels]),
        audio_out=tuple(f"{stage.value}:{p}" for p in spec.audio_out[:channels]),
    )


# --------------------------------------------------------------------------- Volume Boost


def _boost_block(channels: int) -> StageBlock:
    """Kanal başına bir PipeWire `linear` node'u.

    `linear` mono: `Out = In * Mult + Add`. Bypass `Mult = 1.0`, yani conf bypass'ta
    doğuyor ve boost'u açıp kapatmak grafı değiştirmiyor.
    """
    names = _channel_names(FilterStage.BOOST, channels)
    nodes = tuple(
        {
            "type": registry.PluginKind.BUILTIN.value,
            "name": name,
            "label": "linear",
            "control": {"Mult": 1.0, "Add": 0.0},
        }
        for name in names
    )
    return StageBlock(
        nodes=nodes,
        audio_in=tuple(f"{name}:In" for name in names),
        audio_out=tuple(f"{name}:Out" for name in names),
    )


# --------------------------------------------------------------------------- Spatial Audio


def _spatial_block(channels: int) -> StageBlock:
    """HRTF ile iki sanal hoparlör.

    Alt graf (stereo):

    ```
    spatial_l ─┬─ "Out L" ─► spatial_mix_l:"In 1"
               └─ "Out R" ─► spatial_mix_r:"In 1"
    spatial_r ─┬─ "Out L" ─► spatial_mix_l:"In 2"
               └─ "Out R" ─► spatial_mix_r:"In 2"
    ```

    `spatializer` mono girip stereo çıkıyor, yani iki sanal hoparlörün binaural
    çıktısını **toplamak** gerekiyor; mikserler bunun için.

    ## Neden bu blok yapısal (conf'a girip çıkıyor)

    İlk sürümde blokta ayrıca bir kuru yol ve karışım kazançları vardı; aşama
    "bypass"ta bile konvolverler çalışıyordu. Ölçüldü: altı zincirde **boştaki CPU
    %0.0 → %14.4**. Bir konvolveri bypass etmek onu ucuzlatmıyor.

    Bu yüzden Spatial Audio, projedeki tek "aşamayı aç/kapa = grafı yeniden kur"
    istisnası. Açma/kapama profilde değil, hedefin kendi ayarında (`Channel.spatial`,
    `MasterBus.spatial`) — böylece profil değiştirmek asla grafı yeniden kurmuyor,
    Faz 2'nin değişmez kuralı bozulmuyor.
    """
    if channels != 2:  # pragma: no cover - plan_chain buraya izin vermez
        raise ValueError("Spatial Audio yalnızca stereo zincirde kurulabilir")

    config = {"filename": registry.hrtf_file()}
    nodes = (
        _sofa("spatial_l", config),
        _sofa("spatial_r", config),
        _mixer("spatial_mix_l"),
        _mixer("spatial_mix_r"),
    )
    links = (
        {"output": "spatial_l:Out L", "input": "spatial_mix_l:In 1"},
        {"output": "spatial_r:Out L", "input": "spatial_mix_l:In 2"},
        {"output": "spatial_l:Out R", "input": "spatial_mix_r:In 1"},
        {"output": "spatial_r:Out R", "input": "spatial_mix_r:In 2"},
    )
    return StageBlock(
        nodes=nodes,
        audio_in=("spatial_l:In", "spatial_r:In"),
        audio_out=("spatial_mix_l:Out", "spatial_mix_r:Out"),
        links=links,
    )


def _builtin(name: str, label: str, control: dict | None = None) -> dict:
    node = {"type": registry.PluginKind.BUILTIN.value, "name": name, "label": label}
    if control:
        node["control"] = control
    return node


def _mixer(name: str) -> dict:
    """İki sanal hoparlörün aynı kulağa düşen katkılarını toplar."""
    return _builtin(name, "mixer", {"Gain 1": 1.0, "Gain 2": 1.0})


def _sofa(name: str, config: dict) -> dict:
    return {
        "type": registry.PluginKind.SOFA.value,
        "name": name,
        "label": "spatializer",
        "config": config,
        "control": {"Azimuth": 0.0, "Elevation": 0.0, "Radius": 1.0},
    }


def _channel_names(stage: FilterStage, channels: int) -> tuple[str, ...]:
    """Kanal başına node adı. Mono zincirde sonek yok, stereo'da `_l` / `_r`."""
    if channels == 1:
        return (stage.value,)
    return (f"{stage.value}_l", f"{stage.value}_r")


def _node(stage: FilterStage, spec: registry.PluginSpec) -> dict:
    node: dict = {
        "type": spec.kind.value,
        "name": stage.value,
        "plugin": registry.plugin_reference(spec),
    }
    if spec.kind is registry.PluginKind.LADSPA:
        node["label"] = spec.label
    node["control"] = _neutral_control(stage, spec)
    return node


def _neutral_control(stage: FilterStage, spec: registry.PluginSpec) -> dict[str, float]:
    """Conf'a yazılacak **başlangıç** değerleri.

    Bilinçli olarak nötr: her aşama bypass'ta doğar. Gerçek profil değerleri daemon açılışta
    canlı yazımla uygular. Aksi hâlde her EQ dokunuşu conf'u değiştirir ve süreci yeniden
    başlatırdı — Faz 2'nin en önemli kısıtı bu.
    """
    ports = eq_bypass_ports(spec) if stage is FilterStage.EQ else stage_bypass_ports(stage)
    return {port: spec.clamp(port, value) for port, value in ports.items()}


def _plugin_key(stage: FilterStage, channels: int, band_count: int) -> str:
    if stage is FilterStage.EQ:
        return registry.eq_plugin_for(band_count, channels=channels).key
    suffix = "mono" if channels == 1 else "stereo"
    return {
        FilterStage.DEEPFILTER: f"deepfilter_{suffix}",
        FilterStage.GATE: f"lsp_gate_{suffix}",
        FilterStage.COMP: f"lsp_compressor_{suffix}",
        FilterStage.LIMITER: f"lsp_limiter_{suffix}",
    }[stage]
