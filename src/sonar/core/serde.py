"""Dataclass ↔ JSON/TOML uyumlu sözlük dönüşümü.

Model katmanındaki her dataclass'a elle `to_dict`/`from_dict` yazmak yerine tip
anotasyonlarından türeyen tek bir kodek kullanıyoruz. İki uyumluluk garantisi verir:

* **İleriye dönük:** okunan sözlükteki bilinmeyen anahtarlar sessizce yok sayılır, böylece
  eski bir sürüm yeni bir config dosyasını okuyabilir.
* **Geriye dönük:** eksik anahtarlar dataclass varsayılanına düşer, böylece yeni bir alan
  eklemek eski config dosyalarını bozmaz.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from enum import Enum
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

T = TypeVar("T")

__all__ = ["SerdeError", "from_jsonable", "to_jsonable"]


class SerdeError(ValueError):
    """Bir sözlük hedef tipe dönüştürülemedi."""


def to_jsonable(obj: Any) -> Any:
    """Dataclass ağacını JSON/TOML'a yazılabilir ilkel yapılara çevirir."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {_key_out(k): to_jsonable(v) for k, v in obj.items()}
    return obj


def from_jsonable(tp: type[T] | Any, value: Any, *, path: str = "") -> T:
    """`value`'yu `tp` tipine dönüştürür.

    `path` yalnızca hata mesajlarında kullanılır; iç içe yapılarda hatanın tam yerini gösterir.
    """
    origin = get_origin(tp)

    if origin in (types.UnionType, typing.Union):
        return _from_union(tp, value, path)
    if origin in (list, tuple):
        return _from_list(tp, value, path)
    if origin is dict:
        return _from_dict(tp, value, path)

    if isinstance(tp, type):
        if issubclass(tp, Enum):
            try:
                return tp(value)
            except ValueError as exc:
                raise SerdeError(f"{_at(path)}geçersiz {tp.__name__} değeri: {value!r}") from exc
        if dataclasses.is_dataclass(tp):
            return _from_dataclass(tp, value, path)
        return _from_scalar(tp, value, path)

    return value


# --------------------------------------------------------------------------- iç yardımcılar


def _at(path: str) -> str:
    return f"{path}: " if path else ""


def _sub(path: str, part: str) -> str:
    return f"{path}.{part}" if path else part


def _key_out(key: Any) -> str:
    if isinstance(key, Enum):
        return str(key.value)
    return str(key)


def _from_union(tp: Any, value: Any, path: str) -> Any:
    args = [a for a in get_args(tp) if a is not type(None)]
    if value is None:
        if len(args) != len(get_args(tp)):  # Optional idi
            return None
        raise SerdeError(f"{_at(path)}None kabul edilmiyor")
    errors: list[str] = []
    for arg in args:
        try:
            return from_jsonable(arg, value, path=path)
        except (SerdeError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    raise SerdeError(f"{_at(path)}hiçbir birleşim üyesine uymadı: {'; '.join(errors)}")


def _from_list(tp: Any, value: Any, path: str) -> Any:
    if not isinstance(value, list):
        raise SerdeError(f"{_at(path)}liste bekleniyordu, {type(value).__name__} geldi")
    args = get_args(tp)
    item_tp = args[0] if args else Any
    return [from_jsonable(item_tp, v, path=_sub(path, str(i))) for i, v in enumerate(value)]


def _from_dict(tp: Any, value: Any, path: str) -> Any:
    if not isinstance(value, dict):
        raise SerdeError(f"{_at(path)}sözlük bekleniyordu, {type(value).__name__} geldi")
    args = get_args(tp)
    key_tp, val_tp = args if args else (Any, Any)
    return {
        from_jsonable(key_tp, k, path=_sub(path, str(k))): from_jsonable(
            val_tp, v, path=_sub(path, str(k))
        )
        for k, v in value.items()
    }


def _from_dataclass(tp: type, value: Any, path: str) -> Any:
    if not isinstance(value, dict):
        raise SerdeError(f"{_at(path)}{tp.__name__} için sözlük bekleniyordu")
    hints = get_type_hints(tp)
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for f in dataclasses.fields(tp):
        if not f.init:
            continue
        if f.name in value:
            kwargs[f.name] = from_jsonable(hints[f.name], value[f.name], path=_sub(path, f.name))
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            missing.append(f.name)
    if missing:
        raise SerdeError(f"{_at(path)}{tp.__name__} için eksik alan(lar): {', '.join(missing)}")
    return tp(**kwargs)


def _from_scalar(tp: type, value: Any, path: str) -> Any:
    if tp is Any or tp is object:
        return value
    # bool, int'in alt sınıfı olduğu için önce kontrol edilmeli.
    if tp is bool:
        if isinstance(value, bool):
            return value
        raise SerdeError(f"{_at(path)}bool bekleniyordu, {value!r} geldi")
    if tp is int:
        if isinstance(value, bool):
            raise SerdeError(f"{_at(path)}int bekleniyordu, bool geldi")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise SerdeError(f"{_at(path)}int bekleniyordu, {value!r} geldi")
    if tp is float:
        if isinstance(value, bool):
            raise SerdeError(f"{_at(path)}float bekleniyordu, bool geldi")
        if isinstance(value, (int, float)):
            return float(value)
        raise SerdeError(f"{_at(path)}float bekleniyordu, {value!r} geldi")
    if tp is str:
        if isinstance(value, str):
            return value
        raise SerdeError(f"{_at(path)}str bekleniyordu, {value!r} geldi")
    if isinstance(value, tp):
        return value
    raise SerdeError(f"{_at(path)}{tp.__name__} bekleniyordu, {type(value).__name__} geldi")
