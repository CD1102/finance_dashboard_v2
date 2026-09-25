"""Forward projections.

Nothing in this module is a prediction. It is arithmetic applied to
assumptions the user supplies, and every output carries the inputs that
produced it so the numbers can be checked by hand.

Model:

- Three pots are tracked separately — investments, cash and pension — because
  they compound at genuinely different rates.
- Growth compounds monthly at the monthly equivalent of the annual rate,
  ``(1 + annual) ** (1/12) - 1``, not ``annual / 12``.
- Contributions are added at the end of each month, which is the conservative
  choice: it never credits a month of growth on money that has not arrived.
- Contributions escalate once a year, on the anniversary, by the contribution
  growth rate.
- Real values deflate the nominal total by inflation over the same horizon.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from financelib.models import CASH, INVESTMENT, PENSION, Dataset, shift_month
from financelib.calculations.cashflow import average_monthly_contributions
from financelib.calculations.networth import category_totals

MAX_YEARS = 60


@dataclass
class Assumptions:
    """Inputs to a projection. All rates are annual percentages."""

    starting_investments: float = 0.0
    starting_cash: float = 0.0
    starting_pension: float = 0.0

    monthly_investment_contribution: float = 0.0
    monthly_cash_contribution: float = 0.0
    monthly_pension_contribution: float = 0.0

    investment_return: float = 5.0
    cash_rate: float = 3.0
    pension_return: float = 5.0

    inflation: float = 2.5
    #: Annual percentage increase applied to every contribution each year.
    contribution_growth: float = 0.0

    years: int = 20
    label: str = "Scenario"

    def __post_init__(self) -> None:
        self.years = max(1, min(int(self.years), MAX_YEARS))

    @property
    def starting_total(self) -> float:
        return round(
            self.starting_investments + self.starting_cash + self.starting_pension, 2
        )

    @property
    def monthly_contribution_total(self) -> float:
        return round(
            self.monthly_investment_contribution
            + self.monthly_cash_contribution
            + self.monthly_pension_contribution,
            2,
        )

    def variant(self, label: str, **changes) -> "Assumptions":
        return replace(self, label=label, **changes)


@dataclass(frozen=True)
class ProjectionPoint:
    """One month of a projection, fully decomposed."""

    month_index: int
    month: str
    starting_wealth: float
    contributions: float
    investment_growth: float
    interest: float
    total: float
    real_total: float
    investments: float
    cash: float
    pension: float

    @property
    def year_index(self) -> float:
        return self.month_index / 12

    @property
    def total_growth(self) -> float:
        return round(self.investment_growth + self.interest, 2)


@dataclass
class Projection:
    """A projected trajectory plus the assumptions that produced it."""

    assumptions: Assumptions
    points: list[ProjectionPoint] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.assumptions.label

    @property
    def final(self) -> ProjectionPoint:
        return self.points[-1]

    @property
    def yearly(self) -> list[ProjectionPoint]:
        """One point per anniversary, including the starting position."""
        return [p for p in self.points if p.month_index % 12 == 0]

    def at_year(self, year: int) -> ProjectionPoint | None:
        return next((p for p in self.points if p.month_index == year * 12), None)

    def year_when_reaching(self, target: float) -> float | None:
        """Years until the projection first reaches ``target``, if it does."""
        for point in self.points:
            if point.total >= target:
                return round(point.month_index / 12, 2)
        return None


def _monthly_rate(annual_percent: float) -> float:
    """Monthly equivalent of an annual percentage rate."""
    base = 1 + annual_percent / 100
    if base <= 0:
        return -1.0
    return base ** (1 / 12) - 1


def project(assumptions: Assumptions, start_month: str | None = None) -> Projection:
    """Run the projection month by month."""
    investment_rate = _monthly_rate(assumptions.investment_return)
    cash_rate = _monthly_rate(assumptions.cash_rate)
    pension_rate = _monthly_rate(assumptions.pension_return)
    inflation_rate = _monthly_rate(assumptions.inflation)

    investments = assumptions.starting_investments
    cash = assumptions.starting_cash
    pension = assumptions.starting_pension

    investment_contribution = assumptions.monthly_investment_contribution
    cash_contribution = assumptions.monthly_cash_contribution
    pension_contribution = assumptions.monthly_pension_contribution

    cumulative_contributions = 0.0
    cumulative_investment_growth = 0.0
    cumulative_interest = 0.0

    origin = start_month or "2000-01"
    starting_total = assumptions.starting_total

    points = [
        ProjectionPoint(
            month_index=0,
            month=origin,
            starting_wealth=starting_total,
            contributions=0.0,
            investment_growth=0.0,
            interest=0.0,
            total=round(starting_total, 2),
            real_total=round(starting_total, 2),
            investments=round(investments, 2),
            cash=round(cash, 2),
            pension=round(pension, 2),
        )
    ]

    for month_index in range(1, assumptions.years * 12 + 1):
        # Escalate contributions on each anniversary.
        if month_index > 1 and (month_index - 1) % 12 == 0 and assumptions.contribution_growth:
            factor = 1 + assumptions.contribution_growth / 100
            investment_contribution *= factor
            cash_contribution *= factor
            pension_contribution *= factor

        investment_gain = investments * investment_rate
        pension_gain = pension * pension_rate
        cash_gain = cash * cash_rate

        investments += investment_gain + investment_contribution
        pension += pension_gain + pension_contribution
        cash += cash_gain + cash_contribution

        cumulative_investment_growth += investment_gain + pension_gain
        cumulative_interest += cash_gain
        cumulative_contributions += (
            investment_contribution + cash_contribution + pension_contribution
        )

        total = investments + cash + pension
        deflator = (1 + inflation_rate) ** month_index

        points.append(
            ProjectionPoint(
                month_index=month_index,
                month=shift_month(origin, month_index),
                starting_wealth=round(starting_total, 2),
                contributions=round(cumulative_contributions, 2),
                investment_growth=round(cumulative_investment_growth, 2),
                interest=round(cumulative_interest, 2),
                total=round(total, 2),
                real_total=round(total / deflator, 2) if deflator else round(total, 2),
                investments=round(investments, 2),
                cash=round(cash, 2),
                pension=round(pension, 2),
            )
        )

    return Projection(assumptions=assumptions, points=points)


def assumptions_from_dataset(dataset: Dataset, years: int = 20) -> Assumptions:
    """Seed a projection from what has actually been recorded.

    Starting balances come from the latest snapshot. Contribution rates come
    from the average of recent months, split across pots in the same
    proportion as those contributions actually went — so the default scenario
    is "carry on exactly as you are".
    """
    settings = dataset.settings
    latest = dataset.latest_record(require_balances=True)
    totals = category_totals(latest, dataset.accounts)

    recent = [r for r in dataset.months if r.contributions][-6:]
    by_category = {INVESTMENT: 0.0, CASH: 0.0, PENSION: 0.0}
    for record in recent:
        for account_id, amount in record.contributions.items():
            account = dataset.account(account_id)
            key = account.category if account else CASH
            by_category[key] = by_category.get(key, 0.0) + amount

    divisor = len(recent) or 1
    monthly = {key: round(value / divisor, 2) for key, value in by_category.items()}

    # Fall back to the planned contributions on each account when nothing has
    # been logged yet, so a brand-new setup still projects something sensible.
    if not any(monthly.values()):
        for account in dataset.active_accounts():
            if account.planned_contribution:
                monthly[account.category] = round(
                    monthly.get(account.category, 0.0) + account.planned_contribution, 2
                )

    other_assets = round(
        totals.get("other", 0.0) + totals.get("property", 0.0), 2
    )

    return Assumptions(
        starting_investments=round(totals.get(INVESTMENT, 0.0), 2),
        # Property and miscellaneous assets grow at the cash rate by default,
        # which is the least speculative assumption available.
        starting_cash=round(totals.get(CASH, 0.0) + other_assets - totals.get("liability", 0.0), 2),
        starting_pension=round(totals.get(PENSION, 0.0), 2),
        monthly_investment_contribution=monthly.get(INVESTMENT, 0.0),
        monthly_cash_contribution=monthly.get(CASH, 0.0),
        monthly_pension_contribution=monthly.get(PENSION, 0.0),
        investment_return=settings.default_investment_return,
        cash_rate=settings.default_cash_rate,
        pension_return=settings.default_investment_return,
        inflation=settings.default_inflation,
        years=years,
        label="Current trajectory",
    )


def default_scenarios(base: Assumptions) -> list[Assumptions]:
    """A useful starting trio: as-is, paying in more, and a weaker market."""
    uplift = max(round(base.monthly_contribution_total * 0.25), 50)
    return [
        base,
        base.variant(
            f"+£{uplift:,.0f}/month",
            monthly_investment_contribution=base.monthly_investment_contribution + uplift,
        ),
        base.variant(
            "Lower returns",
            investment_return=max(base.investment_return - 2, 0),
            pension_return=max(base.pension_return - 2, 0),
        ),
    ]


def compare(scenarios: list[Assumptions], start_month: str | None = None) -> list[Projection]:
    return [project(assumption, start_month) for assumption in scenarios]


def trajectory_check(dataset: Dataset, years: int = 1) -> dict[str, float] | None:
    """Compare recent actual net-worth growth with the projected rate.

    Used by the dashboard to say whether the last few months have run ahead of
    or behind the default trajectory. Returns ``None`` when there is not
    enough history to say anything meaningful.
    """
    from financelib.calculations.networth import net_worth_series

    series = net_worth_series(dataset)
    if len(series) < 4:
        return None

    window = min(len(series) - 1, 12)
    recent = series[-window - 1:]
    actual_change = recent[-1].total - recent[0].total
    actual_monthly = actual_change / window

    assumptions = assumptions_from_dataset(dataset, years=max(years, 1))
    projection = project(assumptions)
    projected_point = projection.at_year(1) or projection.final
    projected_monthly = (projected_point.total - assumptions.starting_total) / 12

    return {
        "actual_monthly": round(actual_monthly, 2),
        "projected_monthly": round(projected_monthly, 2),
        "difference": round(actual_monthly - projected_monthly, 2),
        "months_observed": window,
    }
