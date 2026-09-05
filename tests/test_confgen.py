from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from sonar.core.dsp import registry
from sonar.core.model import (
    DEFAULT_FILTER_PARAMS,
    Channel,
    EffectSlot,
    FilterStage,
    default_config,
    default_profile,
)
from sonar.engine import confgen

GOLDEN = "tests/data/graph.conf.golden"


#: Altın dosyanın zinciri. Her **node türünü** kapsıyor: LADSPA (df), LV2 (gate/eq/comp/
#: lim), çok node'lu builtin alt graf (spatial) ve kanal başına builtin (boost). Katalogdaki
#: on altı efektin hepsini koymak dosyayı beş bin satıra çıkarır ve yeni bir efekt eklemek
#: her seferinde altın dosyayı değiştirirdi; kapsam node türü düzeyinde tutuluyor.
#: Efektlerin **kendi** kurulabilirliğini `test_every_effect_kind_builds_a_graph` sınıyor.
GOLDEN_CHAIN = (
    FilterStage.DEEPFILTER,
    FilterStage.GATE,
    FilterStage.EQ,
    FilterStage.COMP,
    FilterStage.SPATIAL,
    FilterStage.BOOST,
    FilterStage.LIMITER,
)


def full_chain(target: str, name: str):
    """Altın dosyanın profil sağlayıcısı."""
    del target
    profile = default_profile(name)
    profile.effects = [
        EffectSlot(
            kind=kind,
            slot=kind.value,
            enabled=False,
            params=dict(DEFAULT_FILTER_PARAMS.get(kind, {})),
        )
        for kind in GOLDEN_CHAIN
    ]
    return profile


@pytest.fixture
def portable(monkeypatch):
    """Conf'u makineden bağımsız yapar.

    İki kaynak makineye bağlıdır: eklentinin kurulu olup olmaması (kurulu değilse aşama
    zincirden düşer) ve LADSPA kütüphanesinin mutlak yolu. İkisini de sabitliyoruz ki
    altın dosya karşılaştırması her makinede aynı sonucu versin.
    """
    monkeypatch.setattr(registry, "is_available", lambda _key: True)
    monkeypatch.setattr(registry, "plugin_reference", lambda spec: spec.uri)


@pytest.fixture
def conf(portable):
    return confgen.generate(default_config(), full_chain)


# --------------------------------------------------------------------------- determinizm


def test_output_is_deterministic(portable):
    config = default_config()
    assert confgen.generate(config, full_chain) == confgen.generate(config, full_chain)


def test_matches_the_golden_file(conf):
    from pathlib import Path

    golden = Path(GOLDEN)
    if not golden.exists():  # pragma: no cover - ilk üretim
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(conf, encoding="utf-8")
        pytest.skip("altın dosya oluşturuldu")
    assert conf == golden.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- ne conf'u değiştirir?
#
# Faz 2'nin en önemli kısıtı: conf'un değişmesi süreci yeniden başlatmayı, yani ~200 ms ses
# kesintisini gerektirir. Aşağıdaki iki grup testin ayrımı bu yüzden kritik.


def test_profile_change_does_not_touch_the_conf(portable):
    """EQ'yu kurcalamak sesi kesmemeli."""
    config = default_config()
    before = confgen.generate(config)
    config.channel("game").active_profile = "CS2"
    assert confgen.generate(config) == before


def test_volume_and_mute_do_not_touch_the_conf(portable):
    config = default_config()
    before = confgen.generate(config)
    config.channel("game").output.volume = 0.3
    config.channel("chat").stream.muted = True
    config.bus("personal").volume = 0.6
    config.chatmix.value = 90.0
    assert confgen.generate(config) == before


def test_routing_rules_do_not_touch_the_conf(portable):
    from sonar.core.model import RoutingRule

    config = default_config()
    before = confgen.generate(config)
    config.rules.append(RoutingRule(match_key="binary", pattern="cs2", channel_id="game"))
    assert confgen.generate(config) == before


def test_adding_a_channel_changes_the_conf(portable):
    config = default_config()
    before = confgen.generate(config)
    config.channels.append(
        Channel(id="music", name="Music", color="#fff", order=config.next_channel_order())
    )
    after = confgen.generate(config)
    assert after != before
    assert "sonar_music_fx" in after
    assert "sonar_music_to_stream" in after


def test_removing_a_channel_changes_the_conf(portable):
    config = default_config()
    before = confgen.generate(config)
    config.channels = [c for c in config.channels if c.id != "aux"]
    after = confgen.generate(config)
    assert after != before
    assert "sonar_aux" not in after


