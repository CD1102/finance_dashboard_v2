"""Domain models.

These dataclasses are the contract between storage, calculations and the UI.
They contain no Streamlit, no file I/O and no persistence concerns, so the
whole model layer stays testable and portable when JSON is swapped for a
database later.

Money is represented as ``float`` rounded to pence on the way in and out.
That is accurate enough for monthly personal-finance totals and keeps JSON
round-trips simple; if exact decimal arithmetic is ever needed, the change is
contained to ``_money`` and the storage layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Account categories
# --------------------------------------------------------------------------

INVESTMENT = "investment"
CASH = "cash"
PENSION = "pension"
PROPERTY = "property"
OTHER = "other"
LIABILITY = "liability"

ASSET_CATEGORIES: tuple[str, ...] = (INVESTMENT, CASH, PENSION, PROPERTY, OTHER)
ALL_CATEGORIES: tuple[str, ...] = ASSET_CATEGORIES + (LIABILITY,)

CATEGORY_LABELS: dict[str, str] = {
    INVESTMENT: "Investments",
    CASH: "Cash & savings",
    PENSION: "Pension",
    PROPERTY: "Property",
    OTHER: "Other assets",
    LIABILITY: "Liabilities",
}

#: Spending buckets offered by default. Users may add their own; nothing in the
#: calculation layer depends on this list.
DEFAULT_SPENDING_CATEGORIES: tuple[str, ...] = (
    "Housing",
    "Bills & utilities",
    "Food & groceries",
    "Transport",
    "Subscriptions",
    "Shopping",
    "Leisure",
    "Giving",
    "Other",
)

MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ValidationError(ValueError):
    """Raised when incoming data cannot be coerced into a valid model."""


# --------------------------------------------------------------------------
# Coercion helpers
# --------------------------------------------------------------------------


def _money(value: Any, default: float = 0.0) -> float:
    """Coerce a value to a rounded float, tolerating blanks and strings."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValidationError(f"Expected a number, got a boolean: {value!r}")
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("£", "").replace("$", "")
        if cleaned in {"", "-", "—"}:
            return default
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        if negative:
            cleaned = cleaned[1:-1]
        try:
            number = float(cleaned)
        except ValueError as exc:
            raise ValidationError(f"Could not read {value!r} as a number") from exc
        return round(-number if negative else number, 2)
    try:
        return round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Could not read {value!r} as a number") from exc


def _money_map(raw: Any) -> dict[str, float]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError(f"Expected a mapping of amounts, got {type(raw).__name__}")
    return {str(key): _money(value) for key, value in raw.items()}


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _optional_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValidationError(f"Could not read {value!r} as a date (expected YYYY-MM-DD)") from exc


