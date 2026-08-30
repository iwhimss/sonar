from __future__ import annotations

import pytest

from sonar.core.model import (
    CHAIN_ORDER,
    DEFAULT_FILTER_PARAMS,
    DYNAMIC_STAGES,
    SUGGESTED_RULES,
    BusId,
    Channel,
    EqBand,
    FilterStage,
    MatchKey,
    RoutingRule,
    default_config,
    default_profile,
    slugify,
)

# --------------------------------------------------------------------------- node adları


def test_channel_node_names():
    channel = Channel(id="game", name="Game", color="#22C58B")
    assert channel.sink_node == "sonar_game"
    assert channel.fx_node == "sonar_game_fx"
    assert channel.loopback_node(BusId.PERSONAL) == "sonar_game_to_personal"
    assert channel.loopback_node(BusId.STREAM) == "sonar_game_to_stream"


def test_node_names_are_unique_across_the_graph():
    config = default_config()
    names = []
    for channel in config.channels:
        names += [channel.sink_node, channel.fx_node]
        names += [channel.loopback_node(bus) for bus in BusId]
    names += [bus.sink_node for bus in config.buses]
    names += [mic.source_node for mic in config.mic_chains]
    assert len(names) == len(set(names)), "node adlarında çakışma var"


# --------------------------------------------------------------------------- varsayılan config


def test_default_config_shape():
    config = default_config()
    assert [c.id for c in config.ordered_channels()] == ["game", "chat", "media", "aux"]
    assert {b.id for b in config.buses} == {BusId.PERSONAL, BusId.STREAM}
    assert [m.id for m in config.mic_chains] == ["mic", "stream_mic"]
    assert config.settings.take_over_default_sink is False
    assert config.settings.sample_rate == 48_000


def test_default_config_is_transparent():
    """İlk kurulumda hiçbir şey değişmemeli: tam ses, filtreler kapalı."""
    config = default_config()
    for channel in config.channels:
        for bus in BusId:
            assert channel.send(bus).volume == 1.0
            assert channel.send(bus).muted is False


def test_lookup_helpers():
    config = default_config()
    assert config.channel("game").name == "Game"
    assert config.channel("yok") is None
    assert config.bus("stream").name == "Stream Mix"
    assert config.bus(BusId.PERSONAL).id is BusId.PERSONAL
    assert config.mic("stream_mic").name == "Stream Mic"


def test_profile_targets_cover_everything_with_dsp():
    targets = default_config().profile_targets()
    assert targets == ["game", "chat", "media", "aux", "mic", "stream_mic", "personal", "stream"]


def test_next_channel_order_appends():
    config = default_config()
    assert config.next_channel_order() == 4


def test_suggested_rules_point_at_real_channels():
    ids = {c.id for c in default_config().channels}
    for _key, _pattern, channel in SUGGESTED_RULES:
        assert channel in ids


def test_default_channel_setting_is_a_real_channel():
    config = default_config()
    assert config.channel(config.settings.default_channel) is not None


def test_chatmix_endpoints_are_real_channels():
    config = default_config()
    assert config.channel(config.chatmix.left_channel) is not None
    assert config.channel(config.chatmix.right_channel) is not None


# --------------------------------------------------------------------------- profil


def test_default_profile_is_off_everywhere():
    profile = default_profile()
    assert profile.eq.enabled is False
    assert all(not profile.filter(stage).enabled for stage in DYNAMIC_STAGES)
    assert all(band.gain_db == 0.0 for band in profile.eq.bands)


def test_default_profile_has_params_for_every_dynamic_stage():
    profile = default_profile()
    for stage in DYNAMIC_STAGES:
        assert profile.filter(stage).params == DEFAULT_FILTER_PARAMS[stage]


def test_filter_creates_missing_stage_lazily():
    profile = default_profile()
    profile.filters.clear()
    state = profile.filter(FilterStage.COMP)
    assert state.params["ratio"] == 4.0
    assert FilterStage.COMP in profile.filters


