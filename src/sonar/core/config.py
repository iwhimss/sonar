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
    SCHEMA_VERSION,
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

        if config.schema_version != SCHEMA_VERSION:
            config.schema_version = SCHEMA_VERSION
        return config

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
    """Eski şema sürümlerini güncele taşır.

    Şu an tek bir sürüm var, dolayısıyla gövde boş. Yeni bir sürüm eklendiğinde buraya
    adım adım dönüşümler yazılır; her adım bir önceki sürümü bir sonrakine taşır.
    """
    version = raw.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version < 1:
        raise SerdeError(f"geçersiz schema_version: {version!r}")
    if version > SCHEMA_VERSION:
        raise SerdeError(
            f"yapılandırma daha yeni bir Sonar sürümüne ait (v{version} > v{SCHEMA_VERSION})"
        )
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


def load_profile(target: str, name: str) -> Profile:
    return store().load_profile(target, name)


def save_profile(target: str, profile: Profile) -> None:
    store().save_profile(target, profile)
