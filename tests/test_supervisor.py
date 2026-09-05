from __future__ import annotations

import subprocess
import threading

import pytest

from sonar.core.config import ConfigStore
from sonar.core.dsp.params import db_to_linear
from sonar.core.model import default_config, default_profile
from sonar.engine import confgen
from sonar.engine.control import Control
from sonar.engine.pwstate import GraphState, PwMonitor
from sonar.engine.supervisor import Supervisor, chatmix_gains, live_params, live_volumes

# --------------------------------------------------------------------------- ChatMix


def test_chatmix_is_neutral_at_fifty():
    config = default_config()
    assert config.chatmix.value == 50.0
    assert all(gain == pytest.approx(1.0) for gain in chatmix_gains(config).values())


def test_chatmix_attenuates_only_one_side():
    config = default_config()
    config.chatmix.value = 100.0  # tam sohbet
    gains = chatmix_gains(config)
    assert gains["game"] == pytest.approx(db_to_linear(config.chatmix.floor_db))
    assert gains["chat"] == pytest.approx(1.0)

    config.chatmix.value = 0.0  # tam oyun
    gains = chatmix_gains(config)
    assert gains["game"] == pytest.approx(1.0)
    assert gains["chat"] == pytest.approx(db_to_linear(config.chatmix.floor_db))


def test_disabled_chatmix_changes_nothing():
    config = default_config()
    config.chatmix.enabled = False
    config.chatmix.value = 100.0
    assert chatmix_gains(config) == {}
    assert live_volumes(config)["sonar_game_to_personal"][0] == pytest.approx(1.0)


def test_chatmix_never_touches_the_stream_mix():
    """Yayın miksi kullanıcının kulaklık dengesinden etkilenmemeli."""
    config = default_config()
    config.chatmix.value = 100.0
    volumes = live_volumes(config)
    assert volumes["sonar_game_to_stream"][0] == pytest.approx(1.0)
    assert volumes["sonar_game_to_personal"][0] < 0.05


# --------------------------------------------------------------------------- canlı değerler


def test_live_volumes_cover_every_fader():
    volumes = live_volumes(default_config())
    for channel in ("game", "chat", "media", "aux"):
        assert f"sonar_{channel}_to_personal" in volumes
        assert f"sonar_{channel}_to_stream" in volumes
    assert "sonar_personal" in volumes and "sonar_stream" in volumes
    assert "sonar_mic" in volumes and "sonar_stream_mic" in volumes


def test_optional_mic_sends_are_always_present_but_muted_when_off():
    """Loopback'ler conf'ta her zaman kurulu; açma/kapama bir mute yazımı.

    Eskiden conf'a bağlıydı, yani sidetone'u açmak grafı yeniden kurup çalan sesi
    kesiyordu (test turu 2).
    """
    config = default_config()
    config.mic("mic").send_to_stream_bus = False
    off = live_volumes(config)
    assert off["sonar_mic_monitor"][1] is True
    assert off["sonar_mic_to_stream"][1] is True

    config.mic("mic").monitor_enabled = True
    config.mic("mic").send_to_stream_bus = True
    on = live_volumes(config)
    assert on["sonar_mic_monitor"] == (0.5, False)
    assert on["sonar_mic_to_stream"][1] is False


def test_mic_reaches_the_stream_mix_by_default():
    """Test turu 4: varsayılan **açık**.

    Resmî OBS kurulumu tek kaynak (yayın miksinin monitörü); o kaynakta mikrofon yoksa
    yayında ses duyulmuyor ve mikrofonun yayın fader'ı ölü görünüyor.
    """
    assert live_volumes(default_config())["sonar_mic_to_stream"][1] is False


def test_mute_travels_with_the_volume():
    config = default_config()
    config.channel("chat").stream.muted = True
    assert live_volumes(config)["sonar_chat_to_stream"] == (1.0, True)


def test_live_params_target_the_dsp_nodes(config_store: ConfigStore):
    config = config_store.load()
    params = live_params(config, config_store.load_profile)
    assert set(params) == set(confgen.dsp_nodes(config).values())
    # DSP portları capture node'unda; mikrofonda ayrı bir `_capture` node'u var
    assert "sonar_mic_capture" in params
    assert "sonar_mic" not in params


