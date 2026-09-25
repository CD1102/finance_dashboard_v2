"""UK tax-year allowances.

Carried over from the original prototype because the logic is correct and
genuinely useful. Adapted to the monthly model and to generic account flags,
so nothing here depends on an account being named "LISA".

Approximation worth knowing about: the UK tax year runs 6 April to 5 April,
but this app records whole months. Each April is therefore attributed entirely
to the tax year it begins. For monthly totals that is the right call; for
contributions made on 1-5 April it can place them a year late.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from financelib.models import Dataset, month_range

LISA_ANNUAL_LIMIT = 4_000.0
LISA_BONUS_RATE = 0.25
ISA_ANNUAL_ALLOWANCE = 20_000.0
#: A LISA must be opened before 40 and can be paid into until the day before 50.
LISA_MAX_AGE = 50


@dataclass(frozen=True)
class TaxYear:
    label: str
    start: date
    end: date

    @property
    def months(self) -> list[str]:
        """Month keys belonging to this tax year, April through March."""
        return month_range(
            f"{self.start.year:04d}-04",
            f"{self.end.year:04d}-03",
        )

    @property
    def months_elapsed(self) -> int:
        """How many of this tax year's months have started, capped at 12."""
        today = date.today()
        if today >= self.end:
            return 12
        if today < self.start:
            return 0
        return min((today.year - self.start.year) * 12 + today.month - self.start.month + 1, 12)

    @property
    def months_remaining(self) -> int:
        return max(12 - self.months_elapsed, 0)


@dataclass(frozen=True)
class AllowanceStatus:
    """Use of an annual allowance, with the headroom left."""

    name: str
    tax_year: str
    used: float
    limit: float
    accounts: tuple[str, ...] = ()

    @property
    def remaining(self) -> float:
        return round(max(self.limit - self.used, 0.0), 2)

    @property
    def percent_used(self) -> float:
        if self.limit <= 0:
            return 0.0
        return round(min(self.used / self.limit * 100, 100.0), 1)

    @property
    def is_exhausted(self) -> bool:
        return self.used >= self.limit

    def monthly_to_max_out(self, months_remaining: int) -> float | None:
        """Monthly amount needed to use the full allowance before year end."""
        if self.remaining <= 0 or months_remaining <= 0:
            return None
        return round(self.remaining / months_remaining, 2)


@dataclass(frozen=True)
class LisaStatus:
    allowance: AllowanceStatus
    bonus_earned: float
    bonus_available: float

    @property
    def tax_year(self) -> str:
        return self.allowance.tax_year


def current_tax_year(today: date | None = None) -> TaxYear:
    today = today or date.today()
    if today >= date(today.year, 4, 6):
        start = date(today.year, 4, 6)
        end = date(today.year + 1, 4, 5)
    else:
        start = date(today.year - 1, 4, 6)
        end = date(today.year, 4, 5)
    return TaxYear(label=f"{start.year}/{str(end.year)[-2:]}", start=start, end=end)


def contributions_in_tax_year(
    dataset: Dataset, account_ids: list[str], tax_year: TaxYear | None = None
) -> float:
    tax_year = tax_year or current_tax_year()
    wanted = set(tax_year.months)
    total = 0.0
    for record in dataset.months:
        if record.month not in wanted:
            continue
        total += sum(record.contributions.get(account_id, 0.0) for account_id in account_ids)
    return round(total, 2)


def lisa_status(dataset: Dataset, today: date | None = None) -> LisaStatus | None:
    """Lifetime ISA position, if any account is flagged as one."""
    accounts = [a for a in dataset.accounts if a.lisa and a.active]
    if not accounts:
        return None

    tax_year = current_tax_year(today)
    used = contributions_in_tax_year(dataset, [a.id for a in accounts], tax_year)
    counted = min(used, LISA_ANNUAL_LIMIT)

    allowance = AllowanceStatus(
        name="LISA",
        tax_year=tax_year.label,
        used=used,
        limit=LISA_ANNUAL_LIMIT,
        accounts=tuple(a.name for a in accounts),
    )
    return LisaStatus(
        allowance=allowance,
        bonus_earned=round(counted * LISA_BONUS_RATE, 2),
        bonus_available=round(allowance.remaining * LISA_BONUS_RATE, 2),
    )


def isa_status(dataset: Dataset, today: date | None = None) -> AllowanceStatus | None:
    """Combined ISA allowance use across every account flagged as an ISA."""
    accounts = [a for a in dataset.accounts if a.isa and a.active]
    if not accounts:
        return None

    tax_year = current_tax_year(today)
    return AllowanceStatus(
        name="ISA allowance",
        tax_year=tax_year.label,
        used=contributions_in_tax_year(dataset, [a.id for a in accounts], tax_year),
        limit=ISA_ANNUAL_ALLOWANCE,
        accounts=tuple(a.name for a in accounts),
    )