def test_device_change_does_not_touch_the_conf(portable):
    """Cihaz seçimi conf'a **girmez**; `pw-metadata` ile canlı verilir.

    Faz 18'de değişti. Eskiden `target.object` olarak conf'a yazılıyordu, yani cihaz
    değiştirmek grafı yeniden kurup çalan müziği kesiyordu — test turu 2'nin
    "master'dan cihaz değiştirince şarkı duruyor" şikâyeti buydu.
    """
    config = default_config()
    before = confgen.generate(config)
    config.bus("personal").device = "alsa_output.usb-SteelSeries_Arctis_7"
    assert confgen.generate(config) == before
    assert confgen.live_targets(config) == {
        "sonar_personal_out": "alsa_output.usb-SteelSeries_Arctis_7"
    }


def test_mic_device_is_live_too(portable):
    config = default_config()
    before = confgen.generate(config)
    config.mic("mic").source_device = "alsa_input.usb-Fifine"
    assert confgen.generate(config) == before
    assert confgen.live_targets(config)["sonar_mic_capture"] == "alsa_input.usb-Fifine"


def test_stream_bus_has_no_device_target(portable):
    """Yayın miksinin çıkışı sanal bir kaynak; fiziksel bir hedefi yok."""
    config = default_config()
    config.bus("stream").device = "alsa_output.usb-SteelSeries_Arctis_7"
    assert "sonar_stream_out" not in confgen.live_targets(config)


def test_band_count_no_longer_touches_the_conf(portable):
    """Zincir her zaman 32 bandlık eklentiyle kuruluyor.

    Eskiden band sayısı kapasiteyi seçiyordu ve değişimi yapısaldı; kullanıcı band
    eklemeyi eğriye sağ tıkla yapmak isteyince bu kabul edilemez oldu — her nokta
    eklemede ses kesilirdi (Faz 31).
    """
    config = default_config()
    before = confgen.generate(config)
    config.settings.default_band_count = 32
    assert confgen.generate(config) == before
    assert "para_equalizer_x32_stereo" in before


# --------------------------------------------------------------------------- node envanteri


def test_every_expected_node_is_declared(conf):
    for channel in ("game", "chat", "media", "aux"):
        assert f'node.name = "sonar_{channel}"' in conf
        assert f'node.name = "sonar_{channel}_fx"' in conf
        assert f'node.name = "sonar_{channel}_to_personal"' in conf
        assert f'node.name = "sonar_{channel}_to_stream"' in conf
    for name in ("sonar_personal", "sonar_stream", "sonar_mic", "sonar_stream_mic"):
        assert f'node.name = "{name}"' in conf
    assert 'node.name = "sonar_stream_out"' in conf


def test_node_names_are_unique(conf):
    import re

    names = re.findall(r'node\.name = "([^"]+)"', conf)
    duplicates = {name for name in names if names.count(name) > 1}
    assert not duplicates, f"conf'ta çakışan node adı: {duplicates}"


def test_virtual_sources_never_become_the_default_microphone(conf):
    """`priority.session = 0` olmazsa WirePlumber `sonar_game_fx`'i mikrofon sanabilir."""
    blocks = conf.split("playback.props = {")[1:]
    for block in blocks:
        body = block.split("}")[0]
        if 'media.class = "Audio/Source"' in body:
            assert "priority.session = 0" in body


def test_no_node_uses_the_broken_virtual_class(conf):
    """PipeWire 1.6.8 filter-chain `Audio/Source/Virtual`'ı kuramıyor (`-28`)."""
    assert "Audio/Source/Virtual" not in conf


def test_sample_rate_is_pinned_everywhere(portable):
    """DeepFilterNet 48 kHz zorunlu kılıyor."""
    conf = confgen.generate(default_config())
    assert conf.count("audio.rate = 44100") == 0
    assert "default.clock.rate = 48000" in conf
    assert conf.count("audio.rate = 48000") > 20


# --------------------------------------------------------------------------- mikrofon


def test_mic_sends_are_always_in_the_conf(conf):
    """Kapalıyken de kurulurlar; açma/kapama mute ile yapılıyor (Faz 18).

    Eskiden conf'a bağlıydı: sidetone'u açmak grafı yeniden kurup sesi kesiyordu.
    """
    assert 'node.name = "sonar_mic_monitor"' in conf
    assert 'node.name = "sonar_mic_to_stream"' in conf


def test_toggling_a_mic_send_does_not_touch_the_conf(portable):
    config = default_config()
    before = confgen.generate(config)
    config.mic("mic").monitor_enabled = True
    config.mic("mic").send_to_stream_bus = True
    assert confgen.generate(config) == before


