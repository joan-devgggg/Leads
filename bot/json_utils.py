"""
Helpers seguros para preparar estructuras antes de serializar a JSON.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass


def make_json_safe(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(key): make_json_safe(value) for key, value in obj.items()}
    if isinstance(obj, set):
        return [make_json_safe(value) for value in obj]
    if isinstance(obj, tuple):
        return [make_json_safe(value) for value in obj]
    if isinstance(obj, list):
        return [make_json_safe(value) for value in obj]
    if is_dataclass(obj):
        return make_json_safe(asdict(obj))
    if hasattr(obj, "__dict__"):
        return make_json_safe(vars(obj))
    return str(obj)
