"""Goals — targets, progress and what it would take to hit them."""

from __future__ import annotations

from datetime import date

import streamlit as st

from financelib.calculations import goals as goal_calc
from financelib.calculations.taxuk import current_tax_year, isa_status, lisa_status
from financelib.formatting import date_label, duration_label, money, percent
from financelib.models import ACCUMULATION, GOAL_KINDS, NET_WORTH_GOAL, SPEND_DOWN, Goal, slugify
from financelib.ui import charts, components as ui
from financelib.ui.state import commit, confirm_button, load_dataset

KIND_LABELS = {
    ACCUMULATION: "Build up a balance",
    NET_WORTH_GOAL: "Reach a net worth",
    SPEND_DOWN: "Budget to spend",
}

KIND_HELP = {
    ACCUMULATION: "Progress is the combined balance of the accounts you choose.",
    NET_WORTH_GOAL: "Progress is your total net worth.",
    SPEND_DOWN: "Progress is how much of the budget you have used.",
}


def render() -> None:
    dataset = load_dataset()
    symbol = dataset.settings.currency_symbol

    ui.page_header(
        "Goals",
        "What you are working toward, how far along you are, and what the pace implies.",
    )

    _manage_bar(dataset)

    progress = goal_calc.evaluate_all(dataset)
    if not progress:
        ui.empty_state(
            "No goals yet",
            "A goal can be a house deposit, an emergency fund, a net worth target — "
            "anything with a number attached.",
        )
        _allowances(dataset, symbol)
        return

    _cards(progress, symbol)
    _comparison(progress, symbol)
    _detail(dataset, progress, symbol)
    _allowances(dataset, symbol)


# ----------------------------------------------------------------------
# Display
# ----------------------------------------------------------------------


def _cards(progress, symbol: str) -> None:
    ui.spacer(0.4)
    per_row = 3
    for start in range(0, len(progress), per_row):
        chunk = progress[start : start + per_row]
        columns = st.columns(per_row)
        for column, item in zip(columns, chunk):
            with column:
                ui.goal_card(item, symbol)


def _comparison(progress, symbol: str) -> None:
    measurable = [p for p in progress if p.target > 0]
    if len(measurable) < 2:
        return

    ui.section("Progress side by side")
    with st.container(border=True):
        st.plotly_chart(
            charts.goal_progress_chart(
                [p.goal.name for p in measurable],
                [p.current for p in measurable],
                [p.target for p in measurable],
                symbol,
            ),
            width="stretch",
            config=charts.CHART_CONFIG,
        )


