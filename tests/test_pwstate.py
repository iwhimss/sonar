from __future__ import annotations

import json

from sonar.engine.pwstate import EventSplitter, GraphState

# --------------------------------------------------------------------------- olay bölme
#
# `pw-dump -m` ardışık JSON dizileri basar: 0. sütunda `[` başlar, 0. sütunda `]` biter.
# Tek bir olay binlerce satır sürebildiği için satır satır ayrıştırmak yanlış olurdu.


def _event(*objects: dict) -> str:
    body = ",\n".join("  " + json.dumps(o) for o in objects)
    return "[\n" + body + "\n]\n"


def test_splits_consecutive_events():
    splitter = EventSplitter()
    text = _event({"id": 1}) + _event({"id": 2}, {"id": 3})
    events = list(splitter.feed(text))
    assert [[o["id"] for o in e] for e in events] == [[1], [2, 3]]


def test_survives_chunk_boundaries_inside_a_line():
    """Boru hattından gelen parça sınırı satır sınırıyla örtüşmek zorunda değil."""
    text = _event({"id": 7, "type": "PipeWire:Interface:Node"})
    splitter = EventSplitter()
    events = []
    for index in range(0, len(text), 3):  # 3 baytlık parçalar
        events += list(splitter.feed(text[index : index + 3]))
    assert len(events) == 1
    assert events[0][0]["id"] == 7


def test_incomplete_event_yields_nothing_yet():
    splitter = EventSplitter()
    assert list(splitter.feed('[\n  {"id": 1}\n')) == []
    assert [o["id"] for o in next(iter(splitter.feed("]\n")))] == [1]


def test_malformed_event_is_skipped_without_raising():
    splitter = EventSplitter()
    assert list(splitter.feed("[\n  bu json değil\n]\n")) == []
    # akış bozulmadı, sonraki olay okunuyor
    assert next(iter(splitter.feed(_event({"id": 9}))))[0]["id"] == 9


def test_text_outside_brackets_is_ignored():
    splitter = EventSplitter()
    text = "rastgele gürültü\n" + _event({"id": 1})
    assert len(list(splitter.feed(text))) == 1


# --------------------------------------------------------------------------- envanter


def _node(node_id: int, name: str, media_class: str = "", **props) -> dict:
    return {
        "id": node_id,
        "type": "PipeWire:Interface:Node",
        "info": {"props": {"node.name": name, "media.class": media_class, **props}},
    }


def test_node_name_to_id_map():
    state = GraphState()
    state.apply([_node(42, "sonar_game", "Audio/Sink")])
    assert state.node_id("sonar_game") == 42
    assert state.node_name(42) == "sonar_game"
    assert state.node_id("yok") is None


def test_non_node_objects_are_ignored():
    state = GraphState()
    state.apply([{"id": 1, "type": "PipeWire:Interface:Client", "info": {"props": {}}}])
    assert state.nodes == {}


def test_removal_clears_every_inventory():
    state = GraphState()
    state.apply([_node(5, "firefox", "Stream/Output/Audio")])
    assert state.streams
    state.apply([{"id": 5, "type": "PipeWire:Interface:Node", "info": None}])
    assert state.nodes == {} and state.streams == {}


def test_id_reuse_after_restart_does_not_leave_a_stale_name():
    """PipeWire id'leri geri dönüştürür; eski ad haritada kalırsa yanlış node'a yazarız."""
    state = GraphState()
    state.apply([_node(10, "sonar_game", "Audio/Sink")])
    state.apply([_node(10, "sonar_chat", "Audio/Sink")])
    assert state.node_id("sonar_game") is None
    assert state.node_id("sonar_chat") == 10


def test_streams_carry_routing_keys():
    state = GraphState()
    state.apply(
        [
            _node(
                8,
                "firefox",
                "Stream/Output/Audio",
                **{
                    "application.process.binary": "firefox",
                    "application.name": "Firefox",
                    "media.name": "YouTube",
                    "application.process.id": 1234,
                },
            )
        ]
    )
    stream = state.streams[8]
    assert (stream.app_binary, stream.app_name, stream.media_name) == (
        "firefox",
        "Firefox",
        "YouTube",
    )
    assert stream.pid == 1234
    assert stream.is_capture is False
    assert stream.label == "Firefox"


