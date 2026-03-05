"""Deduplication store backed by data/sent.json."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .config import settings

_PRUNE_DAYS = 30


def _path() -> Path:
    return Path(settings.data_dir) / "sent.json"


def load() -> dict[str, float]:
    p = _path()
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)


def save(store: dict[str, float]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(store, f, indent=2)


def prune(store: dict[str, float]) -> dict[str, float]:
    cutoff = time.time() - _PRUNE_DAYS * 86400
    return {k: v for k, v in store.items() if v > cutoff}


def filter_new(articles: list[dict], store: dict[str, float]) -> list[dict]:
    return [a for a in articles if a["id"] not in store]


def mark_sent(articles: list[dict], store: dict[str, float]) -> dict[str, float]:
    now = time.time()
    for a in articles:
        store[a["id"]] = now
    return store
