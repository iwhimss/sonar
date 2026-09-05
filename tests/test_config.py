from __future__ import annotations

import json
import tomllib

import pytest

from sonar.core.config import ConfigStore, Paths, migrate_profile, safe_name, write_atomic
from sonar.core.model import (
    BusSend,
    EqBand,
    FilterStage,
    RoutingRule,
    default_config,
    default_profile,
)
from sonar.core.serde import SerdeError

# --------------------------------------------------------------------------- config.toml


def state_of(profile, kind):
    """Bir aşamanın profildeki durumu. Şema 7'de zincir slot listesi; testler aşama
    üzerinden bakmaya devam edebilsin diye ilk eşleşen slot dönüyor."""
    effect = next((e for e in profile.effects if e.kind is kind), None)
    return profile.state(effect.slot) if effect else None


def test_first_run_creates_config_and_profiles(config_store: ConfigStore):
    config = config_store.load()
    assert config_store.paths.config_file.exists()
    assert [c.id for c in config.ordered_channels()] == ["game", "chat", "media", "aux"]
    for target in config.profile_targets():
        assert config_store.paths.profile_file(target, "Default").exists()


def test_roundtrip_preserves_everything(config_store: ConfigStore):
    config = default_config()
    config.channel("game").output.volume = 0.42
    config.channel("game").stream.muted = True
    config.bus("stream").device = "alsa_output.usb-Test"
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
    assert raw["schema_version"] == 6
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
    from sonar.core.model import EffectSlot

    profile = default_profile("CS2")
    profile.eq.enabled = True
    profile.eq.bands[3].gain_db = 5.5
    from sonar.core.model import DEFAULT_FILTER_PARAMS

    # Yükleme parametreleri tanıma tamamlıyor (`_normalise_filters`); karşılaştırma
    # anlamlı olsun diye slot da tam parametreyle kuruluyor.
    profile.effects.append(
        EffectSlot(
            kind=FilterStage.GATE,
            slot="gate",
            params={**DEFAULT_FILTER_PARAMS[FilterStage.GATE], "threshold_db": -35.0},
        )
    )

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
    # Şema 7: zincir sıralı bir liste ve yeni profilde yalnızca ekolayzer var.
    assert [e["kind"] for e in raw["effects"]] == ["eq"]


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
        config_path.read_text(encoding="utf-8").replace("schema_version = 6", "schema_version = 1"),
        encoding="utf-8",
    )

    config = config_store.load()
    assert config.favorites["game"] == ["Arc", "CS2"], "eski slot numarası sırayı belirler"
    assert config.schema_version == 6


def test_a_config_without_old_favorites_migrates_to_an_empty_list(config_store: ConfigStore):
    config_store.save(default_config())
    config_path = config_store.paths.config_file
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("schema_version = 6", "schema_version = 1"),
        encoding="utf-8",
    )
    assert config_store.load().favorites == {}


# --------------------------------------------------------------------------- şema 2 → 3
#
# Şema 2'de her kanalın `personal` ve `stream` diye iki sabit gönderisi vardı ve yalnızca
# iki bus olabilirdi. Şema 3'te gönderiler bus kimliğine göre bir sözlük ve kullanıcı
# istediği kadar **çıkış** bus'ı ekleyebiliyor (Faz 20).
#
# Göç ham sözlük üzerinde yapılıyor: `serde` bilinmeyen anahtarları sessizce attığı için
# taşınmayan bir alan kullanıcının fader'larını sessizce sıfırlardı.


def _schema2_toml() -> str:
    return """\
schema_version = 2

[settings]
default_channel = "media"

[[channels]]
id = "game"
name = "Game"
color = "#22C58B"
order = 0
active_profile = "CS2"

[channels.personal]
volume = 0.42
muted = false

[channels.stream]
volume = 0.7
muted = true

[[buses]]
id = "personal"
name = "Personal Mix"
device = "alsa_output.usb-Test"
volume = 0.9

[[buses]]
id = "stream"
name = "Stream Mix"
"""


