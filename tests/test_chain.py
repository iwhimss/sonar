from __future__ import annotations

import pytest

from sonar.core.dsp import registry
from sonar.core.dsp.chain import build_chain, plan_chain
from sonar.core.model import CHAIN_ORDER, FilterStage

S = FilterStage


@pytest.fixture
def all_installed(monkeypatch):
    """Eklenti varlığından bağımsız test — makinede LSP kurulu olmayabilir."""
    monkeypatch.setattr(registry, "is_available", lambda _key: True)


# --------------------------------------------------------------------------- planlama


def test_plan_keeps_chain_order_regardless_of_input_order(all_installed):
    plan = plan_chain((S.LIMITER, S.EQ, S.DEEPFILTER, S.COMP, S.GATE))
    assert plan.stages == CHAIN_ORDER


def test_plan_skips_missing_plugins(monkeypatch):
    monkeypatch.setattr(registry, "is_available", lambda key: not key.startswith("deepfilter"))
    plan = plan_chain()
    assert S.DEEPFILTER not in plan.stages
    assert plan.skipped == (S.DEEPFILTER,)
    assert plan.stages[0] is S.GATE


def test_plan_ignores_availability_when_asked():
    plan = plan_chain(require_installed=False)
    assert plan.stages == CHAIN_ORDER


@pytest.mark.parametrize(("bands", "capacity"), [(5, 8), (10, 16), (16, 16), (32, 32)])
def test_plan_picks_eq_capacity(bands, capacity, all_installed):
    assert plan_chain(band_count=bands).eq_capacity == capacity


def test_plan_rejects_odd_channel_counts():
    with pytest.raises(ValueError, match="1 veya 2"):
        plan_chain(channels=3, require_installed=False)


# --------------------------------------------------------------------------- graf kurulumu


def test_graph_wires_stages_in_order(all_installed):
    graph = build_chain(plan_chain())
    assert [node["name"] for node in graph["nodes"]] == [s.value for s in CHAIN_ORDER]
    assert graph["inputs"] == ["df:Audio In L", "df:Audio In R"]
    assert graph["outputs"] == ["lim:out_l", "lim:out_r"]
    # 5 aşama, 4 geçiş, kanal başına bir link
    assert len(graph["links"]) == 8


def test_missing_stage_is_relinked_not_left_dangling(monkeypatch):
    monkeypatch.setattr(registry, "is_available", lambda key: "para_eq" not in key)
    graph = build_chain(plan_chain())
    pairs = {(link["output"].split(":")[0], link["input"].split(":")[0]) for link in graph["links"]}
    assert ("gate", "comp") in pairs, "EQ düşünce gate doğrudan comp'a bağlanmalı"
    assert not any("eq" in name for name in {p for pair in pairs for p in pair})


def test_single_stage_chain_has_no_links(all_installed):
    graph = build_chain(plan_chain((S.EQ,)))
    assert "links" not in graph
    assert graph["inputs"] == ["eq:in_l", "eq:in_r"]
    assert graph["outputs"] == ["eq:out_l", "eq:out_r"]


def test_mono_chain_uses_mono_ports(all_installed):
    graph = build_chain(plan_chain((S.GATE, S.EQ), channels=1))
    assert graph["inputs"] == ["gate:in"]
    assert graph["outputs"] == ["eq:out"]
    assert len(graph["links"]) == 1


def test_empty_chain_is_an_error(monkeypatch):
    monkeypatch.setattr(registry, "is_available", lambda _key: False)
    with pytest.raises(ValueError, match="loopback"):
        build_chain(plan_chain())


# --------------------------------------------------------------------------- başlangıç değerleri


def test_every_stage_starts_bypassed(all_installed):
    """Conf nötr doğar; gerçek profil canlı yazımla gelir. Bu kuralın testi."""
    graph = build_chain(plan_chain())
    controls = {node["name"]: node["control"] for node in graph["nodes"]}
    assert controls["gate"]["enabled"] == 0.0
    assert controls["eq"]["enabled"] == 0.0
    assert controls["comp"]["enabled"] == 0.0
    assert controls["lim"]["enabled"] == 0.0
    # DeepFilterNet'te `enabled` portu yok; sıfır azaltma bypass demek.
    assert controls["df"]["Attenuation Limit (dB)"] == 0.0


def test_eq_analyzers_start_disabled(all_installed):
    """LSP'nin FFT'leri bypass'ta bile CPU yakar; kapalı doğmalılar."""
    graph = build_chain(plan_chain())
    control = next(n["control"] for n in graph["nodes"] if n["name"] == "eq")
    analyzers = registry.eq_analyzer_ports(registry.eq_plugin_for(10))
    assert analyzers, "analizör portları kataloğdan kaybolmuş"
    assert all(control[port] == 0.0 for port in analyzers)


def test_ladspa_node_carries_a_label_and_lv2_does_not(all_installed):
    graph = build_chain(plan_chain())
    nodes = {node["name"]: node for node in graph["nodes"]}
    assert nodes["df"]["type"] == "ladspa"
    assert nodes["df"]["label"] == "deep_filter_stereo"
    assert nodes["eq"]["type"] == "lv2"
    assert "label" not in nodes["eq"]


def test_ladspa_plugin_is_an_absolute_path_when_installed():
    spec = registry.plugin("deepfilter_stereo")
    if not registry.is_available("deepfilter_stereo"):
        pytest.skip("deepfilter-ladspa kurulu değil")
    assert registry.plugin_reference(spec).startswith("/")
