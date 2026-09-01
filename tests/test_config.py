from __future__ import annotations

import json
import tomllib

import pytest

from sonar.core.config import ConfigStore, Paths, safe_name, write_atomic
from sonar.core.model import (
    BusId,
    EqBand,
    FilterStage,
    RoutingRule,
    default_config,
    default_profile,
)
from sonar.core.serde import SerdeError

# --------------------------------------------------------------------------- config.toml


def test_first_run_creates_config_and_profiles(config_store: ConfigStore):
    config = config_store.load()
    assert config_store.paths.config_file.exists()
    assert [c.id for c in config.ordered_channels()] == ["game", "chat", "media", "aux"]
    for target in config.profile_targets():
        assert config_store.paths.profile_file(target, "Default").exists()


def test_roundtrip_preserves_everything(config_store: ConfigStore):
    config = default_config()
    config.channel("game").personal.volume = 0.42
    config.channel("game").stream.muted = True
    config.bus(BusId.STREAM).device = "alsa_output.usb-Test"
    config.mic("mic").monitor_enabled = True
    config.chatmix.value = 73.5
    config.settings.take_over_default_sink = True
    config.rules.append(RoutingRule(match_key="binary", pattern="cs2", channel_id="game"))

    config_store.save(config)
    assert config_store.load() == config


def test_config_file_is_valid_toml_and_hand_editable(config_store: ConfigStore):
    config_store.save(default_config())
    text = config_store.paths.config_file.read_text(encoding="utf-8")
    assert text.startswith("# Sonar yapılandırması")
    raw = tomllib.loads(text)
    assert raw["schema_version"] == 2
    assert raw["channels"][0]["id"] == "game"


def test_hand_edited_value_is_read_back(config_store: ConfigStore):
    config_store.save(default_config())
    path = config_store.paths.config_file
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'default_channel = "media"', 'default_channel = "game"'
        ),
        encoding="utf-8",
    )
    assert config_store.load().settings.default_channel == "game"


# --------------------------------------------------------------------------- kurtarma


def test_unparseable_config_is_backed_up_and_reset(config_store: ConfigStore, caplog):
    config_store.save(default_config())
    config_store.paths.config_file.write_text("bu = geçersiz [ toml", encoding="utf-8")

    config = config_store.load()

    assert config == default_config()
    backups = list(config_store.paths.config_dir.glob("config.toml.corrupt-*"))
    assert len(backups) == 1
    assert "geçersiz" in backups[0].read_text(encoding="utf-8")


def test_schema_violation_is_backed_up_and_reset(config_store: ConfigStore):
    config_store.paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    config_store.paths.config_file.write_text(
        'schema_version = 1\n[[channels]]\nname = "Adsız"\n', encoding="utf-8"
    )
    config = config_store.load()
    assert config == default_config()
    assert list(config_store.paths.config_dir.glob("config.toml.corrupt-*"))


def test_newer_schema_version_is_refused(config_store: ConfigStore):
    config_store.paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    config_store.paths.config_file.write_text("schema_version = 99\n", encoding="utf-8")
    config = config_store.load()
    assert config == default_config()
    assert list(config_store.paths.config_dir.glob("config.toml.corrupt-*"))


def test_load_without_create_missing_does_not_write(paths: Paths):
    store = ConfigStore(paths)
    config = store.load(create_missing=False)
    assert config == default_config()
    assert not paths.config_file.exists()


# --------------------------------------------------------------------------- atomik yazım


def test_write_atomic_leaves_no_temp_files(tmp_path):
    target = tmp_path / "sub" / "f.txt"
    write_atomic(target, "merhaba")
    assert target.read_text(encoding="utf-8") == "merhaba"
    assert list(tmp_path.glob("sub/.*tmp")) == []


def test_write_atomic_keeps_old_content_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "f.txt"
    write_atomic(target, "eski")

    def boom(*_args, **_kwargs):
        raise OSError("disk dolu")

    monkeypatch.setattr("sonar.core.config.os.replace", boom)
    with pytest.raises(OSError):
        write_atomic(target, "yeni")

    assert target.read_text(encoding="utf-8") == "eski"
    assert list(tmp_path.glob(".*tmp")) == []


# --------------------------------------------------------------------------- profiller


def test_profile_roundtrip(config_store: ConfigStore):
    profile = default_profile("CS2")
    profile.eq.enabled = True
    profile.eq.bands[3].gain_db = 5.5
    profile.filter(FilterStage.GATE).enabled = True
    profile.filter(FilterStage.GATE).params["threshold_db"] = -35.0

    config_store.save_profile("game", profile)
    assert config_store.load_profile("game", "CS2") == profile