def test_schema_2_sends_move_into_the_bus_dictionary(config_store: ConfigStore):
    config_store.paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    config_store.paths.config_file.write_text(_schema2_toml(), encoding="utf-8")
    config = config_store.load()

    channel = config.channel("game")
    assert channel.send("personal").volume == 0.42
    assert channel.send("stream") == BusSend(volume=0.7, muted=True)
    assert config.schema_version == 6


def test_schema_2_buses_get_their_kind(config_store: ConfigStore):
    config_store.paths.config_file.parent.mkdir(parents=True, exist_ok=True)
    config_store.paths.config_file.write_text(_schema2_toml(), encoding="utf-8")
    config = config_store.load()

    assert [b.id for b in config.output_buses()] == ["personal"]
    assert config.stream_bus().id == "stream"
    assert config.bus("personal").device == "alsa_output.usb-Test"


def test_extra_output_buses_are_collapsed(config_store: ConfigStore):
    """Faz 20'de kanal başına ayrı çıkış eklenebiliyordu; Faz 27'de geri alındı.

    Eski bir yapılandırmada fazladan bus kalmışsa yüklemede temizlenmeli, yoksa graf
    kullanıcının bir daha ulaşamayacağı node'lar kurmaya devam ederdi.
    """
    from sonar.core.model import BusKind, MasterBus

    config = default_config()
    config.buses.append(MasterBus(id="hoparlor", name="Hoparlör", kind=BusKind.OUTPUT, order=2))
    config.ensure_sends()
    config_store.save(config)

    loaded = config_store.load()

    assert [b.id for b in loaded.output_buses()] == ["personal"]
    assert loaded.stream_bus() is not None
    assert all("hoparlor" not in c.sends for c in loaded.channels)


def test_ducking_moves_from_settings_into_the_active_profiles(config_store: ConfigStore):
    """Şema 3 → 4: Smart Volume global bir bloktu, artık profilin içinde."""
    config = default_config()
    config.channel("chat").active_profile = "Oyun"
    config_store.save(config)
    config_store.save_profile("chat", default_profile("Oyun"))

    path = config_store.paths.config_file
    text = path.read_text(encoding="utf-8").replace("schema_version = 6", "schema_version = 3")
    path.write_text(
        text
        + "\n[ducking]\nenabled = true\ntrigger_channels = [\"chat\"]\n"
          "reduction_db = -9.0\nhold_ms = 250.0\n",
        encoding="utf-8",
    )

    loaded = config_store.load()

    assert loaded.schema_version == 6
    duck = config_store.load_profile("chat", "Oyun").ducking
    assert duck.enabled is True
    assert duck.reduction_db == -9.0
    assert duck.hold_ms == 250.0
    # Diğer kanallara dokunulmadı.
    assert config_store.load_profile("game", "Default").ducking.enabled is False


def test_stale_filter_params_are_normalised(config_store: ConfigStore):
    """Spatial Audio HRTF açılarından crossfeed ayarlarına geçti; eski profiller kalıcı.

    Tanımda olmayan anahtarlar düşmeli, eksik olanlar varsayılanla dolmalı — yoksa
    kullanıcının profili sessizce kullanılamaz hâle gelirdi.
    """
    import json

    from sonar.core.model import DEFAULT_FILTER_PARAMS, FilterStage

    profile = default_profile("Eski")
    config_store.save_profile("game", profile)
    path = config_store.paths.profile_file("game", "Eski")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["effects"].append(
        {
            "kind": "spatial",
            "slot": "spatial",
            "enabled": True,
            "params": {"width_deg": 30.0, "elevation_deg": 0.0, "distance_m": 1.0},
        }
    )
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = config_store.load_profile("game", "Eski")

    assert set(loaded.state("spatial").params) == set(
        DEFAULT_FILTER_PARAMS[FilterStage.SPATIAL]
    )
    assert loaded.state("spatial").enabled is True, "açık/kapalı korunmalı"


