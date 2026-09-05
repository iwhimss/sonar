"""Daemon'un iş mantığı — D-Bus'tan bağımsız.

Plan `service.py` + `dbus_iface.py` diyordu; araya bu modül eklendi. Sebep: tüm doğrulama,
mutasyon ve kalıcılık mantığı burada saf Python olarak durunca Qt olay döngüsü, D-Bus
oturumu veya çalışan bir PipeWire olmadan test edilebiliyor. `dbus_iface.py` yalnızca ince
bir sarmalayıcı.

## Hata bildirimi neden JSON zarfı

`QDBusContext.sendErrorReply()` PySide6 6.11.2'de **segfault ediyor** (ölçüldü: çıkış kodu
139, süreç ölüyor). Yani native D-Bus hatası kullanılamıyor — kullanılsaydı her geçersiz
argüman daemon'ı düşürürdü. Bunun yerine **her metot bir JSON zarfı** döndürür:

```json
{"ok": true,  "...": ...}
{"ok": false, "code": "unknown_channel", "message": "böyle bir kanal yok: xyz"}
```

Yan faydası: `busctl` çıktısı okunabilir kalıyor ve API sürüm değiştirdiğinde eski
istemciler kırılmıyor.

## Profil düzenleme semantiği

Kullanıcı EQ'yu kurcaladığında değişiklik **aktif profile** yazılır — anında grafa, 500 ms
gecikmeyle diske. "Kaydet" demeyi unutmak ayarların kaybolması anlamına gelmez.

`save_profile(target, ad)` bir **"farklı kaydet"**tir: çalışılan kopyayı yeni bir adla yazar
ve aktif profili ona çevirir. Eski profil o âna kadarki hâliyle kalır.

## Gömülü presetler salt okunur

`Flat`, `FPS Footsteps`, `Broadcast`… kod içinde tanımlı ve **diske yazılmaz**. Kullanıcı
salt okunur bir preset aktifken bir şeyi kurcalarsa, önce `"<ad> (özel)"` adıyla bir kopya
oluşturulup ona geçilir; preset bozulmaz.

Bu, otomatik kalıcılığın kaçınılmaz sonucu: düzenleme aktif profile yazıldığı için, kopya
alınmasaydı preset'in kendisi değişirdi. (Faz 8'de tam bu yüzden bir ölçüm kirlendi.)

## Canlı mı, yapısal mı

Her mutasyon ikisinden biridir:

* **Canlı** — fader, mute, EQ, filtre, profil, ChatMix, kural. Yalnızca ilgili node'a yazılır,
  ses kesilmez.
* **Yapısal** — kanal ekle/sil, kanal başına OBS kaynağı. `graph.conf` değişir, süreç
  yeniden başlar (~200 ms).

Mikrofon monitörü (sidetone) ve yayına gönderi bir dönem yapısaldı; her ikisinin
`loopback` modülü artık conf'ta **koşulsuz** kurulu olduğu için açma/kapama tek bir mute
yazımı, yani canlı. Cihaz değişimi de canlı: hedef conf'a yazılmıyor, `pw-metadata` ile
veriliyor.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import threading
import time
from collections.abc import Callable
from typing import Any

from sonar.core import config as config_mod
from sonar.core import i18n, importers, presets, serde
from sonar.core.dsp import registry
from sonar.core.dsp.chain import plan_chain
from sonar.core.model import (
    CHAIN_ORDER,
    DEFAULT_FILTER_PARAMS,
    EQ_FREQ_MAX,
    EQ_FREQ_MIN,
    MIC_ONLY_STAGES,
    PLAYBACK_ONLY_STAGES,
    STREAM_BUS,
    Channel,
    EffectSlot,
    EqBand,
    EqBandType,
    FilterStage,
    MatchKey,
    MicChain,
    Profile,
    RoutingRule,
    SonarConfig,
    StreamDirection,
    default_band_q,
    default_config,
    default_profile,
    slugify,
)
from sonar.engine import confgen
from sonar.engine.ducking import Ducker
from sonar.engine.headset import ChatMixReader, detect_headsets
from sonar.engine.meters import Level, MeterManager, meter_sources
from sonar.engine.router import Decision, Router, target_node_for
from sonar.engine.supervisor import Supervisor, chatmix_gains

__all__ = ["ApiError", "SonarApi", "envelope"]

log = logging.getLogger(__name__)

#: Yapılandırmayı diske yazmadan önce beklenen süre. Fader sürüklerken her hareket için
#: diske yazmak anlamsız; kullanıcı durunca tek yazım yeter.
SAVE_DELAY = 0.5

_EQ_FIELDS = frozenset({"freq", "gain_db", "q", "band_type", "slope", "enabled"})

#: Sistem geneli ses işleyen, bizimle aynı işi yapmaya çalışan araçlar.
#:
#: EasyEffects "service mode"da çalışırken **her** oynatma akışını kendi sink'ine çekiyor —
#: `target.object` ile açıkça bir cihaz istesek bile. Ölçüldü: `pactl move-sink-input`
#: hatasız dönüyor ama bağlantı anında `easyeffects_sink`'e geri alınıyor. Sonuç: kullanıcı
#: arayüzden kulaklığını seçiyor, ses başka yoldan gidiyor ve hiçbir hata görünmüyor.
#: Bu yüzden açılışta tespit edip söylüyoruz.
CONFLICTING_SINKS: dict[str, str] = {
    "easyeffects_sink": "EasyEffects",
    "jamesdsp_sink": "JamesDSP",
}


class ApiError(Exception):
    """İstemciye dönecek, beklenen bir hata. Daemon'ı düşürmez."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def envelope(result: Any = None) -> dict:
    return {"ok": True} if result is None else {"ok": True, "result": result}