def slugify(text: str) -> str:
    """Turn a display name into a stable identifier."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    return slug or "item"


# --------------------------------------------------------------------------
# Month keys
# --------------------------------------------------------------------------


def normalise_month(value: Any) -> str:
    """Return a ``YYYY-MM`` key from a range of common month representations.

    Accepts ``date``/``datetime`` objects, ``2026-09``, ``2026-09-14``,
    ``09/2026`` and ``Sep 2026``.
    """
    if isinstance(value, date):
        return f"{value.year:04d}-{value.month:02d}"

    text = _clean_text(value)
    if not text:
        raise ValidationError("A month is required")

    if MONTH_PATTERN.match(text):
        return text

    # ISO date, or anything else pandas/Excel may hand us with a day component.
    try:
        return normalise_month(date.fromisoformat(text[:10]))
    except ValueError:
        pass

    slash = re.match(r"^(\d{1,2})[/-](\d{4})$", text)
    if slash:
        month, year = int(slash.group(1)), int(slash.group(2))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"

    named = re.match(r"^([A-Za-z]{3,})[\s\-,]+(\d{4})$", text)
    if named:
        months = [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ]
        prefix = named.group(1).lower()[:3]
        for index, name in enumerate(months, start=1):
            if name.startswith(prefix):
                return f"{int(named.group(2)):04d}-{index:02d}"

    raise ValidationError(f"Could not read {value!r} as a month (expected YYYY-MM)")


def month_to_date(month: str) -> date:
    """First day of the given month key."""
    year, mon = month.split("-")
    return date(int(year), int(mon), 1)


def shift_month(month: str, delta: int) -> str:
    """Move a month key forward (or backward) by ``delta`` months."""
    year, mon = (int(part) for part in month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def months_between(start: str, end: str) -> int:
    """Whole months from ``start`` to ``end``. Negative if end precedes start."""
    start_year, start_month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))
    return (end_year - start_year) * 12 + (end_month - start_month)


def month_range(start: str, end: str) -> list[str]:
    """Every month key from ``start`` to ``end`` inclusive."""
    span = months_between(start, end)
    if span < 0:
        return []
    return [shift_month(start, offset) for offset in range(span + 1)]


# --------------------------------------------------------------------------
# Account
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Account:
    """A place money sits. Balances live on monthly records, not here.

    Keeping balances out of the account record means there is exactly one
    source of truth for "what was this worth", which removes the drift that
    happens when a current balance and a history file are written separately.
    """

    id: str
    name: str
    category: str = CASH
    provider: str = ""
    purpose: str = ""
    #: Expected annual rate as a percentage, e.g. ``4.5``. Informational only:
    #: it is never used to invent balances, only to show alongside them.
    interest_rate: float | None = None
    #: What the user intends to pay in each month. Actuals live on the records.
    planned_contribution: float = 0.0
    #: Marks accounts that count toward the emergency fund.
    emergency_fund: bool = False
    #: Marks a UK Lifetime ISA so the bonus tracker can find it generically.
    lisa: bool = False
    #: Marks accounts that consume the annual ISA allowance.
    isa: bool = False
    include_in_net_worth: bool = True
    active: bool = True
    notes: str = ""
    sort_order: int = 0

    def __post_init__(self) -> None:
        self.id = slugify(self.id or self.name)
        self.name = _clean_text(self.name) or self.id
        if self.category not in ALL_CATEGORIES:
            self.category = OTHER
        self.planned_contribution = _money(self.planned_contribution)
        if self.interest_rate is not None:
            self.interest_rate = round(float(self.interest_rate), 4)

    @property
    def is_liability(self) -> bool:
        return self.category == LIABILITY

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, "Other assets")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "provider": self.provider,
            "purpose": self.purpose,
            "interest_rate": self.interest_rate,
            "planned_contribution": self.planned_contribution,
            "emergency_fund": self.emergency_fund,
            "lisa": self.lisa,
            "isa": self.isa,
            "include_in_net_worth": self.include_in_net_worth,
            "active": self.active,
            "notes": self.notes,
            "sort_order": self.sort_order,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Account":
        if not isinstance(raw, dict):
            raise ValidationError(f"Account must be an object, got {type(raw).__name__}")

        # ``type`` was the field name in the original prototype.
        category = raw.get("category") or raw.get("type") or CASH
        rate = raw.get("interest_rate", raw.get("expected_return"))
        return cls(
            id=_clean_text(raw.get("id") or raw.get("name")),
            name=_clean_text(raw.get("name")),
            category=_clean_text(category).lower(),
            provider=_clean_text(raw.get("provider")),
            purpose=_clean_text(raw.get("purpose")),
            interest_rate=None if rate in (None, "") else float(rate),
            planned_contribution=_money(raw.get("planned_contribution")),
            emergency_fund=bool(raw.get("emergency_fund", False)),
            lisa=bool(raw.get("lisa", False)),
            isa=bool(raw.get("isa", False)),
            include_in_net_worth=bool(raw.get("include_in_net_worth", True)),
            active=bool(raw.get("active", True)),
            notes=_clean_text(raw.get("notes")),
            sort_order=int(raw.get("sort_order", 0) or 0),
        )


# --------------------------------------------------------------------------
# Monthly record
# --------------------------------------------------------------------------


@dataclass(slots=True)
class MonthlyRecord:
    """One month of the spreadsheet: what came in, what went out, what's left.

    Every field is optional so partial months degrade gracefully — a month with
    only balances still contributes to the net-worth series, and a month with
    only income and spending still contributes to the savings-rate series.
    """

    month: str
    income: float | None = None
    spending: float | None = None
    spending_categories: dict[str, float] = field(default_factory=dict)
    #: Money deliberately moved into an account this month, by account id.
    contributions: dict[str, float] = field(default_factory=dict)
    #: Closing balance for each account, by account id.
    balances: dict[str, float] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        self.month = normalise_month(self.month)
        self.income = None if self.income in (None, "") else _money(self.income)
        self.spending = None if self.spending in (None, "") else _money(self.spending)
        self.spending_categories = _money_map(self.spending_categories)
        self.contributions = _money_map(self.contributions)
        self.balances = _money_map(self.balances)

    # -- derived -----------------------------------------------------------

    @property
    def date(self) -> date:
        return month_to_date(self.month)

    @property
    def year(self) -> int:
        return int(self.month[:4])

    @property
    def total_contributions(self) -> float:
        return round(sum(self.contributions.values()), 2)

    @property
    def categorised_spending(self) -> float:
        return round(sum(self.spending_categories.values()), 2)

    @property
    def effective_spending(self) -> float | None:
        """Total spending, falling back to the sum of categories."""
        if self.spending is not None:
            return self.spending
        if self.spending_categories:
            return self.categorised_spending
        return None

    @property
    def has_cashflow(self) -> bool:
        """True when income and spending are both present for this month."""
        return self.income is not None and self.effective_spending is not None

    @property
    def has_balances(self) -> bool:
        return bool(self.balances)

    @property
    def is_empty(self) -> bool:
        return not (
            self.has_balances
            or self.income is not None
            or self.spending is not None
            or self.spending_categories
            or self.contributions
        )

    def balance_of(self, account_id: str) -> float | None:
        return self.balances.get(account_id)

    def with_updates(self, **changes: Any) -> "MonthlyRecord":
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"month": self.month}
        if self.income is not None:
            payload["income"] = self.income
        if self.spending is not None:
            payload["spending"] = self.spending
        if self.spending_categories:
            payload["spending_categories"] = self.spending_categories
        if self.contributions:
            payload["contributions"] = self.contributions
        if self.balances:
            payload["balances"] = self.balances
        if self.note:
            payload["note"] = self.note
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "MonthlyRecord":
        if not isinstance(raw, dict):
            raise ValidationError(f"Month must be an object, got {type(raw).__name__}")
        income = raw.get("income")
        spending = raw.get("spending", raw.get("expenses"))
        return cls(
            month=raw.get("month", ""),
            income=None if income in (None, "") else _money(income),
            spending=None if spending in (None, "") else _money(spending),
            spending_categories=_money_map(raw.get("spending_categories")),
            contributions=_money_map(raw.get("contributions")),
            balances=_money_map(raw.get("balances")),
            note=_clean_text(raw.get("note")),
        )


# --------------------------------------------------------------------------
# Goal
# --------------------------------------------------------------------------

ACCUMULATION = "accumulation"
NET_WORTH_GOAL = "net_worth"
SPEND_DOWN = "spend_down"

GOAL_KINDS: tuple[str, ...] = (ACCUMULATION, NET_WORTH_GOAL, SPEND_DOWN)


@dataclass(slots=True)
class Goal:
    """A financial target.

    ``kind`` decides where the current amount comes from:

    - ``accumulation`` sums the balances of ``account_ids``
    - ``net_worth`` uses total net worth
    - ``spend_down`` tracks ``spent`` against a budget (e.g. a wedding fund)
    """

    id: str
    name: str
    target_amount: float
    kind: str = ACCUMULATION
    account_ids: list[str] = field(default_factory=list)
    target_date: date | None = None
    description: str = ""
    #: Optional user assumption used only for projected completion dates.
    monthly_contribution: float | None = None
    #: Manual override for goals that no account can measure.
    manual_amount: float | None = None
    spent: float = 0.0
    active: bool = True
    sort_order: int = 0

    def __post_init__(self) -> None:
        self.id = slugify(self.id or self.name)
        self.name = _clean_text(self.name) or self.id
        self.target_amount = _money(self.target_amount)
        if self.kind not in GOAL_KINDS:
            self.kind = ACCUMULATION
        self.spent = _money(self.spent)
        if self.monthly_contribution is not None:
            self.monthly_contribution = _money(self.monthly_contribution)
        if self.manual_amount is not None:
            self.manual_amount = _money(self.manual_amount)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "target_amount": self.target_amount,
            "account_ids": list(self.account_ids),
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "description": self.description,
            "monthly_contribution": self.monthly_contribution,
            "manual_amount": self.manual_amount,
            "spent": self.spent,
            "active": self.active,
            "sort_order": self.sort_order,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Goal":
        if not isinstance(raw, dict):
            raise ValidationError(f"Goal must be an object, got {type(raw).__name__}")
        target = raw.get("target_amount", raw.get("target", 0))
        accounts = raw.get("account_ids", raw.get("accounts", []))
        contribution = raw.get("monthly_contribution")
        manual = raw.get("manual_amount")
        return cls(
            id=_clean_text(raw.get("id") or raw.get("name")),
            name=_clean_text(raw.get("name")),
            target_amount=_money(target),
            kind=_clean_text(raw.get("kind"), ACCUMULATION).lower(),
            account_ids=[slugify(a) for a in accounts or []],
            target_date=_optional_date(raw.get("target_date")),
            description=_clean_text(raw.get("description") or raw.get("note")),
            monthly_contribution=None if contribution in (None, "") else _money(contribution),
            manual_amount=None if manual in (None, "") else _money(manual),
            spent=_money(raw.get("spent")),
            active=bool(raw.get("active", True)),
            sort_order=int(raw.get("sort_order", 0) or 0),
        )


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Settings:
    """User preferences that affect analysis rather than presentation only."""

    currency_symbol: str = "£"
    #: Months of essential spending the emergency fund should cover.
    emergency_fund_months: float = 6.0
    #: Used when an emergency-fund target cannot be derived from spending.
    emergency_fund_target: float | None = None
    spending_categories: list[str] = field(default_factory=lambda: list(DEFAULT_SPENDING_CATEGORIES))
    #: Default assumptions pre-loaded into the projections page.
    default_investment_return: float = 5.0
    default_cash_rate: float = 3.0
    default_inflation: float = 2.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency_symbol": self.currency_symbol,
            "emergency_fund_months": self.emergency_fund_months,
            "emergency_fund_target": self.emergency_fund_target,
            "spending_categories": list(self.spending_categories),
            "default_investment_return": self.default_investment_return,
            "default_cash_rate": self.default_cash_rate,
            "default_inflation": self.default_inflation,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "Settings":
        raw = raw or {}
        target = raw.get("emergency_fund_target")
        return cls(
            currency_symbol=_clean_text(raw.get("currency_symbol"), "£") or "£",
            emergency_fund_months=float(raw.get("emergency_fund_months", 6.0) or 0),
            emergency_fund_target=None if target in (None, "") else _money(target),
            spending_categories=[
                str(c) for c in raw.get("spending_categories") or DEFAULT_SPENDING_CATEGORIES
            ],
            default_investment_return=float(raw.get("default_investment_return", 5.0) or 0),
            default_cash_rate=float(raw.get("default_cash_rate", 3.0) or 0),
            default_inflation=float(raw.get("default_inflation", 2.5) or 0),
        )


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Dataset:
    """Everything the app knows about, loaded once per run."""

    accounts: list[Account] = field(default_factory=list)
    months: list[MonthlyRecord] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)

    def __post_init__(self) -> None:
        self.months = sorted(self.months, key=lambda record: record.month)
        self.accounts = sorted(self.accounts, key=lambda a: (a.sort_order, a.name.lower()))
        self.goals = sorted(self.goals, key=lambda g: (g.sort_order, g.name.lower()))

    # -- lookups -----------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return not self.accounts and not self.months and not self.goals

    @property
    def has_history(self) -> bool:
        return any(record.has_balances for record in self.months)

    @property
    def month_keys(self) -> list[str]:
        return [record.month for record in self.months]

    def account(self, account_id: str) -> Account | None:
        return next((a for a in self.accounts if a.id == account_id), None)

    def account_name(self, account_id: str) -> str:
        found = self.account(account_id)
        return found.name if found else account_id

    def active_accounts(self) -> list[Account]:
        return [a for a in self.accounts if a.active]

    def accounts_in(self, category: str) -> list[Account]:
        return [a for a in self.accounts if a.category == category]

    def record(self, month: str) -> MonthlyRecord | None:
        return next((r for r in self.months if r.month == month), None)

    def records_with_balances(self) -> list[MonthlyRecord]:
        return [r for r in self.months if r.has_balances]

    def records_with_cashflow(self) -> list[MonthlyRecord]:
        return [r for r in self.months if r.has_cashflow]

    def latest_record(self, *, require_balances: bool = False) -> MonthlyRecord | None:
        candidates = self.records_with_balances() if require_balances else self.months
        return candidates[-1] if candidates else None

    def previous_record(self, *, require_balances: bool = False) -> MonthlyRecord | None:
        candidates = self.records_with_balances() if require_balances else self.months
        return candidates[-2] if len(candidates) >= 2 else None

    def years(self) -> list[int]:
        return sorted({record.year for record in self.months})

    def known_spending_categories(self) -> list[str]:
        """Settings categories plus anything already present in the data."""
        seen: list[str] = list(self.settings.spending_categories)
        for record in self.months:
            for name in record.spending_categories:
                if name not in seen:
                    seen.append(name)
        return seen

    def replace_months(self, records: Iterable[MonthlyRecord]) -> None:
        self.months = sorted(records, key=lambda record: record.month)
