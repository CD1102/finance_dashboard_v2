"""Model coercion, month arithmetic and record derivation."""

from __future__ import annotations

from datetime import date

import pytest

from financelib.models import (
    Account,
    Dataset,
    Goal,
    MonthlyRecord,
    Settings,
    ValidationError,
    month_range,
    months_between,
    normalise_month,
    shift_month,
    slugify,
)


class TestMonthKeys:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("2026-09", "2026-09"),
            ("2026-09-14", "2026-09"),
            ("09/2026", "2026-09"),
            ("9-2026", "2026-09"),
            ("Sep 2026", "2026-09"),
            ("September 2026", "2026-09"),
            (date(2026, 9, 14), "2026-09"),
        ],
    )
    def test_accepts_common_formats(self, value, expected):
        assert normalise_month(value) == expected

    @pytest.mark.parametrize("value", ["", None, "not a month", "2026-13", "13/2026"])
    def test_rejects_nonsense(self, value):
        with pytest.raises(ValidationError):
            normalise_month(value)

    def test_shift_crosses_year_boundaries(self):
        assert shift_month("2026-01", -1) == "2025-12"
        assert shift_month("2026-12", 1) == "2027-01"
        assert shift_month("2026-06", 0) == "2026-06"

    def test_months_between_is_signed(self):
        assert months_between("2026-01", "2026-04") == 3
        assert months_between("2026-04", "2026-01") == -3
        assert months_between("2026-04", "2026-04") == 0

    def test_range_is_inclusive_and_empty_when_reversed(self):
        assert month_range("2026-01", "2026-03") == ["2026-01", "2026-02", "2026-03"]
        assert month_range("2026-03", "2026-01") == []


class TestMoneyCoercion:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1,234.56", 1234.56),
            ("£1,234", 1234.0),
            ("(500)", -500.0),
            ("—", 0.0),
            (42, 42.0),
            (0, 0.0),
        ],
    )
    def test_reads_spreadsheet_shaped_values(self, value, expected):
        assert MonthlyRecord(month="2026-01", income=value).income == expected

    @pytest.mark.parametrize("value", [None, ""])
    def test_blanks_mean_not_recorded_rather_than_zero(self, value):
        assert MonthlyRecord(month="2026-01", income=value).income is None

    def test_rejects_text(self):
        with pytest.raises(ValidationError):
            MonthlyRecord(month="2026-01", income="about three thousand")


class TestMonthlyRecord:
    def test_blank_is_not_zero(self):
        empty = MonthlyRecord(month="2026-01")
        assert empty.income is None
        assert empty.effective_spending is None
        assert empty.is_empty

    def test_spending_falls_back_to_categories(self):
        record = MonthlyRecord(
            month="2026-01", spending_categories={"Food": 300, "Bills": 200}
        )
        assert record.effective_spending == 500
        assert not record.has_cashflow  # still no income

    def test_explicit_total_wins_over_categories(self):
        record = MonthlyRecord(
            month="2026-01", spending=600, spending_categories={"Food": 300}
        )
        assert record.effective_spending == 600

    def test_zero_income_is_recorded_not_missing(self):
        record = MonthlyRecord(month="2026-01", income=0, spending=500)
        assert record.income == 0
        assert record.has_cashflow

    def test_round_trip_through_dict(self):
        original = MonthlyRecord(
            month="2026-01",
            income=3000,
            spending=2000,
            contributions={"isa": 400},
            balances={"isa": 10_000},
            note="bonus month",
        )
        assert MonthlyRecord.from_dict(original.to_dict()) == original

    def test_omits_empty_fields_when_serialising(self):
        payload = MonthlyRecord(month="2026-01", income=100).to_dict()
        assert "spending" not in payload
        assert "balances" not in payload


class TestAccount:
    def test_derives_id_from_name(self):
        assert Account(id="", name="S&S ISA!").id == "s_s_isa"

    def test_unknown_category_falls_back_rather_than_raising(self):
        assert Account(id="a", name="A", category="crypto").category == "other"

    def test_reads_legacy_type_field(self):
        account = Account.from_dict({"id": "isa", "name": "ISA", "type": "investment"})
        assert account.category == "investment"

    def test_liability_flag(self):
        assert Account(id="c", name="Card", category="liability").is_liability


class TestGoal:
    def test_reads_legacy_target_and_accounts_fields(self):
        goal = Goal.from_dict(
            {"id": "house", "name": "House", "target": 50_000, "accounts": ["cash_isa"]}
        )
        assert goal.target_amount == 50_000
        assert goal.account_ids == ["cash_isa"]

    def test_target_date_may_be_absent(self):
        assert Goal(id="g", name="G", target_amount=100).target_date is None

    def test_invalid_date_is_reported(self):
        with pytest.raises(ValidationError):
            Goal.from_dict({"name": "G", "target": 1, "target_date": "not a date"})


class TestDataset:
    def test_sorts_months_on_construction(self):
        data = Dataset(
            months=[MonthlyRecord(month="2026-03"), MonthlyRecord(month="2026-01")]
        )
        assert data.month_keys == ["2026-01", "2026-03"]

    def test_empty_dataset_reports_itself_as_empty(self, empty_dataset):
        assert empty_dataset.is_empty
        assert not empty_dataset.has_history
        assert empty_dataset.latest_record() is None
        assert empty_dataset.previous_record() is None
        assert empty_dataset.years() == []

    def test_latest_can_require_balances(self):
        data = Dataset(
            months=[
                MonthlyRecord(month="2026-01", balances={"a": 100}),
                MonthlyRecord(month="2026-02", income=500),
            ]
        )
        assert data.latest_record().month == "2026-02"
        assert data.latest_record(require_balances=True).month == "2026-01"

    def test_unknown_account_name_degrades_to_its_id(self, dataset):
        assert dataset.account_name("missing") == "missing"

    def test_known_categories_include_ones_only_present_in_data(self):
        data = Dataset(
            months=[MonthlyRecord(month="2026-01", spending_categories={"Hobbies": 50})],
            settings=Settings(spending_categories=["Food"]),
        )
        assert "Hobbies" in data.known_spending_categories()
        assert "Food" in data.known_spending_categories()


def test_slugify_never_returns_empty():
    assert slugify("!!!") == "item"
    assert slugify("My Account 2") == "my_account_2"
