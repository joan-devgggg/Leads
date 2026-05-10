"""
Helpers seguros para preparar estructuras antes de serializar a JSON.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass


def _is_namedtuple(obj) -> bool:
    return isinstance(obj, tuple) and hasattr(obj, "_fields") and hasattr(obj, "_asdict")


def make_json_safe(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(key): make_json_safe(value) for key, value in obj.items()}
    if isinstance(obj, Mapping):
        return {str(key): make_json_safe(value) for key, value in obj.items()}
    if isinstance(obj, set):
        return [make_json_safe(value) for value in obj]
    if isinstance(obj, tuple):
        if _is_namedtuple(obj):
            return make_json_safe(obj._asdict())
        return [make_json_safe(value) for value in obj]
    if isinstance(obj, list):
        return [make_json_safe(value) for value in obj]
    if is_dataclass(obj):
        return make_json_safe(asdict(obj))
    if hasattr(obj, "__dict__"):
        return make_json_safe(vars(obj))
    return str(obj)
