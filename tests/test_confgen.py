from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from sonar.core.dsp import registry
from sonar.core.model import BusId, Channel, default_config, default_profile
from sonar.engine import confgen

GOLDEN = "tests/data/graph.conf.golden"


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
    return confgen.generate(default_config())


# --------------------------------------------------------------------------- determinizm


def test_output_is_deterministic(portable):
    config = default_config()
    assert confgen.generate(config) == confgen.generate(config)


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
    config.channel("game").personal.volume = 0.3
    config.channel("chat").stream.muted = True
    config.bus(BusId.PERSONAL).volume = 0.6
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


def test_device_change_changes_the_conf(portable):
    """Cihaz conf'ta `target.object` olarak yazılı; değişimi yapısal."""
    config = default_config()
    before = confgen.generate(config)
    config.bus(BusId.PERSONAL).device = "alsa_output.usb-SteelSeries_Arctis_7"
    after = confgen.generate(config)
    assert after != before
    assert "alsa_output.usb-SteelSeries_Arctis_7" in after


def test_band_count_change_changes_the_conf(portable):
    """EQ eklentisinin kapasitesi conf'ta; band sayısı yapısal bir ayardır."""
    config = default_config()
    before = confgen.generate(config)
    config.settings.default_band_count = 32
    after = confgen.generate(config)
    assert "para_equalizer_x32_stereo" in after
    assert "para_equalizer_x16_stereo" in before


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


def test_mic_monitor_and_stream_send_are_off_by_default(conf):
    assert "sonar_mic_monitor" not in conf
    assert "sonar_mic_to_stream" not in conf


def test_mic_monitor_appears_when_enabled(portable):
    config = default_config()
    config.mic("mic").monitor_enabled = True
    conf = confgen.generate(config)
    assert 'node.name = "sonar_mic_monitor"' in conf
    assert 'target.object = "sonar_personal"' in conf


def test_shared_mic_chain_uses_a_loopback_instead_of_a_second_dsp(portable):
    config = default_config()
    config.mic("stream_mic").share_chain_with_mic = True
    conf = confgen.generate(config)
    block = conf.split('node.description = "Sonar Stream Mic"')[1]
    assert "libpipewire-module-filter-chain" not in block.split("libpipewire-module")[0]
    assert 'target.object = "sonar_mic"' in conf


def test_deepfilter_is_only_in_the_mic_chain(portable):
    """Oynatma zincirinde gürültü engelleme anlamsız ve pahalı."""
    modules = confgen.generate_modules(default_config())
    chains = {
        m["args"]["capture.props"]["node.name"]: m["args"]["filter.graph"]
        for m in modules
        if m["name"] == "libpipewire-module-filter-chain"
    }
    assert [n["name"] for n in chains["sonar_game"]["nodes"]] == ["gate", "eq", "comp", "lim"]
    assert [n["name"] for n in chains["sonar_personal"]["nodes"]] == ["gate", "eq", "comp", "lim"]
    assert chains["sonar_mic_capture"]["nodes"][0]["name"] == "df"


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
    assert len(loopbacks) == 4 * 2  # kanal başına personal + stream

    game = next(c for c in chains if c["args"]["capture.props"]["node.name"] == "sonar_game")
    graph = game["args"]["filter.graph"]
    assert [n["name"] for n in graph["nodes"]] == ["gate", "eq", "comp", "lim"]
    assert graph["inputs"] == ["gate:in_l", "gate:in_r"]
    assert graph["outputs"] == ["lim:out_l", "lim:out_r"]


@pytest.mark.skipif(shutil.which("spa-json-dump") is None, reason="spa-json-dump yok")
def test_quoted_keys_survive_the_roundtrip(portable, tmp_path):
    """DeepFilterNet'in port adlarında boşluk ve parantez var: "Attenuation Limit (dB)"."""
    path = tmp_path / "graph.conf"
    path.write_text(confgen.generate(default_config()), encoding="utf-8")
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
    cfg = default_config()
    assert _capture_props(cfg, "sonar_game")["node.description"] == "Sonar Game — Virtual Output"
    assert (
        _playback_props(cfg, "sonar_stream_out")["node.description"]
        == "Sonar Stream Mix — Virtual Input"
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
