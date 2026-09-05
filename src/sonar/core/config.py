"""Yapılandırmanın diskte kalıcılığı.

Yerleşim::

    ~/.config/sonar/config.toml              kanallar, fader'lar, kurallar, ayarlar
    ~/.config/sonar/profiles/<hedef>/*.json  kanal/mikrofon/bus profilleri
    ~/.local/state/sonar/graph.conf          üretilen PipeWire yapılandırması

Profiller ayrı dosyalarda tutulur; bir profil eklemek veya silmek `config.toml`'u yeniden
yazmaz. Bütün yazımlar atomiktir (geçici dosya + `os.replace`), böylece yarıda kesilen bir
yazım mevcut yapılandırmayı bozmaz.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from sonar.core import tomlio
from sonar.core.model import (
    DEFAULT_FILTER_PARAMS,
    DEFAULT_OUTPUT_BUS,
    SCHEMA_VERSION,
    STREAM_BUS,
    Profile,
    SonarConfig,
    default_config,
    default_profile,
)
from sonar.core.serde import SerdeError, from_jsonable, to_jsonable

log = logging.getLogger(__name__)

__all__ = [
    "ConfigStore",
    "Paths",
    "load",
    "load_profile",
    "save",
    "save_profile",
    "store",
]

_UNSAFE_NAME = re.compile(r"[^\w \-().çğıöşüÇĞİÖŞÜ]", re.UNICODE)
_MAX_NAME_LEN = 64


# --------------------------------------------------------------------------- yollar


@dataclass(frozen=True, slots=True)
class Paths:
    """Sonar'ın kullandığı dizinler. Testler kendi köklerini verebilir."""

    config_dir: Path
    state_dir: Path

    @classmethod
    def default(cls) -> Paths:
        config_home = Path(
            os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        ).expanduser()
        state_home = Path(
            os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
        ).expanduser()
        return cls(config_dir=config_home / "sonar", state_dir=state_home / "sonar")

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def ui_file(self) -> Path:
        return self.config_dir / "ui.json"

    @property
    def profiles_dir(self) -> Path:
        return self.config_dir / "profiles"

    @property
    def graph_conf(self) -> Path:
        return self.state_dir / "graph.conf"

    def profile_dir(self, target: str) -> Path:
        return self.profiles_dir / safe_name(target)

    def profile_file(self, target: str, name: str) -> Path:
        return self.profile_dir(target) / f"{safe_name(name)}.json"


def safe_name(name: str) -> str:
    """Kullanıcının verdiği adı güvenli bir dosya adına indirger."""
    cleaned = _UNSAFE_NAME.sub("_", name.strip())[:_MAX_NAME_LEN].strip(" .")
    return cleaned or "adsiz"


# --------------------------------------------------------------------------- atomik yazım


