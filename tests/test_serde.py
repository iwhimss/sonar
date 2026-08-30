from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import pytest

from sonar.core.serde import SerdeError, from_jsonable, to_jsonable


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


@dataclass
class Leaf:
    value: float = 1.0
    label: str = "x"


@dataclass
class Node:
    name: str
    color: Color = Color.RED
    leaf: Leaf = field(default_factory=Leaf)
    children: list[Leaf] = field(default_factory=list)
    table: dict[Color, Leaf] = field(default_factory=dict)
    optional: int | None = None


def test_roundtrip():
    node = Node(
        name="kök",
        color=Color.BLUE,
        leaf=Leaf(2.5, "y"),
        children=[Leaf(1.0), Leaf(3.0, "z")],
        table={Color.RED: Leaf(9.0)},
        optional=7,
    )
    assert from_jsonable(Node, to_jsonable(node)) == node


def test_enum_keys_become_strings():
    data = to_jsonable(Node(name="a", table={Color.BLUE: Leaf()}))
    assert list(data["table"]) == ["blue"]


def test_unknown_keys_are_ignored():
    """İleriye dönük uyumluluk: eski sürüm yeni bir dosyayı okuyabilmeli."""
    node = from_jsonable(Node, {"name": "a", "gelecekteki_alan": 123})
    assert node.name == "a"


def test_missing_keys_fall_back_to_defaults():
    """Geriye dönük uyumluluk: yeni alan eski dosyayı bozmamalı."""
    node = from_jsonable(Node, {"name": "a"})
    assert node.color is Color.RED
    assert node.leaf == Leaf()


def test_missing_required_field_raises():
    with pytest.raises(SerdeError, match="eksik alan"):
        from_jsonable(Node, {})


def test_bad_enum_value_raises():
    with pytest.raises(SerdeError, match="geçersiz Color"):
        from_jsonable(Node, {"name": "a", "color": "yeşil"})


def test_int_widens_to_float():
    assert from_jsonable(Leaf, {"value": 3}).value == 3.0


def test_bool_is_not_an_int():
    with pytest.raises(SerdeError):
        from_jsonable(Node, {"name": "a", "optional": True})


def test_optional_accepts_none():
    assert from_jsonable(Node, {"name": "a", "optional": None}).optional is None


def test_error_path_points_at_the_field():
    with pytest.raises(SerdeError, match=r"children\.1\.value"):
        from_jsonable(Node, {"name": "a", "children": [{}, {"value": "abc"}]})
