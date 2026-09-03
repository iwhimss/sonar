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
    assert plan.stages == tuple(
        s for s in CHAIN_ORDER if s not in (S.SPATIAL, S.BOOST)
    ), "istenmeyen aşama zincire girmemeli"


def test_boost_is_always_in_the_chain(all_installed):
    """Boost bypass'ta bedava (`Mult = 1`), bu yüzden her zaman kurulu."""
    assert S.BOOST in plan_chain().stages


def test_spatial_is_always_in_a_stereo_chain(all_installed):
    """Crossfeed PipeWire'ın kendi bloklarıyla kuruluyor: bypass bedava, kurulum yok.

    HRTF sürümü yapısaldı çünkü bir konvolveri bypass etmek onu ucuzlatmıyordu
    (ölçüldü: boşta CPU %0.0 → %14.4). Crossfeed'de böyle bir bedel yok.
    """
    assert plan_chain().stages == CHAIN_ORDER


def test_spatial_is_dropped_from_a_mono_chain(all_installed):
    """Kulaklık simülasyonunun mikrofon zincirinde karşılığı yok."""
    plan = plan_chain(channels=1)
    assert S.SPATIAL not in plan.stages
    assert S.SPATIAL in plan.skipped
    assert S.BOOST in plan.stages


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
    graph = build_chain(plan_chain((S.DEEPFILTER, S.GATE, S.EQ, S.COMP, S.LIMITER)))
    assert [node["name"] for node in graph["nodes"]] == ["df", "gate", "eq", "comp", "lim"]
    assert graph["inputs"] == ["df:Audio In L", "df:Audio In R"]
    assert graph["outputs"] == ["lim:out_l", "lim:out_r"]
    # 5 aşama, 4 geçiş, kanal başına bir link
    assert len(graph["links"]) == 8


def test_multi_node_stages_expose_a_single_pair_of_ports(all_installed):
    """Spatial sekiz node, Boost iki node; zincir bunu bilmek zorunda değil."""
    graph = build_chain(plan_chain())
    names = [node["name"] for node in graph["nodes"]]
    assert names == [
        "df", "gate", "eq", "comp",
        "spatial_copy_l", "spatial_copy_r", "spatial_delay_l", "spatial_delay_r",
        "spatial_lp_l", "spatial_lp_r", "spatial_mix_l", "spatial_mix_r",
        "boost_l", "boost_r", "lim",
    ]  # fmt: skip
    assert graph["outputs"] == ["lim:out_l", "lim:out_r"]
    links = {(link["output"], link["input"]) for link in graph["links"]}
    assert ("comp:out_l", "spatial_copy_l:In") in links
    assert ("spatial_mix_l:Out", "boost_l:In") in links
    assert ("boost_l:Out", "lim:in_l") in links
    # Sol kanalın sızıntısı **sağ** kulağa gidiyor.
    assert ("spatial_lp_l:Out", "spatial_mix_r:In 2") in links
    assert ("spatial_lp_r:Out", "spatial_mix_l:In 2") in links


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


def test_empty_chain_is_an_error():
    """Aşamasız bir filter-chain anlamsız; çağıran taraf loopback kurmalı."""
    with pytest.raises(ValueError, match="loopback"):
        build_chain(plan_chain((), require_installed=False))


def test_boost_survives_even_when_no_plugin_is_installed(monkeypatch):
    """Volume Boost PipeWire'ın kendi `linear` eklentisi; kurulum gerektirmiyor.

    Yani hiçbir LV2/LADSPA eklentisi olmayan bir sistemde bile zincir kurulabiliyor
    ve ses düz geçiyor.
    """
    monkeypatch.setattr(registry, "is_available", lambda _key: False)
    plan = plan_chain()
    assert plan.stages == (S.SPATIAL, S.BOOST), "ikisi de PipeWire'ın kendi blokları"
    graph = build_chain(plan)
    assert graph["inputs"] == ["spatial_copy_l:In", "spatial_copy_r:In"]


# --------------------------------------------------------------------------- başlangıç değerleri


def test_every_stage_starts_bypassed(all_installed):
    """Conf nötr doğar; gerçek profil canlı yazımla gelir. Bu kuralın testi."""
    graph = build_chain(plan_chain())
    controls = {node["name"]: node.get("control", {}) for node in graph["nodes"]}
    # Boost bypass'ı: çarpan 1. Spatial bypass'ı: sızıntı kazancı 0.
    assert controls["boost_l"]["Mult"] == 1.0
    assert controls["spatial_mix_l"] == {"Gain 1": 1.0, "Gain 2": 0.0}
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
