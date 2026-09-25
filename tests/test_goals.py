"""Goal progress, required contributions and projected completion."""

from __future__ import annotations

from datetime import date

from financelib.calculations import goals as goal_calc
from financelib.models import Dataset, Goal, MonthlyRecord

TODAY = date(2026, 3, 15)


class TestCurrentAmount:
    def test_sums_the_chosen_accounts(self, dataset):
        goal = Goal(id="g", name="G", target_amount=100, account_ids=["savings", "isa"])
        assert goal_calc.current_amount(dataset, goal) == 16_600

    def test_net_worth_goal_uses_total(self, dataset):
        goal = Goal(id="g", name="G", kind="net_worth", target_amount=100_000)
        assert goal_calc.current_amount(dataset, goal) == 37_500

    def test_manual_override_wins(self, dataset):
        goal = Goal(id="g", name="G", target_amount=100, account_ids=["isa"], manual_amount=42)
        assert goal_calc.current_amount(dataset, goal) == 42

    def test_spend_down_tracks_spent(self, dataset):
        goal = Goal(id="g", name="G", kind="spend_down", target_amount=5_000, spent=1_200)
        assert goal_calc.current_amount(dataset, goal) == 1_200

    def test_unknown_account_contributes_nothing(self, dataset):
        goal = Goal(id="g", name="G", target_amount=100, account_ids=["nope"])
        assert goal_calc.current_amount(dataset, goal) == 0

    def test_no_history_gives_zero(self, empty_dataset):
        goal = Goal(id="g", name="G", target_amount=100, account_ids=["isa"])
        assert goal_calc.current_amount(empty_dataset, goal) == 0


class TestProgress:
    def test_percentage_and_remainder(self, dataset):
        goal = Goal(id="g", name="G", target_amount=20_000, account_ids=["savings", "isa"])
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.percent == 83.0
        assert progress.remaining == 3_400

    def test_progress_is_capped_but_raw_is_not(self, dataset):
        goal = Goal(id="g", name="G", target_amount=1_000, account_ids=["savings"])
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.percent == 100.0
        assert progress.raw_percent == 540.0
        assert progress.is_complete
        assert progress.remaining == 0

    def test_zero_target_does_not_divide_by_zero(self, dataset):
        goal = Goal(id="g", name="G", target_amount=0, account_ids=["isa"])
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.percent == 0.0
        assert not progress.is_complete


class TestRequiredContribution:
    def test_divides_the_remainder_over_remaining_months(self, dataset):
        goal = Goal(
            id="g",
            name="G",
            target_amount=20_000,
            account_ids=["savings", "isa"],
            target_date=date(2026, 9, 1),
        )
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.months_remaining == 6
        assert progress.required_monthly == round(3_400 / 6, 2)

    def test_no_target_date_means_no_requirement(self, dataset):
        goal = Goal(id="g", name="G", target_amount=20_000, account_ids=["savings"])
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.required_monthly is None
        assert progress.months_remaining is None
        assert not progress.has_deadline

    def test_passed_deadline_requires_the_whole_remainder(self, dataset):
        goal = Goal(
            id="g",
            name="G",
            target_amount=20_000,
            account_ids=["savings", "isa"],
            target_date=date(2026, 1, 1),
        )
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.is_overdue
        assert progress.required_monthly == 3_400

    def test_completed_goal_requires_nothing(self, dataset):
        goal = Goal(
            id="g",
            name="G",
            target_amount=1_000,
            account_ids=["savings"],
            target_date=date(2027, 1, 1),
        )
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.required_monthly is None
        assert progress.pace == "complete"


class TestProjection:
    def test_uses_the_stated_assumption_when_given(self, dataset):
        goal = Goal(
            id="g",
            name="G",
            target_amount=20_000,
            account_ids=["savings", "isa"],
            monthly_contribution=1_000,
        )
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.projection_basis == "your assumption"
        assert progress.projected_completion == date(2026, 7, 1)

    def test_falls_back_to_recorded_contributions(self, dataset):
        goal = Goal(id="g", name="G", target_amount=20_000, account_ids=["savings", "isa"])
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.observed_monthly == 600
        assert progress.projection_basis == "recent contributions"

    def test_zero_contributions_give_no_projected_date(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[MonthlyRecord(month="2026-01", balances={"savings": 100})],
        )
        goal = Goal(id="g", name="G", target_amount=10_000, account_ids=["savings"])
        progress = goal_calc.evaluate(data, goal, TODAY)
        assert progress.observed_monthly is None
        assert progress.projected_completion is None
        assert progress.projection_basis is None

    def test_pace_is_unknown_without_a_deadline(self, dataset):
        goal = Goal(id="g", name="G", target_amount=20_000, account_ids=["savings"])
        assert goal_calc.evaluate(dataset, goal, TODAY).pace is None

    def test_behind_pace_reports_a_shortfall(self, dataset):
        goal = Goal(
            id="g",
            name="G",
            target_amount=20_000,
            account_ids=["savings", "isa"],
            target_date=date(2026, 6, 1),
            monthly_contribution=100,
        )
        progress = goal_calc.evaluate(dataset, goal, TODAY)
        assert progress.pace == "behind"
        assert progress.monthly_shortfall > 0


class TestHeadlines:
    def test_deadlines_come_first(self, dataset):
        dataset.goals = [
            Goal(id="a", name="No deadline", target_amount=1_000, account_ids=["isa"]),
            Goal(
                id="b",
                name="Soon",
                target_amount=1_000,
                account_ids=["isa"],
                target_date=date(2026, 6, 1),
            ),
        ]
        headline = goal_calc.headline_goals(dataset, limit=2, today=TODAY)
        assert headline[0].goal.id == "b"

    def test_inactive_goals_are_excluded(self, dataset):
        dataset.goals = [
            Goal(id="a", name="A", target_amount=1_000, account_ids=["isa"], active=False)
        ]
        assert goal_calc.evaluate_all(dataset, TODAY) == []

    def test_goals_without_targets_are_not_shown(self, dataset):
        dataset.goals = [Goal(id="a", name="A", target_amount=0)]
        assert goal_calc.headline_goals(dataset, today=TODAY) == []
