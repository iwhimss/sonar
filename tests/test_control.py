from __future__ import annotations

import time

import pytest

from sonar.engine.control import Control, PwCliSession, format_params, format_value
from sonar.engine.pwstate import GraphState


class FakeSession:
    """Gerçek `pw-cli` yerine gönderilen komutları toplar."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, line: str) -> bool:
        self.sent.append(line)
        return True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def state():
    graph = GraphState()
    graph.apply(
        [
            {
                "id": 42,
                "type": "PipeWire:Interface:Node",
                "info": {"props": {"node.name": "sonar_game", "media.class": "Audio/Sink"}},
            }
        ]
    )
    return graph


@pytest.fixture
def control(state):
    session = FakeSession()
    return Control(state, session, window_ms=0)  # penceresiz: yazımlar anında gider


# --------------------------------------------------------------------------- biçimlendirme


def test_value_format_is_locale_independent():
    """Sabit ondalık biçim — `pw-cli` yerel ayarın virgülünü kabul etmez."""
    assert format_value(1.5) == "1.500000"
    assert format_value(2) == "2.000000"
    assert format_value(True) == "true"
    assert format_value(False) == "false"


def test_params_format_matches_pw_cli_syntax():
    assert format_params({"eq:g_3": 2.0}) == '{ params = [ "eq:g_3" 2.000000 ] }'


def test_params_format_keeps_quoted_port_names():
    """DeepFilterNet'in port adında boşluk ve parantez var."""
    text = format_params({"df:Attenuation Limit (dB)": 40.0})
    assert '"df:Attenuation Limit (dB)" 40.000000' in text


# --------------------------------------------------------------------------- yazım


def test_set_params_resolves_the_node_id(control):
    control.set_param("sonar_game", "eq:g_3", 2.0)
    assert control.session.sent == ['set-param 42 Props { params = [ "eq:g_3" 2.000000 ] }']


def test_unknown_node_is_skipped_not_raised(control):
    """Graf yeniden kurulurken node henüz belirmemiş olabilir; çökmemeliyiz."""
    control.set_param("sonar_yok", "eq:g_3", 2.0)
    assert control.session.sent == []


def test_empty_params_send_nothing(control):
    control.set_params("sonar_game", {})
    assert control.session.sent == []


def test_volume_is_linear_not_cubic(control):
    """`wpctl` kübik ölçek uygular (0.5 → -18 dB); biz lineer yazıyoruz (0.5 → -6.02 dB)."""
    control.set_volume("sonar_game", 0.5)
    assert control.session.sent == [
        "set-param 42 Props { channelVolumes = [ 0.500000, 0.500000 ] }"
    ]


def test_negative_volume_is_clamped(control):
    control.set_volume("sonar_game", -1.0)
    assert "0.000000" in control.session.sent[0]


def test_mute(control):
    control.set_mute("sonar_game", True)
    assert control.session.sent == ["set-param 42 Props { mute = true }"]


# --------------------------------------------------------------------------- toplu yazım
#
# Ölçüm: kalıcı oturumda bir yazım 0.003 ms, süreç açmak 14 ms. Toplu yazımın asıl kazancı
# PipeWire tarafındaki gereksiz yeniden hesabı azaltmak.


def test_writes_inside_the_window_are_coalesced(state):
    session = FakeSession()
    control = Control(state, session, window_ms=30)
    for value in range(10):
        control.set_param("sonar_game", "eq:g_3", float(value))
    assert session.sent == [], "pencere dolmadan gönderilmemeli"
    control.flush()
    assert len(session.sent) == 1
    assert "9.000000" in session.sent[0], "son değer kazanmalı"


def test_different_ports_are_merged_into_one_call(state):
    session = FakeSession()
    control = Control(state, session, window_ms=30)
    control.set_param("sonar_game", "eq:g_3", 1.0)
    control.set_param("sonar_game", "eq:f_3", 1000.0)
    control.flush()
    assert len(session.sent) == 1
    assert '"eq:g_3"' in session.sent[0] and '"eq:f_3"' in session.sent[0]


def test_timer_flushes_without_an_explicit_call(state):
    session = FakeSession()
    control = Control(state, session, window_ms=10)
    control.set_param("sonar_game", "eq:g_3", 3.0)
    deadline = time.monotonic() + 2.0
    while not session.sent and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.sent, "zamanlayıcı boşaltmayı tetiklemeliydi"


def test_pending_is_reported(state):
    control = Control(state, FakeSession(), window_ms=1000)
    control.set_param("sonar_game", "eq:g_3", 1.0)
    control.set_volume("sonar_game", 0.5)
    assert control.pending_nodes() == frozenset({"sonar_game"})
    control.flush()
    assert control.pending_nodes() == frozenset()


def test_close_flushes_then_closes(state):
    session = FakeSession()
    control = Control(state, session, window_ms=1000)
    control.set_param("sonar_game", "eq:g_3", 1.0)
    control.close()
    assert session.sent and session.closed


# --------------------------------------------------------------------------- nadir işlemler


def test_move_stream_uses_pactl(state):
    calls: list[list[str]] = []
    control = Control(
        state, FakeSession(), window_ms=0, runner=lambda argv: calls.append(argv) or True
    )
    assert control.move_stream(77, "sonar_chat") is True
    assert calls == [["pactl", "move-sink-input", "77", "sonar_chat"]]


def test_set_default_sink_prefers_the_resolved_id(state):
    calls: list[list[str]] = []
    control = Control(
        state, FakeSession(), window_ms=0, runner=lambda argv: calls.append(argv) or True
    )
    control.set_default_sink("sonar_game")
    assert calls == [["wpctl", "set-default", "42"]]


def test_failing_command_is_reported_not_raised(state):
    control = Control(state, FakeSession(), window_ms=0, runner=lambda _argv: False)
    assert control.move_stream(1, "sonar_game") is False


# --------------------------------------------------------------------------- oturum


def test_session_reopens_after_the_process_dies():
    """`pw-cli` ölürse bir sonraki yazım sessizce yeni bir oturum açmalı."""
    session = PwCliSession(command=("cat",))  # `cat` stdin'i sessizce yutar
    assert session.send("bir") is True
    session._process.kill()
    session._process.wait()
    assert session.send("iki") is True
    session.close()


def test_missing_binary_is_reported_not_raised():
    session = PwCliSession(command=("bu-komut-yok-12345",))
    assert session.send("herhangi bir şey") is False