class SonarApi:
    """Tüm D-Bus metotlarının arkasındaki mantık."""

    def __init__(
        self,
        store: config_mod.ConfigStore,
        supervisor: Supervisor,
        *,
        save_delay: float = SAVE_DELAY,
        on_change: Callable[[dict], None] | None = None,
        on_rebuild: Callable[[], None] | None = None,
        on_levels: Callable[[dict[str, Level]], None] | None = None,
    ) -> None:
        self.store = store
        self.supervisor = supervisor
        self.save_delay = save_delay
        self.on_change = on_change
        self.on_rebuild = on_rebuild

        self.config: SonarConfig = store.load()
        # Hata mesajları daemon'da üretiliyor; kullanıcının dili burada da geçerli olmalı.
        i18n.set_language(self.config.settings.language)
        store.ensure_default_profiles(self.config)
        #: Bellekte tutulan **çalışılan** profiller. Kullanıcı EQ'yu kurcaladığında burada
        #: değişir; diske yazım gecikmeli, grafa yazım anında.
        self.profiles: dict[str, Profile] = {}
        self._dirty_profiles: set[str] = set()
        self._dirty_config = False
        self._save_timer: threading.Timer | None = None
        self._lock = threading.RLock()

        supervisor.load_profile = self._profile_provider
        # Ses yolu koptuğunda kullanıcıya haber ver: sessizce susan bir kanal,
        # bulunması en zor hata. `supervisor` bekçisi eşiği aşınca burayı çağırır.
        supervisor.on_links_changed.append(self._on_links_changed)
        # Yeniden inşa node id'lerini eskitiyor; `pw-cat` ölçüm süreçleri eski node'a
        # bağlı kalıyor ve sessizce ölü veri veriyor. `_structural` bunu zaten yapıyordu
        # ama çökme kurtarması ve PipeWire restart yolları atlıyordu (test turu 3).
        supervisor.on_rebuild.append(self._reconfigure_meters)
        #: Kulaklığın fiziksel ChatMix tekeri. Okunamıyorsa sessizce boşta bekler ve
        #: yazılım slider'ı bugünkü gibi çalışır.
        self.chatmix_reader = ChatMixReader(self._chatmix_from_hardware)
        #: Smart Volume: ölçüm turlarında zarfı yürütür, kazançları fader'lara yazar.
        self.ducker = Ducker()
        self._duck_gains: dict[str, float] = {}
        self._duck_meters = False
        self._last_levels_at: float | None = None
        self._on_levels = on_levels
        self.meters = MeterManager(on_levels=self._levels_arrived)
        self.meters.configure(meter_sources(self.config))
        self.router = Router(
            supervisor.state,
            supervisor.control.move_stream,
            lambda: self.config,
            on_route=self._on_route,
        )

    # ------------------------------------------------------------------ yaşam döngüsü

    def start(self) -> None:
        """Daemon ayağa kalkıyor.

        Sanal kanallar **kurulu değilse** PipeWire'a hiç dokunulmaz: graf kurulmaz,
        varsayılan çıkış devralınmaz, kulaklık tekeri okunmaz. Daemon yalnızca D-Bus'ta
        durur ve arayüzün karşılama ekranını beklemesi için grafı **izler** (izleme
        salt okunur; cihaz listesi kurulum ekranında da lazım).

        Eskiden kurulum diye bir adım yoktu: daemon açılır açılmaz `default_config()`
        yazılıp dört kanal PipeWire'a kuruluyordu. Kullanıcının onayı hiçbir yerde
        sorulmuyordu.
        """
        self.supervisor.start_monitor()
        self.supervisor.monitor.wait_ready(timeout=5.0)
        if not self.config.settings.provisioned:
            log.info("sanal kanallar kurulu değil — PipeWire'a dokunulmuyor")
            return
        if self.config.settings.chatmix_source != "software":
            self.chatmix_reader.start()
        self.supervisor.reconcile(self.config)
        self.supervisor.take_over_default_sink(self.config)

    def shutdown(self) -> None:
        self.chatmix_reader.stop()
        self.flush_save()
        self.meters.stop()
        self.supervisor.stop()

    # ------------------------------------------------------------------ kurulum

    def provision(self) -> dict:
        """Sanal kanalları kurar. Karşılama ekranındaki düğmenin arkasındaki iş.

        Dönen özet **yapılandırmadan** okunuyor, sabit metin değil: arayüz "şunlar
        oluşturuldu" derken gerçekten oluşturulanı gösteriyor.
        """
        self.config.settings.provisioned = True
        self.supervisor.start_monitor()  # kaldırma sonrası izleyici durmuş olabilir
        self.supervisor.monitor.wait_ready(timeout=5.0)
        if self.config.settings.chatmix_source != "software":
            self.chatmix_reader.start()
        self._structural({"kind": "provisioned", "enabled": True})
        self.supervisor.take_over_default_sink(self.config)
        return self.setup_summary()

    def setup_summary(self) -> dict:
        """Kurulacak (veya kurulmuş) sanal cihazların listesi.

        Karşılama ekranının "ne kurulacak" sayfası bunu gösteriyor; kurulumdan önce de
        çağrılabilir, çünkü yalnızca yapılandırmayı okuyor.
        """
        return {
            "provisioned": bool(self.config.settings.provisioned),
            "channels": [
                {"id": c.id, "name": c.name, "device": f"Sonar {c.name}", "color": c.color}
                for c in sorted(self.config.channels, key=lambda c: (c.order, c.id))
            ],
            "buses": [
                {"id": b.id, "name": b.name, "device": f"Sonar {b.name}", "stream": b.is_stream}
                for b in sorted(self.config.buses, key=lambda b: (b.order, b.id))
            ],
            "mics": [
                {"id": m.id, "name": m.name, "device": f"Sonar {m.name}"}
                for m in sorted(self.config.mic_chains, key=lambda m: (m.order, m.id))
            ],
        }

    def deprovision(self, purge_settings: bool = False) -> dict:
        """Sanal kanalları söker; sistem Sonar hiç kurulmamış gibi kalır.

        Graf süreci öldürülür, varsayılan ses cihazı kullanıcıya geri verilir ve
        uygulamalar doğrudan fiziksel cihazlara çalmaya döner. `purge_settings` verilirse
        yapılandırma dizini de silinir.

        Kalan işler (udev kuralı, systemd unit, paketin kendisi) root'a ait; daemon onlara
        dokunmaz, yalnızca **söyler**.
        """
        self.chatmix_reader.stop()
        self.meters.stop()
        self.supervisor.stop(restore_default_sink=True)
        with contextlib.suppress(OSError):
            self.store.paths.graph_conf.unlink(missing_ok=True)

        self.config.settings.provisioned = False
        purged = False
        if purge_settings:
            purged = self._purge_settings()
        else:
            self._dirty_config = True
            self.flush_save()
        self._emit({"kind": "provisioned", "enabled": False})
        return {
            "purged": purged,
            "manual_steps": [
                {"note": i18n.t("uninstall.step.udev"),
                 "command": "sudo rm -f /etc/udev/rules.d/60-sonar-headset.rules"},
                {"note": i18n.t("uninstall.step.service"),
                 "command": "systemctl --user disable --now sonar-daemon"},
                {"note": i18n.t("uninstall.step.package"),
                 "command": "pip uninstall sonar-linux"},
            ],
        }

    def _purge_settings(self) -> bool:
        """Yapılandırma dizinini siler ve belleği sıfırlar."""
        try:
            shutil.rmtree(self.store.paths.config_dir)
        except OSError as error:
            log.error("yapılandırma dizini silinemedi: %s", error)
            return False
        self._dirty_config = False
        self._dirty_profiles.clear()
        self.config = default_config()
        self.profiles = {}
        return True

    # ------------------------------------------------------------------ okuma

    def get_state(self) -> dict:
        """Arayüzün ihtiyacı olan her şey. Tek çağrıda tam durum."""
        state = self.supervisor.state
        return {
            "config": serde.to_jsonable(self.config),
            "profiles": {
                target: serde.to_jsonable(self.profile(target))
                for target in self.config.profile_targets()
            },
            "profile_names": {
                target: self.list_profiles(target) for target in self.config.profile_targets()
            },
            "builtin_profiles": {
                target: self.builtin_names(target) for target in self.config.profile_targets()
            },
            "streams": self.get_streams(),
            "devices": self.get_devices(),
            "graph_ready": bool(state.sonar_nodes()),
            # Arayüz kurulu değilken mikser yerine karşılama ekranını çiziyor.
            "provisioned": bool(self.config.settings.provisioned),
            "conflicts": self.conflicts(),
            # Arayüz fader'ın altında "ChatMix yönetiyor" rozetini buna bakarak gösteriyor:
            # gösterilen değer taban seviye, duyulan ise taban × bu çarpan.
            "favorites": {
                target: self.list_favorites(target) for target in self.config.profile_targets()
            },
            "chatmix_gains": chatmix_gains(self.config),
            "headsets": self.headsets(),
            "chatmix_hardware": self.chatmix_is_hardware(),
        }

    def diagnose(self) -> dict:
        """`sonar-cli doctor`: ses yolunun neresi bozuk?

        Sessizce susan bir kanal, kullanıcının bulabileceği en zor hata. Buraya bakınca
        hangi bağlantının eksik, hangi node'un doğmadığı ve hangi uygulamanın
        yönlendirilmediği tek çıktıda görünür.
        """
        state = self.supervisor.state
        expected_links = confgen.send_links(self.config)
        missing_nodes = sorted(
            name
            for name in set(confgen.dsp_nodes(self.config).values())
            if state.node_id(name) is None
        )
        broken = self.supervisor.broken_links
        return {
            "graph_ready": bool(state.sonar_nodes()),
            "expected_links": len(expected_links),
            "broken_links": [f"{source} → {target}" for source, target in broken],
            "missing_nodes": missing_nodes,
            "conflicts": self.conflicts(),
            "unrouted_streams": [
                {"id": stream.id, "label": stream.label}
                for stream in state.streams.values()
                if not stream.is_internal
                and not stream.is_capture
                and not stream.target_node.startswith("sonar_")
                and (stream.serial or stream.id) not in self.router.decided
            ],
        }

    def stream_setup(self) -> dict:
        """Yayın kurulumunun canlı tanısı — "OBS'i nasıl kuracağım?"ın cevabı.

        Kullanıcının en çok takıldığı yer burası ve takılma hep aynı iki şekilde oluyor:
        ya OBS yayın miksini **hiç** dinlemiyor, ya da **iki kez** dinliyor. İkisi de
        graftan okunabiliyor, tahmine gerek yok.

        Yayın miksine iki yoldan erişilebilir:

        * `sonar_stream` sink'inin **monitörü** — OBS'te *Ayarlar → Ses → Masaüstü Sesi*.
          Akış `stream.capture.sink = True` ve `target.object = sonar_stream` taşır.
          **Resmî yol budur**; Windows'ta "SteelSeries GG Stream"i Masaüstü Sesi seçmenin
          birebir karşılığı.
        * `sonar_stream_out` (`Audio/Source`) — OBS'te *Ses Girişi Yakalama*. Aynı miksin
          ikinci kopyası; ikisi birden eklenirse her şey iki kez duyulur.

        Dönen sözlük arayüzdeki panelin ve `doctor`'ın tek kaynağı.
        """
        bus = self.config.bus(STREAM_BUS)
        sink = bus.sink_node if bus is not None else f"sonar_{STREAM_BUS}"
        out_node = bus.out_node if bus is not None else f"sonar_{STREAM_BUS}_out"
        device = f"Sonar {bus.name}" if bus is not None else "Sonar Stream Mix"

        listeners: list[dict] = []
        for stream in self.supervisor.state.streams.values():
            if stream.is_internal or not stream.is_capture:
                continue
            if stream.target_node == sink and stream.captures_sink:
                via = "monitor"
            elif stream.target_node == out_node:
                via = "source"
            else:
                continue
            listeners.append(
                {
                    "id": stream.id,
                    "label": stream.label,
                    "binary": stream.app_binary,
                    "via": via,
                }
            )

        mics = [
            {
                "id": mic.id,
                "name": mic.name,
                "in_stream": bool(mic.send_to_stream_bus),
                "muted": bool(mic.muted),
            }
            for mic in self.config.mic_chains
        ]

        problems: list[dict] = []
        if not listeners:
            problems.append(
                {
                    "code": "no_stream_listener",
                    "message": i18n.t("problem.no_stream_listener", device=device),
                }
            )
        # Aynı uygulamanın iki yoldan da dinlemesi: üçüncü turdaki "iki kaynak da her şeyi
        # çalıyor" tam olarak buydu. Uygulama adına göre eşleştiriyoruz çünkü OBS'in iki
        # kaynağı iki ayrı node olarak doğuyor.
        by_app: dict[str, set[str]] = {}
        for row in listeners:
            by_app.setdefault(row["binary"] or row["label"], set()).add(row["via"])
        for app, ways in sorted(by_app.items()):
            if len(ways) > 1:
                problems.append(
                    {
                        "code": "duplicate_capture",
                        "message": i18n.t(
                            "problem.duplicate_capture", app=app, device=device
                        ),
                    }
                )
        if listeners and not any(m["in_stream"] and not m["muted"] for m in mics):
            problems.append(
                {
                    "code": "mic_not_in_stream",
                    "message": i18n.t("problem.mic_not_in_stream"),
                }
            )

        return {
            "device": device,
            "sink_node": sink,
            "source_node": out_node,
            "listeners": listeners,
            "mics": mics,
            "problems": problems,
        }

    def sync_routing(self) -> list[Decision]:
        """Yeni akışları kurallara göre dağıtır. `pwstate` değişiklik bildirdiğinde çağrılır."""
        return self.router.sync()

    def get_streams(self) -> list[dict]:
        """Kullanıcıya gösterilecek akışlar — Sonar'ın kendi loopback'leri hariç.

        Her akışa `channel` alanı eklenir. Bunu node'un `target.object` prop'undan okumak
        **mümkün değil**: akışı `pw-metadata` ile taşıdığımızda hedef metadata deposunda
        tutuluyor, node'un kendi props'una yazılmıyor (pw-dump'ta boş görünüyor). Doğru
        kaynak yönlendiricinin kendi kaydı — hem kural kararlarını hem kullanıcının elle
        taşımalarını içeriyor.
        """
        decided = self.router.decided
        out = []
        for stream in self.supervisor.state.streams.values():
            if stream.is_internal:
                continue
            row = serde.to_jsonable(stream)
            row["channel"] = decided.get(stream.serial or stream.id, "")
            # Arayüz aynı uygulamayı hem çıkış hem giriş şeridinde gösteriyor.
            row["direction"] = "in" if stream.is_capture else "out"
            out.append(row)
        return out

    def conflicts(self) -> list[dict]:
        """Bizimle çakışan, sistem geneli çalışan ses işleyicileri."""
        nodes = self.supervisor.state.nodes
        return [
            {
                "code": "conflicting_processor",
                "node": node,
                "name": name,
                "message": i18n.t("problem.conflicting_sink", name=name),
            }
            for node, name in CONFLICTING_SINKS.items()
            if node in nodes
        ]

    def headsets(self) -> list[dict]:
        """Donanım ChatMix tekeri olduğu bilinen kulaklıklar ve erişilebilirlikleri."""
        return [
            {
                "device": info.device,
                "name": info.name,
                "readable": info.readable,
                "hint": info.hint,
            }
            for info in detect_headsets()
        ]

    def get_devices(self) -> list[dict]:
        """Fiziksel cihazlar. Kendi sanal node'larımız listeden düşer."""
        return [
            serde.to_jsonable(device)
            for device in sorted(
                self.supervisor.state.devices.values(), key=lambda d: (-d.priority, d.name)
            )
            if not device.name.startswith("sonar_")
        ]

    def list_profiles(self, target: str) -> list[str]:
        """Gömülü presetler önce, kullanıcının kendi profilleri sonra."""
        self._check_target(target)
        builtin = presets.builtin_names(target, self._mic_targets())
        user = [name for name in self.store.list_profiles(target) if name not in builtin]
        return builtin + user

    def builtin_names(self, target: str) -> list[str]:
        return presets.builtin_names(target, self._mic_targets())

    def _mic_targets(self) -> frozenset[str]:
        return frozenset(mic.id for mic in self.config.mic_chains)

    def _is_builtin(self, target: str, name: str) -> bool:
        return presets.is_builtin(target, name, self._mic_targets())

    def list_rules(self) -> list[dict]:
        return [serde.to_jsonable(rule) for rule in self.config.rules]

    def profile(self, target: str) -> Profile:
        """Hedefin çalışılan profili; yoksa preset'ten veya diskten yüklenir."""
        if target not in self.profiles:
            self.profiles[target] = self._load(target, self._active_name(target))
        return self.profiles[target]

    def _load(self, target: str, name: str) -> Profile:
        builtin = presets.builtin_profile(target, name, self._mic_targets())
        return builtin if builtin is not None else self.store.load_profile(target, name)

    def _editable(self, target: str) -> Profile:
        """Düzenlemeden önce çağrılır. Aktif profil salt okunursa kopyaya geçilir."""
        name = self._active_name(target)
        if not self._is_builtin(target, name):
            return self.profile(target)

        copy_name = self._unique_copy_name(target, name)
        working = self.profile(target)
        working.name = copy_name
        self.store.save_profile(target, working)
        self._set_active_name(target, copy_name)
        self._emit({"kind": "profile_copied", "target": target, "from": name, "to": copy_name})
        return working

    def _unique_copy_name(self, target: str, name: str) -> str:
        existing = set(self.store.list_profiles(target)) | set(self.builtin_names(target))
        candidate = f"{name} ({presets.COPY_SUFFIX})"
        index = 2
        while candidate in existing:
            candidate = f"{name} ({presets.COPY_SUFFIX} {index})"
            index += 1
        return candidate

    # ------------------------------------------------------------------ seviye

    def set_channel_volume(self, channel: str, bus: str, value: float) -> None:
        target = self._channel(channel)
        target.send(self._bus(bus, target)).volume = self._level(value)
        self._live_volumes({"kind": "channel_volume", "channel": channel, "bus": bus})

    def set_channel_mute(self, channel: str, bus: str, muted: bool) -> None:
        target = self._channel(channel)
        target.send(self._bus(bus, target)).muted = bool(muted)
        self._live_volumes({"kind": "channel_mute", "channel": channel, "bus": bus})

    def set_master_volume(self, bus: str, value: float) -> None:
        self._master(bus).volume = self._level(value)
        self._live_volumes({"kind": "master_volume", "bus": bus})

    def set_master_mute(self, bus: str, muted: bool) -> None:
        self._master(bus).muted = bool(muted)
        self._live_volumes({"kind": "master_mute", "bus": bus})

    def set_mic_volume(self, chain: str, value: float) -> None:
        self._mic(chain).volume = self._level(value)
        self._live_volumes({"kind": "mic_volume", "chain": chain})

    def set_mic_mute(self, chain: str, muted: bool) -> None:
        self._mic(chain).muted = bool(muted)
        self._live_volumes({"kind": "mic_mute", "chain": chain})

    def set_mic_monitor_volume(self, chain: str, value: float) -> None:
        """Sidetone seviyesi. Giriş şeridindeki kulaklık fader'ı buna bağlı —
        eskiden arayüzde karşılığı yoktu ve fader sessizce hiçbir şey yapmıyordu."""
        self._mic(chain).monitor_volume = self._level(value)
        self._live_volumes({"kind": "mic_monitor_volume", "chain": chain})

    # ------------------------------------------------------------------ filtreler

    def set_filter_enabled(self, target: str, stage: str, enabled: bool) -> None:
        """`stage` artık bir **slot kimliği** (`comp`, `comp2`), aşama adı değil.

        Aç/kapa hâlâ **canlı**: efekt zincirde duruyor, yalnızca bypass portuna yazılıyor.
        Ekleme/silme yapısal (`add_effect` / `remove_effect`).
        """
        profile = self._editable(target)
        effect = self._slot(target, profile, stage)
        if effect.kind is FilterStage.EQ:
            # EQ'nun bayrağı `profile.eq`'te; eğri ve içe/dışa aktarma oradan okuyor.
            profile.eq.enabled = bool(enabled)
        effect.enabled = bool(enabled)
        self._live_target(target, {"kind": "filter_enabled", "target": target, "stage": stage})

    def set_filter_param(self, target: str, stage: str, name: str, value: float) -> None:
        """`name` insan birimindeki parametre adıdır (`threshold_db`), port sembolü değil.

        Doğrulama **tanıma** bakıyor, profilde depolanana değil: eski bir profil
        aşamanın artık kullanılmayan parametrelerini taşıyor olabilir ve o zaman yeni
        parametreler reddedilirdi (Spatial Audio HRTF'ten crossfeed'e geçerken oldu).
        """
        profile = self._editable(target)
        effect = self._slot(target, profile, stage)
        if name not in DEFAULT_FILTER_PARAMS.get(effect.kind, {}):
            raise ApiError("unknown_param", i18n.t("error.unknown_param", stage=stage, name=name))
        effect.params[name] = float(value)
        self._live_target(
            target, {"kind": "filter_param", "target": target, "stage": stage, "param": name}
        )

    # ------------------------------------------------------------------ efekt zinciri

    def add_effect(self, target: str, kind: str, index: int = -1) -> str:
        """Zincire yeni bir efekt ekler ve slot kimliğini döndürür. **Yapısal**.

        Aynı efektten birden fazla eklenebiliyor (EasyEffects'te olduğu gibi); tek
        istisna ekolayzer, çünkü band modeli ve eğrisi profilde tek.
        """
        profile = self._editable(target)
        stage = self._stage(target, kind)
        if stage is FilterStage.EQ and any(e.kind is FilterStage.EQ for e in profile.effects):
            raise ApiError("duplicate_effect", i18n.t("error.one_eq_only"))
        effect = EffectSlot(
            kind=stage,
            slot=profile.next_slot_id(stage),
            enabled=True,
            params=dict(DEFAULT_FILTER_PARAMS.get(stage, {})),
        )
        position = len(profile.effects) if index < 0 else max(0, min(index, len(profile.effects)))
        profile.effects.insert(position, effect)
        self._structural({"kind": "effect_added", "target": target, "slot": effect.slot})
        return effect.slot

    def remove_effect(self, target: str, slot: str) -> None:
        """Efekti zincirden çıkarır. **Yapısal**."""
        profile = self._editable(target)
        self._slot(target, profile, slot)
        profile.effects = [e for e in profile.effects if e.slot != slot]
        self._structural({"kind": "effect_removed", "target": target, "slot": slot})

    def move_effect(self, target: str, slot: str, index: int) -> None:
        """Efekti listede taşır — sinyal listedeki sırayla akıyor. **Yapısal**."""
        profile = self._editable(target)
        effect = self._slot(target, profile, slot)
        remaining = [e for e in profile.effects if e.slot != slot]
        position = max(0, min(index, len(remaining)))
        remaining.insert(position, effect)
        if [e.slot for e in remaining] == [e.slot for e in profile.effects]:
            return  # sıra değişmedi: grafı boşuna yeniden kurma
        profile.effects = remaining
        self._structural({"kind": "effect_moved", "target": target, "slot": slot})

    def list_effects(self, target: str) -> list[dict]:
        """Hedefin zincirindeki efektler, sinyal sırasıyla."""
        profile = self._editable(target)
        return [
            {
                "slot": effect.slot,
                "kind": effect.kind.value,
                "enabled": self.profile(target).state(effect.slot).enabled,
                "params": dict(self.profile(target).state(effect.slot).params),
            }
            for effect in profile.effects
        ]

    def list_effect_kinds(self, target: str = "") -> list[dict]:
        """Bu hedefe eklenebilecek efektler.

        Kurulu olmayan eklentiler ve hedefe uymayanlar (mikrofonda Uzamsal Ses, oynatmada
        DeepFilterNet) listeye girmiyor — kullanıcıya ekleyemeyeceği bir şeyi göstermek
        onu graf kurulamadığında yalnız bırakır.
        """
        is_mic = bool(target) and self.config.mic(target) is not None
        channels = 2
        out: list[dict] = []
        for stage in CHAIN_ORDER:
            if target:
                if is_mic and stage in PLAYBACK_ONLY_STAGES:
                    continue
                if not is_mic and stage in MIC_ONLY_STAGES:
                    continue
            probe = EffectSlot(kind=stage, slot=stage.value)
            plan = plan_chain((probe,), channels=channels,
                              band_count=self.config.settings.default_band_count)  # fmt: skip
            if not plan.slots:
                continue
            out.append(
                {"kind": stage.value, "params": sorted(DEFAULT_FILTER_PARAMS.get(stage, {}))}
            )
        return out

    def set_eq_enabled(self, target: str, enabled: bool) -> None:
        self.set_filter_enabled(target, FilterStage.EQ.value, enabled)

    def set_eq_preamp(self, target: str, value_db: float) -> None:
        self._editable(target).eq.preamp_db = float(value_db)
        self._live_target(target, {"kind": "eq_preamp", "target": target})

    def set_eq_band(self, target: str, band: int, field: str, value: float | str) -> None:
        eq = self._editable(target).eq
        if not 0 <= band < len(eq.bands):
            raise ApiError("unknown_band", i18n.t("error.band_out_of_range", band=band))
        if field not in _EQ_FIELDS:
            raise ApiError("unknown_field", i18n.t("error.unknown_band_field", field=field))
        target_band = eq.bands[band]
        if field == "band_type":
            try:
                target_band.band_type = EqBandType(str(value))
            except ValueError as exc:
                raise ApiError(
                    "unknown_field", i18n.t("error.unknown_band_type", value=value)
                ) from exc
        elif field == "enabled":
            target_band.enabled = bool(value)
        elif field == "slope":
            target_band.slope = int(value)
        else:
            setattr(target_band, field, float(value))
        eq.bands[band] = target_band.clamped()
        self._live_target(
            target, {"kind": "eq_band", "target": target, "band": band, "field": field}
        )

    def add_eq_band(self, target: str, freq: float, gain_db: float = 0.0) -> int:
        """Belirtilen frekansa yeni bir EQ bandı ekler ve indeksini döndürür. **Canlı**.

        Arayüzde eğriye sağ tıklamanın karşılığı. Bandlar frekansa göre sıralı tutuluyor:
        kullanıcı eğriye baktığında soldan sağa gitmesi bekleniyor.

        Zincir her zaman 32 bandlık eklentiyle kurulduğu için burada yapısal bir
        değişiklik yok — band eklemek ses kesmiyor.
        """
        eq = self._editable(target).eq
        if len(eq.bands) >= registry.EQ_CAPACITY:
            raise ApiError(
                "eq_full", i18n.t("error.eq_full", count=registry.EQ_CAPACITY)
            )
        band = EqBand(
            freq=max(EQ_FREQ_MIN, min(float(freq), EQ_FREQ_MAX)),
            gain_db=float(gain_db),
            q=default_band_q(max(len(eq.bands) + 1, 1)),
        )
        eq.bands.append(band)
        eq.bands.sort(key=lambda b: b.freq)
        eq.band_count = len(eq.bands)
        index = eq.bands.index(band)
        self._live_target(target, {"kind": "eq_band_added", "target": target, "band": index})
        return index

    def remove_eq_band(self, target: str, index: int) -> None:
        """Bir EQ bandını siler. **Canlı**."""
        eq = self._editable(target).eq
        if not 0 <= index < len(eq.bands):
            raise ApiError("unknown_band", i18n.t("error.no_such_band", index=index))
        if len(eq.bands) <= 1:
            raise ApiError("last_band", i18n.t("error.last_band"))
        eq.bands.pop(index)
        eq.band_count = len(eq.bands)
        self._live_target(target, {"kind": "eq_band_removed", "target": target, "band": index})

    # ------------------------------------------------------------------ profiller

    def load_profile(self, target: str, name: str) -> None:
        self._check_target(target)
        self.profiles[target] = self._load(target, name)
        self._dirty_profiles.discard(target)
        self._set_active_name(target, name)
        self._live_target(target, {"kind": "profile", "target": target, "name": name})

    def save_profile(self, target: str, name: str) -> None:
        self._check_target(target)
        if self._is_builtin(target, name):
            raise ApiError("profile_readonly", i18n.t("error.preset_readonly", name=name))
        profile = self.profile(target)
        profile.name = name
        self.store.save_profile(target, profile)
        self._set_active_name(target, name)
        self._dirty_profiles.discard(target)
        self._emit({"kind": "profile_saved", "target": target, "name": name})
        self._save_soon()

    def delete_profile(self, target: str, name: str) -> None:
        self._check_target(target)
        if self._is_builtin(target, name):
            raise ApiError("profile_readonly", i18n.t("error.preset_undeletable", name=name))
        if not self.store.delete_profile(target, name):
            raise ApiError("profile_protected", i18n.t("error.profile_protected", name=name))
        favorites = self.config.favorites_of(target)
        if name in favorites:
            favorites.remove(name)
            self.config.favorites[target] = favorites
            self._dirty_config = True
        if self._active_name(target) == name:
            self.load_profile(target, "Default")
        self._emit({"kind": "profile_deleted", "target": target, "name": name})

    def rename_profile(self, target: str, old: str, new: str) -> None:
        self._check_target(target)
        if self._is_builtin(target, old):
            raise ApiError("profile_readonly", i18n.t("error.preset_unrenamable", name=old))
        if self._is_builtin(target, new):
            raise ApiError("profile_readonly", i18n.t("error.name_is_preset", name=new))
        if not self.store.rename_profile(target, old, new):
            raise ApiError("profile_not_renamed", i18n.t("error.profile_not_renamed", name=old))
        favorites = self.config.favorites_of(target)
        if old in favorites:
            self.config.favorites[target] = [new if n == old else n for n in favorites]
        if self._active_name(target) == old:
            self._set_active_name(target, new)
            self.profile(target).name = new
        self._emit({"kind": "profile_renamed", "target": target, "old": old, "new": new})
        self._save_soon()

    def import_profile(self, target: str, text: str, name: str = "") -> dict:
        """Dış bir EQ dosyasını profil olarak içe aktarır ve ona geçer.

        Biçim içerikten bulunur (uzantıya güvenilmiyor): AutoEQ/APO, EasyEffects preset'i
        veya `.sonarprofile`.
        """
        self._check_target(target)
        try:
            result = importers.import_any(text, name or None)
        except importers.ProfileImportError as error:
            raise ApiError("import_failed", str(error)) from error

        final = name or result.profile.name
        if self._is_builtin(target, final):
            final = f"{final} ({presets.COPY_SUFFIX})"
        result.profile.name = final
        self.store.save_profile(target, result.profile)
        self.profiles[target] = result.profile
        self._set_active_name(target, final)
        self.supervisor.apply_target(self.config, target)
        self._emit({"kind": "profile_imported", "target": target, "name": final})
        self._save_soon()
        return {
            "name": final,
            "source": result.source,
            "bands": result.profile.eq.band_count,
            "dropped": result.dropped,
            "warnings": list(result.warnings),
        }

    def export_profile(self, target: str, name: str = "", autoeq: bool = False) -> str:
        """Profili metin olarak verir. `autoeq` ise AutoEQ/APO biçiminde."""
        self._check_target(target)
        wanted = name or self._active_name(target)
        profile = (
            self.profile(target)
            if wanted == self._active_name(target)
            else self._load(target, wanted)
        )
        return importers.export_autoeq(profile) if autoeq else importers.export_profile(profile)

    def copy_profile(self, target: str, name: str) -> str:
        """Aktif profili yeni bir adla çoğaltır ve ona geçer."""
        self._check_target(target)
        if self._is_builtin(target, name):
            raise ApiError("profile_readonly", i18n.t("error.name_is_preset", name=name))
        self.save_profile(target, name)
        return name

    def reset_profile(self, target: str) -> None:
        """Aktif profili düz hâle döndürür (EQ sıfır, filtreler kapalı)."""
        self._check_target(target)
        working = self._editable(target)
        flat = presets.builtin_profile(target, "Flat", self._mic_targets())
        if flat is None:  # pragma: no cover - Flat her katalogda var
            return
        flat.name = working.name
        self.profiles[target] = flat
        self._live_target(target, {"kind": "profile_reset", "target": target})

    def new_profile(self, target: str, name: str) -> str:
        """Sıfırdan **düz** bir profil oluşturur ve ona geçer.

        "Farklı kaydet" yerine geçiyor. Eskiden yeni bir varyant için önce aktif
        profili bozmak, sonra farklı adla kaydetmek gerekiyordu — kullanıcının
        şikâyeti tam buydu: "mevcut kanalın ayarlarının bozulmasına sebep oluyor".
        """
        self._check_target(target)
        name = str(name).strip()
        if not name:
            raise ApiError("invalid_name", i18n.t("error.empty_profile_name"))
        if self._is_builtin(target, name):
            raise ApiError("profile_readonly", i18n.t("error.name_is_preset", name=name))
        if name in self.store.list_profiles(target):
            raise ApiError("duplicate_profile", i18n.t("error.duplicate_profile", name=name))

        profile = default_profile(name, self.config.settings.default_band_count)
        self.store.save_profile(target, profile)
        self.profiles[target] = profile
        self._dirty_profiles.discard(target)
        self._set_active_name(target, name)
        self.supervisor.apply_target(self.config, target)
        self._dirty_config = True
        self._emit({"kind": "profile_created", "target": target, "name": name})
        self._save_soon()
        return name

    def list_favorites(self, target: str) -> list[str]:
        """Hedefin sıralı favori profilleri; silinmiş profiller elenir."""
        self._check_target(target)
        known = set(self.list_profiles(target))
        return [name for name in self.config.favorites_of(target) if name in known]

    def set_profile_favorite(self, target: str, name: str, favorite: bool) -> None:
        """Bir profili favorilere ekler veya çıkarır. Sayı sınırı yok."""
        self._check_target(target)
        if name not in self.list_profiles(target):
            raise ApiError("unknown_profile", i18n.t("error.no_such_profile", name=name))
        current = self.config.favorites_of(target)
        if favorite and name not in current:
            current.append(name)
        elif not favorite and name in current:
            current.remove(name)
        else:
            return
        self.config.favorites[target] = current
        self._dirty_config = True
        self._emit(
            {"kind": "profile_favorite", "target": target, "name": name, "favorite": favorite}
        )
        self._save_soon()

    def reorder_favorites(self, target: str, names: list[str]) -> None:
        """Favori sırasını verilen listeye göre yeniden yazar.

        Listede olmayan ama hâlâ favori olan adlar sona eklenir; tanınmayan adlar
        yok sayılır. Böylece arayüz eski bir sırayla çağırsa bile favori kaybolmaz.
        """
        self._check_target(target)
        current = self.config.favorites_of(target)
        wanted = [name for name in names if name in current]
        self.config.favorites[target] = wanted + [n for n in current if n not in wanted]
        self._dirty_config = True
        self._emit({"kind": "favorites_reordered", "target": target})
        self._save_soon()

    # ------------------------------------------------------------------ yapısal

    def set_bus_device(self, bus: str, device: str) -> None:
        """Bir çıkış bus'ının fiziksel cihazı. **Canlı** — ses kesilmez.

        Eskiden `_structural()` idi: cihaz adı conf'a `target.object` olarak giriyordu,
        yani her değişiklik grafı yeniden kurup çalan müziği kesiyor, metre süreçlerini
        öldürüyordu. Artık hedef `pw-metadata` ile canlı yazılıyor (Faz 18'de ölçüldü).
        """
        self._master(bus).device = str(device)
        self._live_targets({"kind": "bus_device", "bus": bus})

    def set_mic_device(self, chain: str, device: str) -> None:
        self._mic(chain).source_device = str(device)
        self._live_targets({"kind": "mic_device", "chain": chain})

    def set_mic_monitor(self, chain: str, enabled: bool) -> None:
        # Monitör loopback'i conf'ta her zaman kurulu; açma/kapama bir mute yazımı.
        self._mic(chain).monitor_enabled = bool(enabled)
        self._live_volumes({"kind": "mic_monitor", "chain": chain})

    def set_mic_stream_send(self, chain: str, enabled: bool) -> None:
        self._mic(chain).send_to_stream_bus = bool(enabled)
        self._live_volumes({"kind": "mic_stream_send", "chain": chain})

    def set_channel_stream_source(self, channel: str, enabled: bool) -> None:
        """Kanalın OBS için ayrı bir sanal giriş cihazı yayınlayıp yayınlamayacağı.

        Kapalıyken (varsayılan) kanal yalnızca birleşik Stream Mix üzerinden yayına
        gider ve sistemin mikrofon listesini kirletmez. **Yapısal** — graf yeniden kurulur.
        """
        self._channel(channel).stream_source = bool(enabled)
        self._structural({"kind": "channel_stream_source", "channel": channel})

    # ------------------------------------------------------------------ kanallar

    def add_channel(
        self, name: str, direction: str = "output", color: str = "#8B95A5"
    ) -> str:
        """Yeni bir kanal ekler ve id'sini döndürür. **Yapısal**.

        `direction` kanalın hangi sanal cihazı üreteceğini belirler:

        * `"output"` → uygulamaların çaldığı bir sink (`Sonar <Ad> — Virtual Output`)
          artı DSP ve iki bus gönderisi. Model karşılığı `Channel`.
        * `"input"` → fiziksel bir mikrofonu işleyip yayınlayan bir kaynak
          (`Sonar <Ad> — Virtual Input`). Model karşılığı `MicChain`.

        İkisi ayrı sınıflar olduğu için yön modelde ayrı bir alan olarak tutulmuyor;
        hangi listede durduğu yönü zaten söylüyor.
        """
        name = str(name).strip()
        if not name:
            raise ApiError("invalid_name", i18n.t("error.empty_channel_name"))
        if direction not in ("output", "input"):
            raise ApiError(
                "invalid_direction", i18n.t("error.bad_channel_direction", value=direction)
            )

        channel_id = slugify(name)
        if channel_id in self.config.profile_targets():
            raise ApiError("duplicate_channel", i18n.t("error.duplicate_channel", name=channel_id))

        if direction == "output":
            self.config.channels.append(
                Channel(
                    id=channel_id,
                    name=name,
                    color=str(color),
                    order=self.config.next_channel_order(),
                )
            )
            self.config.ensure_sends()
        else:
            self.config.mic_chains.append(
                MicChain(
                    id=channel_id,
                    name=name,
                    color=str(color),
                    order=self.config.next_mic_order(),
                )
            )
        self.store.ensure_default_profiles(self.config)
        self._structural(
            {"kind": "channel_added", "channel": channel_id, "direction": direction}
        )
        return channel_id

    def remove_channel(self, channel: str) -> None:
        """Bir çıkış veya giriş kanalını siler. **Yapısal**.

        Yerleşik koruması yok — kullanıcı Aux'u da Media'yı da silebilir. Yalnızca
        grafı tutarsız bırakacak durumlar engellenir ve kanala bağlı her şey
        (kurallar, profiller, favoriler, ChatMix tarafı, çalan akışlar) temizlenir.
        """
        if self.config.channel(channel) is not None:
            self._remove_output_channel(channel)
        elif self.config.mic(channel) is not None:
            self._remove_input_channel(channel)
        else:
            raise ApiError("unknown_channel", i18n.t("error.no_such_channel", name=channel))

        self.profiles.pop(channel, None)
        self._dirty_profiles.discard(channel)
        self.config.favorites.pop(channel, None)
        self.store.delete_target(channel)
        self._structural({"kind": "channel_removed", "channel": channel})

    def _remove_output_channel(self, channel: str) -> None:
        if len(self.config.channels) <= 1:
            raise ApiError("last_channel", i18n.t("error.last_output_channel"))

        self.config.channels = [c for c in self.config.channels if c.id != channel]
        self.config.rules = [r for r in self.config.rules if r.channel_id != channel]

        # Varsayılan kanal silindiyse başka birine devret, yoksa yeni açılan her
        # uygulama var olmayan bir kanala yönlendirilmeye çalışılır.
        if self.config.settings.default_channel == channel:
            self.config.settings.default_channel = self.config.ordered_channels()[0].id

        chatmix = self.config.chatmix
        chatmix.left_channel = _without(chatmix.left_channel, channel)
        chatmix.right_channel = _without(chatmix.right_channel, channel)
        if not chatmix.left_channel or not chatmix.right_channel:
            chatmix.enabled = False

        # O kanalda çalan akışların kaydını burada unutuyoruz: kanal artık yok, karar
        # geçersiz. `_structural()` sonrası `sync()` onlara kurallara göre baştan
        # karar verir.
        self.router.forget_channel(channel)

    def _remove_input_channel(self, chain: str) -> None:
        if len(self.config.mic_chains) <= 1:
            raise ApiError("last_channel", i18n.t("error.last_input_channel"))
        mic = self.config.mic(chain)
        assert mic is not None
        if not mic.share_chain_with_mic and not any(
            m.id != chain and not m.share_chain_with_mic for m in self.config.mic_chains
        ):
            # Kendi DSP'si olan tek zinciri silmek, ondan beslenen zincirleri
            # kaynaksız bırakır (`confgen._primary_mic` hata yükseltir).
            raise ApiError(
                "mic_chain_needed",
                i18n.t("error.mic_chain_needed"),
            )
        self.config.mic_chains = [m for m in self.config.mic_chains if m.id != chain]

    # ------------------------------------------------------------------ yönlendirme

    def move_stream(self, stream_id: int, channel: str, remember: bool = False) -> None:
        """Bir akışı elle taşır.

        `channel` bir çıkış kanalı ya da bir giriş zinciri olabilir; hangisi olduğunu
        hedefin kendisi söylüyor. Yakalama akışları (uygulamanın dinlediği mikrofon) da
        aynı yolla taşınıyor — ayrı bir API'ye gerek yok (Faz 21).

        `remember` verilirse uygulamanın binary'sinden kalıcı bir kural üretilir —
        arayüzdeki "bu uygulamayı hep buraya gönder" seçeneği bunu kullanır. Üretilen
        kural akışın **yönünü** taşır, yoksa Discord'un mikrofon kuralı ses kuralını
        da eziyor olurdu.
        """
        node = self._target_node(channel)
        if not self.supervisor.control.move_stream(int(stream_id), node):
            raise ApiError("move_failed", i18n.t("error.move_failed", id=stream_id))
        # Taşıma komutu başarılı dönse de bağlantı kurulmamış olabilir; kullanıcı bunu
        # yalnızca sesin kesilmesiyle fark ediyordu. Bir kez daha deneyip bırakıyoruz.
        if not self._stream_reached(int(stream_id), node):
            self.supervisor.control.move_stream(int(stream_id), node)
        # Kural motoru bu akışa bir daha dokunmasın: kullanıcının kararı kalıcıdır.
        self.router.mark_manual(int(stream_id), channel)
        self._emit({"kind": "stream_moved", "stream": int(stream_id), "channel": channel})
        if remember:
            self._remember_stream(int(stream_id), channel)

    def _target_node(self, target: str) -> str:
        """Taşıma hedefinin node adı: kanalda sink, giriş zincirinde sanal kaynak."""
        node = target_node_for(target, self.config)
        if node is None:
            raise ApiError("unknown_channel", i18n.t("error.no_such_channel", name=target))
        return node

    def _stream_reached(self, stream_id: int, node: str) -> bool:
        """Akış gerçekten hedefe bağlandı mı? `pw-link -l` üzerinden bakar."""
        stream = self.supervisor.state.streams.get(stream_id)
        if stream is None:
            return True  # akış kapanmış; taşımayı zorlamanın anlamı yok
        name = self.supervisor.state.node_name(stream_id)
        if name is None:
            return True
        links = self.supervisor.control.node_links()
        if not links:
            # `pw-link -l` okunamadı (komut yok, zaman aşımı). Bilmediğimiz için
            # körlemesine tekrar denemek akışı ikinci kez sarsmaktan başka işe yaramaz.
            return True
        return any(source == name and target == node for source, target in links)

    def _remember_stream(self, stream_id: int, channel: str) -> None:
        stream = self.supervisor.state.streams.get(stream_id)
        if stream is None:
            raise ApiError("unknown_stream", i18n.t("error.no_such_stream", id=stream_id))
        direction = StreamDirection.IN if stream.is_capture else StreamDirection.OUT
        for key in (MatchKey.BINARY, MatchKey.APP_NAME, MatchKey.MEDIA_NAME):
            value = _stream_field(stream, key)
            if value:
                self.set_rule(key.value, value, channel, direction=direction.value)
                return
        raise ApiError(
            "not_identifiable",
            i18n.t("error.not_identifiable"),
        )

    def set_rule(
        self,
        match_key: str,
        pattern: str,
        channel: str,
        is_regex: bool = False,
        direction: str = "out",
    ) -> None:
        """Bir yönlendirme kuralı ekler veya günceller.

        Kural **yön taşır**: aynı desenin bir çıkış bir de giriş kuralı olabilir
        (Discord hem `chat` kanalına hem `mic` zincirine).
        """
        self._target_node(channel)
        try:
            key = MatchKey(match_key)
        except ValueError as exc:
            raise ApiError(
                "unknown_match_key", i18n.t("error.unknown_match_key", value=match_key)
            ) from exc
        try:
            way = StreamDirection(direction)
        except ValueError as exc:
            raise ApiError(
                "unknown_direction", i18n.t("error.bad_rule_direction", value=direction)
            ) from exc
        if not str(pattern).strip():
            raise ApiError("invalid_pattern", i18n.t("error.empty_pattern"))
        for rule in self.config.rules:
            if rule.match_key == key and rule.pattern == pattern and rule.direction is way:
                rule.channel_id = channel
                rule.is_regex = bool(is_regex)
                rule.enabled = True
                break
        else:
            self.config.rules.append(
                RoutingRule(
                    match_key=key,
                    pattern=pattern,
                    channel_id=channel,
                    is_regex=bool(is_regex),
                    direction=way,
                )
            )
        self._emit({"kind": "rules", "pattern": pattern})
        self._save_soon()

    def remove_rule(self, match_key: str, pattern: str, direction: str = "") -> None:
        """Kuralı siler. `direction` verilmezse o desenin her iki yönü de silinir."""
        before = len(self.config.rules)
        self.config.rules = [
            r
            for r in self.config.rules
            if not (
                r.match_key == match_key
                and r.pattern == pattern
                and (not direction or r.direction == direction)
            )
        ]
        if len(self.config.rules) == before:
            raise ApiError(
                "unknown_rule", i18n.t("error.no_such_rule", key=match_key, pattern=pattern)
            )
        self._emit({"kind": "rules", "pattern": pattern})
        self._save_soon()

    # ------------------------------------------------------------------ ChatMix

    def set_chatmix(self, value: float) -> None:
        self.config.chatmix.value = max(0.0, min(100.0, float(value)))
        self._live_volumes({"kind": "chatmix", "value": self.config.chatmix.value})

    def set_chatmix_invert(self, enabled: bool) -> None:
        """Donanım tekerinin yönünü ters çevirir.

        Hangi ucun Game olduğu HID raporundan çıkmıyor (`headset.decode_chatmix`), o
        yüzden yönü kullanıcı söylüyor. Yalnızca **teker** okumasını etkiler; yazılım
        slider'ına dokunmaz.
        """
        self.config.settings.chatmix_invert = bool(enabled)
        self._touch_config({"kind": "chatmix_invert", "enabled": bool(enabled)})

    def set_language(self, code: str) -> str:
        """Arayüz ve mesaj dilini değiştirir.

        Daemon'ın kendi mesajları da bu dile geçer (hata metinleri burada üretiliyor).
        Grafa dokunmaz: cihaz adları yapılandırmadan geliyor ve dile bağlı değil — dil
        değiştirmek OBS'teki seçili aygıtı bozmaz.
        """
        normalized = i18n.set_language(code)
        self.config.settings.language = normalized
        self._touch_config({"kind": "language", "code": normalized})
        # Gecikmeli kaydetme burada yetmiyor: `sonar-cli` dili **diskten** okuyor ve
        # dil değişiminden hemen sonra çalışan bir komut eski dili görüyordu (ölçüldü:
        # `sonar-cli lang en && sonar-cli status` → başlıklar Türkçe, daemon mesajları
        # İngilizce). Dil değişimi nadir; anında yazmanın maliyeti yok.
        self.flush_save()
        return normalized

    def set_chatmix_config(self, enabled: bool, left: str, right: str) -> None:
        """`left`/`right` virgülle birden fazla kanal alabilir ("chat,media")."""
        from sonar.core.model import _split_channels

        for side in (left, right):
            channels = _split_channels(side)
            if not channels:
                raise ApiError("invalid_value", i18n.t("error.channel_required"))
            for channel in channels:
                self._channel(channel)
        self.config.chatmix.enabled = bool(enabled)
        self.config.chatmix.left_channel = left
        self.config.chatmix.right_channel = right
        self._live_volumes({"kind": "chatmix_config"})

    # ------------------------------------------------------------------ diğer

    def set_default_channel(self, channel: str) -> None:
        self._channel(channel)
        self.config.settings.default_channel = channel
        self._emit({"kind": "settings"})
        self._save_soon()

    def set_take_over_default_sink(self, enabled: bool) -> None:
        self.config.settings.take_over_default_sink = bool(enabled)
        if enabled:
            self.supervisor.take_over_default_sink(self.config)
        self._emit({"kind": "settings"})
        self._save_soon()

    def set_meters_subscribed(self, enabled: bool) -> int:
        """Seviye ölçümü aboneliği.

        İlk abone ölçüm süreçlerini başlatır, son abone gidince hepsi durur — daemon tek
        başına çalışırken tek bir ölçüm süreci bile açık kalmaz.
        """
        count = self.meters.subscribe() if enabled else self.meters.unsubscribe()
        self._emit({"kind": "meters", "subscribed": count})
        return count

    def get_levels(self) -> dict[str, dict]:
        """Anlık seviyeler. Abone yoksa boş sözlük."""
        return {
            node: {
                "peak_db": round(level.peak_db, 2),
                "rms_db": round(level.rms_db, 2),
                "hold_db": round(level.hold_db, 2),
                "clipped": level.clipped,
            }
            for node, level in self.meters.levels().items()
        }

    def reload(self) -> None:
        """Elle düzenlenmiş `config.toml`'u diskten okur ve grafa uygular."""
        self.flush_save()
        self.config = self.store.load()
        self.store.ensure_default_profiles(self.config)
        self.profiles.clear()
        self.supervisor.reconcile(self.config)
        self.meters.configure(meter_sources(self.config))
        self._emit({"kind": "reloaded"})

    # ------------------------------------------------------------------ kalıcılık

    def flush_save(self) -> None:
        """Bekleyen diske yazımı hemen yapar."""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            dirty_config, self._dirty_config = self._dirty_config, False
            dirty_profiles, self._dirty_profiles = self._dirty_profiles, set()
        try:
            for target in dirty_profiles:
                profile = self.profiles.get(target)
                # Gömülü preset asla diske yazılmaz; `_editable()` kopyaya geçirmiş olmalı.
                if profile is not None and not self._is_builtin(target, profile.name):
                    self.store.save_profile(target, profile)
            if dirty_config:
                self.store.save(self.config)
        except OSError as error:
            # Disk dolu, izin yok, salt okunur bağlama… Ayarlar bellekte duruyor ve ses
            # düzeni bozulmuyor; kullanıcıya söylenmesi gereken şey kalıcı olmadıkları.
            log.error("yapılandırma diske yazılamadı: %s", error)
            self._emit(
                {
                    "kind": "save_failed",
                    "message": i18n.t("problem.save_failed", error=error.strerror or error),
                }
            )

    # ------------------------------------------------------------------ iç kısım

    def _levels_arrived(self, levels: dict[str, Level]) -> None:
        """Ölçüm turu. Önce ducking zarfını yürüt, sonra dinleyiciye ilet.

        Bu döngü yalnızca ölçüm açıkken çalışıyor; ducking açıksa daemon aboneliği
        kendisi tutuyor (`_sync_duck_subscription`), yani arayüz kapalıyken de çalışır.
        """
        try:
            self._advance_ducking(levels)
        except Exception:  # pragma: no cover - ducking hatası ölçümü düşürmesin
            log.exception("smart volume döngüsü hata verdi")
        if self._on_levels is not None:
            self._on_levels(levels)

    def _advance_ducking(self, levels: dict[str, Level]) -> None:
        if not self._ducking_wanted():
            if self._duck_gains:
                self._duck_gains = {}
                self.ducker.reset()
                self.supervisor.apply_volumes(self.config)
            return

        now = time.monotonic()
        dt = self.meters.interval if self._last_levels_at is None else now - self._last_levels_at
        self._last_levels_at = now

        by_channel = {
            channel.id: levels[channel.sink_node].peak_db
            for channel in self.config.channels
            if channel.sink_node in levels
        }
        gains = self.ducker.step(self.config, self.profile, by_channel, min(dt, 1.0))
        # Yazımı yalnızca duyulur bir fark olduğunda yap: 20 Hz'de her turda yazmak
        # `pw-cli` oturumunu gereksiz meşgul eder.
        if _gains_differ(gains, self._duck_gains):
            self._duck_gains = gains
            self.supervisor.apply_volumes(self.config, duck=gains)

    def _ducking_wanted(self) -> bool:
        """Herhangi bir kanalın aktif profilinde Smart Volume açık mı?"""
        return any(
            self.profile(channel.id).ducking.enabled for channel in self.config.channels
        )

    def _sync_duck_subscription(self) -> None:
        """Ducking açıkken ölçüm hep açık kalmalı: arayüz kapalıyken de çalışsın."""
        wanted = self._ducking_wanted()
        if wanted and not self._duck_meters:
            self.meters.subscribe()
            self._duck_meters = True
        elif not wanted and self._duck_meters:
            self.meters.unsubscribe()
            self._duck_meters = False

    def set_ducking(self, target: str, **fields: object) -> dict:
        """Bir **profilin** Smart Volume ayarları. Verilmeyen alanlar değişmez.

        Tetikleyici, profili taşıyan kanalın kendisi (şema 4). Gömülü bir preset
        düzenleniyorsa `_editable()` önce kopyaya geçirir — diğer profil düzenlemeleriyle
        aynı davranış.
        """
        if self.config.channel(target) is None:
            raise ApiError("unknown_channel", i18n.t("error.smart_output_only", name=target))
        duck = self._editable(target).ducking
        for name, value in fields.items():
            if not hasattr(duck, name):
                raise ApiError("unknown_field", i18n.t("error.unknown_smart_field", field=name))
            current = getattr(duck, name)
            if isinstance(current, bool):
                setattr(duck, name, bool(value))
            elif isinstance(current, list):
                ids = [str(v) for v in value] if isinstance(value, list | tuple) else []
                setattr(duck, name, [i for i in ids if self.config.channel(i) is not None])
            else:
                setattr(duck, name, float(value))  # type: ignore[arg-type]
        self.ducker.reset()
        self._duck_gains = {}
        self._sync_duck_subscription()
        self.supervisor.apply_volumes(self.config)
        self._dirty_profiles.add(target)
        self._emit({"kind": "ducking", "target": target})
        self._save_soon()
        return serde.to_jsonable(duck)

    def _chatmix_from_hardware(self, value: float) -> None:
        """Kulaklık tekeri döndü. Slider'ı sürer ve arayüze haber verir."""
        if self.config.settings.chatmix_source == "software":
            return
        if self.config.settings.chatmix_invert:
            value = 100.0 - value
        self.set_chatmix(value)
        self._emit({"kind": "chatmix_source", "hardware": True})

    def chatmix_is_hardware(self) -> bool:
        """ChatMix'i şu an kulaklık tekeri mi sürüyor?

        Arayüz slider'ı buna bakarak salt okunur yapıyor: iki kaynağın birbirini
        ezmesi kullanıcının istemediği şeydi.
        """
        source = self.config.settings.chatmix_source
        if source == "software":
            return False
        if source == "hardware":
            return True
        return self.chatmix_reader.active

    def _reconfigure_meters(self) -> None:
        self.meters.configure(meter_sources(self.config))

    def _on_links_changed(self, missing: list[tuple[str, str]]) -> None:
        if not missing:
            self._emit({"kind": "path_ok"})
            return
        names = sorted({self._channel_of_node(source) for source, _ in missing})
        self._emit(
            {
                "kind": "path_broken",
                "channels": [name for name in names if name],
                "links": [f"{source} → {target}" for source, target in sorted(missing)],
            }
        )

    def _channel_of_node(self, node: str) -> str:
        """`sonar_game_fx` → `Game`. Kullanıcıya node adı değil kanal adı gösterilir."""
        for channel in self.config.channels:
            if node == channel.fx_node:
                return channel.name
        return ""

    def _on_route(self, decision: Decision) -> None:
        self._emit(
            {
                "kind": "stream_routed",
                "stream": decision.stream_id,
                "channel": decision.channel_id,
                "reason": decision.reason,
            }
        )

    def _profile_provider(self, target: str, name: str) -> Profile:
        """Süpervizör grafı yeniden kurduğunda bellekteki hâli kullansın."""
        cached = self.profiles.get(target)
        if cached is not None and cached.name == name:
            return cached
        return self._load(target, name)

    def _touch_config(self, delta: dict) -> None:
        """Grafa dokunmayan bir ayar değişti: yalnızca kaydet ve haber ver."""
        self._dirty_config = True
        self._emit(delta)
        self._save_soon()

    def _live_targets(self, delta: dict) -> None:
        self.supervisor.apply_targets(self.config)
        self._dirty_config = True
        self._emit(delta)
        self._save_soon()

    def _live_volumes(self, delta: dict) -> None:
        self.supervisor.apply_volumes(self.config)
        self._dirty_config = True
        self._emit(delta)
        self._save_soon()

    def _live_target(self, target: str, delta: dict) -> None:
        self.supervisor.apply_target(self.config, target)
        self._dirty_profiles.add(target)
        self._dirty_config = True
        self._emit(delta)
        self._save_soon()

    def _structural(self, delta: dict) -> None:
        self._dirty_config = True
        self.supervisor.reconcile(self.config)
        # Node id'leri değişti ama kullanıcının kararları geçerli: akışları kararlarının
        # üstüne geri oturt. Eskiden burada `reset()` vardı ve hiçbir akış yeniden
        # yerleştirilmiyordu (bkz. `Router.reassert` başlığı).
        self.router.reassert(lambda name: self.supervisor.state.node_id(name) is not None)
        # Kanal eklendi/silindi olabilir: ölçüm noktaları yeniden bağlanmalı.
        self.meters.configure(meter_sources(self.config))
        self._emit(delta)
        if self.on_rebuild is not None:
            self.on_rebuild()
        self.flush_save()

    def _emit(self, delta: dict) -> None:
        if self.on_change is not None:
            try:
                self.on_change(delta)
            except Exception:  # pragma: no cover - dinleyici hatası API'yi düşürmemeli
                log.exception("durum dinleyicisi hata verdi")

    def _save_soon(self) -> None:
        if self.save_delay <= 0:
            self.flush_save()
            return
        with self._lock:
            if self._save_timer is not None:
                return
            self._save_timer = threading.Timer(self.save_delay, self.flush_save)
            self._save_timer.name = "sonar-save"
            self._save_timer.daemon = True
            self._save_timer.start()

    # ------------------------------------------------------------------ doğrulama

    def _channel(self, channel: str) -> Channel:
        found = self.config.channel(channel)
        if found is None:
            raise ApiError("unknown_channel", i18n.t("error.no_such_channel", name=channel))
        return found

    def _bus(self, bus: str, channel: Channel | None = None) -> str:
        """Bus kimliğini çözer.

        `"output"` özel bir addır: **varsayılan çıkış bus'ı** demek. Arayüzdeki kulaklık
        fader'ı bunu kullanıyor, böylece bus'ın kimliğini bilmek zorunda değil.

        Bir dönem kanal başına ayrı çıkış bus'ı vardı ve bu ad "kanalın seçtiği çıkış"
        anlamına geliyordu; kullanıcı karışıklık ürettiği için geri alındı (Faz 27).
        """
        if bus == "output":
            default = self.config.default_output_bus()
            if default is not None:
                return default.id
        if self.config.bus(bus) is None:
            names = ", ".join(b.id for b in self.config.ordered_buses())
            raise ApiError("unknown_bus", i18n.t("error.no_such_bus", name=bus, names=names))
        return bus

    def _master(self, bus: str):
        found = self.config.bus(bus)
        if found is None:
            names = ", ".join(b.id for b in self.config.ordered_buses())
            raise ApiError("unknown_bus", i18n.t("error.no_such_bus", name=bus, names=names))
        return found

    def _mic(self, chain: str):
        found = self.config.mic(chain)
        if found is None:
            raise ApiError("unknown_mic", i18n.t("error.no_such_mic", name=chain))
        return found

    def _slot(self, target: str, profile: Profile, slot: str) -> EffectSlot:
        """Slot kimliğini çözer.

        Geriye dönük kolaylık: eski istemciler aşama adı (`gate`) gönderiyor olabilir ve
        tek örnekli zincirlerde slot kimliği zaten aşama adının kendisi.
        """
        effect = profile.slot(slot)
        if effect is None:
            raise ApiError("unknown_stage", i18n.t("error.no_such_effect", name=slot))
        del target
        return effect

    def _stage(self, target: str, stage: str) -> FilterStage:
        try:
            value = FilterStage(stage)
        except ValueError as exc:
            raise ApiError("unknown_stage", i18n.t("error.unknown_stage", name=stage)) from exc
        if value is FilterStage.DEEPFILTER and self.config.mic(target) is None:
            raise ApiError(
                "stage_not_in_chain",
                i18n.t("error.stage_not_in_chain"),
            )
        return value

    def _check_target(self, target: str) -> None:
        if target not in self.config.profile_targets():
            raise ApiError("unknown_target", i18n.t("error.no_such_target", name=target))

    def _level(self, value: float) -> float:
        try:
            level = float(value)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_value", i18n.t("error.not_a_number", value=value)) from exc
        if not 0.0 <= level <= 4.0:
            raise ApiError("invalid_value", i18n.t("error.level_out_of_range", value=level))
        return level

    def _active_name(self, target: str) -> str:
        channel = self.config.channel(target)
        if channel is not None:
            return channel.active_profile
        mic = self.config.mic(target)
        if mic is not None:
            return mic.active_profile
        bus = self.config.bus(target)
        return bus.active_profile if bus is not None else "Default"

    def _set_active_name(self, target: str, name: str) -> None:
        for holder in (
            self.config.channel(target),
            self.config.mic(target),
            self.config.bus(target),
        ):
            if holder is not None:
                holder.active_profile = name
                break
        self._dirty_config = True


def _without(value: str, channel: str) -> str:
    """ChatMix'in virgüllü kanal listesinden bir kanalı çıkarır."""
    return ",".join(part for part in value.split(",") if part.strip() and part.strip() != channel)


def _stream_field(stream, key: MatchKey) -> str:
    from sonar.engine.router import stream_value

    return stream_value(stream, key)


def dsp_targets(config: SonarConfig) -> dict[str, str]:
    """Profil hedefi → DSP node'u. Arayüzün hata ayıklaması için dışa açılıyor."""
    return confgen.dsp_nodes(config)


def _gains_differ(new: dict[str, float], old: dict[str, float], epsilon: float = 0.002) -> bool:
    """Kazançlarda duyulur bir fark var mı? 0.002 lineer ≈ 0.02 dB."""
    if set(new) != set(old):
        return True
    return any(abs(new[key] - old[key]) > epsilon for key in new)
