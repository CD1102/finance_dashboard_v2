"""Accounts — the portfolio list and a drill-down for each account."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from financelib.calculations import networth, performance
from financelib.formatting import money, month_label, percent, signed_money
from financelib.models import ALL_CATEGORIES, CATEGORY_LABELS, Account, slugify
from financelib.ui import charts, components as ui
from financelib.ui.state import commit, confirm_button, load_dataset, period_selector, trim
from financelib.ui.theme import CATEGORY_COLORS


def render() -> None:
    dataset = load_dataset()
    symbol = dataset.settings.currency_symbol

    ui.page_header(
        "Accounts",
        "Every place your money sits, what it holds now, and how it has moved.",
    )

    _manage_bar(dataset)

    if not dataset.accounts:
        ui.empty_state(
            "No accounts yet",
            "Add your first account above. Accounts are just labels for where money "
            "sits — you decide what to track.",
        )
        return

    overview_tab, detail_tab = st.tabs(["All accounts", "Account detail"])

    with overview_tab:
        _overview(dataset, symbol)
    with detail_tab:
        _detail(dataset, symbol)


# ----------------------------------------------------------------------
# Overview
# ----------------------------------------------------------------------


def _overview(dataset, symbol: str) -> None:
    latest = dataset.latest_record(require_balances=True)
    if latest is None:
        ui.empty_state(
            "No balances recorded",
            "Your accounts exist but no month has balances yet.",
        )
        return

    previous = dataset.previous_record(require_balances=True)
    total = networth.net_worth(latest, dataset.accounts) or 1

    ui.caption(f"Balances as at {month_label(latest.month, 'long')}")
    ui.spacer(0.4)

    for category in ALL_CATEGORIES:
        accounts = [a for a in dataset.accounts if a.category == category and a.active]
        if not accounts:
            continue

        subtotal = sum(latest.balances.get(a.id, 0.0) for a in accounts)
        ui.section(
            CATEGORY_LABELS[category],
            f"{money(subtotal, symbol)} · {subtotal / total * 100:.0f}% of net worth",
        )

        columns = st.columns(min(len(accounts), 4))
        for index, account in enumerate(accounts):
            balance = latest.balances.get(account.id)
            before = previous.balances.get(account.id) if previous else None
            delta = (balance - before) if (balance is not None and before is not None) else None

            with columns[index % len(columns)]:
                ui.metric_card(
                    account.name,
                    money(balance, symbol) if balance is not None else "Not recorded",
                    delta=signed_money(delta, symbol) if delta else None,
                    delta_tone="positive" if (delta or 0) >= 0 else "negative",
                    caption=account.purpose or account.provider or "",
                    bar_percent=(balance or 0) / total * 100,
                    bar_color=CATEGORY_COLORS.get(category),
                    muted=balance is None,
                )

    _uncovered_accounts(dataset, latest.month)


def _uncovered_accounts(dataset, month: str) -> None:
    missing = networth.missing_accounts(dataset, month)
    if not missing:
        return
    ui.spacer(0.8)
    ui.note(
        f"No balance recorded for {month_label(month)}: "
        + ", ".join(a.name for a in missing)
        + ". Their last known values are still used in the history.",
        tone="warning",
    )


# ----------------------------------------------------------------------
# Detail
# ----------------------------------------------------------------------


def _detail(dataset, symbol: str) -> None:
    names = {a.name: a.id for a in dataset.accounts}
    chosen = st.selectbox("Account", list(names), key="account_detail_pick")
    account = dataset.account(names[chosen])
    if account is None:
        return

    series = networth.account_series(dataset, account.id)

    head, controls = st.columns([2, 1.4])
    with controls:
        months = period_selector("account_period", default="1Y")

    if not series.points:
        ui.empty_state(
            f"No balances recorded for {account.name}",
            "Record a month that includes this account to see its history.",
        )
        _account_meta(account, symbol)
        return

    change = networth.account_change(dataset, account.id, months)
    latest_balance = series.latest or 0.0

    metrics = st.columns(4)
    with metrics[0]:
        ui.metric_card("Current balance", money(latest_balance, symbol), provenance="recorded")
    with metrics[1]:
        ui.change_metric("Change over period", change, symbol)
    with metrics[2]:
        contributions = sum(
            record.contributions.get(account.id, 0.0) for record in trim(dataset.months, months)
        )
        ui.metric_card(
            "Paid in over period",
            money(contributions, symbol) if contributions else "—",
            caption="From recorded contributions",
            provenance="recorded",
            muted=not contributions,
        )
    with metrics[3]:
        if account.planned_contribution:
            ui.metric_card(
                "Planned monthly",
                money(account.planned_contribution, symbol),
                caption="Your intended amount",
                provenance="assumption",
            )
        elif account.interest_rate is not None:
            ui.metric_card(
                "Stated rate",
                percent(account.interest_rate),
                caption="As recorded on the account",
                provenance="recorded",
            )
        else:
            ui.metric_card("Months tracked", str(len(series.points)), muted=True)

    ui.spacer(0.8)
    with st.container(border=True):
        shown_points = trim(series.points, months)
        trimmed = networth.AccountSeries(account=account, points=shown_points)
        st.plotly_chart(
            charts.account_chart(trimmed, symbol),
            width="stretch",
            config=charts.CHART_CONFIG,
        )

    _account_attribution(dataset, account, months, symbol)
    _account_meta(account, symbol)
    _account_table(dataset, account, months, symbol)


def _account_attribution(dataset, account: Account, months, symbol: str) -> None:
    points = networth.account_series(dataset, account.id).points
    shown = trim(points, months)
    if len(shown) < 2:
        return

    result = performance.attribute_account(dataset, account.id, shown[0][0], shown[-1][0])
    if result is None:
        return

    ui.section("Contributions versus growth")
    if not result.is_complete:
        ui.note(
            f"Growth cannot be separated for this period — {len(result.missing_months)} month(s) "
            "have no contribution recorded. Add them on the Monthly page to unlock this.",
            tone="warning",
        )
        return

    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        with st.container(border=True):
            st.plotly_chart(
                charts.attribution_waterfall(result, symbol),
                width="stretch",
                config=charts.CHART_CONFIG,
            )
    with right:
        with st.container(border=True):
            ui.stat_line(
                [
                    ("You paid in", money(result.contributions, symbol)),
                    ("Growth", signed_money(result.growth, symbol)),
                ]
            )
            ui.spacer(0.7)
            ui.stat_line(
                [
                    ("Return", percent(result.growth_percent)),
                    ("Annualised", percent(result.annualised_percent)),
                ]
            )
            ui.spacer(0.5)
            ui.caption(
                "Return is measured against the starting balance plus half of what you paid "
                "in, which avoids overstating performance when money arrived late in the "
                "period. It is an approximation."
            )


def _account_meta(account: Account, symbol: str) -> None:
    with st.expander("Account details"):
        st.markdown(
            f"**Category** · {CATEGORY_LABELS.get(account.category, account.category)}  \n"
            f"**Provider** · {account.provider or '—'}  \n"
            f"**Purpose** · {account.purpose or '—'}  \n"
            f"**Stated rate** · {percent(account.interest_rate)}  \n"
            f"**Planned monthly contribution** · {money(account.planned_contribution, symbol)}"
        )
        if account.notes:
            st.markdown(f"**Notes** · {account.notes}")
        flags = [
            label
            for flag, label in (
                (account.emergency_fund, "Counts toward emergency fund"),
                (account.lisa, "Lifetime ISA"),
                (account.isa, "Uses ISA allowance"),
                (not account.include_in_net_worth, "Excluded from net worth"),
                (not account.active, "Inactive"),
            )
            if flag
        ]
        if flags:
            st.markdown("**Flags** · " + " · ".join(flags))


def _account_table(dataset, account: Account, months, symbol: str) -> None:
    records = trim([r for r in dataset.months if account.id in r.balances], months)
    if len(records) < 2:
        return

    rows = []
    previous = None
    for record in records:
        balance = record.balances[account.id]
        rows.append(
            {
                "Month": month_label(record.month),
                "Balance": balance,
                "Change": None if previous is None else round(balance - previous, 2),
                "Paid in": record.contributions.get(account.id),
            }
        )
        previous = balance

    with st.expander(f"Monthly figures ({len(rows)} months)"):
        frame = pd.DataFrame(rows).iloc[::-1]
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
            column_config={
                "Balance": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
                "Change": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
                "Paid in": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
            },
        )


# ----------------------------------------------------------------------
# Management
# ----------------------------------------------------------------------


def _manage_bar(dataset) -> None:
    add, edit, _ = st.columns([1, 1, 3])

    with add:
        with st.popover("Add account", width="stretch"):
            _account_form(dataset, None)

    with edit:
        if dataset.accounts:
            with st.popover("Edit accounts", width="stretch"):
                names = {a.name: a.id for a in dataset.accounts}
                picked = st.selectbox("Account to edit", list(names), key="account_edit_pick")
                _account_form(dataset, dataset.account(names[picked]))

    ui.spacer(0.5)


def _account_form(dataset, account: Account | None) -> None:
    editing = account is not None
    prefix = f"account_form_{account.id if account else 'new'}"

    with st.form(f"{prefix}_form"):
        name = st.text_input("Name", value=account.name if account else "")
        category = st.selectbox(
            "Category",
            ALL_CATEGORIES,
            index=ALL_CATEGORIES.index(account.category) if account else 1,
            format_func=lambda key: CATEGORY_LABELS[key],
        )

        left, right = st.columns(2)
        provider = left.text_input("Provider", value=account.provider if account else "")
        purpose = right.text_input(
            "Purpose",
            value=account.purpose if account else "",
            placeholder="e.g. house deposit",
        )

        rate_col, contribution_col = st.columns(2)
        rate = rate_col.number_input(
            "Stated annual rate (%)",
            value=float(account.interest_rate) if account and account.interest_rate else 0.0,
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            help="Informational only. It is never used to invent balances.",
        )
        planned = contribution_col.number_input(
            "Planned monthly contribution",
            value=float(account.planned_contribution) if account else 0.0,
            min_value=0.0,
            step=25.0,
            help="Your intention. Actual amounts are recorded each month.",
        )

        flags = st.columns(3)
        emergency = flags[0].checkbox(
            "Emergency fund", value=account.emergency_fund if account else False
        )
        is_lisa = flags[1].checkbox("Lifetime ISA", value=account.lisa if account else False)
        is_isa = flags[2].checkbox("Uses ISA allowance", value=account.isa if account else False)

        more = st.columns(2)
        in_net_worth = more[0].checkbox(
            "Include in net worth", value=account.include_in_net_worth if account else True
        )
        active = more[1].checkbox("Active", value=account.active if account else True)

        notes = st.text_area("Notes", value=account.notes if account else "", height=70)

        submitted = st.form_submit_button(
            "Save changes" if editing else "Add account",
            type="primary",
            width="stretch",
        )

    if submitted:
        cleaned = name.strip()
        if not cleaned:
            st.error("Give the account a name.")
            return

        new_id = account.id if account else slugify(cleaned)
        if not editing and dataset.account(new_id) is not None:
            st.error(f"An account called '{cleaned}' already exists.")
            return

        updated = Account(
            id=new_id,
            name=cleaned,
            category=category,
            provider=provider.strip(),
            purpose=purpose.strip(),
            interest_rate=rate or None,
            planned_contribution=planned,
            emergency_fund=emergency,
            lisa=is_lisa,
            isa=is_isa or is_lisa,
            include_in_net_worth=in_net_worth,
            active=active,
            notes=notes.strip(),
            sort_order=account.sort_order if account else len(dataset.accounts),
        )
        if commit(
            lambda repo: repo.upsert_account(updated),
            f"{'Updated' if editing else 'Added'} {cleaned}",
        ):
            st.rerun()

    if editing and account is not None:
        ui.spacer(0.4)
        ui.caption(
            "Deleting removes the account and clears it from your goals. Recorded balances "
            "are kept unless you tick the box."
        )
        purge = st.checkbox("Also delete its recorded balances", key=f"{prefix}_purge")
        if confirm_button("Delete account", key=f"{prefix}_delete"):
            if commit(
                lambda repo: repo.delete_account(account.id, purge_balances=purge),
                f"Deleted {account.name}",
            ):
                st.rerun()


render()
