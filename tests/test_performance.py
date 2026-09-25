"""Separating contributions from growth."""

from __future__ import annotations

from financelib.calculations import performance
from financelib.models import Dataset, MonthlyRecord


class TestAccountAttribution:
    def test_splits_change_into_contributions_and_growth(self, dataset):
        result = performance.attribute_account(dataset, "isa", "2026-01", "2026-02")
        assert result.change == 600
        assert result.contributions == 400
        assert result.growth == 200

    def test_contributions_from_the_start_month_are_not_double_counted(self, dataset):
        """A balance is a closing balance, so January's payment is already in it."""
        result = performance.attribute_account(dataset, "isa", "2026-01", "2026-03")
        assert result.contributions == 800  # February and March only
        assert result.growth == 400

    def test_growth_is_unknown_when_a_month_lacks_contributions(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 1_000}, contributions={"isa": 100}),
                MonthlyRecord(month="2026-02", balances={"isa": 1_200}),
                MonthlyRecord(month="2026-03", balances={"isa": 1_500}, contributions={"isa": 100}),
            ],
        )
        result = performance.attribute_account(data, "isa", "2026-01", "2026-03")
        assert result.growth is None
        assert not result.is_complete
        assert result.missing_months == ("2026-02",)

    def test_negative_growth_is_reported(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 10_000}),
                MonthlyRecord(month="2026-02", balances={"isa": 9_800}, contributions={"isa": 200}),
            ],
        )
        result = performance.attribute_account(data, "isa", "2026-01", "2026-02")
        assert result.growth == -400

    def test_missing_month_returns_nothing(self, dataset):
        assert performance.attribute_account(dataset, "isa", "2025-01", "2026-02") is None

    def test_account_absent_from_a_month_returns_nothing(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"savings": 10}),
                MonthlyRecord(month="2026-02", balances={"isa": 10}),
            ],
        )
        assert performance.attribute_account(data, "isa", "2026-01", "2026-02") is None


class TestReturnPercentages:
    def test_return_uses_half_of_contributions_as_capital(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 1_000}),
                MonthlyRecord(month="2026-02", balances={"isa": 1_300}, contributions={"isa": 200}),
            ],
        )
        result = performance.attribute_account(data, "isa", "2026-01", "2026-02")
        # growth 100 against a base of 1000 + 100
        assert result.growth_percent == round(100 / 1100 * 100, 2)

    def test_return_measured_against_average_capital_when_starting_from_zero(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 0}),
                MonthlyRecord(month="2026-02", balances={"isa": 500}, contributions={"isa": 500}),
            ],
        )
        result = performance.attribute_account(data, "isa", "2026-01", "2026-02")
        assert result.growth == 0
        assert result.growth_percent == 0.0

    def test_return_is_undefined_with_no_capital_at_all(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 0}),
                MonthlyRecord(month="2026-02", balances={"isa": 0}, contributions={"isa": 0}),
            ],
        )
        result = performance.attribute_account(data, "isa", "2026-01", "2026-02")
        assert result.growth_percent is None

    def test_annualised_matches_simple_return_over_exactly_a_year(self, accounts):
        months = []
        for index in range(13):
            month = f"2026-{index + 1:02d}" if index < 12 else "2027-01"
            months.append(
                MonthlyRecord(
                    month=month,
                    balances={"isa": 1_000 + index * 10},
                    contributions={"isa": 0},
                )
            )
        data = Dataset(accounts=accounts, months=months)
        result = performance.attribute_account(data, "isa", "2026-01", "2027-01")
        assert result.annualised_percent == result.growth_percent


class TestTotalAttribution:
    def test_covers_whole_portfolio(self, dataset):
        result = performance.attribute_total(dataset, "2026-01", "2026-02")
        assert result.change == 1_200
        assert result.contributions == 900
        assert result.growth == 300

    def test_latest_needs_two_months(self, accounts):
        data = Dataset(
            accounts=accounts, months=[MonthlyRecord(month="2026-01", balances={"isa": 1})]
        )
        assert performance.latest_attribution(data) is None

    def test_growth_history_yields_one_entry_per_transition(self, dataset):
        history = performance.growth_history(dataset)
        assert [item.end_month for item in history] == ["2026-02", "2026-03"]

    def test_attribute_period_sorts_by_size_of_movement(self, dataset):
        result = performance.attribute_period(dataset, "2026-01", "2026-03")
        changes = [abs(item.change) for item in result.by_account]
        assert changes == sorted(changes, reverse=True)

    def test_empty_dataset_is_handled(self, empty_dataset):
        assert performance.attribute_total(empty_dataset, "2026-01", "2026-02") is None
        assert performance.growth_history(empty_dataset) == []
