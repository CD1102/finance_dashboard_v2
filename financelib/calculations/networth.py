"""Net worth, allocation and balance movement.

Every function here takes plain models and returns plain data. Nothing reads
files and nothing imports Streamlit, so all of it is directly testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from financelib.models import (
    ASSET_CATEGORIES,
    CATEGORY_LABELS,
    LIABILITY,
    Account,
    Dataset,
    MonthlyRecord,
    months_between,
)


@dataclass(frozen=True)
class NetWorthPoint:
    month: str
    total: float
    assets: float
    liabilities: float
    by_category: dict[str, float]


@dataclass(frozen=True)
class Change:
    """A movement between two points, with the context needed to explain it."""

    absolute: float
    percent: float | None
    from_value: float
    to_value: float
    from_month: str
    to_month: str
    months_elapsed: int

    @property
    def is_increase(self) -> bool:
        return self.absolute >= 0

    @property
    def average_per_month(self) -> float | None:
        if self.months_elapsed <= 0:
            return None
        return self.absolute / self.months_elapsed


@dataclass(frozen=True)
class AllocationSlice:
    key: str
    label: str
    amount: float
    percent: float


@dataclass
class AccountSeries:
    account: Account
    points: list[tuple[str, float]] = field(default_factory=list)

    @property
    def latest(self) -> float | None:
        return self.points[-1][1] if self.points else None

    @property
    def first(self) -> float | None:
        return self.points[0][1] if self.points else None


def _net_worth_accounts(accounts: list[Account]) -> dict[str, Account]:
    return {a.id: a for a in accounts if a.include_in_net_worth}


def net_worth(record: MonthlyRecord | None, accounts: list[Account]) -> float:
    """Assets minus liabilities for one month.

    Balances are signed by the account's category rather than by the stored
    number, so a credit card recorded as ``2400`` still reduces net worth.
    """
    if record is None or not record.balances:
        return 0.0

    lookup = _net_worth_accounts(accounts)
    total = 0.0
    for account_id, balance in record.balances.items():
        account = lookup.get(account_id)
        if account is None:
            # Unknown account: assume it is an asset rather than dropping it,
            # and surface the orphan separately through the integrity checks.
            total += balance
        elif account.is_liability:
            total -= abs(balance)
        else:
            total += balance
    return round(total, 2)


def category_totals(record: MonthlyRecord | None, accounts: list[Account]) -> dict[str, float]:
    """Balance per category for one month, including empty categories."""
    totals = {key: 0.0 for key in (*ASSET_CATEGORIES, LIABILITY)}
    if record is None:
        return totals

    lookup = {a.id: a for a in accounts}
    for account_id, balance in record.balances.items():
        account = lookup.get(account_id)
        if account is not None and not account.include_in_net_worth:
            continue
        key = account.category if account else "other"
        if key == LIABILITY:
            totals[key] = round(totals[key] + abs(balance), 2)
        else:
            totals[key] = round(totals.get(key, 0.0) + balance, 2)
    return totals


def net_worth_point(record: MonthlyRecord, accounts: list[Account]) -> NetWorthPoint:
    by_category = category_totals(record, accounts)
    liabilities = by_category.get(LIABILITY, 0.0)
    assets = round(sum(v for k, v in by_category.items() if k != LIABILITY), 2)
    return NetWorthPoint(
        month=record.month,
        total=round(assets - liabilities, 2),
        assets=assets,
        liabilities=liabilities,
        by_category=by_category,
    )


def net_worth_series(dataset: Dataset) -> list[NetWorthPoint]:
    """Chronological net worth for every month that recorded balances."""
    return [net_worth_point(record, dataset.accounts) for record in dataset.records_with_balances()]


def current_net_worth(dataset: Dataset) -> float:
    series = net_worth_series(dataset)
    return series[-1].total if series else 0.0


def change_between(series: list[NetWorthPoint], start_month: str, end_month: str) -> Change | None:
    lookup = {point.month: point.total for point in series}
    if start_month not in lookup or end_month not in lookup:
        return None
    return _build_change(lookup[start_month], lookup[end_month], start_month, end_month)


def latest_change(series: list[NetWorthPoint]) -> Change | None:
    """Movement between the two most recent months with balances."""
    if len(series) < 2:
        return None
    previous, current = series[-2], series[-1]
    return _build_change(previous.total, current.total, previous.month, current.month)


def change_over(series: list[NetWorthPoint], months: int | None) -> Change | None:
    """Movement across the trailing ``months``, or all history when ``None``.

    Falls back to the earliest available month when the requested window is
    longer than the history, so a "3 year" view still works after 8 months.
    """
    if len(series) < 2:
        return None
    end = series[-1]
    if months is None:
        start = series[0]
    else:
        index = max(len(series) - 1 - months, 0)
        start = series[index]
    if start.month == end.month:
        return None
    return _build_change(start.total, end.total, start.month, end.month)


def _build_change(from_value: float, to_value: float, from_month: str, to_month: str) -> Change:
    absolute = round(to_value - from_value, 2)
    # A percentage against a zero or negative base is meaningless, not infinite.
    percent = round(absolute / abs(from_value) * 100, 2) if from_value > 0 else None
    return Change(
        absolute=absolute,
        percent=percent,
        from_value=from_value,
        to_value=to_value,
        from_month=from_month,
        to_month=to_month,
        months_elapsed=months_between(from_month, to_month),
    )


def allocation(dataset: Dataset, month: str | None = None) -> list[AllocationSlice]:
    """Share of assets held in each category. Liabilities are excluded."""
    record = dataset.record(month) if month else dataset.latest_record(require_balances=True)
    totals = category_totals(record, dataset.accounts)
    assets = {k: v for k, v in totals.items() if k != LIABILITY and v}
    grand_total = sum(assets.values())

    slices = [
        AllocationSlice(
            key=key,
            label=CATEGORY_LABELS.get(key, key.title()),
            amount=amount,
            percent=round(amount / grand_total * 100, 2) if grand_total else 0.0,
        )
        for key, amount in assets.items()
    ]
    return sorted(slices, key=lambda s: s.amount, reverse=True)


def account_allocation(dataset: Dataset, month: str | None = None) -> list[AllocationSlice]:
    """Share of assets held in each individual account."""
    record = dataset.record(month) if month else dataset.latest_record(require_balances=True)
    if record is None:
        return []

    lookup = {a.id: a for a in dataset.accounts}
    entries: list[tuple[str, str, float]] = []
    for account_id, balance in record.balances.items():
        account = lookup.get(account_id)
        if account is not None and (account.is_liability or not account.include_in_net_worth):
            continue
        if not balance:
            continue
        entries.append((account_id, account.name if account else account_id, balance))

    grand_total = sum(amount for _, _, amount in entries)
    slices = [
        AllocationSlice(
            key=key,
            label=label,
            amount=amount,
            percent=round(amount / grand_total * 100, 2) if grand_total else 0.0,
        )
        for key, label, amount in entries
    ]
    return sorted(slices, key=lambda s: s.amount, reverse=True)


def account_series(dataset: Dataset, account_id: str) -> AccountSeries:
    """Balance history for one account, skipping months it wasn't recorded in."""
    account = dataset.account(account_id)
    if account is None:
        return AccountSeries(account=Account(id=account_id, name=account_id))

    points = [
        (record.month, record.balances[account_id])
        for record in dataset.months
        if account_id in record.balances
    ]
    return AccountSeries(account=account, points=points)


def account_change(dataset: Dataset, account_id: str, months: int | None = None) -> Change | None:
    series = account_series(dataset, account_id)
    if len(series.points) < 2:
        return None
    if months is None:
        start_index = 0
    else:
        start_index = max(len(series.points) - 1 - months, 0)
    start_month, start_value = series.points[start_index]
    end_month, end_value = series.points[-1]
    if start_month == end_month:
        return None
    return _build_change(start_value, end_value, start_month, end_month)


def current_balances(dataset: Dataset) -> dict[str, float]:
    """Most recently recorded balance for each account.

    Uses the latest month in which each account appears rather than the latest
    month overall, so an account skipped in one update keeps its known value.
    """
    balances: dict[str, float] = {}
    for record in dataset.months:
        balances.update(record.balances)
    return balances


def missing_accounts(dataset: Dataset, month: str) -> list[Account]:
    """Active accounts with no balance recorded for the given month."""
    record = dataset.record(month)
    recorded = set(record.balances) if record else set()
    return [a for a in dataset.active_accounts() if a.id not in recorded]
