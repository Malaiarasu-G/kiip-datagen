"""Load config/config.yaml into a plain attribute-accessible object.

Only this module knows about the YAML file shape — everything else just reads
attributes off the `Config` it returns, so the YAML can grow without touching
this loader.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Union

import yaml


def _to_namespace(obj: Any) -> Any:
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_to_namespace(v) for v in obj]
    return obj


class Config(SimpleNamespace):
    """Attribute-accessible config, already resolved for one scale preset."""


def load_config(path: Union[str, Path], scale: str = "dev") -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    if scale not in raw["volumes"]:
        raise ValueError(f"Unknown scale '{scale}'. Choose one of: {list(raw['volumes'])}")
    raw["volumes"] = raw["volumes"][scale]
    raw["scale"] = scale

    as_of = raw["dates"].get("as_of_date")
    raw["dates"]["as_of_date"] = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
    raw["dates"]["history_start"] = dt.date.fromisoformat(raw["dates"]["history_start"])
    raw["dates"]["history_end"] = dt.date.fromisoformat(raw["dates"]["history_end"])

    return _to_namespace(raw)