def write_atomic(path: Path, text: str) -> None:
    """Dosyayı atomik olarak yazar: aynı dizinde geçici dosya, fsync, sonra rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Rename'in kalıcı olduğundan emin olmak için dizini de senkronize et."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- depo


class ConfigStore:
    """Yapılandırma ve profillerin okunup yazıldığı yer."""

    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or Paths.default()

    # ------------------------------------------------------------------ config.toml

    def load(self, *, create_missing: bool = True) -> SonarConfig:
        """Yapılandırmayı okur.

        Dosya yoksa varsayılan üretilir (ve `create_missing` ise diske yazılır).
        Dosya bozuksa yedeklenip varsayılana düşülür — kullanıcı sessiz bir sistemle kalmaz.
        """
        path = self.paths.config_file
        if not path.exists():
            config = default_config()
            if create_missing:
                self.save(config)
                self.ensure_default_profiles(config)
            return config

        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            return self._recover(path, f"okunamadı: {exc}")

        try:
            config = from_jsonable(SonarConfig, migrate(raw))
        except (SerdeError, TypeError, ValueError) as exc:
            return self._recover(path, f"şemaya uymuyor: {exc}")

        self._collapse_extra_outputs(config)
        config.ensure_sends()
        if config.schema_version < 2:
            self._migrate_favorites(config)
        if config.schema_version < 4:
            self._migrate_ducking(raw, config)
        if config.schema_version < 5:
            self._migrate_mic_stream_send(config)
        if config.schema_version < 6:
            self._migrate_provisioned(config)
        if config.schema_version != SCHEMA_VERSION:
            config.schema_version = SCHEMA_VERSION
        return config

    def _migrate_provisioned(self, config: SonarConfig) -> None:
        """Şema 5 → 6: mevcut kurulumlar "kurulu" sayılır.

        `provisioned` varsayılanı `False` — yeni kullanıcı karşılama ekranını görsün diye.
        Ama diskte bir `config.toml` varsa o kullanıcının grafı bugün **zaten ayakta**;
        ona kurulum ekranı göstermek kanallarını sessizce söktürürdü. Dosyanın varlığı
        kurulumun kanıtıdır: bu göç yalnızca okunmuş bir dosya üzerinde çalışıyor.
        """
        config.settings.provisioned = True

    def _migrate_mic_stream_send(self, config: SonarConfig) -> None:
        """Şema 4 → 5: mikrofon yayın miksine katılır.

        Varsayılan `False`'tan `True`'ya döndü ve dataclass varsayılanı yalnızca **yeni**
        yapılandırmaları etkiliyor; mevcut dosyada `false` yazılı duruyor. Bu göç olmadan
        kullanıcı yeni davranışı hiç görmezdi — üstelik göçün düzelttiği şey tam da onun
        bildirdiği hata (yayında mikrofon duyulmuyor).

        Kullanıcı kapatırsa şema artık 5 olduğu için bir daha açılmaz.
        """
        for mic in config.mic_chains:
            mic.send_to_stream_bus = True

    def _migrate_ducking(self, raw: dict, config: SonarConfig) -> None:
        """Şema 3 → 4: Smart Volume ayarlardan profillere taşınır.

        Şema 3'te tek bir global blok vardı ve tetikleyici kanal ayrıca seçiliyordu.
        Şema 4'te ayar profilin içinde ve tetikleyici, profili taşıyan kanalın kendisi —
        kullanıcı her profilde ayrı olmasını istedi.

        Eski blok `trigger_channels` listesindeki kanalların **aktif** profillerine
        yazılır; o profiller diske kaydedilir.
        """
        old = raw.get("ducking")
        if not isinstance(old, dict) or not old.get("enabled"):
            return
        triggers = [c for c in (old.get("trigger_channels") or []) if config.channel(c)]
        fields = {
            key: old[key]
            for key in ("target_channels", "reduction_db", "threshold_db",
                        "attack_ms", "hold_ms", "release_ms")
            if key in old
        }  # fmt: skip
        for channel_id in triggers:
            channel = config.channel(channel_id)
            assert channel is not None
            profile = self.load_profile(channel_id, channel.active_profile)
            profile.ducking.enabled = True
            for key, value in fields.items():
                setattr(profile.ducking, key, value)
            self.save_profile(channel_id, profile)
            log.info("Smart Volume '%s/%s' profiline taşındı", channel_id, profile.name)

    def _collapse_extra_outputs(self, config: SonarConfig) -> None:
        """Fazladan çıkış bus'larını siler — artık tek çıkış var (Faz 27).

        Faz 20'de kanal başına ayrı fiziksel çıkış eklenebiliyordu; kullanıcı için
        karışıklık ürettiği için geri alındı. Eski bir yapılandırmada fazladan bus
        kalmışsa burada temizleniyor: kanallar varsayılan çıkışa döner, silinen bus'ın
        gönderileri düşer. Profil dosyaları diskte kalır — kullanıcı geri dönmek
        isterse elde olsun.
        """
        outputs = config.output_buses()
        if len(outputs) <= 1:
            return
        keep = config.bus(DEFAULT_OUTPUT_BUS) or outputs[0]
        dropped = [b.id for b in outputs if b.id != keep.id]
        config.buses = [b for b in config.buses if b.id == keep.id or b.is_stream]
        for channel in config.channels:
            for bus_id in dropped:
                channel.sends.pop(bus_id, None)
        log.info("fazladan çıkış bus'ı kaldırıldı: %s", ", ".join(dropped))

    def _migrate_favorites(self, config: SonarConfig) -> None:
        """Şema 1 → 2: favoriler profil dosyalarından yapılandırmaya taşınır.

        Şema 1'de favorilik profil dosyasında `favorite_slot` (1–9) olarak duruyordu;
        şema 2'de `config.favorites[hedef]` sıralı bir ad listesi ve sayı sınırı yok.
        Eski slot numaraları sıralamayı belirler.
        """
        for target in config.profile_targets():
            slots: list[tuple[int, str]] = []
            for name in self.list_profiles(target):
                path = self.paths.profile_file(target, name)
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                slot = raw.get("favorite_slot")
                if isinstance(slot, int) and slot > 0:
                    slots.append((slot, name))
            if slots:
                config.favorites[target] = [name for _, name in sorted(slots)]

    def save(self, config: SonarConfig) -> None:
        """Yapılandırmayı atomik olarak yazar."""
        config.schema_version = SCHEMA_VERSION
        text = _HEADER + tomlio.dumps(to_jsonable(config))
        write_atomic(self.paths.config_file, text)

    def _recover(self, path: Path, reason: str) -> SonarConfig:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.corrupt-{stamp}")
        log.warning("Yapılandırma %s — %s olarak yedeklendi, varsayılana dönülüyor", reason, backup)
        try:
            path.replace(backup)
        except OSError:
            log.warning("Bozuk yapılandırma yedeklenemedi: %s", path)
        config = default_config()
        self.save(config)
        self.ensure_default_profiles(config)
        return config

    # ------------------------------------------------------------------ profiller

    def list_profiles(self, target: str) -> list[str]:
        """Bir hedefin profillerini alfabetik döndürür; `Default` her zaman başta."""
        directory = self.paths.profile_dir(target)
        if not directory.is_dir():
            return []
        names = sorted(
            (p.stem for p in directory.glob("*.json")),
            key=lambda n: (n != "Default", n.casefold()),
        )
        return names

    def load_profile(self, target: str, name: str) -> Profile:
        """Profili okur. Dosya yoksa veya bozuksa varsayılan profil döndürülür."""
        path = self.paths.profile_file(target, name)
        if not path.exists():
            log.debug("Profil bulunamadı, varsayılan kullanılıyor: %s/%s", target, name)
            return default_profile(name)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            profile = from_jsonable(Profile, raw)
        except (OSError, json.JSONDecodeError, SerdeError, TypeError, ValueError) as exc:
            log.warning("Profil okunamadı (%s/%s): %s", target, name, exc)
            return default_profile(name)
        profile.name = name
        _normalise_filters(profile)
        return profile

    def save_profile(self, target: str, profile: Profile) -> None:
        path = self.paths.profile_file(target, profile.name)
        text = json.dumps(to_jsonable(profile), ensure_ascii=False, indent=2) + "\n"
        write_atomic(path, text)

    def delete_profile(self, target: str, name: str) -> bool:
        """Profili siler. `Default` silinemez."""
        if safe_name(name) == "Default":
            return False
        path = self.paths.profile_file(target, name)
        if not path.exists():
            return False
        path.unlink()
        return True

    def rename_profile(self, target: str, old: str, new: str) -> bool:
        if safe_name(old) == "Default" or not new.strip():
            return False
        source = self.paths.profile_file(target, old)
        if not source.exists():
            return False
        profile = self.load_profile(target, old)
        profile.name = new
        self.save_profile(target, profile)
        source.unlink()
        return True

    def delete_target(self, target: str) -> None:
        """Bir hedefin tüm profillerini siler. Kanal silinince çağrılır."""
        directory = self.paths.profile_dir(target)
        if not directory.is_dir():
            return
        for path in directory.glob("*.json"):
            path.unlink(missing_ok=True)
        try:
            directory.rmdir()
        except OSError:
            # İçinde tanımadığımız bir dosya kalmış: dizini bırak, profilleri sildik.
            log.warning("profil dizini boşaltılamadı: %s", directory)

    def ensure_default_profiles(self, config: SonarConfig) -> None:
        """Profili olmayan her hedef için bir `Default` üretir."""
        band_count = config.settings.default_band_count
        for target in config.profile_targets():
            path = self.paths.profile_file(target, "Default")
            if not path.exists():
                self.save_profile(target, default_profile("Default", band_count))

    # ------------------------------------------------------------------ arayüz durumu

    def load_ui_state(self) -> dict:
        try:
            return json.loads(self.paths.ui_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save_ui_state(self, state: dict) -> None:
        write_atomic(self.paths.ui_file, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


# --------------------------------------------------------------------------- göç


def migrate(raw: dict) -> dict:
    """Eski şema sürümlerini güncele taşır — **çözümlemeden önce**, ham sözlük üzerinde.

    Burada olmasının sebebi: `serde` bilinmeyen anahtarları sessizce atıyor. Kaldırılan
    bir alan (örneğin şema 2'deki `channels[].personal`) burada taşınmazsa kullanıcının
    fader'ları sessizce sıfırlanırdı.
    """
    version = raw.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version < 1:
        raise SerdeError(f"geçersiz schema_version: {version!r}")
    if version > SCHEMA_VERSION:
        raise SerdeError(
            f"yapılandırma daha yeni bir Sonar sürümüne ait (v{version} > v{SCHEMA_VERSION})"
        )
    if version < 3:
        raw = _migrate_to_buses(raw)
    # Şema 3 → 4 (Smart Volume'un profillere taşınması) `ConfigStore.load()` içinde
    # yapılıyor: profil **dosyalarına** yazmak gerekiyor, ham sözlükte yapılamaz.
    return raw


def _migrate_to_buses(raw: dict) -> dict:
    """Şema 2 → 3: iki sabit bus yerine adlandırılmış bus listesi.

    Şema 2'de her kanalın `personal` ve `stream` diye iki sabit gönderisi vardı ve
    yalnızca iki bus olabilirdi. Şema 3'te gönderiler bus kimliğine göre bir sözlük ve
    kullanıcı istediği kadar **çıkış** bus'ı ekleyebiliyor (Game hoparlöre, Media
    kulaklığa). Yayın bus'ı hâlâ tek.
    """
    for channel in raw.get("channels") or []:
        if not isinstance(channel, dict):
            continue
        sends = channel.setdefault("sends", {})
        for old, bus_id in (("personal", DEFAULT_OUTPUT_BUS), ("stream", STREAM_BUS)):
            value = channel.pop(old, None)
            if isinstance(value, dict):
                sends.setdefault(bus_id, value)
        channel.setdefault("output_bus", DEFAULT_OUTPUT_BUS)

    for order, bus in enumerate(raw.get("buses") or []):
        if not isinstance(bus, dict):
            continue
        bus.setdefault("kind", "stream" if bus.get("id") == STREAM_BUS else "output")
        bus.setdefault("order", order)
    return raw


_HEADER = f"""\
# Sonar yapılandırması — elle düzenlenebilir.
# Değişikliklerden sonra: sonar-cli reload  (veya daemon'u yeniden başlatın)
# Profiller bu dosyada değil, profiles/<hedef>/<ad>.json içinde tutulur.
# Şema sürümü: {SCHEMA_VERSION}

