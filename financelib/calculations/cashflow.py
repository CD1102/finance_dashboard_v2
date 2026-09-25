"""Income, spending, saving and the ratios derived from them."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from financelib.models import Dataset, MonthlyRecord


@dataclass(frozen=True)
class MonthSummary:
    """One month of cash flow with its derived ratios.

    ``None`` is used throughout for "not recorded" so the UI can say so instead
    of showing a misleading zero.
    """

    month: str
    income: float | None
    spending: float | None
    contributions: float
    surplus: float | None
    savings_rate: float | None
    contribution_rate: float | None
    unallocated: float | None

    @property
    def has_cashflow(self) -> bool:
        return self.income is not None and self.spending is not None


@dataclass
class PeriodTotals:
    """Aggregated cash flow over a set of months."""

    label: str
    months_counted: int = 0
    income: float = 0.0
    spending: float = 0.0
    contributions: float = 0.0
    spending_by_category: dict[str, float] = field(default_factory=dict)

    @property
    def surplus(self) -> float:
        return round(self.income - self.spending, 2)

    @property
    def savings_rate(self) -> float | None:
        return savings_rate(self.income, self.spending)

    @property
    def average_income(self) -> float | None:
        return round(self.income / self.months_counted, 2) if self.months_counted else None

    @property
    def average_spending(self) -> float | None:
        return round(self.spending / self.months_counted, 2) if self.months_counted else None

    @property
    def average_contributions(self) -> float | None:
        return round(self.contributions / self.months_counted, 2) if self.months_counted else None


def savings_rate(income: float | None, spending: float | None) -> float | None:
    """Percentage of income not spent.

    Returns ``None`` rather than zero when income is missing or non-positive,
    because a savings rate is undefined without income to divide by.
    """
    if income is None or spending is None or income <= 0:
        return None
    return round((income - spending) / income * 100, 2)


def contribution_rate(income: float | None, contributions: float | None) -> float | None:
    """Percentage of income deliberately moved into accounts."""
    if income is None or contributions is None or income <= 0:
        return None
    return round(contributions / income * 100, 2)


def summarise_month(record: MonthlyRecord) -> MonthSummary:
    income = record.income
    spending = record.effective_spending
    contributions = record.total_contributions
    surplus = round(income - spending, 2) if income is not None and spending is not None else None

    # Money left after spending and contributions. Negative means contributions
    # were funded from savings rather than from this month's income.
    unallocated = round(surplus - contributions, 2) if surplus is not None else None

    return MonthSummary(
        month=record.month,
        income=income,
        spending=spending,
        contributions=contributions,
        surplus=surplus,
        savings_rate=savings_rate(income, spending),
        contribution_rate=contribution_rate(income, contributions),
        unallocated=unallocated,
    )


def summaries(dataset: Dataset) -> list[MonthSummary]:
    return [summarise_month(record) for record in dataset.months]


def totals_for(records: list[MonthlyRecord], label: str = "") -> PeriodTotals:
    """Sum cash flow across records, counting only months that recorded it."""
    totals = PeriodTotals(label=label)
    for record in records:
        counted = False
        if record.income is not None:
            totals.income = round(totals.income + record.income, 2)
            counted = True
        spending = record.effective_spending
        if spending is not None:
            totals.spending = round(totals.spending + spending, 2)
            counted = True
        if record.contributions:
            totals.contributions = round(totals.contributions + record.total_contributions, 2)
        for name, amount in record.spending_categories.items():
            totals.spending_by_category[name] = round(
                totals.spending_by_category.get(name, 0.0) + amount, 2
            )
        if counted:
            totals.months_counted += 1
    return totals


def year_totals(dataset: Dataset, year: int) -> PeriodTotals:
    records = [record for record in dataset.months if record.year == year]
    return totals_for(records, label=str(year))


def all_year_totals(dataset: Dataset) -> list[PeriodTotals]:
    return [year_totals(dataset, year) for year in dataset.years()]


def year_to_date(dataset: Dataset, year: int | None = None, up_to: str | None = None) -> PeriodTotals:
    """Totals for the calendar year so far.

    ``up_to`` bounds the window to a month, which keeps year-on-year
    comparisons fair when the current year is only partly recorded.
    """
    if not dataset.months:
        return PeriodTotals(label="Year to date")
    latest = up_to or dataset.months[-1].month
    year = year or int(latest[:4])
    records = [r for r in dataset.months if r.year == year and r.month <= latest]
    return totals_for(records, label=f"{year} to {latest[-2:]}")


def trailing(dataset: Dataset, months: int) -> PeriodTotals:
    """Totals for the most recent ``months`` records."""
    records = dataset.months[-months:] if months else dataset.months
    return totals_for(records, label=f"Last {months} months")


def rolling_average(
    values: list[tuple[str, float | None]], window: int = 3
) -> list[tuple[str, float | None]]:
    """Trailing mean, emitting ``None`` until the window is full."""
    output: list[tuple[str, float | None]] = []
    buffer: list[float] = []
    for month, value in values:
        if value is None:
            buffer.clear()
            output.append((month, None))
            continue
        buffer.append(value)
        if len(buffer) > window:
            buffer.pop(0)
        output.append((month, round(mean(buffer), 2) if len(buffer) == window else None))
    return output


def average_monthly_spending(dataset: Dataset, months: int = 6) -> float | None:
    """Mean spending over the most recent months that recorded it."""
    recorded = [r.effective_spending for r in dataset.months if r.effective_spending is not None]
    if not recorded:
        return None
    window = recorded[-months:] if months else recorded
    return round(mean(window), 2)


def average_monthly_contributions(dataset: Dataset, months: int = 6) -> float | None:
    recorded = [r.total_contributions for r in dataset.months if r.contributions]
    if not recorded:
        return None
    window = recorded[-months:] if months else recorded
    return round(mean(window), 2)


def spending_by_category(dataset: Dataset, months: int | None = None) -> dict[str, float]:
    records = dataset.months[-months:] if months else dataset.months
    return totals_for(records).spending_by_category


@dataclass(frozen=True)
class EmergencyFund:
    """Where the emergency fund stands against a spending-based target."""

    balance: float
    target: float | None
    months_covered: float | None
    monthly_spending: float | None
    target_months: float
    source_accounts: list[str]

    @property
    def percent_complete(self) -> float | None:
        if not self.target:
            return None
        return round(min(self.balance / self.target * 100, 100), 1)

    @property
    def shortfall(self) -> float | None:
        if self.target is None:
            return None
        return round(max(self.target - self.balance, 0.0), 2)


def emergency_fund(dataset: Dataset) -> EmergencyFund | None:
    """Emergency fund position, if any account is flagged as one."""
    flagged = [a for a in dataset.accounts if a.emergency_fund]
    if not flagged:
        return None

    latest = dataset.latest_record(require_balances=True)
    balances = latest.balances if latest else {}
    balance = round(sum(balances.get(a.id, 0.0) for a in flagged), 2)

    monthly = average_monthly_spending(dataset, months=6)
    target_months = dataset.settings.emergency_fund_months

    if dataset.settings.emergency_fund_target is not None:
        target = dataset.settings.emergency_fund_target
    elif monthly:
        target = round(monthly * target_months, 2)
    else:
        target = None

    covered = round(balance / monthly, 1) if monthly else None

    return EmergencyFund(
        balance=balance,
        target=target,
        months_covered=covered,
        monthly_spending=monthly,
        target_months=target_months,
        source_accounts=[a.name for a in flagged],
    )