def test_live_params_use_the_active_profile(config_store: ConfigStore):
    config = config_store.load()
    boosted = default_profile("Bass Boost")
    boosted.eq.enabled = True
    boosted.eq.bands[0].gain_db = 6.0
    config_store.save_profile("game", boosted)
    config.channel("game").active_profile = "Bass Boost"

    params = live_params(config, config_store.load_profile)
    assert params["sonar_game"]["eq:enabled"] == 1.0
    assert params["sonar_game"]["eq:g_0"] == pytest.approx(db_to_linear(6.0))
    # dokunulmamış kanal nötr kalmalı
    assert params["sonar_chat"]["eq:enabled"] == 0.0


def test_only_the_mic_chain_gets_deepfilter_params(config_store: ConfigStore):
    """Şema 7: efektler profilden geliyor, o yüzden önce zincire ekleniyorlar.

    Gürültü engelleme oynatma zincirinde anlamsız; profile elle yazılsa bile
    `confgen.effect_slots` onu süzüyor.
    """
    from sonar.core.model import EffectSlot, FilterStage

    config = config_store.load()

    def with_deepfilter(target: str, name: str):
        profile = config_store.load_profile(target, name)
        profile.effects.append(EffectSlot(kind=FilterStage.DEEPFILTER, slot="df"))
        return profile

    params = live_params(config, with_deepfilter)
    assert any(key.startswith("df:") for key in params["sonar_mic_capture"])
    assert not any(key.startswith("df:") for key in params["sonar_game"])


def test_shared_mic_chain_is_not_written_twice(config_store: ConfigStore):
    """Zinciri paylaşan mikrofonun kendi DSP'si yok; ona yazmak boşa giderdi."""
    config = config_store.load()
    config.mic("stream_mic").share_chain_with_mic = True
    params = live_params(config, config_store.load_profile)
    assert "sonar_stream_mic_capture" not in params
    assert "sonar_stream_mic" not in params


# --------------------------------------------------------------------------- uzlaştırma
#
# Faz 3'ün asıl sorusu: ne zaman yeniden inşa, ne zaman canlı yazım?


class FakeProcess:
    def __init__(self) -> None:
        self._alive = True
        self._exited = threading.Event()
        self.terminated = False

    def poll(self):
        return None if self._alive else 0

    def wait(self, timeout=None):
        self._exited.wait(timeout)
        return 0

    def terminate(self):
        self.terminated = True
        self._alive = False
        self._exited.set()

    def kill(self):
        self.terminate()

    def die(self):
        self._alive = False
        self._exited.set()


class FakeSession:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, line: str) -> bool:
        self.sent.append(line)
        return True

    def close(self) -> None:
        pass


@pytest.fixture
def supervisor(config_store, monkeypatch):
    """Gerçek PipeWire olmadan: süreç sahte, node haritası önceden dolu."""
    state = GraphState()
    config = config_store.load()
    expected = sorted(set(confgen.dsp_nodes(config).values()) | set(live_volumes(config)))
    for output, target in confgen.send_links(config):
        expected += [output, target]
    expected = sorted(set(expected))
    for index, name in enumerate(expected, start=100):
        state.apply(
            [
                {
                    "id": index,
                    "type": "PipeWire:Interface:Node",
                    "info": {"props": {"node.name": name, "media.class": "Audio/Sink"}},
                }
            ]
        )
    monitor = PwMonitor(state)
    monkeypatch.setattr(monitor, "start", lambda: None)
    monkeypatch.setattr(monitor, "stop", lambda timeout=2.0: None)

    session = FakeSession()
    spawned: list[FakeProcess] = []
    # `pw-link` gerçekten çalıştırılmasın: testler geliştiricinin ses grafına dokunmamalı.
    linked: list[tuple[str, str]] = []
    #: `sup._link_ok = False` → `pw-link` çağrılıyor ama bağlantı kurulmuyor.
    #: Bekçinin "onaramadım" yolunu test etmek için.
    link_ok = {"value": True}

    def run(argv: list[str]) -> bool:
        if argv[:1] == ["pw-link"]:
            if not link_ok["value"]:
                return False
            linked.append((argv[1], argv[2]))
        return True

    def capture(_argv: list[str]) -> str:
        return "".join(f"{a}:out_FL\n  |-> {b}:input_FL\n" for a, b in linked)

    def spawn(_conf):
        process = FakeProcess()
        spawned.append(process)
        return process

    sup = Supervisor(
        config_store.paths,
        store=config_store,
        state=state,
        monitor=monitor,
        control=Control(state, session, window_ms=0, runner=run, capturer=capture),
        spawn=spawn,
        node_timeout=0.5,
        autostart_monitor=False,
    )
    sup._spawned = spawned  # type: ignore[attr-defined]
    sup._session = session  # type: ignore[attr-defined]
    sup._linked = linked  # type: ignore[attr-defined]
    sup._link_ok = link_ok  # type: ignore[attr-defined]
    return sup


