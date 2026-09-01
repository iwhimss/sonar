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
* **Yapısal** — kanal ekle/sil, cihaz değiştir, mikrofon monitörü/yayın gönderisi aç-kapa,
  band sayısı. `graph.conf` değişir, süreç yeniden başlar (~200 ms).

Mikrofon monitörü ve yayına gönderi bilinçli olarak **yapısal** listede: ikisi de conf'a
birer `loopback` modülü ekliyor.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from sonar.core import config as config_mod
from sonar.core import importers, presets, serde
from sonar.core.model import (
    SUPPORTED_BAND_COUNTS,
    BusId,
    Channel,
    EqBandType,
    FilterStage,
    MatchKey,
    MicChain,
    Profile,
    RoutingRule,
    SonarConfig,
    slugify,
)
from sonar.engine import confgen
from sonar.engine.headset import detect_headsets
from sonar.engine.meters import Level, MeterManager, meter_sources
from sonar.engine.router import Decision, Router
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
        store.ensure_default_profiles(self.config)
        #: Bellekte tutulan **çalışılan** profiller. Kullanıcı EQ'yu kurcaladığında burada
        #: değişir; diske yazım gecikmeli, grafa yazım anında.
        self.profiles: dict[str, Profile] = {}
        self._dirty_profiles: set[str] = set()
        self._dirty_config = False
        self._save_timer: threading.Timer | None = None
        self._lock = threading.RLock()

        supervisor.load_profile = self._profile_provider
        self.meters = MeterManager(on_levels=on_levels)
        self.meters.configure(meter_sources(self.config))
        self.router = Router(
            supervisor.state,
            supervisor.control.move_stream,
            lambda: self.config,
            on_route=self._on_route,
        )

    # ------------------------------------------------------------------ yaşam döngüsü

    def start(self) -> None:
        """Grafı kurar ve mevcut yapılandırmayı uygular."""
        self.supervisor.start_monitor()
        self.supervisor.monitor.wait_ready(timeout=5.0)
        self.supervisor.reconcile(self.config)
        self.supervisor.take_over_default_sink(self.config)

    def shutdown(self) -> None:
        self.flush_save()
        self.meters.stop()
        self.supervisor.stop()

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
            "conflicts": self.conflicts(),
            # Arayüz fader'ın altında "ChatMix yönetiyor" rozetini buna bakarak gösteriyor:
            # gösterilen değer taban seviye, duyulan ise taban × bu çarpan.
            "chatmix_gains": chatmix_gains(self.config),
            "headsets": self.headsets(),
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
                "message": (
                    f"{name} sistem geneli çalışıyor ve Sonar'ın çıkışını kendi zincirine "
                    f"çekiyor; seçtiğiniz çıkış cihazı yok sayılabilir. {name}'i kapatın "
                    f"veya Sonar'ın node'larını dışlama listesine ekleyin."
                ),
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
        self._channel(channel).send(self._bus(bus)).volume = self._level(value)
        self._live_volumes({"kind": "channel_volume", "channel": channel, "bus": bus})

    def set_channel_mute(self, channel: str, bus: str, muted: bool) -> None:
        self._channel(channel).send(self._bus(bus)).muted = bool(muted)
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

    # ------------------------------------------------------------------ filtreler

    def set_filter_enabled(self, target: str, stage: str, enabled: bool) -> None:
        profile = self._editable(target)
        if stage == FilterStage.EQ:
            profile.eq.enabled = bool(enabled)
        else:
            profile.filter(self._stage(target, stage)).enabled = bool(enabled)
        self._live_target(target, {"kind": "filter_enabled", "target": target, "stage": stage})

    def set_filter_param(self, target: str, stage: str, name: str, value: float) -> None:
        """`name` insan birimindeki parametre adıdır (`threshold_db`), port sembolü değil."""
        state = self._editable(target).filter(self._stage(target, stage))
        if name not in state.params:
            raise ApiError("unknown_param", f"'{stage}' aşamasında böyle bir parametre yok: {name}")
        state.params[name] = float(value)
        self._live_target(
            target, {"kind": "filter_param", "target": target, "stage": stage, "param": name}
        )

    def set_eq_enabled(self, target: str, enabled: bool) -> None:
        self.set_filter_enabled(target, FilterStage.EQ.value, enabled)

    def set_eq_preamp(self, target: str, value_db: float) -> None:
        self._editable(target).eq.preamp_db = float(value_db)
        self._live_target(target, {"kind": "eq_preamp", "target": target})

    def set_eq_band(self, target: str, band: int, field: str, value: float | str) -> None:
        eq = self._editable(target).eq
        if not 0 <= band < len(eq.bands):
            raise ApiError("unknown_band", f"band aralık dışında: {band}")
        if field not in _EQ_FIELDS:
            raise ApiError("unknown_field", f"bilinmeyen band alanı: {field}")
        target_band = eq.bands[band]
        if field == "band_type":
            try:
                target_band.band_type = EqBandType(str(value))
            except ValueError as exc:
                raise ApiError("unknown_field", f"bilinmeyen band tipi: {value}") from exc
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

    def set_band_count(self, target: str, count: int) -> None:
        """Band sayısı EQ eklentisinin kapasitesini belirler → **yapısal**."""
        if count not in SUPPORTED_BAND_COUNTS:
            raise ApiError(
                "unsupported_band_count",
                f"desteklenen band sayıları: {', '.join(map(str, SUPPORTED_BAND_COUNTS))}",
            )
        self._editable(target).eq.band_count = count
        self.config.settings.default_band_count = count
        self._structural({"kind": "band_count", "target": target})

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
            raise ApiError("profile_readonly", f"gömülü preset üzerine yazılamaz: {name}")
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
            raise ApiError("profile_readonly", f"gömülü preset silinemez: {name}")
        if not self.store.delete_profile(target, name):
            raise ApiError("profile_protected", f"bu profil silinemez: {name}")
        if self._active_name(target) == name:
            self.load_profile(target, "Default")
        self._emit({"kind": "profile_deleted", "target": target, "name": name})

    def rename_profile(self, target: str, old: str, new: str) -> None:
        self._check_target(target)
        if self._is_builtin(target, old):
            raise ApiError("profile_readonly", f"gömülü preset yeniden adlandırılamaz: {old}")
        if self._is_builtin(target, new):
            raise ApiError("profile_readonly", f"bu ad gömülü bir presete ait: {new}")
        if not self.store.rename_profile(target, old, new):
            raise ApiError("profile_not_renamed", f"profil yeniden adlandırılamadı: {old}")
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
            raise ApiError("profile_readonly", f"bu ad gömülü bir presete ait: {name}")
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
        flat.favorite_slot = working.favorite_slot
        self.profiles[target] = flat
        self._live_target(target, {"kind": "profile_reset", "target": target})

    def set_profile_favorite(self, target: str, name: str, slot: int) -> None:
        self._check_target(target)
        profile = self.store.load_profile(target, name)
        profile.favorite_slot = int(slot)
        self.store.save_profile(target, profile)
        if self._active_name(target) == name:
            self.profile(target).favorite_slot = int(slot)
        self._emit({"kind": "profile_favorite", "target": target, "name": name, "slot": slot})

    # ------------------------------------------------------------------ yapısal

    def set_bus_device(self, bus: str, device: str) -> None:
        self._master(bus).device = str(device)
        self._structural({"kind": "bus_device", "bus": bus})

    def set_mic_device(self, chain: str, device: str) -> None:
        self._mic(chain).source_device = str(device)
        self._structural({"kind": "mic_device", "chain": chain})

    def set_mic_monitor(self, chain: str, enabled: bool) -> None:
        self._mic(chain).monitor_enabled = bool(enabled)
        self._structural({"kind": "mic_monitor", "chain": chain})

    def set_mic_stream_send(self, chain: str, enabled: bool) -> None:
        self._mic(chain).send_to_stream_bus = bool(enabled)
        self._structural({"kind": "mic_stream_send", "chain": chain})

    def set_channel_stream_source(self, channel: str, enabled: bool) -> None:
        """Kanalın OBS için ayrı bir sanal giriş cihazı yayınlayıp yayınlamayacağı.

        Kapalıyken (varsayılan) kanal yalnızca birleşik Stream Mix üzerinden yayına
        gider ve sistemin mikrofon listesini kirletmez. **Yapısal** — graf yeniden kurulur.
        """
        self._channel(channel).stream_source = bool(enabled)
        self._structural({"kind": "channel_stream_source", "channel": channel})

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
            raise ApiError("invalid_name", "kanal adı boş olamaz")
        if direction not in ("output", "input"):
            raise ApiError("invalid_direction", f"yön 'output' veya 'input' olmalı: {direction}")

        channel_id = slugify(name)
        if channel_id in self.config.profile_targets():
            raise ApiError("duplicate_channel", f"bu kanal zaten var: {channel_id}")

        if direction == "output":
            self.config.channels.append(
                Channel(
                    id=channel_id,
                    name=name,
                    color=str(color),
                    order=self.config.next_channel_order(),
                )
            )
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
            raise ApiError("unknown_channel", f"böyle bir kanal yok: {channel}")

        self.profiles.pop(channel, None)
        self._dirty_profiles.discard(channel)
        self.store.delete_target(channel)
        self._structural({"kind": "channel_removed", "channel": channel})

    def _remove_output_channel(self, channel: str) -> None:
        if len(self.config.channels) <= 1:
            raise ApiError("last_channel", "en az bir çıkış kanalı kalmalı")

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

        # O kanalda çalan akışlar boşta kalmasın.
        for stream_id, target in list(self.router.decided.items()):
            if target == channel:
                self.router.decided.pop(stream_id, None)

    def _remove_input_channel(self, chain: str) -> None:
        if len(self.config.mic_chains) <= 1:
            raise ApiError("last_channel", "en az bir giriş kanalı kalmalı")
        mic = self.config.mic(chain)
        assert mic is not None
        if not mic.share_chain_with_mic and not any(
            m.id != chain and not m.share_chain_with_mic for m in self.config.mic_chains
        ):
            # Kendi DSP'si olan tek zinciri silmek, ondan beslenen zincirleri
            # kaynaksız bırakır (`confgen._primary_mic` hata yükseltir).
            raise ApiError(
                "mic_chain_needed",
                "kendi zincirine sahip son mikrofon silinemez; önce diğerlerini bağımsızlaştırın",
            )
        self.config.mic_chains = [m for m in self.config.mic_chains if m.id != chain]

    # ------------------------------------------------------------------ yönlendirme

    def move_stream(self, stream_id: int, channel: str, remember: bool = False) -> None:
        """Bir akışı elle taşır.

        `remember` verilirse uygulamanın binary'sinden kalıcı bir kural üretilir —
        arayüzdeki "bu uygulamayı hep buraya gönder" seçeneği bunu kullanır.
        """
        node = self._channel(channel).sink_node
        if not self.supervisor.control.move_stream(int(stream_id), node):
            raise ApiError("move_failed", f"akış taşınamadı: {stream_id}")
        # Kural motoru bu akışa bir daha dokunmasın: kullanıcının kararı kalıcıdır.
        self.router.mark_manual(int(stream_id), channel)
        self._emit({"kind": "stream_moved", "stream": int(stream_id), "channel": channel})
        if remember:
            self._remember_stream(int(stream_id), channel)

    def _remember_stream(self, stream_id: int, channel: str) -> None:
        stream = self.supervisor.state.streams.get(stream_id)
        if stream is None:
            raise ApiError("unknown_stream", f"böyle bir akış yok: {stream_id}")
        for key in (MatchKey.BINARY, MatchKey.APP_NAME, MatchKey.MEDIA_NAME):
            value = _stream_field(stream, key)
            if value:
                self.set_rule(key.value, value, channel)
                return
        raise ApiError(
            "not_identifiable",
            "bu akışın kural üretilebilecek bir kimliği yok (binary/ad/medya adı boş)",
        )

    def set_rule(self, match_key: str, pattern: str, channel: str, is_regex: bool = False) -> None:
        self._channel(channel)
        try:
            key = MatchKey(match_key)
        except ValueError as exc:
            raise ApiError(
                "unknown_match_key", f"bilinmeyen eşleşme anahtarı: {match_key}"
            ) from exc
        if not str(pattern).strip():
            raise ApiError("invalid_pattern", "desen boş olamaz")
        for rule in self.config.rules:
            if rule.match_key == key and rule.pattern == pattern:
                rule.channel_id = channel
                rule.is_regex = bool(is_regex)
                rule.enabled = True
                break
        else:
            self.config.rules.append(
                RoutingRule(
                    match_key=key, pattern=pattern, channel_id=channel, is_regex=bool(is_regex)
                )
            )
        self._emit({"kind": "rules", "pattern": pattern})
        self._save_soon()

    def remove_rule(self, match_key: str, pattern: str) -> None:
        before = len(self.config.rules)
        self.config.rules = [
            r for r in self.config.rules if not (r.match_key == match_key and r.pattern == pattern)
        ]
        if len(self.config.rules) == before:
            raise ApiError("unknown_rule", f"böyle bir kural yok: {match_key}={pattern}")
        self._emit({"kind": "rules", "pattern": pattern})
        self._save_soon()

    # ------------------------------------------------------------------ ChatMix

    def set_chatmix(self, value: float) -> None:
        self.config.chatmix.value = max(0.0, min(100.0, float(value)))
        self._live_volumes({"kind": "chatmix", "value": self.config.chatmix.value})

    def set_chatmix_config(self, enabled: bool, left: str, right: str) -> None:
        """`left`/`right` virgülle birden fazla kanal alabilir ("chat,media")."""
        from sonar.core.model import _split_channels

        for side in (left, right):
            channels = _split_channels(side)
            if not channels:
                raise ApiError("invalid_value", "en az bir kanal gerekli")
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
                    "message": f"Ayarlar diske yazılamadı ({error.strerror or error}). "
                    f"Değişiklikler çalışıyor ama yeniden başlatınca kaybolacak.",
                }
            )

    # ------------------------------------------------------------------ iç kısım

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
        # Node id'leri değişti; hangi akışın nereye gittiğine dair kayıt geçersiz.
        self.router.reset()
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
            raise ApiError("unknown_channel", f"böyle bir kanal yok: {channel}")
        return found

    def _bus(self, bus: str) -> BusId:
        try:
            return BusId(bus)
        except ValueError as exc:
            raise ApiError("unknown_bus", f"bus 'personal' veya 'stream' olmalı: {bus}") from exc

    def _master(self, bus: str):
        found = self.config.bus(self._bus(bus))
        if found is None:  # pragma: no cover - varsayılan config her ikisini de içerir
            raise ApiError("unknown_bus", f"böyle bir bus yok: {bus}")
        return found

    def _mic(self, chain: str):
        found = self.config.mic(chain)
        if found is None:
            raise ApiError("unknown_mic", f"böyle bir mikrofon zinciri yok: {chain}")
        return found

    def _stage(self, target: str, stage: str) -> FilterStage:
        try:
            value = FilterStage(stage)
        except ValueError as exc:
            raise ApiError("unknown_stage", f"bilinmeyen filtre aşaması: {stage}") from exc
        if value is FilterStage.DEEPFILTER and self.config.mic(target) is None:
            raise ApiError(
                "stage_not_in_chain",
                "gürültü engelleme yalnızca mikrofon zincirinde var",
            )
        return value

    def _check_target(self, target: str) -> None:
        if target not in self.config.profile_targets():
            raise ApiError("unknown_target", f"böyle bir profil hedefi yok: {target}")

    def _level(self, value: float) -> float:
        try:
            level = float(value)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_value", f"sayı bekleniyordu: {value!r}") from exc
        if not 0.0 <= level <= 4.0:
            raise ApiError("invalid_value", f"ses seviyesi 0–4 aralığında olmalı: {level}")
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