def test_shared_mic_chain_uses_a_loopback_instead_of_a_second_dsp(portable):
    config = default_config()
    config.mic("stream_mic").share_chain_with_mic = True
    conf = confgen.generate(config)
    block = conf.split('node.description = "Sonar Stream Mic"')[1]
    assert "libpipewire-module-filter-chain" not in block.split("libpipewire-module")[0]
    assert 'target.object = "sonar_mic"' in conf


def test_deepfilter_is_only_in_the_mic_chain(portable):
    """Oynatma zincirinde gürültü engelleme anlamsız ve pahalı."""
    modules = confgen.generate_modules(default_config(), full_chain)
    chains = {
        m["args"]["capture.props"]["node.name"]: m["args"]["filter.graph"]
        for m in modules
        if m["name"] == "libpipewire-module-filter-chain"
    }
    playback = [
        "gate", "eq", "comp",
        "spatial_copy_l", "spatial_copy_r", "spatial_delay_l", "spatial_delay_r",
        "spatial_lp_l", "spatial_lp_r", "spatial_mix_l", "spatial_mix_r",
        "boost_l", "boost_r", "lim",
    ]  # fmt: skip
    assert [n["name"] for n in chains["sonar_game"]["nodes"]] == playback
    assert [n["name"] for n in chains["sonar_personal"]["nodes"]] == playback
    assert chains["sonar_mic_capture"]["nodes"][0]["name"] == "df"
    # Uzamsal Ses (crossfeed) mikrofon zincirinde anlamsız. Şema 6'da `_graph` yalnızca
    # DeepFilterNet'i süzüyordu ve crossfeed node'ları mikrofon zincirinde de duruyordu;
    # `PLAYBACK_ONLY_STAGES` vardı ama kullanılmıyordu. Şema 7'de `effect_slots` süzüyor.
    assert not any(
        n["name"].startswith("spatial") for n in chains["sonar_mic_capture"]["nodes"]
    )


def test_missing_deepfilter_does_not_break_the_mic_chain(monkeypatch):
    monkeypatch.setattr(registry, "is_available", lambda key: not key.startswith("deepfilter"))
    conf = confgen.generate(default_config())
    assert "deep_filter" not in conf
    assert 'node.name = "sonar_mic"' in conf


# --------------------------------------------------------------------------- başlangıç nötrlüğü


def test_conf_carries_no_profile_values(portable):
    """Conf'taki tüm DSP değerleri bypass olmalı — aksi hâlde profil conf'a sızmış demektir."""
    config = default_config()
    profile = default_profile("Bass Boost")
    profile.eq.enabled = True
    profile.eq.bands[2].gain_db = 9.0
    config.channel("game").active_profile = "Bass Boost"
    conf = confgen.generate(config)
    assert "enabled = 1.0" not in conf
    assert "9.0" not in conf


# --------------------------------------------------------------------------- SPA-JSON geçerliliği


@pytest.mark.skipif(shutil.which("spa-json-dump") is None, reason="spa-json-dump yok")
def test_pipewire_can_parse_the_generated_conf(conf, tmp_path):
    """PipeWire'ın kendi ayrıştırıcısıyla doğrula — kendi yazıcımıza güvenmiyoruz."""
    path = tmp_path / "graph.conf"
    path.write_text(conf, encoding="utf-8")
    dumped = subprocess.run(
        ["spa-json-dump", str(path)], capture_output=True, text=True, check=True
    )
    parsed = json.loads(dumped.stdout)

    modules = parsed["context.modules"]
    chains = [m for m in modules if m["name"] == "libpipewire-module-filter-chain"]
    loopbacks = [m for m in modules if m["name"] == "libpipewire-module-loopback"]
    assert len(chains) == 4 + 2 + 2  # kanallar + bus'lar + mikrofonlar
    # kanal başına personal + stream, artı mikrofon başına monitor + to_stream
    assert len(loopbacks) == 4 * 2 + 2 * 2

    game = next(c for c in chains if c["args"]["capture.props"]["node.name"] == "sonar_game")
    graph = game["args"]["filter.graph"]
    assert [n["name"] for n in graph["nodes"]] == [
        "gate", "eq", "comp",
        "spatial_copy_l", "spatial_copy_r", "spatial_delay_l", "spatial_delay_r",
        "spatial_lp_l", "spatial_lp_r", "spatial_mix_l", "spatial_mix_r",
        "boost_l", "boost_r", "lim",
    ]  # fmt: skip
    assert graph["inputs"] == ["gate:in_l", "gate:in_r"]
    assert graph["outputs"] == ["lim:out_l", "lim:out_r"]


