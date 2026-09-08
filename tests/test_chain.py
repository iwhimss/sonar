from __future__ import annotations

import pytest

from sonar.core.dsp import registry
from sonar.core.dsp.chain import build_chain, plan_chain
from sonar.core.model import CHAIN_ORDER, EffectSlot, FilterStage

S = FilterStage


def slots(*kinds: FilterStage) -> tuple[EffectSlot, ...]:
    """Aşama listesinden slot demeti. Şema 7'de zincir bir slot listesi (bkz. `EffectSlot`)."""
    return tuple(EffectSlot(kind=k, slot=k.value) for k in kinds)


def kinds(plan) -> tuple[FilterStage, ...]:
    return tuple(effect.kind for effect in plan.slots)


#: Node **türlerinin** hepsini kapsayan temsili zincir: LADSPA, LV2, çok node'lu builtin
#: alt graf (spatial) ve kanal başına builtin (boost). Katalogdaki on altı efektin hepsini
#: her teste koymak, yeni bir efekt eklendiğinde ilgisiz testleri bozardı.
CORE_CHAIN = (S.DEEPFILTER, S.GATE, S.EQ, S.COMP, S.SPATIAL, S.BOOST, S.LIMITER)


@pytest.fixture
def all_installed(monkeypatch):
    """Eklenti varlığından bağımsız test — makinede LSP kurulu olmayabilir."""
    monkeypatch.setattr(registry, "is_available", lambda _key: True)


# --------------------------------------------------------------------------- planlama


def test_plan_keeps_the_users_order(all_installed):
    """Sıra artık `CHAIN_ORDER` değil kullanıcının dizdiği sıra (şema 7).

    EasyEffects'te olduğu gibi sinyal listedeki sırayla akıyor: limitleyiciyi zincirin
    başına koymak isteyen koyabiliyor.
    """
    wanted = (S.LIMITER, S.EQ, S.DEEPFILTER, S.COMP, S.GATE)
    assert kinds(plan_chain(slots(*wanted))) == wanted


def test_boost_needs_no_plugin(all_installed):
    """Boost PipeWire'ın kendi `linear` bloğu; katalogda yok ve hep kurulabilir."""
    assert kinds(plan_chain(slots(S.BOOST))) == (S.BOOST,)


def test_spatial_is_always_in_a_stereo_chain(all_installed):
    """Crossfeed PipeWire'ın kendi bloklarıyla kuruluyor: bypass bedava, kurulum yok.

    HRTF sürümü yapısaldı çünkü bir konvolveri bypass etmek onu ucuzlatmıyordu
    (ölçüldü: boşta CPU %0.0 → %14.4). Crossfeed'de böyle bir bedel yok.
    """
    assert kinds(plan_chain(slots(*CHAIN_ORDER))) == CHAIN_ORDER


def test_spatial_is_dropped_from_a_mono_chain(all_installed):
    """Kulaklık simülasyonunun mikrofon zincirinde karşılığı yok."""
    plan = plan_chain(slots(*CHAIN_ORDER), channels=1)
    assert S.SPATIAL not in kinds(plan)
    assert S.SPATIAL in [e.kind for e in plan.skipped]
    assert S.BOOST in kinds(plan)


def test_plan_skips_missing_plugins(monkeypatch):
    monkeypatch.setattr(registry, "is_available", lambda key: not key.startswith("deepfilter"))
    plan = plan_chain(slots(*CORE_CHAIN))
    assert S.DEEPFILTER not in kinds(plan)
    assert [e.kind for e in plan.skipped] == [S.DEEPFILTER]
    assert kinds(plan)[0] is S.GATE


def test_plan_ignores_availability_when_asked():
    plan = plan_chain(slots(*CHAIN_ORDER), require_installed=False)
    assert kinds(plan) == CHAIN_ORDER


@pytest.mark.parametrize(("bands", "capacity"), [(5, 32), (10, 32), (16, 32), (32, 32)])
def test_plan_picks_eq_capacity(bands, capacity, all_installed):
    assert plan_chain(slots(S.EQ), band_count=bands).eq_capacity == capacity


def test_plan_rejects_odd_channel_counts():
    with pytest.raises(ValueError, match="1 veya 2"):
        plan_chain(slots(S.EQ), channels=3, require_installed=False)


# --------------------------------------------------------------------------- graf kurulumu


def test_graph_wires_stages_in_order(all_installed):
    graph = build_chain(plan_chain(slots(S.DEEPFILTER, S.GATE, S.EQ, S.COMP, S.LIMITER)))
    assert [node["name"] for node in graph["nodes"]] == ["df", "gate", "eq", "comp", "lim"]
    assert graph["inputs"] == ["df:Audio In L", "df:Audio In R"]
    assert graph["outputs"] == ["lim:out_l", "lim:out_r"]
    # 5 aşama, 4 geçiş, kanal başına bir link
    assert len(graph["links"]) == 8


