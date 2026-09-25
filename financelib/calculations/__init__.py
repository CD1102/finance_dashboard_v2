"""Financial calculations.

Split by subject so each module stays readable and independently testable:

- :mod:`networth`     balances, allocation, movement between months
- :mod:`cashflow`     income, spending, savings rate, emergency fund
- :mod:`performance`  contributions versus growth
- :mod:`goals`        progress, required contributions, projected completion
- :mod:`projections`  forward scenarios
- :mod:`taxuk`        ISA and LISA allowances
- :mod:`insights`     plain-English narrative built from the above
"""

from financelib.calculations import (  # noqa: F401
    cashflow,
    goals,
    insights,
    networth,
    performance,
    projections,
    taxuk,
)

__all__ = [
    "cashflow",
    "goals",
    "insights",
    "networth",
    "performance",
    "projections",
    "taxuk",
]
