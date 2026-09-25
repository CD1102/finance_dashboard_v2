"""Storage contract.

Pages and calculations only ever talk to a :class:`Repository`. Swapping JSON
for SQLite or a cloud database means writing one new implementation of this
interface — no page or calculation needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from financelib.models import Account, Dataset, Goal, MonthlyRecord, Settings

#: Bumped when the on-disk shape changes in a way that needs a migration.
SCHEMA_VERSION = 2


class StorageError(RuntimeError):
    """Raised when stored data cannot be read or written safely.

    Deliberately *not* swallowed by the loaders: silently returning an empty
    dataset for a corrupt file risks overwriting good data with nothing on the
    next save.
    """


@dataclass(frozen=True)
class BackupInfo:
    name: str
    created_at: datetime
    size_bytes: int


@dataclass(frozen=True)
class StorageStatus:
    """Human-facing summary of where data lives and how healthy it is."""

    backend: str
    location: str
    writable: bool
    account_count: int
    month_count: int
    goal_count: int
    first_month: str | None
    last_month: str | None
    last_modified: datetime | None
    size_bytes: int
    backup_count: int
    issues: tuple[str, ...] = ()


class Repository(ABC):
    """Read/write access to the whole dataset."""

    backend: str = "abstract"

    # -- whole dataset -----------------------------------------------------

    @abstractmethod
    def load(self) -> Dataset:
        """Load everything. Raises :class:`StorageError` on corrupt data."""

    @abstractmethod
    def save(self, dataset: Dataset) -> None:
        """Persist everything."""

    # -- accounts ----------------------------------------------------------

    @abstractmethod
    def save_accounts(self, accounts: Iterable[Account]) -> None: ...

    @abstractmethod
    def upsert_account(self, account: Account) -> None: ...

    @abstractmethod
    def delete_account(self, account_id: str, *, purge_balances: bool = False) -> None: ...

    # -- months ------------------------------------------------------------

    @abstractmethod
    def save_months(self, months: Iterable[MonthlyRecord]) -> None: ...

    @abstractmethod
    def upsert_month(self, record: MonthlyRecord, *, merge: bool = False) -> None:
        """Insert or replace a month.

        When ``merge`` is true, populated fields on ``record`` overlay the
        existing month rather than replacing it wholesale. Imports rely on this
        so re-running them never silently discards data.
        """

    @abstractmethod
    def delete_month(self, month: str) -> None: ...

    # -- goals -------------------------------------------------------------

    @abstractmethod
    def save_goals(self, goals: Iterable[Goal]) -> None: ...

    @abstractmethod
    def upsert_goal(self, goal: Goal) -> None: ...

    @abstractmethod
    def delete_goal(self, goal_id: str) -> None: ...

    # -- settings ----------------------------------------------------------

    @abstractmethod
    def save_settings(self, settings: Settings) -> None: ...

    # -- portability -------------------------------------------------------

    @abstractmethod
    def export_bundle(self) -> dict[str, Any]:
        """A single self-describing dict containing the whole dataset."""

    @abstractmethod
    def import_bundle(self, bundle: dict[str, Any], *, replace: bool = False) -> Dataset:
        """Load a previously exported bundle, backing up current data first."""

    # -- operations --------------------------------------------------------

    @abstractmethod
    def create_backup(self, label: str = "manual") -> BackupInfo | None: ...

    @abstractmethod
    def list_backups(self) -> list[BackupInfo]: ...

    @abstractmethod
    def restore_backup(self, name: str) -> Dataset: ...

    @abstractmethod
    def status(self) -> StorageStatus: ...
