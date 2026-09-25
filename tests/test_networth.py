"""Net worth, allocation and movement."""

from __future__ import annotations

from financelib.calculations import networth
from financelib.models import Account, Dataset, MonthlyRecord


class TestNetWorth:
    def test_sums_balances(self, dataset):
        assert networth.current_net_worth(dataset) == 37_500

    def test_liabilities_reduce_net_worth(self):
        data = Dataset(
            accounts=[
                Account(id="savings", name="Savings", category="cash"),
                Account(id="card", name="Card", category="liability"),
            ],
            months=[MonthlyRecord(month="2026-01", balances={"savings": 5_000, "card": 800})],
        )
        assert networth.current_net_worth(data) == 4_200

    def test_liability_stored_as_negative_still_reduces(self):
        """A card recorded as -800 should not accidentally add to net worth."""
        data = Dataset(
            accounts=[
                Account(id="savings", name="Savings", category="cash"),
                Account(id="card", name="Card", category="liability"),
            ],
            months=[MonthlyRecord(month="2026-01", balances={"savings": 5_000, "card": -800})],
        )
        assert networth.current_net_worth(data) == 4_200

    def test_excluded_accounts_are_ignored(self):
        data = Dataset(
            accounts=[
                Account(id="a", name="A", category="cash"),
                Account(id="b", name="B", category="cash", include_in_net_worth=False),
            ],
            months=[MonthlyRecord(month="2026-01", balances={"a": 100, "b": 900})],
        )
        assert networth.current_net_worth(data) == 100

    def test_empty_history_is_zero_not_an_error(self, empty_dataset):
        assert networth.current_net_worth(empty_dataset) == 0
        assert networth.net_worth_series(empty_dataset) == []

    def test_month_without_balances_is_skipped(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 100}),
                MonthlyRecord(month="2026-02", income=3000),
            ],
        )
        series = networth.net_worth_series(data)
        assert [point.month for point in series] == ["2026-01"]


class TestChange:
    def test_latest_change_compares_last_two_months(self, dataset):
        change = networth.latest_change(networth.net_worth_series(dataset))
        assert change.absolute == 1_300
        assert change.is_increase
        assert change.months_elapsed == 1

    def test_negative_movement_is_reported_as_such(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 10_000}),
                MonthlyRecord(month="2026-02", balances={"isa": 9_000}),
            ],
        )
        change = networth.latest_change(networth.net_worth_series(data))
        assert change.absolute == -1_000
        assert not change.is_increase
        assert change.percent == -10.0

    def test_percent_is_none_when_starting_from_zero(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 0}),
                MonthlyRecord(month="2026-02", balances={"isa": 500}),
            ],
        )
        change = networth.latest_change(networth.net_worth_series(data))
        assert change.absolute == 500
        assert change.percent is None

    def test_single_month_has_nothing_to_compare(self, accounts):
        data = Dataset(
            accounts=accounts, months=[MonthlyRecord(month="2026-01", balances={"isa": 10})]
        )
        assert networth.latest_change(networth.net_worth_series(data)) is None

    def test_window_longer_than_history_falls_back_to_earliest(self, dataset):
        series = networth.net_worth_series(dataset)
        change = networth.change_over(series, months=36)
        assert change.from_month == "2026-01"
        assert change.to_month == "2026-03"

    def test_average_per_month(self, dataset):
        series = networth.net_worth_series(dataset)
        change = networth.change_over(series, months=None)
        assert change.months_elapsed == 2
        assert change.average_per_month == change.absolute / 2


class TestAllocation:
    def test_percentages_sum_to_one_hundred(self, dataset):
        slices = networth.allocation(dataset)
        assert round(sum(item.percent for item in slices), 1) == 100.0

    def test_sorted_largest_first(self, dataset):
        amounts = [item.amount for item in networth.allocation(dataset)]
        assert amounts == sorted(amounts, reverse=True)

    def test_liabilities_excluded_from_allocation(self):
        data = Dataset(
            accounts=[
                Account(id="a", name="A", category="cash"),
                Account(id="card", name="Card", category="liability"),
            ],
            months=[MonthlyRecord(month="2026-01", balances={"a": 1_000, "card": 500})],
        )
        keys = {item.key for item in networth.allocation(data)}
        assert "liability" not in keys

    def test_all_zero_balances_do_not_divide_by_zero(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[MonthlyRecord(month="2026-01", balances={"isa": 0, "savings": 0})],
        )
        assert networth.allocation(data) == []

    def test_empty_dataset_returns_nothing(self, empty_dataset):
        assert networth.allocation(empty_dataset) == []


class TestAccountSeries:
    def test_skips_months_the_account_is_absent_from(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 100}),
                MonthlyRecord(month="2026-02", balances={"savings": 50}),
                MonthlyRecord(month="2026-03", balances={"isa": 300}),
            ],
        )
        series = networth.account_series(data, "isa")
        assert series.points == [("2026-01", 100.0), ("2026-03", 300.0)]
        assert series.first == 100.0
        assert series.latest == 300.0

    def test_new_account_with_no_history_is_empty_not_an_error(self, dataset):
        series = networth.account_series(dataset, "brand_new")
        assert series.points == []
        assert series.latest is None

    def test_change_needs_two_points(self, accounts):
        data = Dataset(
            accounts=accounts, months=[MonthlyRecord(month="2026-01", balances={"isa": 100})]
        )
        assert networth.account_change(data, "isa") is None

    def test_missing_accounts_for_a_month(self, dataset):
        data = Dataset(
            accounts=dataset.accounts,
            months=[MonthlyRecord(month="2026-01", balances={"isa": 100})],
        )
        missing = {account.id for account in networth.missing_accounts(data, "2026-01")}
        assert missing == {"savings", "pension"}

    def test_current_balances_carry_forward_last_known_value(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 100, "savings": 50}),
                MonthlyRecord(month="2026-02", balances={"isa": 200}),
            ],
        )
        assert networth.current_balances(data) == {"isa": 200.0, "savings": 50.0}
