"""Goal progress, required contributions and projected completion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from financelib.models import ACCUMULATION, NET_WORTH_GOAL, SPEND_DOWN, Dataset, Goal
from financelib.calculations.networth import current_net_worth


@dataclass(frozen=True)
class GoalProgress:
    """Everything the UI needs to describe one goal honestly."""

    goal: Goal
    current: float
    target: float
    #: Average recorded monthly contribution to the goal's accounts, or None.
    observed_monthly: float | None
    #: The user's stated assumption, if they set one.
    assumed_monthly: float | None
    months_remaining: int | None
    required_monthly: float | None
    projected_completion: date | None
    projection_basis: str | None

    @property
    def percent(self) -> float:
        if self.target <= 0:
            return 0.0
        return round(min(self.current / self.target * 100, 100.0), 1)

    @property
    def raw_percent(self) -> float:
        """Uncapped progress, so overshooting a target is visible."""
        if self.target <= 0:
            return 0.0
        return round(self.current / self.target * 100, 1)

    @property
    def remaining(self) -> float:
        return round(max(self.target - self.current, 0.0), 2)

    @property
    def is_complete(self) -> bool:
        return self.target > 0 and self.current >= self.target

    @property
    def has_deadline(self) -> bool:
        return self.goal.target_date is not None

    @property
    def is_overdue(self) -> bool:
        return (
            self.has_deadline
            and not self.is_complete
            and self.months_remaining is not None
            and self.months_remaining <= 0
        )

    @property
    def pace(self) -> str | None:
        """Comparison of expected pace against what the deadline demands.

        ``None`` when there is nothing to compare — no deadline, or no
        contribution rate to judge against.
        """
        rate = self.assumed_monthly if self.assumed_monthly is not None else self.observed_monthly
        if self.is_complete:
            return "complete"
        if self.required_monthly is None or rate is None:
            return None
        if rate >= self.required_monthly:
            return "ahead"
        if rate >= self.required_monthly * 0.9:
            return "close"
        return "behind"

    @property
    def monthly_shortfall(self) -> float | None:
        rate = self.assumed_monthly if self.assumed_monthly is not None else self.observed_monthly
        if self.required_monthly is None or rate is None:
            return None
        return round(max(self.required_monthly - rate, 0.0), 2)


def current_amount(dataset: Dataset, goal: Goal) -> float:
    """Where a goal stands today, based on how it is measured."""
    if goal.manual_amount is not None:
        return goal.manual_amount

    if goal.kind == NET_WORTH_GOAL:
        return current_net_worth(dataset)

    if goal.kind == SPEND_DOWN:
        return goal.spent

    latest = dataset.latest_record(require_balances=True)
    if latest is None:
        return 0.0
    return round(sum(latest.balances.get(account_id, 0.0) for account_id in goal.account_ids), 2)


def observed_contribution_rate(dataset: Dataset, goal: Goal, months: int = 6) -> float | None:
    """Average monthly contribution into the goal's accounts.

    Returns ``None`` for goals not measured by account balances, or when no
    contributions have been recorded — an average of nothing is not zero.
    """
    if goal.kind != ACCUMULATION or not goal.account_ids:
        return None

    recent = [r for r in dataset.months if r.contributions][-months:]
    if not recent:
        return None

    total = sum(
        sum(record.contributions.get(account_id, 0.0) for account_id in goal.account_ids)
        for record in recent
    )
    return round(total / len(recent), 2)


def _months_until(target_date: date | None, today: date) -> int | None:
    if target_date is None:
        return None
    return (target_date.year - today.year) * 12 + (target_date.month - today.month)


def evaluate(dataset: Dataset, goal: Goal, today: date | None = None) -> GoalProgress:
    today = today or date.today()
    current = current_amount(dataset, goal)
    target = goal.target_amount
    remaining = max(target - current, 0.0)

    months_remaining = _months_until(goal.target_date, today)
    if months_remaining is not None and months_remaining > 0 and remaining > 0:
        required_monthly = round(remaining / months_remaining, 2)
    elif months_remaining is not None and remaining > 0:
        # Deadline has passed or is this month: the whole remainder is required.
        required_monthly = round(remaining, 2)
    else:
        required_monthly = None

    observed = observed_contribution_rate(dataset, goal)
    assumed = goal.monthly_contribution

    rate = assumed if assumed is not None else observed
    basis = "your assumption" if assumed is not None else ("recent contributions" if observed else None)

    projected: date | None = None
    if remaining <= 0:
        projected, basis = today, "already reached"
    elif rate and rate > 0:
        months_needed = int(-(-remaining // rate))  # ceiling division
        index = today.year * 12 + (today.month - 1) + months_needed
        projected = date(index // 12, index % 12 + 1, 1)
    else:
        basis = None

    return GoalProgress(
        goal=goal,
        current=current,
        target=target,
        observed_monthly=observed,
        assumed_monthly=assumed,
        months_remaining=months_remaining,
        required_monthly=required_monthly,
        projected_completion=projected,
        projection_basis=basis,
    )


def evaluate_all(dataset: Dataset, today: date | None = None) -> list[GoalProgress]:
    return [evaluate(dataset, goal, today) for goal in dataset.goals if goal.active]


def headline_goals(dataset: Dataset, limit: int = 3, today: date | None = None) -> list[GoalProgress]:
    """The goals most worth surfacing on the dashboard.

    Prioritises goals with a deadline, then those nearest completion, so the
    overview shows what is actually live rather than an arbitrary first three.
    """
    progress = [p for p in evaluate_all(dataset, today) if p.target > 0]

    def sort_key(item: GoalProgress) -> tuple[int, float, float]:
        has_deadline = 0 if item.has_deadline else 1
        urgency = item.months_remaining if item.months_remaining is not None else 9999
        return (has_deadline, float(urgency), -item.percent)

    return sorted(progress, key=sort_key)[:limit]
