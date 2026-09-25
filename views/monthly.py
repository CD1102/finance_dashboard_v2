"""Monthly record — one snapshot per month, replacing the spreadsheet row."""

from __future__ import annotations

from datetime import date

import streamlit as st

from financelib.calculations import cashflow, networth
from financelib.formatting import money, month_label, percent, signed_money
from financelib.models import CATEGORY_LABELS, MonthlyRecord, normalise_month, shift_month
from financelib.ui import components as ui
from financelib.ui.state import commit, confirm_button, load_dataset


def render() -> None:
    dataset = load_dataset()
    symbol = dataset.settings.currency_symbol

    ui.page_header(
        "Monthly record",
        "One row a month: what came in, what went out, what you paid in, and what "
        "everything was worth at the end.",
    )

    if not dataset.accounts:
        ui.empty_state(
            "Add your accounts first",
            "Balances are recorded per account, so there needs to be at least one.",
        )
        st.page_link("views/accounts.py", label="Go to accounts", icon=":material/arrow_forward:")
        return

    month = _month_picker(dataset)
    existing = dataset.record(month)

    if existing is not None:
        ui.note(f"{month_label(month, 'long')} is already recorded. Editing will update it.")
    ui.spacer(0.6)

    values = _entry_form(dataset, month, existing, symbol)
    _live_summary(dataset, month, values, symbol)
    _actions(dataset, month, values, existing)
    _recent_months(dataset, symbol)


# ----------------------------------------------------------------------
# Month selection
# ----------------------------------------------------------------------


def _month_picker(dataset) -> str:
    today = date.today()
    current = normalise_month(today)

    # Offer the last two years plus anything already recorded, newest first.
    candidates = {shift_month(current, -offset) for offset in range(24)}
    candidates |= set(dataset.month_keys)
    options = sorted(candidates, reverse=True)

    default = dataset.months[-1].month if dataset.months else current
    if st.session_state.get("monthly_pick") not in options:
        st.session_state["monthly_pick"] = default if default in options else options[0]

    picker, status = st.columns([1, 2])
    with picker:
        month = st.selectbox(
            "Month",
            options,
            format_func=lambda key: month_label(key, "long"),
            key="monthly_pick",
        )
    with status:
        recorded = set(dataset.month_keys)
        ui.spacer(1.7)
        ui.caption(
            f"{len(recorded)} month(s) recorded"
            + (f" · {month_label(min(recorded))} to {month_label(max(recorded))}" if recorded else "")
        )
    return month


# ----------------------------------------------------------------------
# Entry
# ----------------------------------------------------------------------


def _number(label: str, key: str, value: float | None, **kwargs) -> float | None:
    """Number input that preserves the difference between zero and blank."""
    raw = st.number_input(
        label,
        value=float(value) if value is not None else None,
        step=kwargs.pop("step", 50.0),
        format="%.2f",
        placeholder="Not recorded",
        key=key,
        **kwargs,
    )
    return None if raw is None else round(float(raw), 2)


def _entry_form(dataset, month: str, existing: MonthlyRecord | None, symbol: str) -> dict:
    prior = _previous_record(dataset, month)
    income_col, spending_col, contribution_col = st.columns(3, gap="medium")

    with income_col:
        with st.container(border=True):
            ui.caption("Income and spending")
            income = _number(
                f"Total income ({symbol})",
                f"income_{month}",
                existing.income if existing else None,
                min_value=0.0,
            )
            spending = _number(
                f"Total spending ({symbol})",
                f"spending_{month}",
                existing.spending if existing else None,
                min_value=0.0,
            )
            if prior and prior.income and income is None:
                ui.caption(f"Last month: {money(prior.income, symbol)} in")

    with spending_col:
        with st.container(border=True):
            ui.caption("Spending breakdown · optional")
            categories: dict[str, float] = {}
            with st.expander(
                "Split by category",
                expanded=bool(existing and existing.spending_categories),
            ):
                for name in dataset.known_spending_categories():
                    amount = _number(
                        name,
                        f"cat_{month}_{name}",
                        existing.spending_categories.get(name) if existing else None,
                        min_value=0.0,
                        step=25.0,
                    )
                    if amount is not None:
                        categories[name] = amount

            if categories:
                total = round(sum(categories.values()), 2)
                ui.stat_line([("Categories total", money(total, symbol))])
                if spending is not None and abs(total - spending) > 1:
                    ui.note(
                        f"That is {money(abs(total - spending), symbol)} "
                        f"{'more' if total > spending else 'less'} than your total spending.",
                        tone="warning",
                    )
            else:
                ui.caption(
                    "Leave this alone if you only track a single spending total. "
                    "Categories are entirely optional."
                )

    with contribution_col:
        with st.container(border=True):
            ui.caption("Paid into accounts")
            contributions: dict[str, float] = {}
            for account in dataset.active_accounts():
                if account.is_liability:
                    continue
                default = None
                if existing:
                    default = existing.contributions.get(account.id)
                amount = _number(
                    account.name,
                    f"contrib_{month}_{account.id}",
                    default,
                    min_value=0.0,
                    step=25.0,
                )
                if amount is not None:
                    contributions[account.id] = amount
            ui.caption(
                "Recording this is what lets the app separate growth from money you added."
            )

    ui.section("Closing balances", "What each account was worth at the end of the month.")

    balances: dict[str, float] = {}
    accounts = dataset.active_accounts()
    columns = st.columns(min(len(accounts), 4), gap="medium")
    for index, account in enumerate(accounts):
        default = None
        if existing:
            default = existing.balances.get(account.id)
        if default is None and prior:
            default = prior.balances.get(account.id)

        with columns[index % len(columns)]:
            amount = _number(
                f"{account.name}",
                f"balance_{month}_{account.id}",
                default,
                step=100.0,
                help=CATEGORY_LABELS.get(account.category),
            )
            if amount is not None:
                balances[account.id] = amount
            if prior and account.id in prior.balances:
                before = prior.balances[account.id]
                if amount is not None and amount != before:
                    ui.caption(f"{signed_money(amount - before, symbol)} vs last month")
                else:
                    ui.caption(f"Last month {money(before, symbol)}")

    note = st.text_input(
        "Note", value=existing.note if existing else "", placeholder="Anything worth remembering"
    )

    return {
        "income": income,
        "spending": spending,
        "spending_categories": categories,
        "contributions": contributions,
        "balances": balances,
        "note": note.strip(),
    }


