"""Regenerate the public sample dataset.

The sample set is entirely synthetic and exists so the app has something to
show on first run, and so screenshots and tests never need real figures.
Run with: ``python tools/make_samples.py``
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from financelib.models import (  # noqa: E402
    CASH,
    INVESTMENT,
    LIABILITY,
    PENSION,
    Account,
    Goal,
    MonthlyRecord,
    Settings,
    shift_month,
)
from financelib.storage.base import SCHEMA_VERSION  # noqa: E402

OUTPUT = ROOT / "data" / "samples"
MONTHS = 26
SEED = 20260925

ACCOUNTS = [
    Account(
        id="current_account",
        name="Current account",
        category=CASH,
        provider="High Street Bank",
        purpose="Day to day",
        sort_order=0,
    ),
    Account(
        id="emergency_savings",
        name="Emergency savings",
        category=CASH,
        provider="High Street Bank",
        purpose="Safety net",
        interest_rate=4.1,
        planned_contribution=150,
        emergency_fund=True,
        sort_order=1,
    ),
    Account(
        id="cash_isa",
        name="Cash ISA",
        category=CASH,
        provider="Building Society",
        purpose="House deposit",
        interest_rate=4.5,
        planned_contribution=300,
        isa=True,
        sort_order=2,
    ),
    Account(
        id="stocks_isa",
        name="Stocks & Shares ISA",
        category=INVESTMENT,
        provider="Investment Platform",
        purpose="Long term growth",
        planned_contribution=450,
        isa=True,
        sort_order=3,
    ),
    Account(
        id="lifetime_isa",
        name="Lifetime ISA",
        category=INVESTMENT,
        provider="Investment Platform",
        purpose="House deposit",
        planned_contribution=333,
        isa=True,
        lisa=True,
        sort_order=4,
    ),
    Account(
        id="workplace_pension",
        name="Workplace pension",
        category=PENSION,
        provider="Pension Provider",
        purpose="Retirement",
        planned_contribution=520,
        sort_order=5,
    ),
    Account(
        id="credit_card",
        name="Credit card",
        category=LIABILITY,
        provider="Card Issuer",
        purpose="Cleared monthly",
        sort_order=6,
    ),
]

GOALS = [
    Goal(
        id="house_deposit",
        name="House deposit",
        target_amount=60_000,
        account_ids=["cash_isa", "lifetime_isa"],
        target_date=date(2029, 6, 1),
        description="Deposit and fees for a first home.",
        sort_order=0,
    ),
    Goal(
        id="emergency_fund",
        name="Six months of spending",
        target_amount=13_200,
        account_ids=["emergency_savings"],
        description="Enough set aside to cover half a year without income.",
        sort_order=1,
    ),
    Goal(
        id="quarter_million",
        name="£250k net worth",
        kind="net_worth",
        target_amount=250_000,
        description="A long run marker, no deadline attached.",
        sort_order=2,
    ),
]

CATEGORY_SHARES = {
    "Housing": 0.33,
    "Bills & utilities": 0.11,
    "Food & groceries": 0.16,
    "Transport": 0.10,
    "Subscriptions": 0.03,
    "Shopping": 0.11,
    "Leisure": 0.11,
    "Giving": 0.05,
}


def build_months(rng: random.Random) -> list[MonthlyRecord]:
    end = date(2026, 9, 1)
    start = shift_month(f"{end.year:04d}-{end.month:02d}", -(MONTHS - 1))

    balances = {
        "current_account": 2_400.0,
        "emergency_savings": 5_800.0,
        "cash_isa": 9_200.0,
        "stocks_isa": 18_400.0,
        "lifetime_isa": 11_300.0,
        "workplace_pension": 21_500.0,
        "credit_card": 780.0,
    }

    contributions_plan = {
        "emergency_savings": 150.0,
        "cash_isa": 300.0,
        "stocks_isa": 450.0,
        "lifetime_isa": 333.0,
        "workplace_pension": 520.0,
    }

    income = 3_150.0
    records: list[MonthlyRecord] = []

    for index in range(MONTHS):
        month = shift_month(start, index)

        # An annual pay rise each April keeps the income series interesting.
        if month.endswith("-04") and index > 0:
            income = round(income * rng.uniform(1.03, 1.06), 2)

        spending = round(income * rng.uniform(0.58, 0.74), 2)
        if month.endswith("-12"):
            spending = round(spending * 1.22, 2)  # Christmas

        contributions = {
            key: round(value * rng.uniform(0.97, 1.03), 2)
            for key, value in contributions_plan.items()
        }

        for account_id, amount in contributions.items():
            growth_rate = {
                "stocks_isa": rng.gauss(0.006, 0.026),
                "lifetime_isa": rng.gauss(0.006, 0.024),
                "workplace_pension": rng.gauss(0.005, 0.021),
                "cash_isa": 0.045 / 12,
                "emergency_savings": 0.041 / 12,
            }.get(account_id, 0.0)
            balances[account_id] = round(
                balances[account_id] * (1 + growth_rate) + amount, 2
            )

        surplus = income - spending - sum(contributions.values())
        balances["current_account"] = round(
            max(balances["current_account"] + surplus, 350.0), 2
        )
        balances["credit_card"] = round(rng.uniform(300, 1_250), 2)

        categories = {
            name: round(spending * share * rng.uniform(0.85, 1.15), 2)
            for name, share in CATEGORY_SHARES.items()
        }
        # Make the categories reconcile with the recorded total.
        scale = spending / sum(categories.values())
        categories = {name: round(value * scale, 2) for name, value in categories.items()}

        records.append(
            MonthlyRecord(
                month=month,
                income=round(income, 2),
                spending=spending,
                spending_categories=categories,
                contributions=contributions,
                balances=dict(balances),
            )
        )

    return records


def write(filename: str, key: str, payload) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": "2026-09-25T00:00:00",
        key: payload,
    }
    (OUTPUT / filename).write_text(
        json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    rng = random.Random(SEED)
    write("accounts.json", "accounts", [a.to_dict() for a in ACCOUNTS])
    write("months.json", "months", [r.to_dict() for r in build_months(rng)])
    write("goals.json", "goals", [g.to_dict() for g in GOALS])
    write("settings.json", "settings", Settings().to_dict())
    print(f"Wrote sample data to {OUTPUT}")


if __name__ == "__main__":
    main()
