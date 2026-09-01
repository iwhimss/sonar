"""Graf sürecinin yaşam döngüsü ve uzlaştırma (reconcile).

Tek bir `pipewire -c graph.conf` süreci tüm sanal cihazları taşır. Bu modül o süreci
ayakta tutar ve yapılandırma değiştiğinde **doğru** tepkiyi verir:

| Değişiklik | Tepki | Ses |
|---|---|---|
| profil, EQ, filtre, fader, mute, ChatMix, kural | canlı yazım | kesintisiz |
| kanal ekle/sil, cihaz değiştir, band sayısı | conf yeniden yazılır + süreç restart | ~200 ms |

Karar tek bir kurala dayanır: **üretilen conf metni değişti mi?** `engine.confgen`
deterministik olduğu için bu karşılaştırma güvenilir; profil değerleri conf'a hiç
girmediğinden EQ kurcalamak asla restart tetiklemez (`test_confgen.py` bunu doğrular).

Yeniden başlatmadan sonra node id'lerinin tamamı değişir. Bu yüzden restart → node'ların
belirmesini bekle → **tüm** canlı durumu baştan uygula sırası zorunludur; aksi hâlde graf
nötr değerlerle ayakta kalır ve kullanıcının profili sessizce kaybolur.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sonar.core import config as config_mod
from sonar.core.dsp.chain import plan_chain
from sonar.core.dsp.params import db_to_linear, profile_to_params
from sonar.core.model import CHAIN_ORDER, BusId, FilterStage, Profile, SonarConfig
from sonar.engine import confgen
from sonar.engine.control import Control
from sonar.engine.pwstate import GraphState, PwMonitor

__all__ = ["Reconciliation", "Supervisor", "chatmix_gains", "live_params", "live_volumes"]

log = logging.getLogger(__name__)

#: Çökme sonrası bekleme: 1, 2, 4, 8, 16 saniye. Sonrasında pes edilir.
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0)
MAX_CRASHES = len(BACKOFF_SECONDS)

#: Graf sağlık yoklaması aralığı. İki üst üste boş ölçüm yeniden inşayı tetikler, yani
#: PipeWire yeniden başlatıldıktan ~4 sn sonra ses geri gelir.
HEALTH_INTERVAL = 2.0


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """`reconcile()` çağrısının ne yaptığı."""

    rebuilt: bool
    reason: str
    conf_path: Path

    def __bool__(self) -> bool:
        return self.rebuilt


# --------------------------------------------------------------------------- saf hesaplar
#
# Aşağıdaki üç fonksiyon yan etkisizdir: yapılandırmadan "grafın nasıl görünmesi gerektiğini"
# hesaplarlar. Süreç yönetiminden ayrı durmaları, doğru değerlerin PipeWire olmadan
# test edilebilmesini sağlıyor.


def chatmix_gains(cfg: SonarConfig) -> dict[str, float]:
    """ChatMix slider'ının kanal kazançlarına etkisi (lineer çarpan).

    50 = nötr (iki kanal da 1.0). 0'a giderken sohbet, 100'e giderken oyun kısılır.
    Kısılma dB'de doğrusaldır — kulağa doğrusal gelen budur.
    """
    mix = cfg.chatmix
    if not mix.enabled:
        return {}
    tilt = (mix.value - 50.0) / 50.0  # -1 (tam sol) … +1 (tam sağ)
    left_gain = db_to_linear(max(tilt, 0.0) * mix.floor_db)
    right_gain = db_to_linear(max(-tilt, 0.0) * mix.floor_db)
    gains = dict.fromkeys(mix.left(), left_gain)
    gains.update(dict.fromkeys(mix.right(), right_gain))
    return gains


def live_params(
    cfg: SonarConfig, load_profile: Callable[[str, str], Profile]
) -> dict[str, dict[str, float]]:
    """Her DSP node'una yazılacak port değerleri: `{node adı: {port: değer}}`."""
    nodes = confgen.dsp_nodes(cfg)
    stages = _stages_for(mic=False)
    mic_stages = _stages_for(mic=True)
    mic_ids = {mic.id for mic in cfg.mic_chains}
    shared = {mic.id for mic in cfg.mic_chains if mic.share_chain_with_mic}

    out: dict[str, dict[str, float]] = {}
    for target in cfg.profile_targets():
        node = nodes.get(target)
        if node is None or target in shared:
            # Zinciri paylaşan mikrofonun kendi DSP'si yok; birincilinki geçerli.
            continue
        profile = load_profile(target, _active_profile(cfg, target))
        out[node] = profile_to_params(
            profile, stages=mic_stages if target in mic_ids else stages, channels=2
        )
    return out


