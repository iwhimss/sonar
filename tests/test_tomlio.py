from __future__ import annotations

import math
import tomllib

import pytest

from sonar.core import tomlio
from sonar.core.config import _HEADER
from sonar.core.model import default_config
from sonar.core.serde import to_jsonable


def roundtrip(data: dict) -> dict:
    return tomllib.loads(tomlio.dumps(data))


def test_scalars():
    data = {"s": "merhaba", "i": 42, "f": 1.5, "b": True, "neg": -3}
    assert roundtrip(data) == data


def test_integral_float_stays_float():
    text = tomlio.dumps({"v": 1.0})
    assert "1.0" in text
    assert isinstance(tomllib.loads(text)["v"], float)


def test_nested_tables():
    data = {"a": 1, "sub": {"b": 2, "deep": {"c": 3}}}
    assert roundtrip(data) == data


def test_table_arrays():
    data = {"channels": [{"id": "game", "send": {"volume": 1.0}}, {"id": "chat", "send": {}}]}
    got = roundtrip(data)
    assert [c["id"] for c in got["channels"]] == ["game", "chat"]
    assert got["channels"][0]["send"]["volume"] == 1.0


def test_empty_list_is_inline_array():
    assert roundtrip({"rules": []}) == {"rules": []}


def test_string_escaping():
    data = {"k": 'tırnak " ters \\ satır\n sekme\t'}
    assert roundtrip(data) == data


def test_non_bare_key_is_quoted():
    data = {"Attenuation Limit (dB)": 40.0}
    assert roundtrip(data) == data


def test_none_is_rejected():
    with pytest.raises(tomlio.TomlWriteError):
        tomlio.dumps({"k": None})


def test_unsupported_type_is_rejected():
    with pytest.raises(tomlio.TomlWriteError):
        tomlio.dumps({"k": object()})


def test_special_floats():
    text = tomlio.dumps({"a": math.inf, "b": -math.inf})
    got = tomllib.loads(text)
    assert got["a"] == math.inf
    assert got["b"] == -math.inf


def test_default_config_roundtrips_through_toml():
    data = to_jsonable(default_config())
    assert roundtrip(data) == data


def test_header_plus_body_parses():
    text = _HEADER + tomlio.dumps(to_jsonable(default_config()))
    assert tomllib.loads(text)["schema_version"] == 4
