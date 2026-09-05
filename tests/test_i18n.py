"""Çeviri kataloglarının bütünlüğü.

Katalog düz JSON olduğu için Qt Linguist'in "eksik çeviri" raporu yok; onun yerini bu
dosya alıyor. Dört soru soruyor ve dördü de sessiz hataları yakalıyor:

* iki dilde **aynı** anahtarlar var mı (biri eklenip diğeri unutulmuş mu),
* yer tutucular eşleşiyor mu (`{name}` çevrilirken kaybolmuş mu),
* kaynakta çağrılan her anahtarın karşılığı var mı (yazım hatası),
* katalogda kullanılmayan anahtar kalmış mı (ölü çeviri).

Üçüncüsü olmasa eksik bir anahtar ancak kullanıcı o ekranı açtığında, ekranda ham
anahtar metniyle görünürdü.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sonar.core import i18n

SOURCE_ROOT = Path(i18n.__file__).resolve().parent.parent
#: `t("x.y")`, `i18n.t("x.y")`, `I18n.t("x.y")`, `I18n.tf("x.y", {...})`, `tr("x.y")`.
KEY_CALL = re.compile(r"\bt[fr]?\(\s*[\"']([a-z0-9_]+(?:\.[a-z0-9_]+)+)[\"']")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def catalogs() -> dict[str, dict[str, str]]:
    out = {}
    for code in i18n.LANGUAGES:
        path = i18n.catalog_dir() / f"{code}.json"
        out[code] = json.loads(path.read_text(encoding="utf-8"))
    return out


def source_files() -> list[Path]:
    """Çeviri çağrısı içerebilecek kaynaklar. `core/i18n.py` kendisi hariç."""
    files = [p for p in SOURCE_ROOT.rglob("*.py") if p.name != "i18n.py"]
    files += list(SOURCE_ROOT.rglob("*.qml"))
    return sorted(files)


def used_keys() -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for path in source_files():
        for key in KEY_CALL.findall(path.read_text(encoding="utf-8")):
            found.setdefault(key, []).append(path)
    return found


def test_every_language_has_a_catalog():
    for code in i18n.LANGUAGES:
        assert (i18n.catalog_dir() / f"{code}.json").exists(), f"{code}.json yok"


def test_catalogs_have_the_same_keys():
    data = catalogs()
    reference = set(data[i18n.DEFAULT_LANGUAGE])
    for code, entries in data.items():
        missing = sorted(reference - set(entries))
        extra = sorted(set(entries) - reference)
        assert not missing, f"{code}.json içinde eksik: {missing[:10]}"
        assert not extra, f"{code}.json içinde fazladan: {extra[:10]}"


def test_placeholders_match_across_languages():
    data = catalogs()
    reference = data[i18n.DEFAULT_LANGUAGE]
    for code, entries in data.items():
        if code == i18n.DEFAULT_LANGUAGE:
            continue
        for key, text in entries.items():
            expected = set(PLACEHOLDER.findall(reference[key]))
            actual = set(PLACEHOLDER.findall(text))
            assert expected == actual, f"{code}.json '{key}': yer tutucular {actual} ≠ {expected}"


def test_no_empty_translations():
    for code, entries in catalogs().items():
        empty = sorted(key for key, text in entries.items() if not text.strip())
        assert not empty, f"{code}.json boş çeviri: {empty[:10]}"


def test_every_used_key_exists():
    entries = catalogs()[i18n.DEFAULT_LANGUAGE]
    missing = {
        key: [p.name for p in paths]
        for key, paths in used_keys().items()
        if key not in entries
    }
    assert not missing, f"katalogda olmayan anahtarlar kullanılıyor: {missing}"


def test_no_dead_translations():
    entries = set(catalogs()[i18n.DEFAULT_LANGUAGE])
    dead = sorted(entries - set(used_keys()))
    assert not dead, f"hiçbir yerde kullanılmayan çeviri: {dead}"


@pytest.mark.parametrize("code,expected", [
    ("tr", "tr"), ("en", "en"), ("tr_TR.UTF-8", "tr"), ("en-GB", "en"),
    ("de", "tr"), ("", "tr"),
])
def test_language_codes_are_normalized(code, expected):
    assert i18n.normalize(code) == expected


def test_missing_key_returns_the_key_itself():
    """Boş string dönseydi arayüzde boş bir etiket kalır ve fark edilmezdi."""
    i18n.set_language("tr")
    assert i18n.t("boyle.bir.anahtar.yok") == "boyle.bir.anahtar.yok"


def test_format_failure_falls_back_to_raw_text():
    i18n.set_language("tr")
    i18n._catalogs["tr"]["_probe"] = "merhaba {name}"
    try:
        assert i18n.t("_probe", isim="x") == "merhaba {name}"
        assert i18n.t("_probe", name="Fatih") == "merhaba Fatih"
    finally:
        i18n._catalogs["tr"].pop("_probe", None)
