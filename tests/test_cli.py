from __future__ import annotations

import json

import pytest

from sonar.cli.__main__ import _print_status, build_parser, main
from sonar.daemon.api import SonarApi
from sonar.daemon.dbus_iface import SonarDBusInterface
from tests.test_api import FakeSupervisor


class LoopbackClient:
    """`sonar-cli`'yi D-Bus'sız test etmek için: çağrıyı doğrudan arayüze bağlar.

    Böylece komut ayrıştırma, argüman dönüşümü ve çıktı biçimi, çalışan bir daemon
    gerektirmeden doğrulanabiliyor.
    """

    def __init__(self, iface: SonarDBusInterface) -> None:
        self.iface = iface
        self.calls: list[tuple] = []

    def call(self, method, *args):
        self.calls.append((method, args))
        payload = json.loads(getattr(self.iface, method)(*args))
        if not payload.get("ok"):
            raise SystemExit(f"hata [{payload.get('code')}]: {payload.get('message')}")
        return payload.get("result")


@pytest.fixture
def cli(config_store, monkeypatch):
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0)
    client = LoopbackClient(SonarDBusInterface(api))
    monkeypatch.setattr("sonar.cli.__main__.Client", lambda: client)
    return client


def run(argv):
    return main(argv)


# --------------------------------------------------------------------------- ayrıştırma


def test_every_subcommand_is_wired():
    """Ayrıştırıcıdaki her komutun bir uygulaması olmalı."""
    from sonar.cli.__main__ import _COMMANDS

    parser = build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert set(actions[0].choices) == set(_COMMANDS)


def test_bus_argument_is_restricted():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["volume", "game", "hayali", "50"])


# --------------------------------------------------------------------------- komutlar


def test_status_prints_a_table(cli, capsys):
    assert run(["status"]) == 0
    out = capsys.readouterr().out
    assert "KANAL" in out and "Game" in out and "Stream Mix" in out


def test_status_json(cli, capsys):
    assert run(["--json", "status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "config" in payload and "streams" in payload


def test_volume_converts_percent_to_linear(cli):
    run(["volume", "game", "personal", "50"])
    assert cli.calls[-1] == ("SetChannelVolume", ("game", "personal", 0.5))
    assert cli.iface.api.config.channel("game").personal.volume == 0.5


def test_master_volume(cli):
    run(["master", "stream", "80"])
    assert cli.iface.api.config.bus("stream").volume == pytest.approx(0.8)


def test_mute_toggle_reads_current_state_first(cli):
    run(["mute", "game", "personal"])
    assert cli.iface.api.config.channel("game").personal.muted is True
    run(["mute", "game", "personal"])
    assert cli.iface.api.config.channel("game").personal.muted is False


def test_mute_explicit(cli):
    run(["mute", "chat", "stream", "on"])
    assert cli.iface.api.config.channel("chat").send("stream").muted is True


def test_mute_toggle_on_unknown_channel_reports_cleanly(cli):
    with pytest.raises(SystemExit) as excinfo:
        run(["mute", "yok", "personal"])
    assert "unknown_channel" in str(excinfo.value)


def test_profile_list_marks_the_active_one(cli, capsys):
    cli.iface.api.save_profile("game", "CS2")
    assert run(["profile", "game"]) == 0
    out = capsys.readouterr().out
    assert "* CS2" in out
    assert "  Default" in out


def test_profile_load(cli):
    cli.iface.api.save_profile("game", "CS2")
    run(["profile", "game", "Default"])
    assert cli.iface.api.config.channel("game").active_profile == "Default"


def test_save_profile(cli):
    run(["save", "game", "Arc Raiders"])
    assert cli.iface.api.config.channel("game").active_profile == "Arc Raiders"


def test_route_adds_a_rule(cli):
    run(["route", "cs2_linux", "game"])
    assert any(r.pattern == "cs2_linux" for r in cli.iface.api.config.rules)


def test_route_regex_flag(cli):
    run(["route", "--key", "media_name", "--regex", "you.?tube", "media"])
    rule = next(r for r in cli.iface.api.config.rules if r.pattern == "you.?tube")
    assert rule.is_regex is True and rule.match_key == "media_name"


def test_rules_list(cli, capsys):
    assert run(["rules"]) == 0
    assert "discord" in capsys.readouterr().out


def test_rules_remove(cli):
    run(["route", "cs2", "game"])
    run(["rules", "--remove", "binary=cs2"])
    assert not [r for r in cli.iface.api.config.rules if r.pattern == "cs2"]


def test_rules_remove_needs_the_equals_form(cli):
    with pytest.raises(SystemExit, match="biçim"):
        run(["rules", "--remove", "cs2"])


def test_chatmix(cli):
    run(["chatmix", "80"])
    assert cli.iface.api.config.chatmix.value == 80.0


def test_move(cli, capsys):
    run(["move", "42", "chat"])
    assert cli.iface.api.supervisor.control.moved == [(42, "sonar_chat")]


def test_devices_lists_physical_ones(cli, capsys):
    cli.iface.api.supervisor.state.apply(
        [
            {
                "id": 1,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "alsa_output.usb",
                        "media.class": "Audio/Sink",
                        "node.description": "Arctis 7",
                    }
                },
            }
        ]
    )
    assert run(["devices"]) == 0
    assert "Arctis 7" in capsys.readouterr().out