def test_first_reconcile_builds_the_graph(supervisor, config_store):
    result = supervisor.reconcile(config_store.load())
    assert result.rebuilt is True
    assert result.reason == "ilk kurulum"
    assert config_store.paths.graph_conf.exists()
    assert len(supervisor._spawned) == 1
    supervisor.stop(restore_default_sink=False)


def test_profile_change_does_not_restart_the_process(supervisor, config_store):
    """Kullanıcının en sık yaptığı şey bu; burada restart olursa ses kesilir."""
    config = config_store.load()
    supervisor.reconcile(config)
    config.channel("game").active_profile = "CS2"
    result = supervisor.reconcile(config)
    assert result.rebuilt is False
    assert result.reason == "canlı yazım"
    assert len(supervisor._spawned) == 1, "süreç yeniden başlatılmamalıydı"
    supervisor.stop(restore_default_sink=False)


def test_volume_change_does_not_restart_the_process(supervisor, config_store):
    config = config_store.load()
    supervisor.reconcile(config)
    config.channel("game").output.volume = 0.25
    supervisor.reconcile(config)
    assert len(supervisor._spawned) == 1
    assert any("0.250000" in line for line in supervisor._session.sent)
    supervisor.stop(restore_default_sink=False)


def test_adding_a_channel_restarts_the_process(supervisor, config_store):
    from sonar.core.model import Channel

    config = config_store.load()
    supervisor.reconcile(config)
    config.channels.append(Channel(id="music", name="Music", color="#fff", order=4))
    result = supervisor.reconcile(config)
    assert result.rebuilt is True
    assert result.reason == "yapısal değişiklik"
    assert len(supervisor._spawned) == 2
    assert supervisor._spawned[0].terminated
    supervisor.stop(restore_default_sink=False)


def test_rebuild_reapplies_the_whole_live_state(supervisor, config_store):
    """Conf nötr doğar ve node id'leri değişir; her şey baştan yazılmalı."""
    config = config_store.load()
    config.channel("game").output.volume = 0.4
    supervisor.reconcile(config)
    sent = "\n".join(supervisor._session.sent)
    assert "eq:enabled" in sent
    assert "0.400000" in sent
    assert sent.count("channelVolumes") >= len(live_volumes(config))
    supervisor.stop(restore_default_sink=False)


def test_rebuild_notifies_listeners(supervisor, config_store):
    seen: list[int] = []
    supervisor.on_rebuild.append(lambda: seen.append(1))
    supervisor.reconcile(config_store.load())
    assert seen == [1]
    supervisor.stop(restore_default_sink=False)


def test_dead_process_forces_a_rebuild_even_with_identical_conf(supervisor, config_store):
    config = config_store.load()
    supervisor.reconcile(config)
    supervisor._spawned[0].die()
    supervisor._stopping.set()  # watchdog'u karıştırma, kararı reconcile versin
    result = supervisor.reconcile(config)
    assert result.rebuilt is True
    supervisor.stop(restore_default_sink=False)


def test_stop_terminates_the_process(supervisor, config_store):
    supervisor.reconcile(config_store.load())
    process = supervisor._spawned[0]
    supervisor.stop(restore_default_sink=False)
    assert process.terminated


def test_graph_conf_is_written_atomically(supervisor, config_store):
    supervisor.reconcile(config_store.load())
    directory = config_store.paths.graph_conf.parent
    assert list(directory.glob(".*tmp")) == []
    assert "libpipewire-module-filter-chain" in config_store.paths.graph_conf.read_text()
    supervisor.stop(restore_default_sink=False)


