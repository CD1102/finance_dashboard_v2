"""Separating money you added from money the market added.

The arithmetic is deliberately conservative. A balance change is only split
into contributions and growth when a contribution figure exists for *every*
month in the window — otherwise the "growth" number silently absorbs any
contribution the user forgot to record, which would be worse than saying
nothing. Incomplete windows are reported as such rather than estimated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from financelib.models import Account, Dataset, month_range, months_between
from financelib.calculations.networth import net_worth_series


@dataclass(frozen=True)
class Attribution:
    """How a balance change splits between contributions and growth."""

    label: str
    start_month: str
    end_month: str
    start_balance: float
    end_balance: float
    contributions: float
    #: ``None`` when contribution data is incomplete for the window.
    growth: float | None
    #: Months in the window with no contribution figure recorded.
    missing_months: tuple[str, ...] = ()

    @property
    def change(self) -> float:
        return round(self.end_balance - self.start_balance, 2)

    @property
    def is_complete(self) -> bool:
        return self.growth is not None

    @property
    def growth_percent(self) -> float | None:
        """Simple return over the window, against average invested capital.

        Uses start balance plus half of contributions as the denominator — a
        standard approximation that avoids over-stating returns when a large
        contribution lands late in the period. It is an approximation, and the
        UI labels it as one.
        """
        if self.growth is None:
            return None
        base = self.start_balance + self.contributions / 2
        if base <= 0:
            return None
        return round(self.growth / base * 100, 2)

    @property
    def annualised_percent(self) -> float | None:
        percent = self.growth_percent
        span = months_between(self.start_month, self.end_month)
        if percent is None or span <= 0:
            return None
        if span == 12:
            return percent
        growth_factor = 1 + percent / 100
        if growth_factor <= 0:
            return None
        return round((growth_factor ** (12 / span) - 1) * 100, 2)


@dataclass
class AttributionSet:
    total: Attribution | None = None
    by_account: list[Attribution] = field(default_factory=list)

    @property
    def any_incomplete(self) -> bool:
        return any(not a.is_complete for a in self.by_account) or (
            self.total is not None and not self.total.is_complete
        )


def _contribution_window(start_month: str, end_month: str) -> list[str]:
    """Months whose contributions land between two closing balances.

    A balance recorded for month M is its closing balance, so money paid in
    during month M is already reflected in it. Moving from the close of March
    to the close of June therefore captures April, May and June.
    """
    window = month_range(start_month, end_month)
    return window[1:] if len(window) > 1 else []


def attribute_account(
    dataset: Dataset, account_id: str, start_month: str, end_month: str
) -> Attribution | None:
    """Split one account's balance change over a period."""
    start = dataset.record(start_month)
    end = dataset.record(end_month)
    if start is None or end is None:
        return None

    start_balance = start.balance_of(account_id)
    end_balance = end.balance_of(account_id)
    if start_balance is None or end_balance is None:
        return None

    contributions = 0.0
    missing: list[str] = []
    for month in _contribution_window(start_month, end_month):
        record = dataset.record(month)
        if record is None or account_id not in record.contributions:
            missing.append(month)
            continue
        contributions += record.contributions[account_id]

    contributions = round(contributions, 2)
    change = round(end_balance - start_balance, 2)
    growth = round(change - contributions, 2) if not missing else None

    account = dataset.account(account_id)
    return Attribution(
        label=account.name if account else account_id,
        start_month=start_month,
        end_month=end_month,
        start_balance=start_balance,
        end_balance=end_balance,
        contributions=contributions,
        growth=growth,
        missing_months=tuple(missing),
    )


def attribute_total(dataset: Dataset, start_month: str, end_month: str) -> Attribution | None:
    """Split the whole portfolio's net worth change over a period."""
    series = {point.month: point for point in net_worth_series(dataset)}
    if start_month not in series or end_month not in series:
        return None

    contributions = 0.0
    missing: list[str] = []
    for month in _contribution_window(start_month, end_month):
        record = dataset.record(month)
        if record is None or not record.contributions:
            missing.append(month)
            continue
        contributions += record.total_contributions

    contributions = round(contributions, 2)
    start_total = series[start_month].total
    end_total = series[end_month].total
    change = round(end_total - start_total, 2)

    return Attribution(
        label="Net worth",
        start_month=start_month,
        end_month=end_month,
        start_balance=start_total,
        end_balance=end_total,
        contributions=contributions,
        growth=round(change - contributions, 2) if not missing else None,
        missing_months=tuple(missing),
    )


def attribute_period(
    dataset: Dataset,
    start_month: str,
    end_month: str,
    *,
    accounts: list[Account] | None = None,
) -> AttributionSet:
    """Attribution for the portfolio and each account over one period."""
    candidates = accounts if accounts is not None else dataset.accounts
    by_account = []
    for account in candidates:
        result = attribute_account(dataset, account.id, start_month, end_month)
        if result is not None:
            by_account.append(result)

    return AttributionSet(
        total=attribute_total(dataset, start_month, end_month),
        by_account=sorted(by_account, key=lambda a: abs(a.change), reverse=True),
    )


def latest_attribution(dataset: Dataset) -> AttributionSet | None:
    """Attribution for the most recent completed month."""
    with_balances = dataset.records_with_balances()
    if len(with_balances) < 2:
        return None
    return attribute_period(dataset, with_balances[-2].month, with_balances[-1].month)


def growth_history(dataset: Dataset) -> list[Attribution]:
    """Month-by-month attribution across all available history."""
    with_balances = dataset.records_with_balances()
    results = []
    for previous, current in zip(with_balances, with_balances[1:]):
        result = attribute_total(dataset, previous.month, current.month)
        if result is not None:
            results.append(result)
    return results