def _detail(dataset, progress, symbol: str) -> None:
    names = {p.goal.name: p for p in progress}
    ui.section("Goal detail")
    chosen = st.selectbox("Goal", list(names), key="goal_detail_pick")
    item = names[chosen]

    if item.goal.description:
        ui.caption(item.goal.description)
        ui.spacer(0.4)

    columns = st.columns(4)
    with columns[0]:
        ui.metric_card(
            "Progress",
            percent(item.raw_percent, 0),
            caption=f"{money(item.current, symbol)} of {money(item.target, symbol)}",
            bar_percent=item.percent,
            provenance="derived",
        )
    with columns[1]:
        ui.metric_card(
            "Still needed",
            money(item.remaining, symbol),
            caption="Target reached" if item.is_complete else "To reach the target",
            provenance="derived",
            muted=item.is_complete,
        )
    with columns[2]:
        if item.required_monthly is not None:
            ui.metric_card(
                "Required each month",
                money(item.required_monthly, symbol),
                caption=f"To hit {date_label(item.goal.target_date)}",
                provenance="derived",
                delta=(
                    f"{duration_label(item.months_remaining)} left"
                    if item.months_remaining and item.months_remaining > 0
                    else "Deadline passed"
                ),
                delta_tone="neutral" if (item.months_remaining or 0) > 0 else "negative",
            )
        else:
            ui.metric_card(
                "Required each month",
                "—",
                caption="Set a target date to calculate this",
                muted=True,
            )
    with columns[3]:
        if item.projected_completion and not item.is_complete:
            ui.metric_card(
                "Projected completion",
                item.projected_completion.strftime("%b %Y"),
                caption=f"Based on {item.projection_basis}",
                provenance="assumption",
            )
        elif item.is_complete:
            ui.metric_card("Status", "Reached", provenance="derived")
        else:
            ui.metric_card(
                "Projected completion",
                "—",
                caption="Needs a contribution rate to estimate",
                muted=True,
            )

    ui.spacer(0.7)
    with st.container(border=True):
        pairs = [
            ("Measured by", KIND_LABELS.get(item.goal.kind, item.goal.kind)),
            (
                "Recent contributions",
                money(item.observed_monthly, symbol) + " / mo"
                if item.observed_monthly
                else "None recorded",
            ),
            (
                "Your assumption",
                money(item.assumed_monthly, symbol) + " / mo"
                if item.assumed_monthly is not None
                else "Not set",
            ),
            ("Target date", date_label(item.goal.target_date)),
        ]
        ui.stat_line(pairs)

        if item.goal.kind == ACCUMULATION and item.goal.account_ids:
            ui.spacer(0.6)
            ui.caption(
                "Counting: "
                + ", ".join(dataset.account_name(a) for a in item.goal.account_ids)
            )

        if item.monthly_shortfall:
            ui.spacer(0.5)
            ui.note(
                f"Paying in {money(item.monthly_shortfall, symbol)} more each month would keep "
                "this on schedule.",
                tone="warning",
            )

        ui.spacer(0.5)
        ui.caption(
            "Projected dates assume the contribution rate continues unchanged and ignore "
            "investment growth. They are arithmetic, not a forecast."
        )


# ----------------------------------------------------------------------
# Tax allowances
# ----------------------------------------------------------------------


def _allowances(dataset, symbol: str) -> None:
    lisa = lisa_status(dataset)
    isa = isa_status(dataset)
    if not lisa and not isa:
        return

    tax_year = current_tax_year()
    ui.section(
        f"Tax year allowances · {tax_year.label}",
        f"{tax_year.months_remaining} month(s) left to use them.",
    )

    columns = st.columns(3)

    if isa:
        with columns[0]:
            ui.metric_card(
                "ISA allowance used",
                money(isa.used, symbol),
                caption=f"{money(isa.remaining, symbol)} of {money(isa.limit, symbol)} left",
                bar_percent=isa.percent_used,
                provenance="derived",
            )

    if lisa:
        with columns[1]:
            ui.metric_card(
                "LISA paid in",
                money(lisa.allowance.used, symbol),
                caption=f"{money(lisa.allowance.remaining, symbol)} of "
                f"{money(lisa.allowance.limit, symbol)} left",
                bar_percent=lisa.allowance.percent_used,
                provenance="derived",
            )
        with columns[2]:
            monthly = lisa.allowance.monthly_to_max_out(tax_year.months_remaining)
            ui.metric_card(
                "Bonus earned",
                money(lisa.bonus_earned, symbol),
                caption=(
                    f"{money(lisa.bonus_available, symbol)} more available"
                    + (f" · {money(monthly, symbol)}/mo to max out" if monthly else "")
                ),
                delta_tone="positive",
                provenance="derived",
            )

    ui.spacer(0.4)
    ui.caption(
        "Allowance use is counted from the contributions you record, month by month. "
        "April is counted in the tax year it begins."
    )


# ----------------------------------------------------------------------
# Management
# ----------------------------------------------------------------------


def _manage_bar(dataset) -> None:
    add, edit, _ = st.columns([1, 1, 3])

    with add:
        with st.popover("Add goal", width="stretch"):
            _goal_form(dataset, None)

    with edit:
        if dataset.goals:
            with st.popover("Edit goals", width="stretch"):
                names = {g.name: g for g in dataset.goals}
                picked = st.selectbox("Goal to edit", list(names), key="goal_edit_pick")
                _goal_form(dataset, names[picked])

    ui.spacer(0.4)