def test_default_sink_is_restored_on_shutdown(supervisor, config_store, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(supervisor.control, "_run", lambda argv: calls.append(list(argv)) or True)
    monkeypatch.setattr("sonar.engine.supervisor._current_default_sink", lambda: "alsa_output.eski")

    config = config_store.load()
    config.settings.take_over_default_sink = True
    supervisor.reconcile(config)
    supervisor.take_over_default_sink(config)
    supervisor.stop()

    assert ["wpctl", "set-default", "alsa_output.eski"] in calls


def test_takeover_is_a_no_op_when_disabled(supervisor, config_store, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(supervisor.control, "_run", lambda argv: calls.append(list(argv)) or True)
    config = config_store.load()
    assert config.settings.take_over_default_sink is False
    supervisor.take_over_default_sink(config)
    assert calls == []


def test_missing_pipewire_binary_surfaces_as_an_error(config_store):
    sup = Supervisor(config_store.paths, store=config_store, autostart_monitor=False)
    sup._spawn = lambda _conf: (_ for _ in ()).throw(FileNotFoundError("pipewire"))
    with pytest.raises(FileNotFoundError):
        sup.reconcile(config_store.load())


def test_spawn_command_shape():
    """Gerçek spawn'ı çalıştırmadan komutunu doğrula."""
    import inspect

    from sonar.engine.supervisor import _spawn_pipewire

    source = inspect.getsource(_spawn_pipewire)
    assert '"pipewire", "-c"' in source
    assert subprocess.Popen is not None


def test_watchdog_survives_a_rebuild(supervisor, config_store):
    """Süreç değişince gözetmen ölmemeli; eskiden ölüyordu ve graf gözetimsiz kalıyordu."""
    from sonar.core.model import Channel

    config = config_store.load()
    supervisor.reconcile(config)
    watchdog = supervisor._watchdog
    config.channels.append(Channel(id="music", name="Music", color="#fff", order=4))
    supervisor.reconcile(config)
    assert supervisor._watchdog is watchdog
    assert watchdog.is_alive(), "yeniden inşadan sonra gözetmen hâlâ çalışmalı"
    supervisor.stop(restore_default_sink=False)


def test_crash_recovery_uses_the_last_applied_config_not_the_disk(supervisor, config_store):
    """Kullanıcı henüz kaydetmediyse diskteki hâl yanlıştır — hatta graftan farklı olabilir."""
    config = config_store.load()
    config.channel("game").output.volume = 0.33  # bilinçli olarak KAYDEDİLMİYOR
    supervisor.reconcile(config)
    assert supervisor._cfg is config

    supervisor._session.sent.clear()
    supervisor._spawned[-1].die()
    deadline = __import__("time").monotonic() + 5.0
    while len(supervisor._spawned) < 2 and __import__("time").monotonic() < deadline:
        __import__("time").sleep(0.05)
    assert len(supervisor._spawned) == 2, "gözetmen yeniden başlatmalıydı"

    deadline = __import__("time").monotonic() + 5.0
    while "0.330000" not in "\n".join(supervisor._session.sent):
        if __import__("time").monotonic() > deadline:
            raise AssertionError("kaydedilmemiş fader değeri geri gelmedi")
        __import__("time").sleep(0.05)
    supervisor.stop(restore_default_sink=False)


# --------------------------------------------------------------------------- gönderi bağlantıları


def test_rebuild_wires_every_send(supervisor, config_store):
    """Gönderiler conf'ta `target.object` ile ifade edilemiyor; `pw-link` ile kuruluyor."""
    config = config_store.load()
    supervisor.reconcile(config)
    assert sorted(supervisor._linked) == sorted(confgen.send_links(config))
    supervisor.stop(restore_default_sink=False)


def test_existing_links_are_not_duplicated(supervisor, config_store):
    config = config_store.load()
    supervisor.reconcile(config)
    before = len(supervisor._linked)
    assert supervisor.reconcile_links(config) == []
    assert len(supervisor._linked) == before
    supervisor.stop(restore_default_sink=False)


def test_link_keeper_repairs_a_missing_link(supervisor, config_store):
    """Bekçinin asıl işi: bağlantı sonradan kopsa da geri kuruluyor.

    Eskiden bu tek atışlıktı; tutmazsa kanal sessizce susuyordu ve kullanıcıya
    hiçbir işaret gitmiyordu (test turu 2, "hiç ses gelmiyor").
    """
    config = config_store.load()
    supervisor.reconcile(config)
    lost = confgen.send_links(config)[0]
    supervisor._linked.remove(lost)

    assert supervisor.reconcile_links(config) == []
    assert lost in supervisor._linked
    supervisor.stop(restore_default_sink=False)


def test_link_keeper_reports_what_it_cannot_fix(supervisor, config_store):
    config = config_store.load()
    supervisor.reconcile(config)
    seen: list[list[tuple[str, str]]] = []
    supervisor.on_links_changed.append(seen.append)

    supervisor._link_ok["value"] = False  # bağlantı kurulamıyor
    lost = confgen.send_links(config)[0]
    supervisor._linked.remove(lost)
    # Yeniden kurulumun yerleşme penceresi kapansın: orada eksiklik **beklenen** ve
    # bilinçli olarak sayılmıyor (bkz. `REBUILD_SETTLE_SECONDS`).
    supervisor._settle_until = 0.0
    for _ in range(3):
        supervisor.reconcile_links(config)

    assert supervisor.broken_links == [lost]
    assert seen == [[lost]]  # eşik aşılınca **bir kez** haber verilir
    supervisor.stop(restore_default_sink=False)


def test_a_rebuild_does_not_raise_a_false_alarm(supervisor, config_store):
    """Yeniden kurulumda tüm linkler bir an yok olur; bu bir kopukluk değil.

    Test turu 7: kullanıcı efekt ekledikçe "ses yolu koptu" ve ardından "Ses yolu
    onarıldı." bildirimi alıyordu. Bekçi yeniden kurulumun geçici eksikliğini gerçek bir
    kopukluk sanıyordu.
    """
    config = config_store.load()
    supervisor.reconcile(config)
    seen: list[list[tuple[str, str]]] = []
    supervisor.on_links_changed.append(seen.append)

    supervisor._link_ok["value"] = False
    lost = confgen.send_links(config)[0]
    supervisor._linked.remove(lost)
    for _ in range(5):  # eşiğin iki katı
        supervisor.reconcile_links(config)

    assert seen == [], "yerleşme penceresinde uyarı çıkmamalı"
    # Pencere dolunca gerçek bir kopukluk yine bildirilir.
    supervisor._settle_until = 0.0
    for _ in range(3):
        supervisor.reconcile_links(config)
    assert seen == [[lost]]
    supervisor.stop(restore_default_sink=False)


# --------------------------------------------------------------------------- tek çıkış
#
# Bir dönem kanal başına ayrı çıkış bus'ı vardı (Faz 20); kullanıcı karışıklık ürettiği
# için geri alındı (Faz 27). Artık tek çıkış + tek yayın bus'ı var ve kanalın çıkış
# gönderisi her zaman varsayılan bus'a gidiyor.


def test_every_channel_feeds_the_single_output_bus():
    config = default_config()
    volumes = live_volumes(config)
    for channel in ("game", "chat", "media", "aux"):
        assert volumes[f"sonar_{channel}_to_personal"][1] is False
        assert volumes[f"sonar_{channel}_to_stream"][1] is False


def test_chatmix_applies_on_the_output_send_only():
    config = default_config()
    config.chatmix.value = 100.0  # tam sağ: oyun kısılır
    volumes = live_volumes(config)

    assert volumes["sonar_game_to_personal"][0] < 0.02  # -40 dB taban
    assert volumes["sonar_chat_to_personal"][0] == pytest.approx(1.0)
    # Yayın miksi ChatMix'ten etkilenmez.
    assert volumes["sonar_game_to_stream"][0] == pytest.approx(1.0)


# --------------------------------------------------------------------------- Smart Volume


def test_ducking_gain_multiplies_the_output_send():
    """ChatMix ile **çarpılarak** birleşiyor; ikisi de aynı gönderiye uygulanıyor."""
    config = default_config()
    volumes = live_volumes(config, {"media": 0.25})
    assert volumes["sonar_media_to_personal"][0] == pytest.approx(0.25)
    # Yayın miksi ducking'den etkilenmez: dinleyici sohbeti zaten ayrı duyuyor.
    assert volumes["sonar_media_to_stream"][0] == pytest.approx(1.0)
