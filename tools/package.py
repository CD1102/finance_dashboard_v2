"""Package the repository into a distributable zip.

Excludes the virtual environment, caches and — importantly — any real data
that may be sitting in ``data/``. Only the synthetic sample set is included.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "finance_dashboard.zip"

EXCLUDED_DIRS = {
    ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".git", ".idea", "backups", "exports", ".mypy_cache",
}

EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".xlsx", ".xls", ".log"}


def is_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name == "secrets.toml":
        return True
    # Real data lives directly in data/. Everything under data/samples is
    # synthetic and safe to ship.
    parts = relative.parts
    if len(parts) == 2 and parts[0] == "data" and path.suffix == ".json":
        return True
    return False


def main() -> None:
    OUTPUT.unlink(missing_ok=True)
    included = 0

    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or is_excluded(path):
                continue
            bundle.write(path, arcname=Path("finance_dashboard") / path.relative_to(ROOT))
            included += 1

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Wrote {OUTPUT} ({included} files, {size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
