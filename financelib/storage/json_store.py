"""JSON file storage.

Chosen for the prototype because it is diffable, trivially backed up and needs
no server. Everything database-shaped (atomic writes, schema versioning,
backups, a single transactional save point) is handled here so that moving to
SQLite later is a matter of writing a sibling module.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from financelib.models import (
    Account,
    Dataset,
    Goal,
    MonthlyRecord,
    Settings,
    ValidationError,
    normalise_month,
)
from financelib.storage.base import (
    SCHEMA_VERSION,
    BackupInfo,
    Repository,
    StorageError,
    StorageStatus,
)

ACCOUNTS_FILE = "accounts.json"
MONTHS_FILE = "months.json"
GOALS_FILE = "goals.json"
SETTINGS_FILE = "settings.json"

DATA_FILES = (ACCOUNTS_FILE, MONTHS_FILE, GOALS_FILE, SETTINGS_FILE)

MAX_AUTOMATIC_BACKUPS = 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JsonRepository(Repository):
    """Stores the dataset as four JSON documents in one directory."""

    backend = "json"

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.backup_dir = self.data_dir / "backups"

    # ------------------------------------------------------------------
    # Low-level file access
    # ------------------------------------------------------------------

    def _path(self, filename: str) -> Path:
        return self.data_dir / filename

    def _read_document(self, filename: str, key: str, default: Any) -> Any:
        """Read one JSON document and unwrap its envelope.

        A missing file is a legitimate first run and yields the default. A file
        that exists but cannot be parsed raises, because treating corruption as
        "no data" would let the next save destroy the original.
        """
        path = self._path(filename)
        if not path.exists():
            return default

        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "null")
        except json.JSONDecodeError as exc:
            raise StorageError(
                f"{path.name} is not valid JSON (line {exc.lineno}, column {exc.colno}). "
                f"The file has not been changed — restore a backup or repair it by hand."
            ) from exc
        except OSError as exc:
            raise StorageError(f"Could not read {path.name}: {exc}") from exc

        if raw is None:
            return default
        # Envelope form: {"schema_version": n, "<key>": [...]}
        if isinstance(raw, dict) and key in raw:
            return raw[key]
        # Bare form: the document is the payload itself.
        return raw

    def _write_document(self, filename: str, key: str, payload: Any) -> None:
        """Write atomically so an interrupted save cannot truncate the file."""
        path = self._path(filename)
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            envelope = {
                "schema_version": SCHEMA_VERSION,
                "updated_at": _utc_now().isoformat(timespec="seconds"),
                key: payload,
            }
            body = json.dumps(envelope, indent=2, ensure_ascii=False)

            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.data_dir,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
            )
            try:
                with handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(handle.name, path)
            except BaseException:
                Path(handle.name).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise StorageError(f"Could not write {filename}: {exc}") from exc

    # ------------------------------------------------------------------
    # Dataset
    # ------------------------------------------------------------------

    def load(self) -> Dataset:
        raw_accounts = self._read_document(ACCOUNTS_FILE, "accounts", [])
        raw_months = self._read_document(MONTHS_FILE, "months", [])
        raw_goals = self._read_document(GOALS_FILE, "goals", [])
        raw_settings = self._read_document(SETTINGS_FILE, "settings", {})

        try:
            accounts = [Account.from_dict(item) for item in raw_accounts or []]
            months = [MonthlyRecord.from_dict(item) for item in raw_months or []]
            goals = [Goal.from_dict(item) for item in raw_goals or []]
            settings = Settings.from_dict(raw_settings)
        except ValidationError as exc:
            raise StorageError(f"Stored data is not in the expected shape: {exc}") from exc

        return Dataset(accounts=accounts, months=months, goals=goals, settings=settings)

    def save(self, dataset: Dataset) -> None:
        self.save_accounts(dataset.accounts)
        self.save_months(dataset.months)
        self.save_goals(dataset.goals)
        self.save_settings(dataset.settings)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def save_accounts(self, accounts: Iterable[Account]) -> None:
        ordered = sorted(accounts, key=lambda a: (a.sort_order, a.name.lower()))
        self._write_document(ACCOUNTS_FILE, "accounts", [a.to_dict() for a in ordered])

    def upsert_account(self, account: Account) -> None:
        accounts = [a for a in self.load().accounts if a.id != account.id]
        accounts.append(account)
        self.save_accounts(accounts)

    def delete_account(self, account_id: str, *, purge_balances: bool = False) -> None:
        dataset = self.load()
        self.save_accounts([a for a in dataset.accounts if a.id != account_id])

        if purge_balances:
            cleaned = []
            for record in dataset.months:
                record.balances.pop(account_id, None)
                record.contributions.pop(account_id, None)
                cleaned.append(record)
            self.save_months(cleaned)

        # A goal pointing at a deleted account would silently under-report.
        touched = [g for g in dataset.goals if account_id in g.account_ids]
        if touched:
            for goal in touched:
                goal.account_ids = [a for a in goal.account_ids if a != account_id]
            self.save_goals(dataset.goals)

    # ------------------------------------------------------------------
    # Months
    # ------------------------------------------------------------------

    def save_months(self, months: Iterable[MonthlyRecord]) -> None:
        ordered = sorted(months, key=lambda record: record.month)
        self._write_document(MONTHS_FILE, "months", [record.to_dict() for record in ordered])

    def upsert_month(self, record: MonthlyRecord, *, merge: bool = False) -> None:
        months = self.load().months
        existing = next((r for r in months if r.month == record.month), None)

        if existing is not None and merge:
            record = merge_records(existing, record)

        months = [r for r in months if r.month != record.month]
        months.append(record)
        self.save_months(months)

    def delete_month(self, month: str) -> None:
        key = normalise_month(month)
        self.save_months([r for r in self.load().months if r.month != key])

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------

    def save_goals(self, goals: Iterable[Goal]) -> None:
        ordered = sorted(goals, key=lambda g: (g.sort_order, g.name.lower()))
        self._write_document(GOALS_FILE, "goals", [g.to_dict() for g in ordered])

    def upsert_goal(self, goal: Goal) -> None:
        goals = [g for g in self.load().goals if g.id != goal.id]
        goals.append(goal)
        self.save_goals(goals)

    def delete_goal(self, goal_id: str) -> None:
        self.save_goals([g for g in self.load().goals if g.id != goal_id])

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def save_settings(self, settings: Settings) -> None:
        self._write_document(SETTINGS_FILE, "settings", settings.to_dict())

    # ------------------------------------------------------------------
    # Portability
    # ------------------------------------------------------------------

    def export_bundle(self) -> dict[str, Any]:
        dataset = self.load()
        return {
            "format": "finance-command-centre",
            "schema_version": SCHEMA_VERSION,
            "exported_at": _utc_now().isoformat(timespec="seconds"),
            "accounts": [a.to_dict() for a in dataset.accounts],
            "months": [r.to_dict() for r in dataset.months],
            "goals": [g.to_dict() for g in dataset.goals],
            "settings": dataset.settings.to_dict(),
        }

    def import_bundle(self, bundle: dict[str, Any], *, replace: bool = False) -> Dataset:
        if not isinstance(bundle, dict) or "months" not in bundle:
            raise StorageError("That file is not a finance command centre export.")

        self.create_backup("pre-import")

        try:
            incoming = Dataset(
                accounts=[Account.from_dict(a) for a in bundle.get("accounts") or []],
                months=[MonthlyRecord.from_dict(m) for m in bundle.get("months") or []],
                goals=[Goal.from_dict(g) for g in bundle.get("goals") or []],
                settings=Settings.from_dict(bundle.get("settings")),
            )
        except ValidationError as exc:
            raise StorageError(f"The export could not be read: {exc}") from exc

        if replace:
            self.save(incoming)
            return incoming

        current = self.load()
        merged_accounts = {a.id: a for a in current.accounts}
        merged_accounts.update({a.id: a for a in incoming.accounts})

        merged_months = {r.month: r for r in current.months}
        for record in incoming.months:
            existing = merged_months.get(record.month)
            merged_months[record.month] = (
                merge_records(existing, record) if existing else record
            )

        merged_goals = {g.id: g for g in current.goals}
        merged_goals.update({g.id: g for g in incoming.goals})

        merged = Dataset(
            accounts=list(merged_accounts.values()),
            months=list(merged_months.values()),
            goals=list(merged_goals.values()),
            settings=current.settings,
        )
        self.save(merged)
        return merged

    # ------------------------------------------------------------------
    # Backups
    # ------------------------------------------------------------------

    def create_backup(self, label: str = "manual") -> BackupInfo | None:
        present = [f for f in DATA_FILES if self._path(f).exists()]
        if not present:
            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = _utc_now().strftime("%Y%m%d-%H%M%S")
        safe_label = "".join(c for c in label if c.isalnum() or c in "-_") or "manual"
        archive = self.backup_dir / f"{stamp}-{safe_label}.zip"

        try:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                for filename in present:
                    bundle.write(self._path(filename), arcname=filename)
        except OSError as exc:
            raise StorageError(f"Could not create a backup: {exc}") from exc

        self._prune_backups()
        stat = archive.stat()
        return BackupInfo(
            name=archive.name,
            created_at=datetime.fromtimestamp(stat.st_mtime),
            size_bytes=stat.st_size,
        )

    def _prune_backups(self) -> None:
        backups = self.list_backups()
        for old in backups[MAX_AUTOMATIC_BACKUPS:]:
            (self.backup_dir / old.name).unlink(missing_ok=True)

    def list_backups(self) -> list[BackupInfo]:
        if not self.backup_dir.exists():
            return []
        found = []
        for path in self.backup_dir.glob("*.zip"):
            stat = path.stat()
            found.append(
                BackupInfo(
                    name=path.name,
                    created_at=datetime.fromtimestamp(stat.st_mtime),
                    size_bytes=stat.st_size,
                )
            )
        return sorted(found, key=lambda b: b.created_at, reverse=True)

    def restore_backup(self, name: str) -> Dataset:
        archive = self.backup_dir / Path(name).name
        if not archive.exists():
            raise StorageError(f"Backup {name!r} no longer exists.")

        # Snapshot the current state first so a restore is itself reversible.
        self.create_backup("pre-restore")

        try:
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.namelist():
                    if member not in DATA_FILES:
                        continue  # ignore anything unexpected inside the zip
                    with bundle.open(member) as source:
                        content = source.read().decode("utf-8")
                    self._path(member).write_text(content, encoding="utf-8")
        except (OSError, zipfile.BadZipFile) as exc:
            raise StorageError(f"Could not restore {name}: {exc}") from exc

        return self.load()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> StorageStatus:
        issues: list[str] = []
        try:
            dataset = self.load()
        except StorageError as exc:
            issues.append(str(exc))
            dataset = Dataset()

        issues.extend(describe_integrity_issues(dataset))

        paths = [self._path(f) for f in DATA_FILES if self._path(f).exists()]
        size = sum(p.stat().st_size for p in paths)
        modified = (
            datetime.fromtimestamp(max(p.stat().st_mtime for p in paths)) if paths else None
        )

        return StorageStatus(
            backend=self.backend,
            location=str(self.data_dir),
            writable=self._is_writable(),
            account_count=len(dataset.accounts),
            month_count=len(dataset.months),
            goal_count=len(dataset.goals),
            first_month=dataset.months[0].month if dataset.months else None,
            last_month=dataset.months[-1].month if dataset.months else None,
            last_modified=modified,
            size_bytes=size,
            backup_count=len(self.list_backups()),
            issues=tuple(issues),
        )

    def _is_writable(self) -> bool:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            probe = self.data_dir / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False


# ----------------------------------------------------------------------
# Helpers shared with importers
# ----------------------------------------------------------------------


def merge_records(existing: MonthlyRecord, incoming: MonthlyRecord) -> MonthlyRecord:
    """Overlay populated fields of ``incoming`` onto ``existing``.

    Absent values never erase known values, which is what makes re-running an
    import safe: importing a balances-only sheet twice cannot wipe the income
    and spending entered by hand.
    """
    return MonthlyRecord(
        month=existing.month,
        income=incoming.income if incoming.income is not None else existing.income,
        spending=incoming.spending if incoming.spending is not None else existing.spending,
        spending_categories={**existing.spending_categories, **incoming.spending_categories},
        contributions={**existing.contributions, **incoming.contributions},
        balances={**existing.balances, **incoming.balances},
        note=incoming.note or existing.note,
    )


def describe_integrity_issues(dataset: Dataset) -> list[str]:
    """Plain-English warnings about data that will confuse the analysis."""
    issues: list[str] = []

    known_ids = {a.id for a in dataset.accounts}
    orphan_ids: set[str] = set()
    for record in dataset.months:
        orphan_ids |= set(record.balances) - known_ids
        orphan_ids |= set(record.contributions) - known_ids
    if orphan_ids:
        listed = ", ".join(sorted(orphan_ids)[:5])
        issues.append(
            f"{len(orphan_ids)} account reference(s) in your history have no matching "
            f"account: {listed}. Recreate the account or remove the balances."
        )

    for record in dataset.months:
        if record.spending is not None and record.spending_categories:
            gap = round(record.categorised_spending - record.spending, 2)
            if abs(gap) > max(1.0, abs(record.spending) * 0.01):
                issues.append(
                    f"{record.month}: spending categories total £{record.categorised_spending:,.0f} "
                    f"but total spending is £{record.spending:,.0f}."
                )

    for goal in dataset.goals:
        if goal.target_amount <= 0:
            issues.append(f"Goal '{goal.name}' has no target amount, so progress cannot be shown.")

    return issues


def copy_samples_into(data_dir: Path | str, samples_dir: Path | str) -> list[str]:
    """Seed an empty data directory from the checked-in sample set."""
    data_dir, samples_dir = Path(data_dir), Path(samples_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for filename in DATA_FILES:
        source = samples_dir / filename
        if source.exists():
            shutil.copyfile(source, data_dir / filename)
            copied.append(filename)
    return copied