def test_multi_node_stages_expose_a_single_pair_of_ports(all_installed):
    """Spatial sekiz node, Boost iki node; zincir bunu bilmek zorunda değil."""
    graph = build_chain(plan_chain(slots(*CORE_CHAIN)))
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
    graph = build_chain(plan_chain(slots(*CORE_CHAIN)))
    pairs = {(link["output"].split(":")[0], link["input"].split(":")[0]) for link in graph["links"]}
    assert ("gate", "comp") in pairs, "EQ düşünce gate doğrudan comp'a bağlanmalı"
    assert not any("eq" in name for name in {p for pair in pairs for p in pair})


def test_single_stage_chain_has_no_links(all_installed):
    graph = build_chain(plan_chain(slots(S.EQ)))
    assert "links" not in graph
    assert graph["inputs"] == ["eq:in_l", "eq:in_r"]
    assert graph["outputs"] == ["eq:out_l", "eq:out_r"]


def test_mono_chain_uses_mono_ports(all_installed):
    graph = build_chain(plan_chain(slots(S.GATE, S.EQ), channels=1))
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
    plan = plan_chain(slots(*CORE_CHAIN))
    assert kinds(plan) == (S.SPATIAL, S.BOOST), "ikisi de PipeWire'ın kendi blokları"
    graph = build_chain(plan)
    assert graph["inputs"] == ["spatial_copy_l:In", "spatial_copy_r:In"]


# --------------------------------------------------------------------------- başlangıç değerleri


def test_every_stage_starts_bypassed(all_installed):
    """Conf nötr doğar; gerçek profil canlı yazımla gelir. Bu kuralın testi."""
    graph = build_chain(plan_chain(slots(*CORE_CHAIN)))
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
    graph = build_chain(plan_chain(slots(*CORE_CHAIN)))
    control = next(n["control"] for n in graph["nodes"] if n["name"] == "eq")
    analyzers = registry.eq_analyzer_ports(registry.eq_plugin_for(10))
    assert analyzers, "analizör portları kataloğdan kaybolmuş"
    assert all(control[port] == 0.0 for port in analyzers)


def test_ladspa_node_carries_a_label_and_lv2_does_not(all_installed):
    graph = build_chain(plan_chain(slots(*CORE_CHAIN)))
    nodes = {node["name"]: node for node in graph["nodes"]}
    assert nodes["df"]["type"] == "ladspa"
    assert nodes["df"]["label"] == "deep_filter_stereo"
    assert nodes["eq"]["type"] == "lv2"
    assert "label" not in nodes["eq"]


def test_ladspa_plugin_is_an_absolute_path_when_installed():
    spec = registry.plugin("deepfilter_stereo")
    if not registry.is_available("deepfilter_stereo"):
        pytest.skip("deepfilternet-plus-bin kurulu değil")
    assert registry.plugin_reference(spec).startswith("/")


# --------------------------------------------------------------------------- efekt kataloğu
#
# Test turu 6'da katalog yedi aşamadan on altıya çıktı. Aşağıdaki testler her efektin
# gerçekten kurulabildiğini ve kapalıyken şeffaf olduğunu tek tek doğruluyor; altın conf
# yalnızca node **türlerini** kapsıyor.


@pytest.mark.parametrize("kind", list(CHAIN_ORDER), ids=lambda k: k.value)
def test_every_effect_kind_builds_a_graph(kind, all_installed):
    """Katalogdaki her efekt tek başına bir zincir kurabilmeli."""
    graph = build_chain(plan_chain(slots(kind)))
    assert graph["nodes"], f"{kind.value} hiç node üretmedi"
    assert graph["inputs"] and graph["outputs"]


@pytest.mark.parametrize("kind", list(CHAIN_ORDER), ids=lambda k: k.value)
def test_every_effect_starts_bypassed(kind, all_installed):
    """Conf nötr doğar: gerçek profil canlı yazımla geliyor.

    Bypass yolu efektten efekte değişiyor — LSP'de `enabled = 0`, Calf'ta `bypass = 1`,
    Calf Reverb'de `on = 0`, DeepFilterNet'te azaltma 0, ZaMaximX2'de tavan 0 dB.
    Yanlış yön, kullanıcı efekti hiç açmadan sesin değişmesi demek olurdu.
    """
    from sonar.core.dsp.params import stage_bypass_ports

    if kind in (S.SPATIAL, S.BOOST):
        pytest.skip("builtin bloklar; bypass'ları kendi testlerinde")
    graph = build_chain(plan_chain(slots(kind)))
    control = graph["nodes"][0].get("control", {})
    for port, value in stage_bypass_ports(kind).items():
        assert control[port] == value, f"{kind.value}: {port} bypass değeri yazılmamış"


@pytest.mark.parametrize("kind", list(CHAIN_ORDER), ids=lambda k: k.value)
def test_every_effect_is_actually_installed(kind):
    """Kataloğa girdiğimiz her eklenti bu makinede gerçekten kurulu olmalı.

    Katalog kürasyonlu: bir eklentiyi listeye ekleyip kurulu olmadığını fark etmemek,
    kullanıcıya listede görünen ama eklenince zinciri düşüren bir efekt vermek demekti.
    """
    plan = plan_chain(slots(kind))
    if not plan.slots:
        pytest.skip(f"{kind.value} bu makinede kurulu değil")
    assert kinds(plan) == (kind,)
