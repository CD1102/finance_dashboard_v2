"""Income, spending, savings rate and the emergency fund."""

from __future__ import annotations

from financelib.calculations import cashflow
from financelib.models import Account, Dataset, MonthlyRecord, Settings


class TestSavingsRate:
    def test_basic_calculation(self):
        assert cashflow.savings_rate(3000, 2000) == pytest_approx(33.33)

    def test_zero_income_is_undefined_not_zero(self):
        assert cashflow.savings_rate(0, 500) is None

    def test_negative_income_is_undefined(self):
        assert cashflow.savings_rate(-100, 50) is None

    def test_missing_values_are_undefined(self):
        assert cashflow.savings_rate(None, 500) is None
        assert cashflow.savings_rate(3000, None) is None

    def test_overspending_gives_a_negative_rate(self):
        assert cashflow.savings_rate(1000, 1500) == -50.0

    def test_zero_spending_is_a_full_rate(self):
        assert cashflow.savings_rate(1000, 0) == 100.0


class TestContributionRate:
    def test_basic_calculation(self):
        assert cashflow.contribution_rate(2000, 500) == 25.0

    def test_no_income_is_undefined(self):
        assert cashflow.contribution_rate(0, 500) is None


class TestMonthSummary:
    def test_derives_surplus_and_unallocated(self):
        summary = cashflow.summarise_month(
            MonthlyRecord(
                month="2026-01", income=3000, spending=2000, contributions={"isa": 600}
            )
        )
        assert summary.surplus == 1000
        assert summary.contributions == 600
        assert summary.unallocated == 400

    def test_contributions_beyond_surplus_show_as_negative_unallocated(self):
        summary = cashflow.summarise_month(
            MonthlyRecord(
                month="2026-01", income=2000, spending=1800, contributions={"isa": 500}
            )
        )
        assert summary.unallocated == -300

    def test_missing_cashflow_leaves_derived_values_undefined(self):
        summary = cashflow.summarise_month(MonthlyRecord(month="2026-01", balances={"a": 1}))
        assert summary.surplus is None
        assert summary.savings_rate is None
        assert not summary.has_cashflow


class TestPeriodTotals:
    def test_only_counts_months_that_recorded_something(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", income=3000, spending=2000),
                MonthlyRecord(month="2026-02", balances={"isa": 100}),
                MonthlyRecord(month="2026-03", income=3000, spending=2200),
            ],
        )
        totals = cashflow.totals_for(data.months)
        assert totals.months_counted == 2
        assert totals.income == 6000
        assert totals.average_spending == 2100

    def test_empty_period_does_not_divide_by_zero(self):
        totals = cashflow.totals_for([])
        assert totals.months_counted == 0
        assert totals.average_income is None
        assert totals.savings_rate is None

    def test_year_totals_filter_by_year(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2025-12", income=1000, spending=500),
                MonthlyRecord(month="2026-01", income=2000, spending=800),
            ],
        )
        assert cashflow.year_totals(data, 2026).income == 2000
        assert cashflow.year_totals(data, 2024).months_counted == 0

    def test_year_to_date_stops_at_the_latest_month(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", income=1000, spending=100),
                MonthlyRecord(month="2026-02", income=1000, spending=100),
            ],
        )
        assert cashflow.year_to_date(data, 2026, up_to="2026-01").income == 1000

    def test_categories_accumulate_across_months(self):
        totals = cashflow.totals_for(
            [
                MonthlyRecord(month="2026-01", spending_categories={"Food": 300}),
                MonthlyRecord(month="2026-02", spending_categories={"Food": 250, "Bills": 100}),
            ]
        )
        assert totals.spending_by_category == {"Food": 550.0, "Bills": 100.0}


class TestAverages:
    def test_average_spending_uses_recorded_months_only(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", spending=1000),
                MonthlyRecord(month="2026-02", balances={"isa": 5}),
                MonthlyRecord(month="2026-03", spending=2000),
            ],
        )
        assert cashflow.average_monthly_spending(data) == 1500

    def test_no_spending_recorded_returns_none(self, empty_dataset):
        assert cashflow.average_monthly_spending(empty_dataset) is None
        assert cashflow.average_monthly_contributions(empty_dataset) is None

    def test_rolling_average_waits_for_a_full_window(self):
        result = cashflow.rolling_average(
            [("2026-01", 10.0), ("2026-02", 20.0), ("2026-03", 30.0)], window=3
        )
        assert [value for _, value in result] == [None, None, 20.0]

    def test_rolling_average_resets_after_a_gap(self):
        result = cashflow.rolling_average(
            [("2026-01", 10.0), ("2026-02", None), ("2026-03", 30.0)], window=2
        )
        assert [value for _, value in result] == [None, None, None]


class TestEmergencyFund:
    def test_none_when_no_account_is_flagged(self, accounts):
        data = Dataset(
            accounts=[Account(id="a", name="A", category="cash")],
            months=[MonthlyRecord(month="2026-01", balances={"a": 100})],
        )
        assert cashflow.emergency_fund(data) is None

    def test_target_derived_from_recent_spending(self, dataset):
        fund = cashflow.emergency_fund(dataset)
        assert fund is not None
        assert fund.balance == 5_400
        assert fund.target_months == 6.0
        assert fund.target == round(fund.monthly_spending * 6, 2)

    def test_fixed_target_overrides_spending(self, dataset):
        dataset.settings = Settings(emergency_fund_target=10_000)
        fund = cashflow.emergency_fund(dataset)
        assert fund.target == 10_000
        assert fund.shortfall == 4_600

    def test_no_spending_means_coverage_is_unknown(self, accounts):
        data = Dataset(
            accounts=[Account(id="s", name="Savings", category="cash", emergency_fund=True)],
            months=[MonthlyRecord(month="2026-01", balances={"s": 5_000})],
        )
        fund = cashflow.emergency_fund(data)
        assert fund.months_covered is None
        assert fund.target is None
        assert fund.percent_complete is None


def pytest_approx(value):
    import pytest

    return pytest.approx(value, abs=0.01)
