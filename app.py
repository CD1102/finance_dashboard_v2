"""Entry point.

Owns page configuration and navigation only. Everything else lives in
``views`` (screens) and ``financelib`` (domain, storage, calculations).
"""

from __future__ import annotations

import streamlit as st

from financelib.calculations import networth
from financelib.formatting import money, month_label, signed_money
from financelib.storage import StorageError
from financelib.ui import components as ui
from financelib.ui.state import bootstrap, load_dataset

bootstrap("Finance")

PAGES = {
    "Overview": [
        st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    ],
    "Track": [
        st.Page("views/monthly.py", title="Monthly record", icon=":material/edit_calendar:"),
        st.Page("views/accounts.py", title="Accounts", icon=":material/account_balance_wallet:"),
        st.Page("views/history.py", title="History", icon=":material/timeline:"),
    ],
    "Plan": [
        st.Page("views/goals.py", title="Goals", icon=":material/flag:"),
        st.Page("views/projections.py", title="Projections", icon=":material/trending_up:"),
    ],
    "Manage": [
        st.Page("views/data.py", title="Data and settings", icon=":material/settings:"),
    ],
}


def _sidebar_summary() -> None:
    """A compact standing summary so net worth is visible from every page."""
    try:
        dataset = load_dataset()
    except StorageError:
        return
    if not dataset.months:
        return

    series = networth.net_worth_series(dataset)
    if not series:
        return

    change = networth.latest_change(series)
    latest = series[-1]

    with st.sidebar:
        st.markdown(
            f"""
<div style="border-top:1px solid var(--border);margin-top:0.6rem;padding-top:0.9rem">
  <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.09em;
              color:var(--muted);font-weight:700">Net worth</div>
  <div style="font-size:1.45rem;font-weight:700;letter-spacing:-0.03em;margin-top:0.2rem;
              font-variant-numeric:tabular-nums">
    {money(latest.total, dataset.settings.currency_symbol)}
  </div>
  <div style="font-size:0.78rem;margin-top:0.2rem;
              color:{'var(--positive)' if (change is None or change.is_increase) else 'var(--negative)'}">
    {signed_money(change.absolute, dataset.settings.currency_symbol) if change else 'First month'}
    <span style="color:var(--muted)"> · {month_label(latest.month)}</span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )


def main() -> None:
    navigation = st.navigation(PAGES, position="sidebar")
    _sidebar_summary()
    navigation.run()


main()
