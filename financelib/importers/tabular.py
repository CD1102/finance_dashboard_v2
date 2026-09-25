"""Importing historical months from a spreadsheet.

Assumes a wide layout — one row per month, one column per figure — because
that is how monthly finance spreadsheets are almost always built. The workflow
is deliberately staged: read, map, preview, validate, confirm. Nothing touches
stored data until the final step, and that step backs up first.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Literal

import pandas as pd

from financelib.models import (
    Account,
    Dataset,
    MonthlyRecord,
    ValidationError,
    normalise_month,
    slugify,
)
from financelib.storage.json_store import merge_records

MergeMode = Literal["skip", "merge", "replace"]

MERGE_MODE_LABELS: dict[MergeMode, str] = {
    "skip": "Keep existing months untouched",
    "merge": "Fill in blanks on existing months",
    "replace": "Overwrite existing months entirely",
}

Role = Literal["ignore", "month", "income", "spending", "balance", "contribution", "category"]

ROLE_LABELS: dict[Role, str] = {
    "ignore": "Ignore",
    "month": "Month",
    "income": "Income",
    "spending": "Total spending",
    "balance": "Account balance",
    "contribution": "Account contribution",
    "category": "Spending category",
}

MONTH_HINTS = ("month", "date", "period", "when")
INCOME_HINTS = ("income", "salary", "pay", "earnings", "in")
SPENDING_HINTS = ("spend", "expense", "outgoing", "cost", "out", "total out")
CONTRIBUTION_HINTS = ("contribution", "paid in", "invested", "deposit", "saved into")
BALANCE_HINTS = ("balance", "value", "total", "pot", "worth")


# ----------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------


@dataclass
class SourceTable:
    frame: pd.DataFrame
    sheet_names: list[str] = field(default_factory=list)
    sheet_used: str | None = None

    @property
    def columns(self) -> list[str]:
        return [str(c) for c in self.frame.columns]

    @property
    def row_count(self) -> int:
        return len(self.frame)


def list_sheets(data: bytes) -> list[str]:
    try:
        return pd.ExcelFile(io.BytesIO(data)).sheet_names
    except Exception:  # noqa: BLE001 - any read failure means "no sheets"
        return []


def read_table(
    data: bytes,
    filename: str,
    sheet_name: str | None = None,
    header_row: int = 0,
) -> SourceTable:
    """Read an uploaded CSV or Excel file into a dataframe."""
    buffer = io.BytesIO(data)
    is_csv = filename.lower().endswith(".csv")

    try:
        if is_csv:
            frame = pd.read_csv(buffer, header=header_row)
            sheets: list[str] = []
            used = None
        else:
            excel = pd.ExcelFile(buffer)
            sheets = list(excel.sheet_names)
            used = sheet_name if sheet_name in sheets else (sheets[0] if sheets else None)
            frame = excel.parse(used, header=header_row)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
        raise ValidationError(f"That file could not be read: {exc}") from exc

    # Drop fully-empty rows and unnamed padding columns Excel loves to add.
    frame = frame.dropna(how="all")
    frame = frame.loc[:, [c for c in frame.columns if not str(c).startswith("Unnamed:")]]
    frame.columns = [str(c).strip() for c in frame.columns]

    return SourceTable(frame=frame, sheet_names=sheets, sheet_used=used)


# ----------------------------------------------------------------------
# Mapping
# ----------------------------------------------------------------------


@dataclass
class ColumnAssignment:
    """What one spreadsheet column means."""

    column: str
    role: Role = "ignore"
    #: Account id for balance/contribution roles, category name for category.
    target: str = ""


@dataclass
class ColumnMapping:
    assignments: list[ColumnAssignment] = field(default_factory=list)

    def role_of(self, column: str) -> Role:
        return next((a.role for a in self.assignments if a.column == column), "ignore")

    def columns_for(self, role: Role) -> list[ColumnAssignment]:
        return [a for a in self.assignments if a.role == role]

    @property
    def month_column(self) -> str | None:
        found = self.columns_for("month")
        return found[0].column if found else None

    @property
    def is_usable(self) -> bool:
        if self.month_column is None:
            return False
        return any(a.role not in ("ignore", "month") for a in self.assignments)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.month_column is None:
            problems.append("Choose which column holds the month.")
        if len(self.columns_for("month")) > 1:
            problems.append("Only one column can be the month.")
        if len(self.columns_for("income")) > 1:
            problems.append("Only one column can be income.")
        if len(self.columns_for("spending")) > 1:
            problems.append("Only one column can be total spending.")

        for role in ("balance", "contribution"):
            missing = [a.column for a in self.columns_for(role) if not a.target]  # type: ignore[arg-type]
            if missing:
                problems.append(
                    f"Choose an account for: {', '.join(missing)}."
                )
            targets = [a.target for a in self.columns_for(role) if a.target]  # type: ignore[arg-type]
            duplicates = {t for t in targets if targets.count(t) > 1}
            if duplicates:
                problems.append(
                    f"More than one column is mapped to the same account ({', '.join(duplicates)})."
                )

        if not self.is_usable and self.month_column is not None:
            problems.append("Map at least one column besides the month.")
        return problems


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _matches(haystack: str, hints: tuple[str, ...]) -> bool:
    return any(hint in haystack for hint in hints)


def suggest_mapping(columns: list[str], accounts: list[Account]) -> ColumnMapping:
    """Best-effort guess at what each column means.

    Only ever a starting point — the user confirms every assignment before
    anything is imported.
    """
    assignments: list[ColumnAssignment] = []
    month_claimed = False
    income_claimed = False
    spending_claimed = False

    account_lookup = {_normalise(a.name): a for a in accounts}

    for column in columns:
        text = _normalise(column)
        assignment = ColumnAssignment(column=column)

        matched_account = account_lookup.get(text)
        if matched_account is None:
            for name, account in account_lookup.items():
                if name and (name in text or text in name):
                    matched_account = account
                    break

        if not month_claimed and _matches(text, MONTH_HINTS):
            assignment.role, month_claimed = "month", True
        elif matched_account is not None and _matches(text, CONTRIBUTION_HINTS):
            assignment.role, assignment.target = "contribution", matched_account.id
        elif matched_account is not None:
            assignment.role, assignment.target = "balance", matched_account.id
        elif not income_claimed and _matches(text, INCOME_HINTS):
            assignment.role, income_claimed = "income", True
        elif not spending_claimed and _matches(text, SPENDING_HINTS):
            assignment.role, spending_claimed = "spending", True

        assignments.append(assignment)

    return ColumnMapping(assignments=assignments)


# ----------------------------------------------------------------------
# Preview
# ----------------------------------------------------------------------


@dataclass
class RowIssue:
    row: int
    column: str
    message: str


@dataclass
class ImportPreview:
    """Everything needed to decide whether to go ahead."""

    records: list[MonthlyRecord] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    skipped_rows: int = 0
    existing_months: list[str] = field(default_factory=list)
    new_months: list[str] = field(default_factory=list)
    duplicate_months: list[str] = field(default_factory=list)

    @property
    def is_importable(self) -> bool:
        return bool(self.records)

    @property
    def summary(self) -> str:
        parts = [f"{len(self.records)} month(s) ready"]
        if self.new_months:
            parts.append(f"{len(self.new_months)} new")
        if self.existing_months:
            parts.append(f"{len(self.existing_months)} already recorded")
        if self.issues:
            parts.append(f"{len(self.issues)} value(s) skipped")
        return " · ".join(parts)

    def to_frame(self, dataset: Dataset) -> pd.DataFrame:
        """Tabular preview using account names rather than ids."""
        rows: list[dict[str, Any]] = []
        for record in self.records:
            row: dict[str, Any] = {
                "Month": record.month,
                "Status": "Update" if record.month in self.existing_months else "New",
                "Income": record.income,
                "Spending": record.spending,
            }
            for account_id, amount in record.balances.items():
                row[f"{dataset.account_name(account_id)} balance"] = amount
            for account_id, amount in record.contributions.items():
                row[f"{dataset.account_name(account_id)} paid in"] = amount
            for name, amount in record.spending_categories.items():
                row[name] = amount
            rows.append(row)
        return pd.DataFrame(rows)


def _read_number(value: Any) -> float | None:
    """Coerce a cell to a number, returning ``None`` for blanks."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if pd.isna(value):
        return None

    text = str(value).strip()
    cleaned = re.sub(r"[£$€,\s]", "", text)
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    if cleaned in ("", "-", "—", "n/a", "N/A"):
        return None
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValidationError(f"{text!r} is not a number") from exc
    return round(-number if negative else number, 2)


