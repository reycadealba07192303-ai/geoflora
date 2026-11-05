"""Workspace settings for the Python side, read from the same file as the web app: apps/web/.env.local.

Every credential and setting lives in that one file. Values already in the environment win, so a test or a one-off
command can still override any of them.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[4] / "apps/web/.env.local"


def load_env(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            os.environ.setdefault(key.strip(), value)
