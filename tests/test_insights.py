"""The narrative layer — statements must be supported by stored data."""

from __future__ import annotations

from financelib.calculations import insights
from financelib.models import Account, Dataset, Goal, MonthlyRecord


class TestMonthNarrative:
    def test_empty_dataset_says_nothing(self, empty_dataset):
        assert insights.month_narrative(empty_dataset) == []

    def test_single_month_explains_why_there_is_no_comparison(self, accounts):
        data = Dataset(
            accounts=accounts, months=[MonthlyRecord(month="2026-01", balances={"isa": 100})]
        )
        result = insights.month_narrative(data)
        assert len(result) == 1
        assert "first recorded month" in result[0].text

    def test_reports_the_change_and_its_direction(self, dataset):
        texts = [item.text for item in insights.month_narrative(dataset)]
        assert any("increased" in text for text in texts)

    def test_reports_a_fall_as_a_fall(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 10_000}),
                MonthlyRecord(month="2026-02", balances={"isa": 9_000}),
            ],
        )
        first = insights.month_narrative(data)[0]
        assert "decreased" in first.text
        assert first.tone == "negative"

    def test_separates_contributions_from_growth_when_it_can(self, dataset):
        texts = " ".join(item.text for item in insights.month_narrative(dataset))
        assert "paid in" in texts
        assert "Market movement" in texts

    def test_says_so_when_growth_cannot_be_separated(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 10_000}),
                MonthlyRecord(month="2026-02", balances={"isa": 10_500}),
            ],
        )
        texts = " ".join(item.text for item in insights.month_narrative(data))
        assert "could not be separated" in texts

    def test_every_statement_carries_its_provenance(self, dataset):
        for item in insights.month_narrative(dataset):
            assert item.provenance in {"recorded", "derived", "assumption"}


class TestPositionInsights:
    def test_quiet_when_there_is_nothing_to_say(self, empty_dataset):
        assert insights.position_insights(empty_dataset) == []

    def test_reports_emergency_fund_coverage(self, dataset):
        texts = " ".join(item.text for item in insights.position_insights(dataset))
        assert "emergency fund" in texts

    def test_flags_unused_lisa_allowance(self):
        data = Dataset(
            accounts=[
                Account(id="lisa", name="LISA", category="investment", lisa=True, isa=True)
            ],
            months=[MonthlyRecord(month="2026-05", contributions={"lisa": 500})],
        )
        texts = " ".join(item.text for item in insights.position_insights(data))
        assert "LISA allowance" in texts

    def test_congratulates_a_completed_goal(self, dataset):
        dataset.goals = [
            Goal(id="g", name="Small target", target_amount=100, account_ids=["savings"])
        ]
        texts = " ".join(item.text for item in insights.position_insights(dataset))
        assert "reached its target" in texts


class TestDataGaps:
    def test_notes_a_month_without_cashflow(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[MonthlyRecord(month="2026-01", balances={"isa": 100})],
        )
        texts = " ".join(item.text for item in insights.data_gaps(data))
        assert "no income or spending" in texts

    def test_notes_widespread_missing_contributions(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(month="2026-01", balances={"isa": 100}),
                MonthlyRecord(month="2026-02", balances={"isa": 200}),
            ],
        )
        texts = " ".join(item.text for item in insights.data_gaps(data))
        assert "growth cannot be separated" in texts

    def test_quiet_when_data_is_complete(self, dataset):
        assert insights.data_gaps(dataset) == []

    def test_empty_dataset_produces_nothing(self, empty_dataset):
        assert insights.data_gaps(empty_dataset) == []