def live_volumes(cfg: SonarConfig) -> dict[str, tuple[float, bool]]:
    """Her fader node'una yazılacak `(lineer seviye, sustur)` değerleri."""
    gains = chatmix_gains(cfg)
    out: dict[str, tuple[float, bool]] = {}

    for channel in cfg.channels:
        for bus in BusId:
            send = channel.send(bus)
            volume = send.volume
            if bus is BusId.PERSONAL:
                # ChatMix yalnızca kulaklık miksini etkiler; yayın miksine dokunmaz.
                volume *= gains.get(channel.id, 1.0)
            out[channel.loopback_node(bus)] = (volume, send.muted)

    for bus in cfg.buses:
        out[bus.sink_node] = (bus.volume, bus.muted)

    for mic in cfg.mic_chains:
        out[mic.source_node] = (mic.volume, mic.muted)
        if mic.monitor_enabled:
            out[f"{mic.source_node}_monitor"] = (mic.monitor_volume, False)
        if mic.send_to_stream_bus:
            out[f"{mic.source_node}_to_stream"] = (mic.volume, mic.muted)
    return out


def _active_profile(cfg: SonarConfig, target: str) -> str:
    channel = cfg.channel(target)
    if channel is not None:
        return channel.active_profile
    mic = cfg.mic(target)
    if mic is not None:
        return mic.active_profile
    bus = cfg.bus(target)
    return bus.active_profile if bus is not None else "Default"


def _stages_for(*, mic: bool) -> tuple[FilterStage, ...]:
    """Zincirde gerçekten kurulmuş aşamalar — kurulu olmayan eklentiye yazmayalım."""
    wanted = CHAIN_ORDER
    if not mic:
        wanted = tuple(s for s in CHAIN_ORDER if s is not FilterStage.DEEPFILTER)
    return plan_chain(wanted, channels=2).stages


# --------------------------------------------------------------------------- süpervizör


