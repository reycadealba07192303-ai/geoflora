"""Configuration loading. One YAML file holds every stage's settings (configs/default.yaml)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .utils import PROJECT_ROOT, resolve_path

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


def deep_update(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_update(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Load the default config, optionally layering a second YAML file and in-memory overrides."""
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if path is not None and Path(path).resolve() != DEFAULT_CONFIG_PATH.resolve():
        with open(path, "r", encoding="utf-8") as fh:
            cfg = deep_update(cfg, yaml.safe_load(fh) or {})
    if overrides:
        cfg = deep_update(cfg, overrides)
    return cfg


def project_root(cfg: dict) -> Path:
    return Path(cfg.get("paths", {}).get("root") or PROJECT_ROOT)


def project_path(cfg: dict, key: str) -> Path:
    """Resolve a path from the `paths` section relative to the project root (or cfg['paths']['root'])."""
    return resolve_path(cfg["paths"][key], project_root(cfg))


def get(cfg: dict, dotted: str, default: Any = None) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