def test_device_sets_a_bus_target(cli):
    run(["device", "personal", "alsa_output.usb"])
    assert cli.iface.api.config.bus("personal").device == "alsa_output.usb"


def test_device_mic_flag(cli):
    run(["device", "--mic", "mic", "alsa_input.usb"])
    assert cli.iface.api.config.mic("mic").source_device == "alsa_input.usb"


def test_reload(cli, capsys):
    assert run(["reload"]) == 0
    assert "yeniden okundu" in capsys.readouterr().out


# --------------------------------------------------------------------------- hata yolu


def test_api_errors_become_a_clean_exit(cli):
    with pytest.raises(SystemExit) as excinfo:
        run(["volume", "yok", "personal", "50"])
    assert "unknown_channel" in str(excinfo.value)


def test_status_warns_when_the_graph_is_not_ready(cli, capsys):
    assert run(["status"]) == 0
    assert "Graf henüz hazır değil" in capsys.readouterr().out


def test_status_handles_no_streams(cli, capsys):
    run(["status"])
    assert "(yok)" in capsys.readouterr().out


def test_print_status_survives_a_muted_everything(config_store, capsys):
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0)
    for channel in api.config.channels:
        channel.personal.muted = True
        channel.stream.muted = True
    state = api.get_state()
    _print_status(state)
    assert "M " in capsys.readouterr().out


def test_status_counts_match_what_is_printed(config_store, capsys, monkeypatch):
    """Başlıktaki sayı listelenen satır sayısıyla uyuşmalı; kayıt akışları ayrı sayılır."""
    api = SonarApi(config_store, FakeSupervisor(), save_delay=0)
    api.supervisor.state.apply(
        [
            {
                "id": 1,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "mpv",
                        "media.class": "Stream/Output/Audio",
                        "application.name": "mpv",
                    }
                },
            },
            {
                "id": 2,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "obs",
                        "media.class": "Stream/Input/Audio",
                        "application.name": "OBS",
                    }
                },
            },
        ]
    )
    client = LoopbackClient(SonarDBusInterface(api))
    monkeypatch.setattr("sonar.cli.__main__.Client", lambda: client)
    run(["status"])
    out = capsys.readouterr().out
    assert "ÇALAN UYGULAMALAR (1)" in out
    assert "MİKROFON KULLANANLAR (1)" in out
    assert "OBS" in out


def test_move_remember_flag(cli):
    cli.iface.api.supervisor.state.apply(
        [
            {
                "id": 42,
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {
                        "node.name": "mpv",
                        "media.class": "Stream/Output/Audio",
                        "application.process.binary": "mpv",
                    }
                },
            }
        ]
    )
    run(["move", "42", "chat", "--remember"])
    assert any(r.pattern == "mpv" and r.channel_id == "chat" for r in cli.iface.api.config.rules)


def test_move_without_remember_creates_no_rule(cli):
    before = len(cli.iface.api.config.rules)
    run(["move", "42", "chat"])
    assert len(cli.iface.api.config.rules) == before


def test_meters_subscribes_and_unsubscribes(cli, monkeypatch):
    """Abonelik mutlaka kapatılmalı; yoksa ölçüm süreçleri sonsuza kadar açık kalır."""
    meters = cli.iface.api.meters
    monkeypatch.setattr(meters, "_start_sources", lambda: None)
    monkeypatch.setattr(meters, "_stop_sources", lambda: None)
    monkeypatch.setattr(meters, "_schedule", lambda: None)
    run(["meters", "--seconds", "0"])
    assert [c[0] for c in cli.calls if c[0] == "SubscribeMeters"] == [
        "SubscribeMeters",
        "SubscribeMeters",
    ]
    assert meters.subscribers == 0


def test_meter_bar_maps_the_range():
    from sonar.cli.__main__ import _meter_bar

    assert _meter_bar(0.0).count("█") == 30
    assert _meter_bar(-60.0).count("█") == 0
    assert _meter_bar(-30.0).count("█") == 15
    assert _meter_bar(-999.0).count("█") == 0
