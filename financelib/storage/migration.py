"""Migration from the original prototype's file layout.

The first version of this app stored balances in ``accounts.json``, monthly
balance snapshots in ``history.json`` and individual contribution entries in
``contributions.json``. This module folds all three into the single
month-per-record model without touching the original files.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from financelib.models import (
    Account,
    Dataset,
    Goal,
    MonthlyRecord,
    Settings,
    normalise_month,
    slugify,
)

LEGACY_FILES = ("accounts.json", "history.json", "contributions.json", "goals.json")


@dataclass
class MigrationReport:
    accounts: int = 0
    months: int = 0
    goals: int = 0
    contributions_folded: int = 0
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []

    @property
    def is_empty(self) -> bool:
        return not (self.accounts or self.months or self.goals)


def looks_like_legacy(data_dir: Path | str) -> bool:
    """True when a directory holds prototype files but no ``months.json``."""
    data_dir = Path(data_dir)
    if (data_dir / "months.json").exists():
        return False
    return (data_dir / "history.json").exists() or (data_dir / "accounts.json").exists()


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null") or default
    except (json.JSONDecodeError, OSError):
        return default


def migrate_directory(data_dir: Path | str) -> tuple[Dataset, MigrationReport]:
    """Build a modern :class:`Dataset` from prototype files. Read-only."""
    data_dir = Path(data_dir)
    report = MigrationReport()

    raw_accounts = _read(data_dir / "accounts.json", {})
    account_items = (
        raw_accounts.get("accounts", []) if isinstance(raw_accounts, dict) else raw_accounts
    )
    history = _read(data_dir / "history.json", [])
    contributions = _read(data_dir / "contributions.json", [])
    raw_goals = _read(data_dir / "goals.json", [])

    accounts: list[Account] = []
    final_balances: dict[str, float] = {}
    for index, item in enumerate(account_items or []):
        if not isinstance(item, dict):
            report.warnings.append(f"Skipped an account entry that was not an object: {item!r}")
            continue
        account = Account.from_dict(item)
        account.sort_order = index
        # The prototype flagged a LISA with a boolean; keep that signal.
        account.lisa = bool(item.get("lisa", account.lisa))
        account.isa = bool(item.get("isa", account.lisa or "isa" in account.id))
        accounts.append(account)
        if item.get("balance") not in (None, ""):
            final_balances[account.id] = float(item["balance"])
    report.accounts = len(accounts)

    # history.json -> one record per month, balances only.
    records: dict[str, MonthlyRecord] = {}
    for entry in history or []:
        if not isinstance(entry, dict) or "month" not in entry:
            report.warnings.append(f"Skipped a history entry without a month: {entry!r}")
            continue
        try:
            month = normalise_month(entry["month"])
        except Exception:
            report.warnings.append(f"Skipped history entry with unreadable month: {entry['month']!r}")
            continue
        records[month] = MonthlyRecord(month=month, balances=entry.get("balances") or {})

    # contributions.json -> monthly totals per account.
    folded: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for entry in contributions or []:
        if not isinstance(entry, dict) or "date" not in entry:
            continue
        try:
            month = normalise_month(entry["date"])
        except Exception:
            report.warnings.append(f"Skipped a contribution with an unreadable date: {entry['date']!r}")
            continue
        account_id = slugify(entry.get("account_id", ""))
        folded[month][account_id] += float(entry.get("amount", 0) or 0)
        report.contributions_folded += 1

    for month, by_account in folded.items():
        record = records.get(month) or MonthlyRecord(month=month)
        record.contributions = {k: round(v, 2) for k, v in by_account.items()}
        records[month] = record

    # The prototype's "current balance" is really the most recent snapshot.
    if final_balances:
        latest = max(records) if records else None
        if latest is None or final_balances != records[latest].balances:
            report.warnings.append(
                "Current balances from accounts.json differed from the last snapshot; "
                "they were kept as the most recent month."
            )
        if latest is not None and not records[latest].balances:
            records[latest].balances = final_balances

    report.months = len(records)

    goals: list[Goal] = []
    for index, item in enumerate(raw_goals or []):
        if not isinstance(item, dict):
            continue
        goal = Goal.from_dict(item)
        goal.sort_order = index
        goals.append(goal)
    report.goals = len(goals)

    dataset = Dataset(
        accounts=accounts,
        months=list(records.values()),
        goals=goals,
        settings=Settings(),
    )
    return dataset, report