class Supervisor:
    """`pipewire -c graph.conf` sürecini yönetir ve canlı durumu uygular."""

    def __init__(
        self,
        paths: config_mod.Paths | None = None,
        *,
        store: config_mod.ConfigStore | None = None,
        state: GraphState | None = None,
        monitor: PwMonitor | None = None,
        control: Control | None = None,
        spawn: Callable[[Path], subprocess.Popen] | None = None,
        node_timeout: float = 5.0,
        autostart_monitor: bool = True,
    ) -> None:
        self.paths = paths if paths is not None else config_mod.Paths.default()
        self.store = store if store is not None else config_mod.ConfigStore(self.paths)
        self.state = state if state is not None else GraphState()
        self.monitor = monitor if monitor is not None else PwMonitor(self.state)
        self.state = self.monitor.state
        self.control = control if control is not None else Control(self.state)
        self._spawn = spawn if spawn is not None else _spawn_pipewire
        self.node_timeout = node_timeout
        self._autostart_monitor = autostart_monitor

        self._process: subprocess.Popen | None = None
        self._conf_text: str | None = None
        #: En son uzlaştırılan yapılandırma. Çökme sonrası toparlanma **bunu** kullanır,
        #: diski değil: kullanıcının henüz kaydetmediği değişiklikler diskte yoktur ve
        #: diskteki hâl çalışan graftan yapısal olarak farklı bile olabilir.
        self._cfg: SonarConfig | None = None
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._watchdog: threading.Thread | None = None
        self._crashes = 0
        self._previous_default = ""
        #: Profil sağlayıcısı. Varsayılan olarak diskten okur; daemon bunu kendi
        #: bellekteki (henüz kaydedilmemiş) profilleriyle değiştirir — aksi hâlde
        #: kullanıcının canlı düzenlemeleri her yeniden inşada diske geri düşerdi.
        self.load_profile: Callable[[str, str], Profile] = self.store.load_profile
        self.on_rebuild: list[Callable[[], None]] = []
        self.on_failure: list[Callable[[str], None]] = []

    # ------------------------------------------------------------------ ana akış

    def reconcile(self, cfg: SonarConfig) -> Reconciliation:
        """Yapılandırmayı grafa uygular. Gerekiyorsa yeniden inşa eder."""
        text = confgen.generate(cfg)
        with self._lock:
            unchanged = text == self._conf_text and self._is_alive()

        if unchanged:
            self.apply_live(cfg)
            return Reconciliation(False, "canlı yazım", self.paths.graph_conf)

        reason = "ilk kurulum" if self._conf_text is None else "yapısal değişiklik"
        self._rebuild(text, cfg)
        return Reconciliation(True, reason, self.paths.graph_conf)

    def apply_live(self, cfg: SonarConfig) -> None:
        """Tüm parametreleri ve fader'ları grafa yazar.

        Yeniden başlatmadan sonra **her şey** yeniden yazılmalıdır: conf nötr doğar, node
        id'leri değişmiştir ve grafın hiçbir eski değerden haberi yoktur.
        """
        for node, params in live_params(cfg, self.load_profile).items():
            self.control.set_params(node, params)
        self.apply_volumes(cfg, flush=False)
        self.control.flush()

    def apply_volumes(self, cfg: SonarConfig, *, flush: bool = True) -> None:
        """Tüm fader'ları yazar.

        Tek bir fader değişse bile hepsini yazıyoruz: kalıcı `pw-cli` oturumunda yazım
        maliyeti ölçülemeyecek kadar küçük (0.003 ms) ve böylece ChatMix'in iki kanalı
        birden sürmesi gibi bağlı etkiler kendiliğinden doğru çıkıyor.
        """
        for node, (volume, muted) in live_volumes(cfg).items():
            self.control.set_volume(node, volume)
            self.control.set_mute(node, muted)
        if flush:
            self.control.flush()

    def apply_target(self, cfg: SonarConfig, target: str) -> bool:
        """Tek bir hedefin DSP parametrelerini yazar (profil geçişi, EQ dokunuşu)."""
        params = live_params(cfg, self.load_profile).get(confgen.dsp_nodes(cfg).get(target, ""))
        if params is None:
            return False
        self.control.set_params(confgen.dsp_nodes(cfg)[target], params)
        self.control.flush()
        return True

    def start_monitor(self) -> None:
        self.monitor.start()

    def stop(self, *, restore_default_sink: bool = True) -> None:
        """Temiz kapanış: graf süreci öldürülür, varsayılan sink geri alınır."""
        self._stopping.set()
        if restore_default_sink and self._previous_default:
            self.control.set_default_sink(self._previous_default)
        with self._lock:
            process, self._process = self._process, None
            self._conf_text = None
        if process is not None:
            _terminate(process)
        if self._watchdog is not None:
            self._watchdog.join(timeout=2.0)
            self._watchdog = None
        self.control.close()
        self.monitor.stop()

    def take_over_default_sink(self, cfg: SonarConfig) -> None:
        """Sistem varsayılanını Sonar'a alır; önceki değeri kapanışta geri vermek için saklar."""
        if not cfg.settings.take_over_default_sink:
            return
        if not self._previous_default:
            self._previous_default = _current_default_sink()
        target = cfg.channel(cfg.settings.default_channel)
        if target is not None:
            self.control.set_default_sink(target.sink_node)

    # ------------------------------------------------------------------ süreç yönetimi

    def _rebuild(self, text: str, cfg: SonarConfig) -> None:
        self._stopping.clear()  # önceki bir stop() sonrası yeniden kurulabilmeli
        self.paths.graph_conf.parent.mkdir(parents=True, exist_ok=True)
        config_mod.write_atomic(self.paths.graph_conf, text)

        # Eski id'leri süreci öldürmeden ÖNCE al: yeniden başlatmadan sonra aynı adların
        # taze id'lerle geldiğini böyle anlıyoruz.
        stale = self._snapshot_ids(cfg)
        with self._lock:
            previous, self._process = self._process, None
            self._conf_text = text
        if previous is not None:
            _terminate(previous)

        if self._autostart_monitor:
            self.monitor.start()

        process = self._spawn(self.paths.graph_conf)
        with self._lock:
            self._process = process
            self._crashes = 0
            self._cfg = cfg
        self._start_watchdog()

        self._wait_for_graph(cfg, stale)
        self._wire_sends(cfg)
        self.apply_live(cfg)
        for callback in list(self.on_rebuild):
            callback()

    def _expected_nodes(self, cfg: SonarConfig) -> set[str]:
        nodes = set(confgen.dsp_nodes(cfg).values()) | set(live_volumes(cfg))
        for output, target in confgen.send_links(cfg):
            nodes.add(output)
            nodes.add(target)
        return nodes

    def _wire_sends(self, cfg: SonarConfig) -> bool:
        """Kanal çıkışlarını bus gönderilerine bağlar.

        Bu bağlantılar conf'ta `target.object` ile ifade edilemiyor: `_fx` node'u
        `media.class` taşımadığında WirePlumber onu bir kaynak saymıyor ve politika
        motoru bağlamıyor (bkz. `confgen._send_loopback`). Bağlantıyı burada `pw-link`
        ile açıkça kuruyoruz.

        `pw-link` var olan bir bağlantı için de sıfırdan farklı dönebildiği için sonuç
        komutun çıkış koduna değil, `pw-link -l` çıktısına bakılarak doğrulanır.
        """
        wanted = confgen.send_links(cfg)
        if not wanted:
            return True
        for attempt in (1, 2):
            existing = self.control.node_links()
            missing = [pair for pair in wanted if pair not in existing]
            if not missing:
                return True
            for output, target in missing:
                self.control.link_nodes(output, target)
            if attempt == 1:
                time.sleep(0.1)
        remaining = [pair for pair in wanted if pair not in self.control.node_links()]
        if remaining:
            log.error(
                "%d kanal gönderisi bağlanamadı (örnek: %s → %s); o kanalın sesi bus'a "
                "ulaşmaz",
                len(remaining),
                *remaining[0],
            )
            return False
        return True

    def _snapshot_ids(self, cfg: SonarConfig) -> dict[str, int]:
        """Yeniden başlatmadan **önceki** node id'leri."""
        ids = {}
        for name in self._expected_nodes(cfg):
            node_id = self.state.node_id(name)
            if node_id is not None:
                ids[name] = node_id
        return ids

    def _wait_for_graph(self, cfg: SonarConfig, stale: dict[str, int] | None = None) -> bool:
        """Yazacağımız tüm node'ların **taze** id'lerle belirmesini bekler.

        İki tuzak var:

        1. Tek bir node'u beklemek yetmez: conf önce filter-chain'leri, sonra loopback'leri
           kurar; `sonar_game` göründüğünde `sonar_game_to_personal` henüz olmayabilir ve
           o an yazılan fader değeri sessizce kaybolur.
        2. Sadece **adın** haritada olmasını beklemek de yetmez. Süreç öldüğünde silinme
           olayları hemen gelmez; eski ad bir süre daha ölü id'siyle haritada durur.
           `stale` verildiğinde id'nin gerçekten değişmiş olması aranır — aksi hâlde tüm
           canlı durum ölü node'lara yazılır ve kullanıcı için "ayarlarım sıfırlandı" olur.
        """
        expected = self._expected_nodes(cfg)
        if not expected:
            return True
        stale = stale or {}
        deadline = time.monotonic() + self.node_timeout
        while True:
            missing = {
                name
                for name in expected
                if (current := self.state.node_id(name)) is None or current == stale.get(name)
            }
            if not missing:
                return True
            if time.monotonic() >= deadline:
                log.warning(
                    "graf node'ları %.1f sn içinde tazelenmedi (%d eksik, örnek: %s)",
                    self.node_timeout,
                    len(missing),
                    sorted(missing)[0],
                )
                return False
            time.sleep(0.05)

    def _start_watchdog(self) -> None:
        if self._watchdog is not None and self._watchdog.is_alive():
            return
        self._watchdog = threading.Thread(target=self._watch, name="sonar-supervisor", daemon=True)
        self._watchdog.start()

    def _watch(self) -> None:
        """Tek ve uzun ömürlü. Süreç değiştiğinde **ölmez**, yeni sürece geçer.

        Eskiden süreç değişince `return` ediyordu ve `_start_watchdog` "zaten canlı" görüp
        yenisini başlatmıyordu; aradaki yarışta graf gözetimsiz kalabiliyordu.
        """
        while not self._stopping.is_set():
            with self._lock:
                process = self._process
            if process is None:
                if self._stopping.wait(0.2):
                    return
                continue
            if not self._await_trouble(process):
                return
            if self._stopping.is_set():
                return
            if process.poll() is None:
                # Süreç yaşıyor ama node'ları graftan silinmiş: PipeWire yeniden
                # başlatıldı ve istemcimiz bağlantısını geri kuramadı. Kendi başına
                # toparlanmıyor, bu yüzden grafı biz yeniden kuruyoruz.
                log.warning("graf süreci PipeWire bağlantısını kaybetti, yeniden kuruluyor")
                with self._lock:
                    text, cfg = self._conf_text, self._cfg
                if text is None or cfg is None:  # pragma: no cover - reconcile'dan önce
                    return
                self._rebuild(text, cfg)
                continue
            with self._lock:
                if self._process is not process:
                    continue  # yeniden inşa yerine yenisini koydu; izlemeye devam
                self._crashes += 1
                crashes = self._crashes
                text = self._conf_text
            if crashes > MAX_CRASHES or text is None:
                message = f"graf süreci {crashes} kez üst üste çöktü, vazgeçildi"
                log.error(message)
                for callback in list(self.on_failure):
                    callback(message)
                return
            delay = BACKOFF_SECONDS[crashes - 1]
            log.warning("graf süreci düştü, %.0f sn sonra yeniden başlatılıyor", delay)
            with self._lock:
                crashed_cfg = self._cfg
            stale = self._snapshot_ids(crashed_cfg) if crashed_cfg is not None else {}
            if self._stopping.wait(delay):
                return
            try:
                restarted = self._spawn(self.paths.graph_conf)
            except OSError:
                log.exception("graf süreci yeniden başlatılamadı")
                return
            with self._lock:
                self._process = restarted
            self._after_restart(stale)

    def _await_trouble(self, process: subprocess.Popen) -> bool:
        """Süreç ölene **veya** node'ları graftan kaybolana kadar bekler.

        `process.wait()` yetmiyor: `systemctl --user restart pipewire` bizim
        `pipewire -c` istemcimizi öldürmüyor, yalnızca bağlantısını koparıyor. Süreç
        canlı görünürken graf boş kalıyor ve hiçbir şey bunu fark etmiyordu (ölçüldü:
        yeniden başlatmadan 15 sn sonra 0 sonar node'u).

        `False` döner: durduruluyoruz.
        """
        vanished = 0
        while not self._stopping.is_set():
            if process.poll() is not None:
                return True
            if self._graph_is_empty():
                vanished += 1
                # İki üst üste ölçüm: kendi yeniden inşamızın ortasına denk gelmeyelim.
                if vanished >= 2:
                    return True
            else:
                vanished = 0
            if self._stopping.wait(HEALTH_INTERVAL):
                return False
        return False

    def _graph_is_empty(self) -> bool:
        """Beklediğimiz node'ların **hiçbiri** grafta yok mu?"""
        with self._lock:
            cfg = self._cfg
        if cfg is None:
            return False
        expected = self._expected_nodes(cfg)
        return bool(expected) and not any(self.state.node_id(name) for name in expected)

    def _after_restart(self, stale: dict[str, int]) -> None:
        """Çökme sonrası kendini toparlama: son uygulanan durumu baştan yaz."""
        with self._lock:
            cfg = self._cfg
        if cfg is None:  # pragma: no cover - reconcile'dan önce çökme
            return
        self._wait_for_graph(cfg, stale)
        self._wire_sends(cfg)
        self.apply_live(cfg)
        for callback in list(self.on_rebuild):
            callback()

    def _is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None


# --------------------------------------------------------------------------- alt süreçler


def _spawn_pipewire(conf: Path) -> subprocess.Popen:
    return subprocess.Popen(
        ["pipewire", "-c", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _terminate(process: subprocess.Popen, timeout: float = 3.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:  # pragma: no cover - nadir
        process.kill()
        process.wait(timeout=timeout)


def _current_default_sink() -> str:
    try:
        result = subprocess.run(
            ["pactl", "get-default-sink"], capture_output=True, text=True, timeout=5, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""
