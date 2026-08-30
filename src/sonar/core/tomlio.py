"""Küçük bir TOML yazıcı.

Python'un standart kütüphanesinde TOML **okuyucusu** var (`tomllib`) ama yazıcısı yok.
Yapılandırmayı JSON'a çevirmek yerine TOML'da tutmayı tercih ediyoruz çünkü kullanıcının
`config.toml`'u elle açıp düzenlemesi tasarımın bir parçası.

Bu yazıcı genel amaçlı bir TOML kütüphanesi değildir; yalnızca bizim şemamızın ürettiği
yapıları (iç içe tablolar, tablo dizileri, ilkel değerler ve ilkel diziler) kapsar.
`tomllib` ile yuvarlak yolculuk testi `tests/test_tomlio.py` içinde.
"""

from __future__ import annotations

from typing import Any

__all__ = ["TomlWriteError", "dumps"]

_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}

_BARE_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


class TomlWriteError(TypeError):
    """Değer TOML'a yazılamıyor."""


def dumps(data: dict[str, Any]) -> str:
    """Bir sözlüğü TOML metnine çevirir."""
    if not isinstance(data, dict):
        raise TomlWriteError("kök değer sözlük olmalı")
    lines: list[str] = []
    _emit_table(data, (), lines, is_root=True)
    text = "\n".join(lines).rstrip("\n")
    return text + "\n" if text else ""


# --------------------------------------------------------------------------- iç yapı


def _emit_table(
    table: dict[str, Any], path: tuple[str, ...], lines: list[str], *, is_root: bool = False
) -> None:
    """Bir tabloyu yazar.

    Başlığı **yalnızca** bu fonksiyon yazar; çağıran taraf yazmaz. Aksi hâlde boş bir alt
    tablo iki kez bildirilir ve TOML ayrıştırıcısı "Cannot declare twice" hatası verir.
    `is_root` başlığın zaten yazıldığını (veya kök olduğu için gerekmediğini) bildirir.
    """
    scalars: list[tuple[str, Any]] = []
    subtables: list[tuple[str, dict]] = []
    tablearrays: list[tuple[str, list]] = []

    for key, value in table.items():
        if isinstance(value, dict):
            subtables.append((key, value))
        elif _is_table_array(value):
            tablearrays.append((key, value))
        else:
            scalars.append((key, value))

    if not is_root:
        _blank(lines)
        lines.append(f"[{_path(path)}]")

    for key, value in scalars:
        lines.append(f"{_key(key)} = {_value(value)}")

    for key, value in subtables:
        _emit_table(value, (*path, key), lines)

    for key, items in tablearrays:
        child = (*path, key)
        for item in items:
            _blank(lines)
            lines.append(f"[[{_path(child)}]]")
            _emit_table(item, child, lines, is_root=True)


def _blank(lines: list[str]) -> None:
    if lines and lines[-1] != "":
        lines.append("")


def _is_table_array(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0 and all(isinstance(v, dict) for v in value)


def _path(path: tuple[str, ...]) -> str:
    return ".".join(_key(p) for p in path)


def _key(key: Any) -> str:
    text = str(key)
    if text and all(c in _BARE_KEY_CHARS for c in text):
        return text
    return _string(text)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _float(value)
    if isinstance(value, str):
        return _string(value)
    if value is None:
        raise TomlWriteError("TOML'da None karşılığı yok; alanı atlayın veya varsayılan verin")
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items())
        return "{" + inner + "}"
    raise TomlWriteError(f"TOML'a yazılamayan tip: {type(value).__name__}")


def _float(value: float) -> str:
    if value != value:  # NaN
        return "nan"
    if value == float("inf"):
        return "inf"
    if value == float("-inf"):
        return "-inf"
    text = repr(float(value))
    # TOML float'ı ondalık nokta veya üs gerektirir: "1" geçersiz, "1.0" geçerli.
    if "." not in text and "e" not in text and "E" not in text:
        text += ".0"
    return text


def _string(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)