def build_preview(
    table: SourceTable,
    mapping: ColumnMapping,
    dataset: Dataset,
) -> ImportPreview:
    """Turn mapped rows into records, collecting problems rather than raising."""
    preview = ImportPreview()
    problems = mapping.validate()
    if problems:
        preview.issues = [RowIssue(row=0, column="", message=p) for p in problems]
        return preview

    month_column = mapping.month_column
    assert month_column is not None  # guaranteed by validate()

    existing_months = set(dataset.month_keys)
    seen: dict[str, MonthlyRecord] = {}

    for position, (_, row) in enumerate(table.frame.iterrows(), start=2):
        raw_month = row.get(month_column)
        try:
            month = normalise_month(raw_month)
        except (ValidationError, Exception):
            preview.skipped_rows += 1
            continue

        record = MonthlyRecord(month=month)

        for assignment in mapping.assignments:
            if assignment.role in ("ignore", "month"):
                continue
            try:
                amount = _read_number(row.get(assignment.column))
            except ValidationError as exc:
                preview.issues.append(
                    RowIssue(row=position, column=assignment.column, message=str(exc))
                )
                continue
            if amount is None:
                continue

            if assignment.role == "income":
                record.income = amount
            elif assignment.role == "spending":
                record.spending = amount
            elif assignment.role == "balance" and assignment.target:
                record.balances[assignment.target] = amount
            elif assignment.role == "contribution" and assignment.target:
                record.contributions[assignment.target] = amount
            elif assignment.role == "category":
                name = assignment.target or assignment.column
                record.spending_categories[name] = amount

        if record.is_empty:
            preview.skipped_rows += 1
            continue

        # The same month appearing twice in one sheet is merged, not duplicated.
        if month in seen:
            preview.duplicate_months.append(month)
            seen[month] = merge_records(seen[month], record)
        else:
            seen[month] = record

    preview.records = sorted(seen.values(), key=lambda r: r.month)
    preview.existing_months = sorted(m for m in seen if m in existing_months)
    preview.new_months = sorted(m for m in seen if m not in existing_months)
    return preview


