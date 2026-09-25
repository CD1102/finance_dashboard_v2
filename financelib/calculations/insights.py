"""Plain-English explanations of what actually changed.

Each insight is generated from stored data only. Where a statement depends on
arithmetic rather than a recorded figure it is tagged ``derived``; where it
depends on an assumption it is tagged ``assumption``. Nothing is emitted when
the underlying data cannot support it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from financelib.models import Dataset
from financelib.calculations import cashflow, goals, performance
from financelib.calculations.networth import latest_change, net_worth_series
from financelib.calculations.taxuk import current_tax_year, isa_status, lisa_status
from financelib.formatting import month_label

Tone = Literal["positive", "negative", "neutral", "warning"]
Provenance = Literal["recorded", "derived", "assumption"]


@dataclass(frozen=True)
class Insight:
    text: str
    tone: Tone = "neutral"
    provenance: Provenance = "derived"
    detail: str | None = None


def _money(value: float, symbol: str = "£") -> str:
    return f"{symbol}{abs(value):,.0f}"


def _signed(value: float, symbol: str = "£") -> str:
    return f"{'+' if value >= 0 else '−'}{symbol}{abs(value):,.0f}"


def month_narrative(dataset: Dataset) -> list[Insight]:
    """What happened in the most recent month, in sentences."""
    symbol = dataset.settings.currency_symbol
    insights: list[Insight] = []

    series = net_worth_series(dataset)
    change = latest_change(series)

    if change is None:
        if series:
            insights.append(
                Insight(
                    "This is your first recorded month, so there is nothing to compare against yet.",
                    tone="neutral",
                    provenance="recorded",
                )
            )
        return insights

    direction = "increased" if change.is_increase else "decreased"
    tone: Tone = "positive" if change.is_increase else "negative"
    percent = f" ({change.percent:+.1f}%)" if change.percent is not None else ""
    insights.append(
        Insight(
            f"Net worth {direction} by {_money(change.absolute, symbol)}{percent} in "
            f"{month_label(change.to_month, 'long')}.",
            tone=tone,
            provenance="derived",
            detail=f"{_money(change.from_value, symbol)} → {_money(change.to_value, symbol)}",
        )
    )

    attribution = performance.latest_attribution(dataset)
    if attribution and attribution.total:
        total = attribution.total
        if total.contributions:
            insights.append(
                Insight(
                    f"{_money(total.contributions, symbol)} of that was money you paid in.",
                    tone="positive",
                    provenance="recorded",
                )
            )
        if total.growth is not None:
            growth_tone: Tone = "positive" if total.growth >= 0 else "negative"
            verb = "added" if total.growth >= 0 else "removed"
            insights.append(
                Insight(
                    f"Market movement and interest {verb} {_money(total.growth, symbol)}.",
                    tone=growth_tone,
                    provenance="derived",
                    detail="Balance change minus recorded contributions.",
                )
            )
        elif total.missing_months:
            insights.append(
                Insight(
                    "Growth could not be separated from contributions because "
                    f"{month_label(total.missing_months[0], 'long')} has no contributions "
                    "recorded.",
                    tone="warning",
                    provenance="derived",
                )
            )

    latest = dataset.latest_record()
    if latest is not None:
        summary = cashflow.summarise_month(latest)
        if summary.has_cashflow:
            rate = f"{summary.savings_rate:.0f}%" if summary.savings_rate is not None else "—"
            insights.append(
                Insight(
                    f"You earned {_money(summary.income or 0, symbol)} and spent "
                    f"{_money(summary.spending or 0, symbol)}, a savings rate of {rate}.",
                    tone="positive" if (summary.savings_rate or 0) >= 20 else "neutral",
                    provenance="recorded",
                )
            )

            average = cashflow.average_monthly_spending(dataset, months=6)
            if average and summary.spending is not None and average > 0:
                gap = summary.spending - average
                if abs(gap) / average >= 0.15:
                    higher = gap > 0
                    insights.append(
                        Insight(
                            f"Spending was {_money(gap, symbol)} {'above' if higher else 'below'} "
                            f"your six-month average of {_money(average, symbol)}.",
                            tone="warning" if higher else "positive",
                            provenance="derived",
                        )
                    )

    return insights


def position_insights(dataset: Dataset) -> list[Insight]:
    """Standing observations about the current position, not the last month."""
    symbol = dataset.settings.currency_symbol
    insights: list[Insight] = []

    fund = cashflow.emergency_fund(dataset)
    if fund is not None:
        if fund.months_covered is None:
            insights.append(
                Insight(
                    f"Your emergency fund holds {_money(fund.balance, symbol)}. Record some "
                    "monthly spending to see how long it would last.",
                    tone="neutral",
                    provenance="recorded",
                )
            )
        elif fund.months_covered >= fund.target_months:
            insights.append(
                Insight(
                    f"Your emergency fund covers {fund.months_covered:.1f} months of spending, "
                    f"meeting your {fund.target_months:.0f}-month target.",
                    tone="positive",
                    provenance="derived",
                )
            )
        else:
            insights.append(
                Insight(
                    f"Your emergency fund covers {fund.months_covered:.1f} months of spending. "
                    f"Another {_money(fund.shortfall or 0, symbol)} would reach "
                    f"{fund.target_months:.0f} months.",
                    tone="warning",
                    provenance="derived",
                )
            )

    lisa = lisa_status(dataset)
    if lisa and lisa.bonus_available > 0:
        remaining = current_tax_year().months_remaining
        monthly = lisa.allowance.monthly_to_max_out(remaining)
        detail = (
            f"About {_money(monthly, symbol)} a month for the remaining {remaining} months."
            if monthly
            else None
        )
        insights.append(
            Insight(
                f"{_money(lisa.allowance.remaining, symbol)} of your {lisa.tax_year} LISA allowance "
                f"is unused, worth {_money(lisa.bonus_available, symbol)} in government bonus.",
                tone="warning",
                provenance="derived",
                detail=detail,
            )
        )

    isa = isa_status(dataset)
    if isa and isa.is_exhausted:
        insights.append(
            Insight(
                f"You have used your full {isa.tax_year} ISA allowance.",
                tone="positive",
                provenance="derived",
            )
        )

    for progress in goals.headline_goals(dataset, limit=2):
        if progress.is_complete:
            insights.append(
                Insight(f"'{progress.goal.name}' has reached its target.", tone="positive")
            )
        elif progress.pace == "behind" and progress.required_monthly:
            insights.append(
                Insight(
                    f"'{progress.goal.name}' needs {_money(progress.required_monthly, symbol)} a "
                    f"month to hit its target date.",
                    tone="warning",
                    provenance="derived",
                    detail=(
                        f"Recent contributions average "
                        f"{_money(progress.observed_monthly or 0, symbol)} a month."
                    ),
                )
            )

    return insights


def data_gaps(dataset: Dataset) -> list[Insight]:
    """Nudges about missing data that limits what the app can tell you."""
    insights: list[Insight] = []

    if not dataset.months:
        return insights

    latest = dataset.months[-1]
    if not latest.has_cashflow:
        insights.append(
            Insight(
                f"{month_label(latest.month, 'long')} has no income or spending recorded, so "
                "savings rate and surplus are unavailable for that month.",
                tone="neutral",
                provenance="recorded",
            )
        )

    without_contributions = [r for r in dataset.records_with_balances() if not r.contributions]
    if len(without_contributions) > len(dataset.records_with_balances()) / 2:
        insights.append(
            Insight(
                "Most months have no contributions recorded, so growth cannot be separated "
                "from money you paid in.",
                tone="neutral",
                provenance="derived",
            )
        )

    return insights
