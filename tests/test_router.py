from __future__ import annotations

import pytest

from sonar.core.model import MatchKey, RoutingRule, default_config
from sonar.engine.pwstate import GraphState, StreamInfo
from sonar.engine.router import Decision, Router, choose_channel, stream_value


def stream(**kwargs) -> StreamInfo:
    base = {"id": 1, "node_name": "app", "app_binary": "", "app_name": "", "media_name": ""}
    return StreamInfo(**{**base, **kwargs})


# --------------------------------------------------------------------------- eşleştirme


def test_binary_beats_app_name():
    """`application.process.binary` en güvenilir: kullanıcının dilinden bağımsız."""
    config = default_config()
    config.rules = [
        RoutingRule(MatchKey.APP_NAME, "Firefox", "media"),
        RoutingRule(MatchKey.BINARY, "firefox", "game"),
    ]
    channel, rule = choose_channel(stream(app_binary="firefox", app_name="Firefox"), config)
    assert channel == "game"
    assert rule.match_key == MatchKey.BINARY


def test_app_name_beats_media_name():
    config = default_config()
    config.rules = [
        RoutingRule(MatchKey.MEDIA_NAME, "YouTube", "aux"),
        RoutingRule(MatchKey.APP_NAME, "Firefox", "media"),
    ]
    channel, _ = choose_channel(stream(app_name="Firefox", media_name="YouTube"), config)
    assert channel == "media"


def test_more_specific_pattern_wins_at_the_same_priority():
    config = default_config()
    config.rules = [
        RoutingRule(MatchKey.BINARY, "cs", "media", is_regex=True),
        RoutingRule(MatchKey.BINARY, "cs2_linux", "game"),
    ]
    channel, rule = choose_channel(stream(app_binary="cs2_linux"), config)
    assert channel == "game"
    assert rule.pattern == "cs2_linux"


def test_regex_rule_matches():
    config = default_config()
    config.rules = [RoutingRule(MatchKey.MEDIA_NAME, r"you\s*tube", "media", is_regex=True)]
    channel, _ = choose_channel(stream(media_name="Watching YouTube now"), config)
    assert channel == "media"


def test_broken_regex_never_matches_and_never_raises():
    config = default_config()
    config.rules = [RoutingRule(MatchKey.BINARY, "[bozuk(", "game", is_regex=True)]
    channel, rule = choose_channel(stream(app_binary="anything"), config)
    assert rule is None
    assert channel == config.settings.default_channel


def test_disabled_rule_is_ignored():
    config = default_config()
    config.rules = [RoutingRule(MatchKey.BINARY, "mpv", "game", enabled=False)]
    channel, rule = choose_channel(stream(app_binary="mpv"), config)
    assert rule is None
    assert channel == "media"


def test_rule_pointing_at_a_deleted_channel_is_ignored():
    """Kanal silindiğinde kural yetim kalır; akışı yok olan yere göndermemeliyiz."""
    config = default_config()
    config.rules = [RoutingRule(MatchKey.BINARY, "mpv", "silinmis_kanal")]
    channel, rule = choose_channel(stream(app_binary="mpv"), config)
    assert rule is None
    assert channel == "media"


def test_no_match_falls_back_to_the_default_channel():
    config = default_config()
    config.settings.default_channel = "aux"
    channel, rule = choose_channel(stream(app_binary="bilinmeyen"), config)
    assert (channel, rule) == ("aux", None)


def test_default_rules_route_discord_and_browsers():
    config = default_config()
    assert choose_channel(stream(app_binary="Discord"), config)[0] == "chat"
    assert choose_channel(stream(app_binary="vesktop"), config)[0] == "chat"
    assert choose_channel(stream(app_binary="firefox"), config)[0] == "media"
    assert choose_channel(stream(app_binary="spotify"), config)[0] == "media"


def test_empty_values_never_match():
    config = default_config()
    config.rules = [RoutingRule(MatchKey.BINARY, "firefox", "media")]
    channel, rule = choose_channel(stream(), config)
    assert rule is None
    assert channel == config.settings.default_channel


@pytest.mark.parametrize(
    ("key", "field"),
    [
        (MatchKey.BINARY, "app_binary"),
        (MatchKey.APP_NAME, "app_name"),
        (MatchKey.MEDIA_NAME, "media_name"),
    ],
)
def test_stream_value_maps_each_key_to_its_field(key, field):
    assert stream_value(stream(**{field: "değer"}), key) == "değer"


# --------------------------------------------------------------------------- Router