# ----------------------------------------------------------------------
# Commit
# ----------------------------------------------------------------------


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    backup_name: str | None = None

    @property
    def total_changed(self) -> int:
        return self.created + self.updated


def apply_preview(repository, preview: ImportPreview, mode: MergeMode = "merge") -> ImportResult:
    """Write previewed records, backing up first.

    ``merge`` is the default because it makes repeated imports safe: a second
    run of the same sheet fills gaps without discarding anything entered by
    hand in between.
    """
    if not preview.records:
        return ImportResult()

    backup = repository.create_backup("pre-import")
    dataset = repository.load()
    by_month = {record.month: record for record in dataset.months}
    result = ImportResult(backup_name=backup.name if backup else None)

    for record in preview.records:
        existing = by_month.get(record.month)
        if existing is None:
            by_month[record.month] = record
            result.created += 1
        elif mode == "skip":
            result.skipped += 1
        elif mode == "replace":
            by_month[record.month] = record
            result.updated += 1
        else:
            by_month[record.month] = merge_records(existing, record)
            result.updated += 1

    repository.save_months(by_month.values())
    return result


def accounts_from_columns(columns: list[str], existing: list[Account]) -> list[Account]:
    """Propose new accounts for balance columns that match nothing yet."""
    known = {a.id for a in existing}
    proposed: list[Account] = []
    for column in columns:
        text = _normalise(column)
        if not _matches(text, BALANCE_HINTS):
            continue
        name = re.sub(r"(?i)\b(balance|value|total|pot|worth)\b", "", column).strip(" -–—:")
        if not name:
            continue
        account_id = slugify(name)
        if account_id in known:
            continue
        known.add(account_id)
        proposed.append(Account(id=account_id, name=name))
    return proposed
