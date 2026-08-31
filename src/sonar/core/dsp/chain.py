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
from itertools import pairwise

from sonar.core.dsp import registry
from sonar.core.dsp.params import eq_bypass_ports, stage_bypass_ports
from sonar.core.model import CHAIN_ORDER, FilterStage

__all__ = ["ChainPlan", "build_chain", "plan_chain"]


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

    nodes = [_node(stage, plan.plugins[stage]) for stage in plan.stages]
    links = []
    for upstream, downstream in pairwise(plan.stages):
        out_spec, in_spec = plan.plugins[upstream], plan.plugins[downstream]
        for index in range(plan.channels):
            links.append(
                {
                    "output": f"{upstream.value}:{out_spec.audio_out[index]}",
                    "input": f"{downstream.value}:{in_spec.audio_in[index]}",
                }
            )

    first, last = plan.stages[0], plan.stages[-1]
    first_spec, last_spec = plan.plugins[first], plan.plugins[last]

    graph: dict = {
        "nodes": nodes,
        "inputs": [f"{first.value}:{p}" for p in first_spec.audio_in[: plan.channels]],
        "outputs": [f"{last.value}:{p}" for p in last_spec.audio_out[: plan.channels]],
    }
    if links:
        graph["links"] = links
    return graph


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