class Graph:
    """Akış envanterini elle kurmak için küçük bir yardımcı."""

    def __init__(self) -> None:
        self.state = GraphState()
        self.moves: list[tuple[int, str]] = []
        self.move_ok = True

    def add(self, stream_id: int, name: str, media_class="Stream/Output/Audio", **props):
        self.state.apply(
            [
                {
                    "id": stream_id,
                    "type": "PipeWire:Interface:Node",
                    "info": {"props": {"node.name": name, "media.class": media_class, **props}},
                }
            ]
        )

    def remove(self, stream_id: int):
        self.state.apply([{"id": stream_id, "type": "PipeWire:Interface:Node", "info": None}])

    def move(self, stream_id: int, node: str) -> bool:
        self.moves.append((stream_id, node))
        return self.move_ok


@pytest.fixture
def graph():
    return Graph()


@pytest.fixture
def router(graph):
    config = default_config()
    return Router(graph.state, graph.move, lambda: config)


def test_new_stream_is_routed(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    decisions = router.sync()
    assert len(decisions) == 1
    decision = decisions[0]
    assert (decision.stream_id, decision.channel_id, decision.reason, decision.pattern) == (
        10,
        "media",
        "rule",
        "firefox",
    )
    assert graph.moves == [(10, "sonar_media")]


def test_unmatched_stream_goes_to_the_default_channel(router, graph):
    graph.add(11, "bilinmeyen", **{"application.process.binary": "bilinmeyen"})
    decision = router.sync()[0]
    assert (decision.channel_id, decision.reason) == ("media", "default")
    assert decision.by_rule is False


def test_a_stream_is_routed_only_once(router, graph):
    """Sürekli düzeltmek kullanıcıyla kavga etmek olurdu — bkz. router modül başlığı."""
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    router.sync()
    router.sync()
    assert graph.moves == [(10, "sonar_media")]


def test_manual_move_is_never_reverted(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.mark_manual(10, "game")
    assert router.sync() == []
    assert graph.moves == []


def test_closed_stream_is_forgotten(router, graph):
    """PipeWire id'leri geri dönüştürüyor; eski kayıt yeni akışı engellememeli."""
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    graph.remove(10)
    router.sync()
    assert router.decided == {}

    graph.add(10, "mpv", **{"application.process.binary": "mpv"})
    router.sync()
    assert graph.moves[-1] == (10, "sonar_media")
    assert len(graph.moves) == 2


def test_our_own_loopbacks_are_never_touched(router, graph):
    graph.add(20, "sonar_game_to_personal")
    graph.add(21, "sonar_personal_out")
    assert router.sync() == []
    assert graph.moves == []


def test_capture_streams_go_to_an_input_chain(router, graph):
    """Faz 21: yakalama akışları da yönlendiriliyor.

    Kullanıcı hangi uygulamanın hangi mikrofonu kullanacağını seçebilmeli. Eskiden
    yakalama akışlarına hiç dokunulmuyordu.
    """
    graph.add(30, "obs", "Stream/Input/Audio", **{"application.process.binary": "obs"})
    decisions = router.sync()
    assert [(d.stream_id, d.channel_id, d.reason) for d in decisions] == [(30, "mic", "default")]
    assert graph.moves == [(30, "sonar_mic")]


def test_stream_already_aimed_at_a_sonar_channel_is_left_alone(router, graph):
    """Uygulama kendisi bir kanalı hedeflediyse (ör. OBS) kararına saygı duyulur."""
    graph.add(
        40,
        "pw-cat",
        **{"application.process.binary": "pw-cat", "target.object": "sonar_game"},
    )
    assert router.sync() == []
    assert graph.moves == []


def test_failed_move_is_not_retried_in_a_loop(router, graph):
    """Aksi hâlde her `pw-dump` olayında yeniden denenir, saniyede onlarca taşıma çağrısı olur."""
    graph.move_ok = False
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    assert router.sync() == []
    router.sync()
    assert len(graph.moves) == 1


def test_disabled_router_does_nothing(graph):
    config = default_config()
    router = Router(graph.state, graph.move, lambda: config, enabled=False)
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    assert router.sync() == []
    assert graph.moves == []


def test_reset_allows_rerouting_after_a_rebuild(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    router.reset()
    router.sync()
    assert graph.moves == [(10, "sonar_media"), (10, "sonar_media")]


def test_forget_single_stream(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    router.forget(10)
    router.sync()
    assert len(graph.moves) == 2


def test_listener_is_notified(graph):
    seen: list[Decision] = []
    config = default_config()
    router = Router(graph.state, graph.move, lambda: config, on_route=seen.append)
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    assert [d.channel_id for d in seen] == ["media"]


def test_a_failing_listener_does_not_break_routing(graph):
    def boom(_decision):
        raise RuntimeError("dinleyici patladı")

    config = default_config()
    router = Router(graph.state, graph.move, lambda: config, on_route=boom)
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    assert router.sync()[0].channel_id == "media"


# --------------------------------------------------------------------------- kenar durumlar


def test_multiple_streams_from_the_same_application(router, graph):
    """Tarayıcı sekmeleri: her akış ayrı ayrı yönlendirilir."""
    for index in (10, 11, 12):
        graph.add(index, f"firefox{index}", **{"application.process.binary": "firefox"})
    decisions = router.sync()
    assert {d.stream_id for d in decisions} == {10, 11, 12}
    assert all(node == "sonar_media" for _, node in graph.moves)


def test_rule_change_affects_only_new_streams(router, graph):
    config = default_config()
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(10, "mpv", **{"application.process.binary": "mpv"})
    router.sync()
    assert graph.moves == [(10, "sonar_media")]

    config.rules.insert(0, RoutingRule(MatchKey.BINARY, "mpv", "game"))
    router.sync()  # açık akış korunur
    assert len(graph.moves) == 1

    graph.add(11, "mpv2", **{"application.process.binary": "mpv"})
    router.sync()
    assert graph.moves[-1] == (11, "sonar_game")


def test_routing_latency_is_measured(graph):
    """Plan gecikmenin loglanmasını istiyor: akışın görülmesinden taşımanın bitişine kadar."""
    import time

    config = default_config()
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    time.sleep(0.01)
    decision = router.sync()[0]
    assert decision.latency >= 0.01
    assert decision.latency < 5.0


def test_stream_seen_timestamp_is_cleared_on_close(graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    assert 10 in graph.state.stream_seen
    graph.remove(10)
    assert 10 not in graph.state.stream_seen


# --------------------------------------------------------------------------- id geri dönüşümü
#
# PipeWire node id'lerini geri dönüştürüyor. Ölçümde beş akıştan ikisi bu yüzden
# yönlendirilmemişti: kapanan akışın id'si yenisine verildi ve silinme olayı bize ulaşmadan
# yeni akış "zaten karar verilmiş" sanıldı.


def test_recycled_id_with_a_new_serial_is_routed_again(router, graph):
    graph.add(10, "mpv", **{"application.process.binary": "mpv", "object.serial": 100})
    router.sync()
    assert graph.moves == [(10, "sonar_media")]

    # Aynı id, yeni serial — silinme olayı henüz gelmemiş olsa bile yeni bir akış.
    graph.add(10, "firefox", **{"application.process.binary": "firefox", "object.serial": 200})
    router.sync()
    assert graph.moves == [(10, "sonar_media"), (10, "sonar_media")]


def test_same_serial_is_not_routed_twice(router, graph):
    graph.add(10, "mpv", **{"application.process.binary": "mpv", "object.serial": 100})
    router.sync()
    graph.add(
        10, "mpv", **{"application.process.binary": "mpv", "object.serial": 100, "media.name": "x"}
    )
    router.sync()
    assert len(graph.moves) == 1


def test_manual_mark_uses_the_serial(router, graph):
    graph.add(10, "mpv", **{"application.process.binary": "mpv", "object.serial": 100})
    router.mark_manual(10, "game")
    assert router.decided == {100: "game"}
    assert router.sync() == []


def test_streams_without_a_serial_fall_back_to_the_id(router, graph):
    """Eski PipeWire veya eksik props: kimlik yine de tutarlı olmalı."""
    graph.add(10, "mpv", **{"application.process.binary": "mpv"})
    router.sync()
    assert router.decided == {10: "media"}
    router.sync()
    assert len(graph.moves) == 1


def test_default_rules_route_wine_and_steam_games_to_game():
    """Proton/Wine altındaki oyunlar varsayılan olarak Game kanalına düşsün."""
    config = default_config()
    for binary in ("ArcRaiders.exe", "cs2.exe", "wine64-preloader", "steam_app_730"):
        assert choose_channel(stream(app_binary=binary), config)[0] == "game", binary


def test_game_rules_do_not_catch_normal_applications():
    config = default_config()
    for binary in ("firefox", "spotify", "Discord", "mpv"):
        assert choose_channel(stream(app_binary=binary), config)[0] != "game", binary


def test_default_rules_are_all_valid_regexes():
    """Bozuk bir varsayılan regex sessizce hiç eşleşmez; erken yakalayalım."""
    import re

    from sonar.core.model import SUGGESTED_RULES

    for _key, pattern, _channel, is_regex in SUGGESTED_RULES:
        if is_regex:
            re.compile(pattern)


# --------------------------------------------------------------------------- yeniden oturtma
#
# Yeniden inşa node id'lerini eskitir ama kullanıcının kararını geçersiz kılmaz. Eskiden
# burada `reset()` çağrılıyordu ve `_is_routable` hedefi `sonar_` ile başlayan akışı
# "kullanıcı seçmiş" sayıp atladığı için **hiçbir akış yeniden yerleştirilmiyordu** —
# test turu 2'deki "ses gidiyor" şikâyetlerinin bir ayağı buydu.


def test_reassert_moves_streams_back_onto_their_decision(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    graph.moves.clear()

    decisions = router.reassert()

    assert graph.moves == [(10, "sonar_media")]
    assert [(d.stream_id, d.channel_id, d.reason) for d in decisions] == [
        (10, "media", "reassert")
    ]
    assert router.decided  # karar korunuyor


def test_reassert_waits_for_the_node_to_appear(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    graph.moves.clear()

    assert router.reassert(lambda _name: False) == []
    assert graph.moves == []
    assert router.decided  # karar yine korunuyor; sonraki tur dener


def test_reassert_forgets_a_channel_that_no_longer_exists(graph):
    config = default_config()
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    router.sync()
    config.channels = [c for c in config.channels if c.id != "media"]

    assert router.reassert() == []
    assert router.decided == {}


def test_forget_channel_drops_only_that_channels_decisions(router, graph):
    graph.add(10, "firefox", **{"application.process.binary": "firefox"})
    graph.add(11, "discord", **{"application.process.binary": "Discord"})
    router.sync()
    assert set(router.decided.values()) == {"media", "chat"}

    router.forget_channel("media")

    assert set(router.decided.values()) == {"chat"}


# --------------------------------------------------------------------------- yön
#
# Discord hem ses çalar hem mikrofon dinler. İkisi ayrı kurallarla, ayrı hedeflere
# yönlendirilebilmeli (Faz 21).


def test_output_rules_do_not_catch_capture_streams(graph):
    config = default_config()
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(10, "Discord", "Stream/Input/Audio", **{"application.process.binary": "Discord"})

    router.sync()

    # "Discord → chat" kuralı bir **çıkış** kuralı; mikrofon akışını yakalamamalı.
    assert graph.moves == [(10, "sonar_mic")]


def test_an_input_rule_sends_the_microphone_to_its_chain(graph):
    from sonar.core.model import MatchKey, RoutingRule, StreamDirection

    config = default_config()
    config.rules.append(
        RoutingRule(
            match_key=MatchKey.BINARY,
            pattern="Discord",
            channel_id="stream_mic",
            direction=StreamDirection.IN,
        )
    )
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(10, "Discord", "Stream/Input/Audio", **{"application.process.binary": "Discord"})
    graph.add(11, "Discord", **{"application.process.binary": "Discord"})

    router.sync()

    assert sorted(graph.moves) == [(10, "sonar_stream_mic"), (11, "sonar_chat")]


def test_an_input_rule_never_catches_playback(graph):
    from sonar.core.model import MatchKey, RoutingRule, StreamDirection

    config = default_config()
    config.rules = [
        RoutingRule(
            match_key=MatchKey.BINARY,
            pattern="spotify",
            channel_id="mic",
            direction=StreamDirection.IN,
        )
    ]
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(10, "spotify", **{"application.process.binary": "spotify"})

    router.sync()

    assert graph.moves == [(10, "sonar_media")], "giriş kuralı oynatmayı kaçırmalı"


def test_desktop_audio_capture_is_left_alone(graph):
    """cava, OBS "Masaüstü Sesi" gibi akışlar mikrofon kullanıcısı değil.

    Ölçüldü (Faz 21): yakalama akışları yönlendirilmeye başlayınca cava sessizce
    `sonar_mic`'e çekildi ve kullanıcının görselleştiricisi bozuldu.
    """
    config = default_config()
    router = Router(graph.state, graph.move, lambda: config)
    graph.add(
        20,
        "cava",
        "Stream/Input/Audio",
        **{"application.process.binary": "cava", "stream.capture.sink": True},
    )

    assert router.sync() == []
    assert graph.moves == []