def test_profiles_are_separate_files(config_store: ConfigStore):
    config_store.load()
    before = config_store.paths.config_file.read_text(encoding="utf-8")
    config_store.save_profile("game", default_profile("Arc Raiders"))
    assert config_store.paths.config_file.read_text(encoding="utf-8") == before
    assert config_store.list_profiles("game") == ["Default", "Arc Raiders"]


def test_default_profile_sorts_first(config_store: ConfigStore):
    config_store.load()
    for name in ("Zebra", "alfa", "CS2"):
        config_store.save_profile("game", default_profile(name))
    assert config_store.list_profiles("game") == ["Default", "alfa", "CS2", "Zebra"]


def test_missing_profile_falls_back_to_default(config_store: ConfigStore):
    profile = config_store.load_profile("game", "YokBöyleBiri")
    assert profile.name == "YokBöyleBiri"
    assert profile.eq.enabled is False


def test_corrupt_profile_falls_back_to_default(config_store: ConfigStore):
    path = config_store.paths.profile_file("game", "Bozuk")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ bu json değil", encoding="utf-8")
    assert config_store.load_profile("game", "Bozuk").eq.enabled is False


def test_default_profile_cannot_be_deleted(config_store: ConfigStore):
    config_store.load()
    assert config_store.delete_profile("game", "Default") is False
    assert config_store.paths.profile_file("game", "Default").exists()


def test_delete_and_rename(config_store: ConfigStore):
    config_store.load()
    config_store.save_profile("game", default_profile("Eski"))
    assert config_store.rename_profile("game", "Eski", "Yeni") is True
    assert config_store.list_profiles("game") == ["Default", "Yeni"]
    assert config_store.delete_profile("game", "Yeni") is True
    assert config_store.list_profiles("game") == ["Default"]


def test_profile_json_is_readable(config_store: ConfigStore):
    profile = default_profile("Test")
    profile.eq.bands[0] = EqBand(freq=100.0, gain_db=3.0)
    config_store.save_profile("mic", profile)
    raw = json.loads(config_store.paths.profile_file("mic", "Test").read_text(encoding="utf-8"))
    assert raw["eq"]["bands"][0]["gain_db"] == 3.0
    assert raw["filters"]["gate"]["enabled"] is False


# --------------------------------------------------------------------------- dosya adı güvenliği


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CS2", "CS2"),
        ("v1.2 ayarı", "v1.2 ayarı"),  # nokta bilinçli olarak izinli
        ("a/b", "a_b"),
        ("", "adsiz"),
        ("   ", "adsiz"),
        ("Türkçe Profil", "Türkçe Profil"),
        (".", "adsiz"),
        ("..", "adsiz"),
        ("...", "adsiz"),
        ("a\x00b", "a_b"),
        ("x" * 200, "x" * 64),
    ],
)
def test_safe_name(raw, expected):
    assert safe_name(raw) == expected


@pytest.mark.parametrize(
    "raw", ["../../etc/passwd", "..", "/etc/passwd", "a/../../b", "\\..\\..\\x", "."]
)
def test_safe_name_never_escapes_its_directory(raw, tmp_path):
    """Adda eğik çizgi kalmadığı için üst dizine çıkmak mümkün olmamalı."""
    name = safe_name(raw)
    assert "/" not in name and "\\" not in name
    resolved = (tmp_path / f"{name}.json").resolve()
    assert resolved.parent == tmp_path.resolve()


def test_profile_path_stays_inside_profiles_dir(config_store: ConfigStore):
    path = config_store.paths.profile_file("../..", "../../evil")
    assert config_store.paths.profiles_dir in path.parents


def test_migrate_rejects_garbage_version():
    from sonar.core.config import migrate

    with pytest.raises(SerdeError):
        migrate({"schema_version": "abc"})


# --------------------------------------------------------------------------- şema 2 göçü


def test_favorites_move_from_profile_files_to_the_config(config_store: ConfigStore, tmp_path):
    """Şema 1'de favorilik profil dosyasında `favorite_slot` (1–9) olarak duruyordu."""
    import json

    config_store.save(default_config())
    for name, slot in (("CS2", 3), ("Arc", 1)):
        config_store.save_profile("game", default_profile(name))
        path = config_store.paths.profile_file("game", name)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["favorite_slot"] = slot
        path.write_text(json.dumps(raw), encoding="utf-8")

    # Yapılandırmayı şema 1'e geri düşür ki göç tetiklensin.
    config_path = config_store.paths.config_file
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("schema_version = 2", "schema_version = 1"),
        encoding="utf-8",
    )

    config = config_store.load()
    assert config.favorites["game"] == ["Arc", "CS2"], "eski slot numarası sırayı belirler"
    assert config.schema_version == 2


def test_a_config_without_old_favorites_migrates_to_an_empty_list(config_store: ConfigStore):
    config_store.save(default_config())
    config_path = config_store.paths.config_file
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("schema_version = 2", "schema_version = 1"),
        encoding="utf-8",
    )
    assert config_store.load().favorites == {}
