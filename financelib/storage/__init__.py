"""Storage package.

``get_repository()`` is the single place the rest of the app asks for data
access. Pointing the app at a different backend later means editing this
factory only.
"""

from __future__ import annotations

import os
from pathlib import Path

from financelib.storage.base import (
    SCHEMA_VERSION,
    BackupInfo,
    Repository,
    StorageError,
    StorageStatus,
)
from financelib.storage.json_store import JsonRepository, merge_records

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SAMPLES_DIR = DEFAULT_DATA_DIR / "samples"

#: Override to point at a mounted volume in Docker or Azure Files.
DATA_DIR_ENV = "FINANCE_DATA_DIR"
BACKEND_ENV = "FINANCE_STORAGE_BACKEND"


def resolve_data_dir() -> Path:
    configured = os.environ.get(DATA_DIR_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_DATA_DIR


def get_repository(data_dir: Path | str | None = None) -> Repository:
    backend = os.environ.get(BACKEND_ENV, "json").lower()
    if backend != "json":
        raise StorageError(
            f"Storage backend {backend!r} is not available yet. "
            f"Unset {BACKEND_ENV} to use JSON files."
        )
    return JsonRepository(Path(data_dir) if data_dir else resolve_data_dir())


__all__ = [
    "BackupInfo",
    "DEFAULT_DATA_DIR",
    "JsonRepository",
    "PROJECT_ROOT",
    "Repository",
    "SAMPLES_DIR",
    "SCHEMA_VERSION",
    "StorageError",
    "StorageStatus",
    "get_repository",
    "merge_records",
    "resolve_data_dir",
]
