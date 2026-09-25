"""UK tax-year allowances and formatting helpers."""

from __future__ import annotations

from datetime import date

import pytest

from financelib.calculations import taxuk
from financelib.formatting import (
    compact_money,
    duration_label,
    file_size,
    money,
    month_axis_label,
    month_label,
    percent,
    pluralise,
    signed_money,
    signed_percent,
)
from financelib.models import Account, Dataset, MonthlyRecord


class TestTaxYear:
    def test_after_sixth_of_april_is_the_new_year(self):
        year = taxuk.current_tax_year(date(2026, 4, 6))
        assert year.label == "2026/27"
        assert year.start == date(2026, 4, 6)

    def test_before_sixth_of_april_is_the_old_year(self):
        year = taxuk.current_tax_year(date(2026, 4, 5))
        assert year.label == "2025/26"

    def test_months_run_april_to_march(self):
        months = taxuk.current_tax_year(date(2026, 6, 1)).months
        assert months[0] == "2026-04"
        assert months[-1] == "2027-03"
        assert len(months) == 12


class TestLisa:
    def _dataset(self, contributed: float) -> Dataset:
        return Dataset(
            accounts=[
                Account(id="lisa", name="LISA", category="investment", lisa=True, isa=True)
            ],
            months=[
                MonthlyRecord(month="2026-05", contributions={"lisa": contributed}),
            ],
        )

    def test_none_when_no_lisa_account_exists(self, dataset):
        assert taxuk.lisa_status(dataset) is None

    def test_bonus_is_a_quarter_of_contributions(self):
        status = taxuk.lisa_status(self._dataset(1_000), date(2026, 6, 1))
        assert status.bonus_earned == 250
        assert status.allowance.remaining == 3_000
        assert status.bonus_available == 750

    def test_bonus_is_capped_at_the_annual_limit(self):
        status = taxuk.lisa_status(self._dataset(6_000), date(2026, 6, 1))
        assert status.bonus_earned == 1_000
        assert status.allowance.remaining == 0
        assert status.allowance.is_exhausted

    def test_contributions_outside_the_tax_year_do_not_count(self):
        data = self._dataset(1_000)
        status = taxuk.lisa_status(data, date(2027, 6, 1))
        assert status.allowance.used == 0

    def test_monthly_amount_to_use_the_rest(self):
        status = taxuk.lisa_status(self._dataset(1_000), date(2026, 6, 1))
        assert status.allowance.monthly_to_max_out(6) == 500

    def test_no_months_left_means_no_amount(self):
        status = taxuk.lisa_status(self._dataset(1_000), date(2026, 6, 1))
        assert status.allowance.monthly_to_max_out(0) is None


class TestIsa:
    def test_sums_across_every_isa_account(self):
        data = Dataset(
            accounts=[
                Account(id="cash_isa", name="Cash ISA", category="cash", isa=True),
                Account(id="ss_isa", name="S&S ISA", category="investment", isa=True),
                Account(id="other", name="Other", category="cash"),
            ],
            months=[
                MonthlyRecord(
                    month="2026-05",
                    contributions={"cash_isa": 5_000, "ss_isa": 3_000, "other": 9_000},
                )
            ],
        )
        status = taxuk.isa_status(data, date(2026, 6, 1))
        assert status.used == 8_000
        assert status.remaining == 12_000
        assert status.percent_used == 40.0

    def test_none_when_no_isa_accounts(self, dataset):
        data = Dataset(accounts=[Account(id="a", name="A", category="cash")])
        assert taxuk.isa_status(data) is None


class TestFormatting:
    @pytest.mark.parametrize(
        "value,expected",
        [(1234.5, "£1,235"), (0, "£0"), (None, "—")],
    )
    def test_money(self, value, expected):
        assert money(value) == expected

    def test_negative_money_uses_a_true_minus_sign(self):
        assert money(-500) == "\u2212£500"

    def test_signed_money_always_shows_a_sign(self):
        assert signed_money(500) == "+£500"
        assert signed_money(-500) == "\u2212£500"
        assert signed_money(0) == "+£0"

    @pytest.mark.parametrize(
        "value,expected",
        [(999, "£999"), (1_500, "£1.5k"), (2_000, "£2k"), (1_400_000, "£1.40m")],
    )
    def test_compact_money(self, value, expected):
        assert compact_money(value) == expected

    def test_percent_handles_missing(self):
        assert percent(None) == "—"
        assert percent(12.345) == "12.3%"
        assert signed_percent(-4.0) == "\u22124.0%"

    def test_month_labels(self):
        assert month_label("2026-09") == "Sep 2026"
        assert month_label("2026-09", "long") == "September 2026"
        assert month_axis_label("2026-09") == "Sep 26"

    def test_month_label_passes_through_nonsense(self):
        assert month_label("not-a-month") == "not-a-month"

    @pytest.mark.parametrize(
        "months,expected",
        [(0, "now"), (1, "1 mo"), (12, "1 yr"), (18, "1 yr 6 mo"), (None, "—")],
    )
    def test_duration_label(self, months, expected):
        assert duration_label(months) == expected

    def test_file_size(self):
        assert file_size(0) == "0 KB"
        assert file_size(2048).endswith("KB")

    def test_pluralise(self):
        assert pluralise(1, "month") == "1 month"
        assert pluralise(3, "month") == "3 months"