def _previous_record(dataset, month: str) -> MonthlyRecord | None:
    earlier = [record for record in dataset.months if record.month < month]
    return earlier[-1] if earlier else None


# ----------------------------------------------------------------------
# Live summary
# ----------------------------------------------------------------------


def _live_summary(dataset, month: str, values: dict, symbol: str) -> None:
    draft = MonthlyRecord(
        month=month,
        income=values["income"],
        spending=values["spending"],
        spending_categories=values["spending_categories"],
        contributions=values["contributions"],
        balances=values["balances"],
    )
    summary = cashflow.summarise_month(draft)

    ui.section("This month works out as", "Updates as you type. Nothing is saved yet.")
    columns = st.columns(4)

    with columns[0]:
        ui.metric_card(
            "Net worth",
            money(networth.net_worth(draft, dataset.accounts), symbol)
            if draft.balances
            else "—",
            caption=f"{len(draft.balances)} of {len(dataset.active_accounts())} accounts",
            muted=not draft.balances,
            provenance="derived",
        )

    with columns[1]:
        prior = _previous_record(dataset, month)
        if prior and prior.balances and draft.balances:
            movement = networth.net_worth(draft, dataset.accounts) - networth.net_worth(
                prior, dataset.accounts
            )
            ui.metric_card(
                "Change on last month",
                signed_money(movement, symbol),
                delta_tone="positive" if movement >= 0 else "negative",
                caption=f"vs {month_label(prior.month)}",
                provenance="derived",
            )
        else:
            ui.metric_card("Change on last month", "—", caption="No earlier balances", muted=True)

    with columns[2]:
        ui.metric_card(
            "Surplus",
            money(summary.surplus, symbol) if summary.surplus is not None else "—",
            caption="Income less spending",
            muted=summary.surplus is None,
            provenance="derived",
        )

    with columns[3]:
        ui.metric_card(
            "Savings rate",
            percent(summary.savings_rate, 0) if summary.savings_rate is not None else "—",
            caption=(
                f"Paid in {money(summary.contributions, symbol)}"
                if summary.contributions
                else "Needs income and spending"
            ),
            bar_percent=summary.savings_rate if summary.savings_rate is not None else None,
            muted=summary.savings_rate is None,
            provenance="derived",
        )


# ----------------------------------------------------------------------
# Actions
# ----------------------------------------------------------------------


def _actions(dataset, month: str, values: dict, existing: MonthlyRecord | None) -> None:
    ui.spacer(0.8)
    save, delete, _ = st.columns([1.2, 1, 3])

    record = MonthlyRecord(
        month=month,
        income=values["income"],
        spending=values["spending"],
        spending_categories=values["spending_categories"],
        contributions=values["contributions"],
        balances=values["balances"],
        note=values["note"],
    )

    with save:
        if st.button(
            "Save month", type="primary", width="stretch", disabled=record.is_empty
        ):
            if commit(
                lambda repo: repo.upsert_month(record),
                f"Saved {month_label(month, 'long')}",
            ):
                st.rerun()

    with delete:
        if existing is not None:
            if confirm_button("Delete month", key=f"delete_month_{month}"):
                if commit(
                    lambda repo: repo.delete_month(month),
                    f"Deleted {month_label(month, 'long')}",
                ):
                    st.rerun()

    if record.is_empty:
        ui.note("Enter at least one figure before saving.", tone="warning")


# ----------------------------------------------------------------------
# Recent months
# ----------------------------------------------------------------------


def _recent_months(dataset, symbol: str) -> None:
    if not dataset.months:
        return

    ui.section("Recently recorded")
    recent = dataset.months[-6:][::-1]

    for record in recent:
        summary = cashflow.summarise_month(record)
        columns = st.columns([1.3, 1, 1, 1, 1])
        columns[0].markdown(f"**{month_label(record.month, 'long')}**")
        columns[1].markdown(
            f"<span style='color:var(--muted)'>Net worth</span><br>"
            f"{money(networth.net_worth(record, dataset.accounts), symbol) if record.balances else '—'}",
            unsafe_allow_html=True,
        )
        columns[2].markdown(
            f"<span style='color:var(--muted)'>Income</span><br>{money(summary.income, symbol)}",
            unsafe_allow_html=True,
        )
        columns[3].markdown(
            f"<span style='color:var(--muted)'>Spending</span><br>{money(summary.spending, symbol)}",
            unsafe_allow_html=True,
        )
        columns[4].markdown(
            f"<span style='color:var(--muted)'>Saved</span><br>"
            f"{percent(summary.savings_rate, 0) if summary.savings_rate is not None else '—'}",
            unsafe_allow_html=True,
        )


render()
