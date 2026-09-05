from __future__ import annotations

import pytest

from sonar.core.model import (
    CHAIN_ORDER,
    DEFAULT_FILTER_PARAMS,
    SUGGESTED_RULES,
    Channel,
    EffectSlot,
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
    assert channel.loopback_node("personal") == "sonar_game_to_personal"
    assert channel.loopback_node("stream") == "sonar_game_to_stream"


def test_node_names_are_unique_across_the_graph():
    config = default_config()
    names = []
    for channel in config.channels:
        names += [channel.sink_node, channel.fx_node]
        names += [channel.loopback_node(bus) for bus in ("personal", "stream")]
    names += [bus.sink_node for bus in config.buses]
    names += [mic.source_node for mic in config.mic_chains]
    assert len(names) == len(set(names)), "node adlarında çakışma var"


# --------------------------------------------------------------------------- varsayılan config


def test_default_config_shape():
    config = default_config()
    assert [c.id for c in config.ordered_channels()] == ["game", "chat", "media", "aux"]
    assert {b.id for b in config.buses} == {"personal", "stream"}
    assert [m.id for m in config.mic_chains] == ["mic", "stream_mic"]
    assert config.settings.take_over_default_sink is False
    assert config.settings.sample_rate == 48_000


def test_default_config_is_transparent():
    """İlk kurulumda hiçbir şey değişmemeli: tam ses, filtreler kapalı."""
    config = default_config()
    for channel in config.channels:
        for bus in ("personal", "stream"):
            assert channel.send(bus).volume == 1.0
            assert channel.send(bus).muted is False


def test_lookup_helpers():
    config = default_config()
    assert config.channel("game").name == "Game"
    assert config.channel("yok") is None
    assert config.bus("stream").name == "Stream Mix"
    assert config.bus("personal").id == "personal"
    assert config.mic("stream_mic").name == "Stream Mic"


def test_profile_targets_cover_everything_with_dsp():
    targets = default_config().profile_targets()
    assert targets == ["game", "chat", "media", "aux", "mic", "stream_mic", "personal", "stream"]


def test_next_channel_order_appends():
    config = default_config()
    assert config.next_channel_order() == 4


def test_suggested_rules_point_at_real_channels():
    ids = {c.id for c in default_config().channels}
    for _key, _pattern, channel, _is_regex in SUGGESTED_RULES:
        assert channel in ids


def test_default_channel_setting_is_a_real_channel():
    config = default_config()
    assert config.channel(config.settings.default_channel) is not None


def test_chatmix_endpoints_are_real_channels():
    config = default_config()
    assert config.channel(config.chatmix.left_channel) is not None
    assert config.channel(config.chatmix.right_channel) is not None


# --------------------------------------------------------------------------- profil


def test_default_profile_only_carries_the_equalizer():
    """Şema 7: zincir kullanıcının eklediklerinden oluşuyor, EQ hazır geliyor."""
    profile = default_profile()
    assert [e.kind for e in profile.effects] == [FilterStage.EQ]
    assert profile.eq.enabled is False
    assert all(band.gain_db == 0.0 for band in profile.eq.bands)


def test_state_fills_in_the_defaults_of_a_slot():
    """Slot yalnızca kullanıcının değiştirdiklerini taşıyabilir; gerisi tanımdan gelir."""
    profile = default_profile()
    profile.effects.append(EffectSlot(kind=FilterStage.COMP, slot="comp"))
    assert profile.state("comp").params == DEFAULT_FILTER_PARAMS[FilterStage.COMP]
    assert profile.state("comp").enabled is True


def test_state_of_an_unknown_slot_is_inert():
    assert default_profile().state("yok").enabled is False


def test_eq_enabled_comes_from_the_eq_state_not_the_slot():
    """EQ'nun bayrağı `profile.eq`'te: eğri, bandlar ve içe/dışa aktarma hep oradan okuyor."""
    profile = default_profile()
    profile.effects[0].enabled = True
    assert profile.state("eq").enabled is False
    profile.eq.enabled = True
    assert profile.state("eq").enabled is True


def test_slot_ids_are_unique_within_a_profile():
    """Aynı efektten ikinci bir örnek: graf node adları çakışmamalı."""
    profile = default_profile()
    assert profile.next_slot_id(FilterStage.COMP) == "comp"
    profile.effects.append(EffectSlot(kind=FilterStage.COMP, slot="comp"))
    assert profile.next_slot_id(FilterStage.COMP) == "comp2"
    profile.effects.append(EffectSlot(kind=FilterStage.COMP, slot="comp2"))
    assert profile.next_slot_id(FilterStage.COMP) == "comp3"


def test_default_filter_params_mutation_does_not_leak():
    """Varsayılan sözlük paylaşılmamalı; bir profili düzenlemek diğerlerini etkilememeli."""
    first = default_profile()
    first.state("eq")
    DEFAULT_FILTER_PARAMS[FilterStage.GATE]["threshold_db"] = -40.0
    profile = default_profile()
    profile.effects.append(EffectSlot(kind=FilterStage.GATE, slot="gate"))
    profile.state("gate").params["threshold_db"] = -12.0
    assert DEFAULT_FILTER_PARAMS[FilterStage.GATE]["threshold_db"] == -40.0


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
        ("Müzik", "muzik"),
        ("Voice Chat", "voice_chat"),
        ("  Boşluk  ", "bosluk"),
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


def test_bus_lookup_returns_none_for_unknown_names():
    """`channel()` ve `mic()` gibi davranmalı; eskiden ValueError yükseltiyordu."""
    config = default_config()
    assert config.bus("game") is None
    assert config.bus("") is None
    assert config.bus("personal") is not None


def test_slugify_transliterates_turkish_letters():
    """Kimlik PipeWire node adına giriyor, yani ASCII kalmalı — ama harfler düşmemeli.

    Düzeltilmeden önce "Hoparlör" `hoparl_r` oluyordu ve kullanıcı bunu hem `sonar-cli`
    çıktısında hem de hata mesajlarında görüyordu.
    """
    assert slugify("Hoparlör") == "hoparlor"
    assert slugify("Oyun Kanalı") == "oyun_kanali"
    assert slugify("Çalışma Müziği") == "calisma_muzigi"


def test_slugify_never_returns_an_empty_id():
    assert slugify("!!!") == "kanal"
    assert slugify("   ") == "kanal"