@pytest.mark.skipif(shutil.which("spa-json-dump") is None, reason="spa-json-dump yok")
def test_quoted_keys_survive_the_roundtrip(portable, tmp_path):
    """DeepFilterNet'in port adlarında boşluk ve parantez var: "Attenuation Limit (dB)"."""
    path = tmp_path / "graph.conf"
    path.write_text(confgen.generate(default_config(), full_chain), encoding="utf-8")
    parsed = json.loads(
        subprocess.run(
            ["spa-json-dump", str(path)], capture_output=True, text=True, check=True
        ).stdout
    )
    mic = next(
        m
        for m in parsed["context.modules"]
        if m["name"] == "libpipewire-module-filter-chain"
        and m["args"]["playback.props"]["node.name"] == "sonar_mic"
    )
    df = next(n for n in mic["args"]["filter.graph"]["nodes"] if n["name"] == "df")
    assert df["control"]["Attenuation Limit (dB)"] == 0.0


# --------------------------------------------------------------------------- CLI


def test_cli_prints_the_conf(config_store, capsys):
    config_store.load()
    assert confgen._main(["--config", str(config_store.paths.config_file)]) == 0
    assert "libpipewire-module-filter-chain" in capsys.readouterr().out


# --------------------------------------------------------------------------- sanal cihazlar


def _playback_props(cfg, node_name):
    for module in confgen.generate_modules(cfg):
        args = module.get("args") or {}
        props = args.get("playback.props") or {}
        if props.get("node.name") == node_name:
            return props
    raise AssertionError(f"node bulunamadı: {node_name}")


def _capture_props(cfg, node_name):
    for module in confgen.generate_modules(cfg):
        args = module.get("args") or {}
        props = args.get("capture.props") or {}
        if props.get("node.name") == node_name:
            return props
    raise AssertionError(f"node bulunamadı: {node_name}")


def test_channel_fx_is_not_a_device_by_default(portable):
    """Varsayılanda kanal başına sahte mikrofon oluşmamalı — kullanıcının 1. şikâyeti."""
    props = _playback_props(default_config(), "sonar_game_fx")
    assert "media.class" not in props
    assert props["node.autoconnect"] is False


def test_channel_fx_becomes_a_source_when_asked(portable):
    cfg = default_config()
    cfg.channel("game").stream_source = True
    props = _playback_props(cfg, "sonar_game_fx")
    assert props["media.class"] == confgen.VIRTUAL_SOURCE_CLASS
    assert props["node.description"] == "Sonar Game — Stream Source (Virtual Input)"


def test_device_names_state_their_direction(portable):
    """Bus sink'inin adı OBS'te seçilecek addır; doküman ile birebir aynı olmalı.

    Çıkış node'u aynı miksin ikinci kopyası; adı eskiden "— Virtual Input"tı ve sink'in
    "— Virtual Output"una o kadar benziyordu ki kullanıcı ikisini birden ekleyip aynı
    miksi iki kez aldı (test turu 3).
    """
    cfg = default_config()
    assert _capture_props(cfg, "sonar_game")["node.description"] == "Sonar Game — Virtual Output"
    assert _capture_props(cfg, "sonar_stream")["node.description"] == "Sonar Stream Mix"
    assert (
        _playback_props(cfg, "sonar_stream_out")["node.description"]
        == "Sonar Stream Mix (alternatif giriş)"
    )
    assert _playback_props(cfg, "sonar_mic")["node.description"] == "Sonar Mic — Virtual Input"


def test_virtual_nodes_are_never_auto_selected(portable):
    """`priority.session = 0`: `sonar_personal` varsayılan sink olursa kendini besler."""
    cfg = default_config()
    assert _capture_props(cfg, "sonar_personal")["priority.session"] == 0
    assert _capture_props(cfg, "sonar_game")["priority.session"] == 0


def test_sends_are_not_wired_in_the_conf(portable):
    """Gönderiler `pw-link` ile kuruluyor; conf'ta `target.object` olmamalı."""
    props = _capture_props(default_config(), "sonar_game_to_personal_capture")
    assert "target.object" not in props
    assert props["node.autoconnect"] is False


def test_send_links_cover_every_channel_and_bus(portable):
    links = confgen.send_links(default_config())
    assert len(links) == 4 * 2
    assert ("sonar_game_fx", "sonar_game_to_personal_capture") in links
    assert ("sonar_media_fx", "sonar_media_to_stream_capture") in links