# --------------------------------------------------------------------------- şema 5 → 6


def test_a_fresh_config_is_not_provisioned_yet(config_store: ConfigStore):
    """Yeni kullanıcı karşılama ekranını görmeli: kanallar henüz kurulmadı."""
    config = config_store.load()
    assert config.settings.provisioned is False
    assert config.settings.language == "tr"


def test_an_existing_config_counts_as_provisioned(config_store: ConfigStore):
    """Diskte config.toml varsa o kullanıcının grafı bugün zaten ayakta.

    Göç olmasaydı mevcut kullanıcılar bir güncellemeden sonra kanallarını kaybedip
    kurulum ekranıyla karşılaşırdı.
    """
    config_store.save(default_config())
    path = config_store.paths.config_file
    path.write_text(
        path.read_text(encoding="utf-8").replace("schema_version = 6", "schema_version = 5"),
        encoding="utf-8",
    )

    loaded = config_store.load()

    assert loaded.settings.provisioned is True
    assert loaded.schema_version == 6


# --------------------------------------------------------------------------- profil şema 6 → 7


def test_profile_migration_keeps_only_the_enabled_stages(config_store: ConfigStore):
    """Şema 6'da yedi aşamanın hepsi profilde duruyordu; kapalı olanlar da görünüyordu.

    Kullanıcının isteği (test turu 6): *"Profil ayarlarına girince sadece ekolayzer
    gözüksün."* Göç bu yüzden kapalı aşamaları düşürüyor — parametreleri zaten
    varsayılandaydı, bilgi kaybı yok.
    """
    raw = {
        "name": "Eski",
        "eq": {"enabled": True, "band_count": 10, "preamp_db": 0.0, "bands": []},
        "filters": {
            "gate": {"enabled": False, "params": {"threshold_db": -30.0}},
            "comp": {"enabled": True, "params": {"ratio": 8.0}},
            "lim": {"enabled": True, "params": {}},
        },
    }

    migrated = migrate_profile(raw)

    assert [e["kind"] for e in migrated["effects"]] == ["eq", "comp", "lim"]
    assert migrated["effects"][0]["enabled"] is True, "EQ'nun bayrağı `eq`'ten geliyor"
    assert migrated["effects"][1]["params"]["ratio"] == 8.0
    assert "filters" not in migrated


def test_profile_migration_keeps_the_chain_order(config_store: ConfigStore):
    """Göçte sıra `CHAIN_ORDER`: kullanıcının duyduğu ses değişmemeli."""
    raw = {
        "name": "Eski",
        "eq": {"enabled": False, "band_count": 10, "preamp_db": 0.0, "bands": []},
        "filters": {stage: {"enabled": True, "params": {}} for stage in ("lim", "gate", "comp")},
    }
    assert [e["kind"] for e in migrate_profile(raw)["effects"]] == ["eq", "gate", "comp", "lim"]


def test_an_already_migrated_profile_is_left_alone(config_store: ConfigStore):
    raw = {"name": "Yeni", "effects": [{"kind": "eq", "slot": "eq"}]}
    assert migrate_profile(raw) is raw


def test_duplicate_slot_ids_are_repaired_on_load(config_store: ConfigStore):
    """Elle düzenlenmiş bir dosya aynı node adını iki kez taşıyabilir.

    Graf node adları çakışırsa `pipewire -c` zinciri hiç kuramaz — sessiz bir felaket.
    """
    from sonar.core.model import EffectSlot, FilterStage

    profile = default_profile("Bozuk")
    profile.effects.append(EffectSlot(kind=FilterStage.COMP, slot="comp"))
    profile.effects.append(EffectSlot(kind=FilterStage.COMP, slot="comp"))
    config_store.save_profile("game", profile)

    loaded = config_store.load_profile("game", "Bozuk")

    slots = [e.slot for e in loaded.effects]
    assert slots == ["eq", "comp", "comp2"]
    assert len(set(slots)) == len(slots)