def test_filter_returns_the_same_object():
    profile = default_profile()
    assert profile.filter(FilterStage.GATE) is profile.filter(FilterStage.GATE)


def test_default_filter_params_mutation_does_not_leak():
    """Varsayılan sözlük paylaşılmamalı; bir profili düzenlemek diğerlerini etkilememeli."""
    first = default_profile()
    first.filter(FilterStage.GATE).params["threshold_db"] = -12.0
    assert default_profile().filter(FilterStage.GATE).params["threshold_db"] == -40.0


@pytest.mark.parametrize("count", [5, 10, 16, 32])
def test_active_bands_respects_band_count(count):
    profile = default_profile(band_count=count)
    assert len(profile.eq.active_bands()) == count


def test_shrinking_band_count_keeps_the_extra_bands():
    profile = default_profile(band_count=32)
    profile.eq.band_count = 10
    assert len(profile.eq.active_bands()) == 10
    assert len(profile.eq.bands) == 32  # kullanıcının ayarları kaybolmadı


def test_chain_order_covers_every_stage():
    assert set(CHAIN_ORDER) == set(FilterStage)
    assert CHAIN_ORDER.index(FilterStage.EQ) > CHAIN_ORDER.index(FilterStage.GATE)
    assert CHAIN_ORDER.index(FilterStage.LIMITER) == len(CHAIN_ORDER) - 1


# --------------------------------------------------------------------------- band kırpma


def test_band_clamped():
    band = EqBand(freq=1e9, gain_db=999.0, q=-5.0, slope=99).clamped()
    assert band.freq == 24_000.0
    assert band.gain_db == 36.0
    assert band.q == 0.05
    assert band.slope == 3


def test_clamped_returns_a_copy():
    band = EqBand(freq=1e9)
    assert band.clamped() is not band
    assert band.freq == 1e9


# --------------------------------------------------------------------------- kurallar


def test_exact_rule_is_case_insensitive():
    rule = RoutingRule(match_key=MatchKey.BINARY, pattern="Discord", channel_id="chat")
    assert rule.matches("discord")
    assert rule.matches("DISCORD")
    assert not rule.matches("discord-canary")


def test_regex_rule():
    rule = RoutingRule(
        match_key=MatchKey.MEDIA_NAME, pattern=r"you\s*tube", channel_id="media", is_regex=True
    )
    assert rule.matches("Watching YouTube now")
    assert not rule.matches("Spotify")


def test_invalid_regex_never_matches_and_never_raises():
    rule = RoutingRule(
        match_key=MatchKey.APP_NAME, pattern="[bozuk(", channel_id="chat", is_regex=True
    )
    assert rule.matches("herhangi bir şey") is False


def test_disabled_rule_never_matches():
    rule = RoutingRule(MatchKey.BINARY, "mpv", "media", enabled=False)
    assert rule.matches("mpv") is False


def test_empty_value_never_matches():
    assert RoutingRule(MatchKey.BINARY, "mpv", "media").matches("") is False


def test_match_key_priority_ordering():
    keys = sorted(MatchKey, key=lambda k: k.priority)
    assert keys == [MatchKey.BINARY, MatchKey.APP_NAME, MatchKey.MEDIA_NAME]


def test_specificity_prefers_longer_patterns():
    short = RoutingRule(MatchKey.BINARY, "cs", "game")
    long = RoutingRule(MatchKey.BINARY, "cs2_linux", "game")
    assert long.specificity > short.specificity


# --------------------------------------------------------------------------- slug


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Müzik", "m_zik"),
        ("Voice Chat", "voice_chat"),
        ("  Boşluk  ", "bo_luk"),
        ("", "kanal"),
        ("!!!", "kanal"),
        ("Aux 2", "aux_2"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_slug_is_usable_as_a_node_name():
    channel = Channel(id=slugify("Voice Chat"), name="Voice Chat", color="#fff")
    assert channel.sink_node == "sonar_voice_chat"