def test_stream_label_falls_back_through_the_keys():
    state = GraphState()
    state.apply([_node(1, "x", "Stream/Output/Audio", **{"media.name": "Bir şey"})])
    assert state.streams[1].label == "Bir şey"
    state.apply([_node(2, "y", "Stream/Output/Audio")])
    assert state.streams[2].label == "#2"


def test_devices_are_collected_with_priority():
    state = GraphState()
    state.apply(
        [
            _node(3, "alsa_input.usb", "Audio/Source", **{"priority.session": 2100}),
            _node(4, "sonar_game_fx", "Audio/Source", **{"priority.session": 0}),
            _node(5, "alsa_output.pci", "Audio/Sink"),
        ]
    )
    assert {d.name for d in state.devices.values()} == {
        "alsa_input.usb",
        "sonar_game_fx",
        "alsa_output.pci",
    }
    assert state.devices[3].is_source and state.devices[3].priority == 2100
    assert state.devices[5].is_source is False


def test_apply_reports_only_what_actually_changed():
    """Aksi hâlde saniyede onlarca olay arayüzü boş yere yeniden çizdirirdi."""
    state = GraphState()
    first = state.apply([_node(1, "sonar_game", "Audio/Sink")])
    assert first == frozenset({GraphState.NODES, GraphState.DEVICES})
    again = state.apply([_node(1, "sonar_game", "Audio/Sink")])
    assert again == frozenset()


def test_nameless_node_does_not_erase_a_known_one():
    state = GraphState()
    state.apply([_node(1, "sonar_game", "Audio/Sink")])
    state.apply([{"id": 1, "type": "PipeWire:Interface:Node", "info": {"props": {}}}])
    assert state.node_id("sonar_game") == 1


def test_reset_empties_everything():
    state = GraphState()
    state.apply([_node(1, "sonar_game", "Audio/Sink"), _node(2, "mpv", "Stream/Output/Audio")])
    state.reset()
    assert not state.nodes and not state.streams and not state.devices


def test_sonar_nodes_filters_our_own():
    state = GraphState()
    state.apply([_node(1, "sonar_game", "Audio/Sink"), _node(2, "alsa_output.pci", "Audio/Sink")])
    assert set(state.sonar_nodes()) == {"sonar_game"}


def test_our_own_loopbacks_are_marked_internal():
    """Kanal→bus loopback'leri de Stream/Output/Audio; kullanıcıya uygulama diye görünmemeli."""
    state = GraphState()
    state.apply(
        [
            _node(1, "sonar_game_to_personal", "Stream/Output/Audio"),
            _node(2, "firefox", "Stream/Output/Audio"),
        ]
    )
    assert state.streams[1].is_internal is True
    assert state.streams[2].is_internal is False


def test_recycled_id_resets_the_seen_timestamp():
    """Yoksa yönlendirme gecikmesi eski akıştan sayılır (ölçümde 3.2 s görüldü)."""
    import time

    state = GraphState()
    state.apply([_node(10, "mpv", "Stream/Output/Audio", **{"object.serial": 100})])
    first = state.stream_seen[10]
    time.sleep(0.01)
    state.apply([_node(10, "firefox", "Stream/Output/Audio", **{"object.serial": 200})])
    assert state.stream_seen[10] > first


def test_same_serial_keeps_the_original_timestamp():
    state = GraphState()
    state.apply([_node(10, "mpv", "Stream/Output/Audio", **{"object.serial": 100})])
    first = state.stream_seen[10]
    state.apply(
        [_node(10, "mpv", "Stream/Output/Audio", **{"object.serial": 100, "media.name": "x"})]
    )
    assert state.stream_seen[10] == first