"""


# --------------------------------------------------------------------------- kolaylık

_default_store: ConfigStore | None = None


def store() -> ConfigStore:
    """Süreç genelinde paylaşılan varsayılan depo."""
    global _default_store
    if _default_store is None:
        _default_store = ConfigStore()
    return _default_store


def load() -> SonarConfig:
    return store().load()


def save(config: SonarConfig) -> None:
    store().save(config)


def _normalise_filters(profile: Profile) -> None:
    """Aşama parametrelerini bugünkü tanıma uydurur.

    Diskteki profiller eski parametre adlarını taşıyabiliyor: Spatial Audio bir dönem
    HRTF açılarıyla (`width_deg`, `elevation_deg`, `distance_m`) çalışıyordu, şimdi
    crossfeed ayarlarıyla (`immersion`, `distance`). Tanımda olmayan anahtarlar düşer,
    eksik olanlar varsayılanla dolar — böylece kullanıcının profili sessizce
    kullanılamaz hâle gelmiyor.
    """
    for stage, state in profile.filters.items():
        defaults = DEFAULT_FILTER_PARAMS.get(stage)
        if defaults is None:  # pragma: no cover - bilinmeyen aşama
            continue
        state.params = {
            key: state.params.get(key, default) for key, default in defaults.items()
        }


def load_profile(target: str, name: str) -> Profile:
    return store().load_profile(target, name)


def save_profile(target: str, profile: Profile) -> None:
    store().save_profile(target, profile)
