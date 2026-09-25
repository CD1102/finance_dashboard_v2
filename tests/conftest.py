"""Shared fixtures.

The builders here keep each test focused on the behaviour it is checking
rather than on constructing data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financelib.models import (  # noqa: E402
    CASH,
    INVESTMENT,
    LIABILITY,
    PENSION,
    Account,
    Dataset,
    Goal,
    MonthlyRecord,
)
from financelib.storage.json_store import JsonRepository  # noqa: E402


@pytest.fixture
def accounts() -> list[Account]:
    return [
        Account(id="isa", name="S&S ISA", category=INVESTMENT, isa=True),
        Account(id="savings", name="Savings", category=CASH, emergency_fund=True),
        Account(id="pension", name="Pension", category=PENSION),
    ]


@pytest.fixture
def dataset(accounts) -> Dataset:
    """Three tidy months with balances, cash flow and contributions."""
    return Dataset(
        accounts=accounts,
        months=[
            MonthlyRecord(
                month="2026-01",
                income=3000,
                spending=2000,
                contributions={"isa": 400, "savings": 200, "pension": 300},
                balances={"isa": 10_000, "savings": 5_000, "pension": 20_000},
            ),
            MonthlyRecord(
                month="2026-02",
                income=3000,
                spending=2100,
                contributions={"isa": 400, "savings": 200, "pension": 300},
                balances={"isa": 10_600, "savings": 5_200, "pension": 20_400},
            ),
            MonthlyRecord(
                month="2026-03",
                income=3200,
                spending=1900,
                contributions={"isa": 400, "savings": 200, "pension": 300},
                balances={"isa": 11_200, "savings": 5_400, "pension": 20_900},
            ),
        ],
        goals=[
            Goal(
                id="house",
                name="House deposit",
                target_amount=20_000,
                account_ids=["savings", "isa"],
            )
        ],
    )


@pytest.fixture
def empty_dataset() -> Dataset:
    return Dataset()


@pytest.fixture
def repo(tmp_path) -> JsonRepository:
    return JsonRepository(tmp_path / "data")


def record(month: str, **kwargs) -> MonthlyRecord:
    return MonthlyRecord(month=month, **kwargs)


def liability_account() -> Account:
    return Account(id="card", name="Credit card", category=LIABILITY)
