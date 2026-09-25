"""Spreadsheet import: reading, mapping, previewing, committing."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from financelib.importers import tabular
from financelib.models import Dataset, MonthlyRecord, ValidationError


def csv_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


@pytest.fixture
def sheet() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Month": ["2026-01", "2026-02", "2026-03"],
            "Income": [3000, 3000, 3200],
            "Total spending": [2000, 2100, 1900],
            "S&S ISA": [10_000, 10_600, 11_200],
            "Savings": [5_000, 5_200, 5_400],
        }
    )


class TestReading:
    def test_reads_csv(self, sheet):
        table = tabular.read_table(csv_bytes(sheet), "history.csv")
        assert table.row_count == 3
        assert "Month" in table.columns

    def test_drops_blank_rows_and_unnamed_columns(self):
        frame = pd.DataFrame(
            {"Month": ["2026-01", None], "Unnamed: 3": [None, None], "Income": [100, None]}
        )
        table = tabular.read_table(csv_bytes(frame), "x.csv")
        assert "Unnamed: 3" not in table.columns

    def test_unreadable_file_raises_a_clear_error(self):
        with pytest.raises(ValidationError):
            tabular.read_table(b"\x00\x01binary", "broken.xlsx")


class TestMapping:
    def test_guesses_month_income_and_spending(self, sheet, accounts):
        mapping = tabular.suggest_mapping(list(sheet.columns), accounts)
        assert mapping.month_column == "Month"
        assert mapping.role_of("Income") == "income"
        assert mapping.role_of("Total spending") == "spending"

    def test_matches_columns_to_accounts_by_name(self, sheet, accounts):
        mapping = tabular.suggest_mapping(list(sheet.columns), accounts)
        assignment = next(a for a in mapping.assignments if a.column == "S&S ISA")
        assert assignment.role == "balance"
        assert assignment.target == "isa"

    def test_distinguishes_contributions_from_balances(self, accounts):
        mapping = tabular.suggest_mapping(["Month", "S&S ISA contribution"], accounts)
        assignment = next(a for a in mapping.assignments if "contribution" in a.column)
        assert assignment.role == "contribution"

    def test_requires_a_month_column(self):
        mapping = tabular.ColumnMapping(
            assignments=[tabular.ColumnAssignment(column="Income", role="income")]
        )
        assert "month" in " ".join(mapping.validate()).lower()

    def test_requires_a_target_for_balance_columns(self):
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="ISA", role="balance"),
            ]
        )
        assert mapping.validate()

    def test_rejects_two_columns_mapped_to_one_account(self):
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="A", role="balance", target="isa"),
                tabular.ColumnAssignment(column="B", role="balance", target="isa"),
            ]
        )
        assert any("same account" in problem for problem in mapping.validate())

    def test_month_alone_is_not_enough(self):
        mapping = tabular.ColumnMapping(
            assignments=[tabular.ColumnAssignment(column="Month", role="month")]
        )
        assert not mapping.is_usable


class TestPreview:
    def _mapping(self):
        return tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
                tabular.ColumnAssignment(column="Total spending", role="spending"),
                tabular.ColumnAssignment(column="S&S ISA", role="balance", target="isa"),
                tabular.ColumnAssignment(column="Savings", role="balance", target="savings"),
            ]
        )

    def test_builds_one_record_per_row(self, sheet, accounts):
        table = tabular.read_table(csv_bytes(sheet), "h.csv")
        preview = tabular.build_preview(table, self._mapping(), Dataset(accounts=accounts))
        assert len(preview.records) == 3
        assert preview.records[0].balances == {"isa": 10_000.0, "savings": 5_000.0}

    def test_flags_months_that_already_exist(self, sheet, accounts):
        existing = Dataset(accounts=accounts, months=[MonthlyRecord(month="2026-02", income=1)])
        table = tabular.read_table(csv_bytes(sheet), "h.csv")
        preview = tabular.build_preview(table, self._mapping(), existing)
        assert preview.existing_months == ["2026-02"]
        assert preview.new_months == ["2026-01", "2026-03"]

    def test_skips_rows_with_unreadable_months(self, accounts):
        frame = pd.DataFrame({"Month": ["2026-01", "rubbish"], "Income": [100, 200]})
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
            ]
        )
        table = tabular.read_table(csv_bytes(frame), "h.csv")
        preview = tabular.build_preview(table, mapping, Dataset(accounts=accounts))
        assert len(preview.records) == 1
        assert preview.skipped_rows == 1

    def test_blank_cells_stay_unrecorded_rather_than_zero(self, accounts):
        frame = pd.DataFrame({"Month": ["2026-01"], "Income": [None]})
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
            ]
        )
        table = tabular.read_table(csv_bytes(frame), "h.csv")
        preview = tabular.build_preview(table, mapping, Dataset(accounts=accounts))
        assert preview.records == []
        assert preview.skipped_rows == 1

    def test_reads_currency_symbols_and_bracketed_negatives(self, accounts):
        frame = pd.DataFrame({"Month": ["2026-01"], "Income": ["£3,200.50"], "Spend": ["(120)"]})
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
                tabular.ColumnAssignment(column="Spend", role="spending"),
            ]
        )
        table = tabular.read_table(csv_bytes(frame), "h.csv")
        preview = tabular.build_preview(table, mapping, Dataset(accounts=accounts))
        assert preview.records[0].income == 3_200.50
        assert preview.records[0].spending == -120.0

    def test_records_a_problem_for_text_in_a_number_column(self, accounts):
        frame = pd.DataFrame({"Month": ["2026-01"], "Income": ["quite a lot"]})
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
            ]
        )
        table = tabular.read_table(csv_bytes(frame), "h.csv")
        preview = tabular.build_preview(table, mapping, Dataset(accounts=accounts))
        assert preview.issues

    def test_repeated_months_in_one_file_are_combined(self, accounts):
        frame = pd.DataFrame(
            {"Month": ["2026-01", "2026-01"], "Income": [1_000, None], "Spend": [None, 500]}
        )
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
                tabular.ColumnAssignment(column="Spend", role="spending"),
            ]
        )
        table = tabular.read_table(csv_bytes(frame), "h.csv")
        preview = tabular.build_preview(table, mapping, Dataset(accounts=accounts))
        assert len(preview.records) == 1
        assert preview.records[0].income == 1_000
        assert preview.records[0].spending == 500

    def test_invalid_mapping_produces_no_records(self, sheet, accounts):
        table = tabular.read_table(csv_bytes(sheet), "h.csv")
        empty = tabular.ColumnMapping(assignments=[])
        preview = tabular.build_preview(table, empty, Dataset(accounts=accounts))
        assert not preview.is_importable


class TestCommit:
    def _preview(self, repo, sheet, accounts):
        repo.save_accounts(accounts)
        table = tabular.read_table(csv_bytes(sheet), "h.csv")
        mapping = tabular.ColumnMapping(
            assignments=[
                tabular.ColumnAssignment(column="Month", role="month"),
                tabular.ColumnAssignment(column="Income", role="income"),
                tabular.ColumnAssignment(column="Total spending", role="spending"),
                tabular.ColumnAssignment(column="S&S ISA", role="balance", target="isa"),
                tabular.ColumnAssignment(column="Savings", role="balance", target="savings"),
            ]
        )
        return tabular.build_preview(table, mapping, repo.load())

    def test_creates_new_months(self, repo, sheet, accounts):
        preview = self._preview(repo, sheet, accounts)
        result = tabular.apply_preview(repo, preview)
        assert result.created == 3
        assert len(repo.load().months) == 3

    def test_takes_a_backup_first(self, repo, sheet, accounts):
        repo.save_months([MonthlyRecord(month="2025-12", income=1)])
        preview = self._preview(repo, sheet, accounts)
        result = tabular.apply_preview(repo, preview)
        assert result.backup_name is not None

    def test_running_the_same_import_twice_is_safe(self, repo, sheet, accounts):
        preview = self._preview(repo, sheet, accounts)
        tabular.apply_preview(repo, preview)

        again = self._preview(repo, sheet, accounts)
        result = tabular.apply_preview(repo, again)
        assert result.created == 0
        assert len(repo.load().months) == 3

    def test_merge_does_not_erase_hand_entered_data(self, repo, sheet, accounts):
        repo.save_accounts(accounts)
        repo.upsert_month(
            MonthlyRecord(month="2026-01", contributions={"isa": 400}, note="by hand")
        )
        preview = self._preview(repo, sheet, accounts)
        tabular.apply_preview(repo, preview, "merge")

        record = repo.load().record("2026-01")
        assert record.contributions == {"isa": 400.0}
        assert record.note == "by hand"
        assert record.income == 3_000

    def test_skip_leaves_existing_months_untouched(self, repo, sheet, accounts):
        repo.save_accounts(accounts)
        repo.upsert_month(MonthlyRecord(month="2026-01", income=999))
        preview = self._preview(repo, sheet, accounts)
        result = tabular.apply_preview(repo, preview, "skip")

        assert result.skipped == 1
        assert repo.load().record("2026-01").income == 999

    def test_replace_overwrites_existing_months(self, repo, sheet, accounts):
        repo.save_accounts(accounts)
        repo.upsert_month(MonthlyRecord(month="2026-01", income=999, note="old"))
        preview = self._preview(repo, sheet, accounts)
        tabular.apply_preview(repo, preview, "replace")

        record = repo.load().record("2026-01")
        assert record.income == 3_000
        assert record.note == ""

    def test_nothing_to_import_changes_nothing(self, repo):
        result = tabular.apply_preview(repo, tabular.ImportPreview())
        assert result.total_changed == 0