def _goal_form(dataset, goal: Goal | None) -> None:
    editing = goal is not None
    prefix = f"goal_form_{goal.id if goal else 'new'}"
    account_names = {a.name: a.id for a in dataset.accounts}

    with st.form(f"{prefix}_form"):
        name = st.text_input("Name", value=goal.name if goal else "")
        kind = st.selectbox(
            "How is progress measured?",
            GOAL_KINDS,
            index=GOAL_KINDS.index(goal.kind) if goal else 0,
            format_func=lambda key: KIND_LABELS[key],
            help="\n\n".join(f"**{KIND_LABELS[k]}** — {KIND_HELP[k]}" for k in GOAL_KINDS),
        )

        target_col, date_col = st.columns(2)
        target = target_col.number_input(
            "Target amount",
            value=float(goal.target_amount) if goal else 0.0,
            min_value=0.0,
            step=500.0,
        )
        has_deadline = date_col.checkbox(
            "Has a target date", value=bool(goal and goal.target_date), key=f"{prefix}_deadline"
        )
        target_date = None
        if has_deadline:
            target_date = date_col.date_input(
                "Target date",
                value=goal.target_date if goal and goal.target_date else date.today(),
                key=f"{prefix}_date",
            )

        selected_accounts: list[str] = []
        if kind == ACCUMULATION:
            defaults = (
                [name for name, id_ in account_names.items() if goal and id_ in goal.account_ids]
                if goal
                else []
            )
            picked = st.multiselect(
                "Accounts that count toward it",
                list(account_names),
                default=defaults,
                key=f"{prefix}_accounts",
            )
            selected_accounts = [account_names[n] for n in picked]

        spent = 0.0
        if kind == SPEND_DOWN:
            spent = st.number_input(
                "Spent so far",
                value=float(goal.spent) if goal else 0.0,
                min_value=0.0,
                step=100.0,
            )

        use_assumption = st.checkbox(
            "Assume a monthly contribution",
            value=bool(goal and goal.monthly_contribution is not None),
            key=f"{prefix}_assume",
            help="Used only to estimate a completion date. Leave off to use your "
            "recorded contributions instead.",
        )
        monthly = None
        if use_assumption:
            monthly = st.number_input(
                "Assumed monthly contribution",
                value=float(goal.monthly_contribution) if goal and goal.monthly_contribution else 0.0,
                min_value=0.0,
                step=50.0,
            )

        description = st.text_area(
            "Description", value=goal.description if goal else "", height=70
        )
        active = st.checkbox("Active", value=goal.active if goal else True)

        submitted = st.form_submit_button(
            "Save changes" if editing else "Add goal", type="primary", width="stretch"
        )

    if submitted:
        cleaned = name.strip()
        if not cleaned:
            st.error("Give the goal a name.")
            return
        if target <= 0:
            st.error("Set a target amount above zero, otherwise progress cannot be shown.")
            return
        if kind == ACCUMULATION and not selected_accounts:
            st.error("Choose at least one account, or pick a different way to measure progress.")
            return

        new_id = goal.id if goal else slugify(cleaned)
        if not editing and any(g.id == new_id for g in dataset.goals):
            st.error(f"A goal called '{cleaned}' already exists.")
            return

        updated = Goal(
            id=new_id,
            name=cleaned,
            target_amount=target,
            kind=kind,
            account_ids=selected_accounts,
            target_date=target_date,
            description=description.strip(),
            monthly_contribution=monthly,
            spent=spent,
            active=active,
            sort_order=goal.sort_order if goal else len(dataset.goals),
        )
        if commit(
            lambda repo: repo.upsert_goal(updated),
            f"{'Updated' if editing else 'Added'} {cleaned}",
        ):
            st.rerun()

    if editing and goal is not None:
        ui.spacer(0.4)
        if confirm_button("Delete goal", key=f"{prefix}_delete"):
            if commit(lambda repo: repo.delete_goal(goal.id), f"Deleted {goal.name}"):
                st.rerun()


render()
