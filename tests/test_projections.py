"""Projection arithmetic."""

from __future__ import annotations

import pytest

from financelib.calculations import projections as proj
from financelib.models import Dataset, MonthlyRecord


class TestMechanics:
    def test_no_growth_and_no_contributions_stays_flat(self):
        result = proj.project(
            proj.Assumptions(
                starting_cash=1_000,
                cash_rate=0,
                investment_return=0,
                pension_return=0,
                inflation=0,
                years=5,
            )
        )
        assert result.final.total == 1_000
        assert result.final.contributions == 0
        assert result.final.total_growth == 0

    def test_contributions_only_add_up_exactly(self):
        result = proj.project(
            proj.Assumptions(
                monthly_cash_contribution=100,
                cash_rate=0,
                investment_return=0,
                pension_return=0,
                inflation=0,
                years=2,
            )
        )
        assert result.final.contributions == 2_400
        assert result.final.total == 2_400

    def test_growth_compounds_monthly_not_annually(self):
        """1000 at 12% should beat simple interest but not exceed the annual rate."""
        result = proj.project(
            proj.Assumptions(starting_investments=1_000, investment_return=12, years=1)
        )
        assert result.final.total == pytest.approx(1_120, abs=1)

    def test_contributions_are_added_after_growth(self):
        """The first month's contribution must not earn that month's return."""
        result = proj.project(
            proj.Assumptions(
                monthly_investment_contribution=100, investment_return=12, years=1
            )
        )
        first = result.points[1]
        assert first.total == 100
        assert first.investment_growth == 0

    def test_total_always_equals_its_parts(self):
        result = proj.project(
            proj.Assumptions(
                starting_investments=5_000,
                starting_cash=2_000,
                starting_pension=8_000,
                monthly_investment_contribution=300,
                monthly_cash_contribution=100,
                monthly_pension_contribution=400,
                years=10,
            )
        )
        for point in result.yearly:
            assert point.total == pytest.approx(
                point.starting_wealth + point.contributions + point.total_growth, abs=0.5
            )

    def test_interest_and_investment_growth_are_separated(self):
        result = proj.project(
            proj.Assumptions(
                starting_investments=10_000,
                starting_cash=10_000,
                investment_return=8,
                cash_rate=2,
                years=10,
            )
        )
        assert result.final.investment_growth > result.final.interest > 0

    def test_contribution_growth_escalates_annually(self):
        flat = proj.project(
            proj.Assumptions(monthly_cash_contribution=100, cash_rate=0, years=5)
        )
        rising = proj.project(
            proj.Assumptions(
                monthly_cash_contribution=100, cash_rate=0, contribution_growth=10, years=5
            )
        )
        assert rising.final.contributions > flat.final.contributions

    def test_inflation_reduces_real_value(self):
        result = proj.project(
            proj.Assumptions(starting_cash=10_000, cash_rate=0, inflation=3, years=10)
        )
        assert result.final.real_total < result.final.total
        assert result.final.real_total == pytest.approx(10_000 / 1.03**10, abs=1)

    def test_zero_inflation_leaves_real_equal_to_nominal(self):
        result = proj.project(proj.Assumptions(starting_cash=5_000, inflation=0, years=5))
        assert result.final.real_total == result.final.total


class TestBounds:
    def test_horizon_is_clamped(self):
        assert proj.Assumptions(years=0).years == 1
        assert proj.Assumptions(years=500).years == proj.MAX_YEARS

    def test_everything_zero_does_not_error(self):
        result = proj.project(proj.Assumptions())
        assert result.final.total == 0
        assert result.final.real_total == 0

    def test_point_count_matches_horizon(self):
        result = proj.project(proj.Assumptions(years=3))
        assert len(result.points) == 37
        assert len(result.yearly) == 4

    def test_year_when_reaching_target(self):
        result = proj.project(
            proj.Assumptions(starting_cash=1_000, monthly_cash_contribution=100, cash_rate=0, years=5)
        )
        assert result.year_when_reaching(2_200) == pytest.approx(1.0, abs=0.1)

    def test_unreachable_target_returns_none(self):
        result = proj.project(proj.Assumptions(starting_cash=100, cash_rate=0, years=5))
        assert result.year_when_reaching(1_000_000) is None


class TestSeeding:
    def test_seeds_starting_balances_from_the_latest_month(self, dataset):
        assumptions = proj.assumptions_from_dataset(dataset)
        assert assumptions.starting_investments == 11_200
        assert assumptions.starting_pension == 20_900

    def test_seeds_contributions_from_recorded_averages(self, dataset):
        assumptions = proj.assumptions_from_dataset(dataset)
        assert assumptions.monthly_investment_contribution == 400
        assert assumptions.monthly_pension_contribution == 300

    def test_falls_back_to_planned_contributions(self, accounts):
        accounts[0].planned_contribution = 250
        data = Dataset(
            accounts=accounts, months=[MonthlyRecord(month="2026-01", balances={"isa": 1_000})]
        )
        assumptions = proj.assumptions_from_dataset(data)
        assert assumptions.monthly_investment_contribution == 250

    def test_empty_dataset_produces_a_zero_scenario(self, empty_dataset):
        assumptions = proj.assumptions_from_dataset(empty_dataset)
        assert assumptions.starting_total == 0
        assert proj.project(assumptions).final.total == 0

    def test_variants_change_only_what_is_asked(self):
        base = proj.Assumptions(monthly_investment_contribution=100, label="Base")
        variant = base.variant("More", monthly_investment_contribution=200)
        assert base.monthly_investment_contribution == 100
        assert variant.monthly_investment_contribution == 200
        assert variant.label == "More"

    def test_default_scenarios_include_the_base(self):
        base = proj.Assumptions(monthly_investment_contribution=400, label="Now")
        scenarios = proj.default_scenarios(base)
        assert scenarios[0] is base
        assert len(scenarios) == 3


class TestTrajectory:
    def test_needs_enough_history(self, dataset):
        assert proj.trajectory_check(dataset) is None

    def test_compares_actual_with_projected(self, accounts):
        months = [
            MonthlyRecord(
                month=f"2026-{index:02d}",
                balances={"isa": 10_000 + index * 500},
                contributions={"isa": 400},
            )
            for index in range(1, 7)
        ]
        data = Dataset(accounts=accounts, months=months)
        result = proj.trajectory_check(data)
        assert result is not None
        assert result["months_observed"] == 5
        assert result["actual_monthly"] == 500
