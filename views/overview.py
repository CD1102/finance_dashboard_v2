"""Financial overview — the page that answers "how am I doing?" at a glance."""

from __future__ import annotations

import streamlit as st

from financelib.calculations import cashflow, goals, insights, networth, performance, projections
from financelib.calculations.taxuk import isa_status, lisa_status
from financelib.formatting import money, month_label, percent, signed_money
from financelib.models import CASH, INVESTMENT, PENSION
from financelib.ui import charts, components as ui
from financelib.ui.state import load_dataset, period_selector, sample_data_button, trim
from financelib.ui.theme import CATEGORY_COLORS


def render() -> None:
    dataset = load_dataset()
    symbol = dataset.settings.currency_symbol

    ui.page_header(
        "Financial overview",
        "Where you stand today, how you got here, and where the current pace leads.",
    )

    if not dataset.accounts:
        _first_run()
        return

    series = networth.net_worth_series(dataset)
    if not series:
        _no_history()
        return

    _hero(dataset, series, symbol)
    _headline_metrics(dataset, series, symbol)
    _trend_and_allocation(dataset, series, symbol)
    _this_month(dataset, symbol)
    _goals(dataset, symbol)
    _position(dataset, symbol)


# ----------------------------------------------------------------------
# Empty states
# ----------------------------------------------------------------------


def _first_run() -> None:
    ui.empty_state(
        "Let's set up your accounts",
        "Add the accounts you want to track — current account, savings, ISA, pension, "
        "anything else. Once they exist you can record your first month, or import "
        "years of history from a spreadsheet.",
    )
    ui.spacer(0.8)
    left, middle, right, _ = st.columns([1, 1, 1, 1.4])
    left.page_link("views/accounts.py", label="Add accounts", icon=":material/add:")
    middle.page_link("views/data.py", label="Import a spreadsheet", icon=":material/upload:")
    with right:
        sample_data_button("overview_samples", "Explore with sample data")
    ui.spacer(0.4)
    ui.caption("Sample data is entirely invented and can be cleared at any time.")


def _no_history() -> None:
    ui.empty_state(
        "No balances recorded yet",
        "Your accounts are set up. Record this month's balances to start building "
        "your net worth history.",
    )
    ui.spacer(0.8)
    left, _ = st.columns([1, 3])
    left.page_link("views/monthly.py", label="Record a month", icon=":material/edit_calendar:")


# ----------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------


def _hero(dataset, series, symbol: str) -> None:
    latest = series[-1]
    change = networth.latest_change(series)

    note = f"As at {month_label(latest.month, 'long')}"
    if latest.liabilities:
        note += f" · {money(latest.assets, symbol)} assets less {money(latest.liabilities, symbol)} owed"

    ui.hero("Total net worth", money(latest.total, symbol), change, note, symbol)


def _headline_metrics(dataset, series, symbol: str) -> None:
    ui.spacer(0.9)
    latest = series[-1]
    totals = latest.by_category
    total = latest.total or 1

    previous = series[-2].by_category if len(series) >= 2 else {}
    summary = cashflow.summarise_month(dataset.months[-1]) if dataset.months else None

    columns = st.columns(4)

    def category_card(column, key: str, label: str) -> None:
        amount = totals.get(key, 0.0)
        delta = amount - previous.get(key, amount) if previous else None
        with column:
            ui.metric_card(
                label,
                money(amount, symbol),
                delta=signed_money(delta, symbol) if delta else None,
                delta_tone="positive" if (delta or 0) >= 0 else "negative",
                caption=f"{amount / total * 100:.0f}% of net worth" if total else "",
                bar_percent=amount / total * 100 if total else 0,
                bar_color=CATEGORY_COLORS.get(key),
                provenance="recorded",
            )

    category_card(columns[0], INVESTMENT, "Investments")
    category_card(columns[1], CASH, "Cash & savings")
    category_card(columns[2], PENSION, "Pension")

    with columns[3]:
        if summary and summary.savings_rate is not None:
            ui.metric_card(
                "Savings rate",
                percent(summary.savings_rate, 0),
                caption=f"{month_label(summary.month)} · kept "
                f"{money((summary.income or 0) - (summary.spending or 0), symbol)}",
                bar_percent=max(min(summary.savings_rate, 100), 0),
                provenance="derived",
            )
        else:
            # Without income there is no savings rate, so show the next most
            # useful thing rather than an empty card.
            average = cashflow.average_monthly_contributions(dataset, months=6)
            if average is not None:
                ui.metric_card(
                    "Average contributions",
                    money(average, symbol),
                    caption="Per month over the last 6 months",
                    provenance="derived",
                )
            else:
                ui.metric_card(
                    "Savings rate",
                    "—",
                    caption="Record income and spending to see this",
                    muted=True,
                )


def _trend_and_allocation(dataset, series, symbol: str) -> None:
    ui.section("Net worth over time", "Every month you have recorded balances for.")

    left, right = st.columns([1.7, 1], gap="medium")

    with left:
        with st.container(border=True):
            head, control = st.columns([1, 1.4])
            with head:
                ui.caption("Tracked net worth")
            with control:
                months = period_selector("overview_period", default="1Y")

            shown = trim(series, months)
            if len(shown) < 2:
                ui.empty_state(
                    "Not enough history for this period",
                    "Choose a longer period, or record another month.",
                )
            else:
                st.plotly_chart(
                    charts.net_worth_chart(shown, symbol),
                    width="stretch",
                    config=charts.CHART_CONFIG,
                )
                change = networth.change_over(series, months)
                if change is not None:
                    pace = change.average_per_month
                    ui.stat_line(
                        [
                            ("Change", signed_money(change.absolute, symbol)),
                            ("Percent", percent(change.percent) if change.percent else "—"),
                            ("Per month", signed_money(pace, symbol) if pace else "—"),
                            ("Months", str(len(shown))),
                        ]
                    )

    with right:
        with st.container(border=True):
            ui.caption("Where it sits")
            allocation = networth.allocation(dataset)
            if not allocation:
                ui.empty_state("No balances recorded")
            else:
                st.plotly_chart(
                    charts.allocation_donut(
                        allocation, CATEGORY_COLORS, money(series[-1].total, symbol)
                    ),
                    width="stretch",
                    config=charts.CHART_CONFIG,
                )
                ui.allocation_rows(allocation, CATEGORY_COLORS, symbol)


def _this_month(dataset, symbol: str) -> None:
    latest = dataset.months[-1] if dataset.months else None
    if latest is None:
        return

    ui.section(
        f"{month_label(latest.month, 'long')}",
        "What happened over the most recent month you recorded.",
    )

    left, right = st.columns([1, 1.25], gap="medium")

    with left:
        with st.container(border=True):
            summary = cashflow.summarise_month(latest)
            if summary.has_cashflow:
                rows = [
                    ("Income", summary.income, "positive"),
                    ("Spending", -(summary.spending or 0), "negative"),
                    ("Paid into accounts", summary.contributions, "neutral"),
                    ("Left over", summary.unallocated, "neutral"),
                ]
                for label, value, tone in rows:
                    metric, amount = st.columns([2, 1])
                    metric.markdown(f"<div style='padding:0.35rem 0'>{label}</div>", unsafe_allow_html=True)
                    colour = {
                        "positive": "var(--positive)",
                        "negative": "var(--negative)",
                    }.get(tone, "var(--text)")
                    amount.markdown(
                        f"<div style='padding:0.35rem 0;text-align:right;font-weight:650;"
                        f"font-variant-numeric:tabular-nums;color:{colour}'>"
                        f"{money(value, symbol) if value is not None else '—'}</div>",
                        unsafe_allow_html=True,
                    )
                if summary.savings_rate is not None:
                    ui.rule()
                    ui.stat_line(
                        [
                            ("Savings rate", percent(summary.savings_rate, 0)),
                            (
                                "Into accounts",
                                percent(summary.contribution_rate, 0)
                                if summary.contribution_rate is not None
                                else "—",
                            ),
                        ]
                    )
            else:
                ui.empty_state(
                    "No income or spending for this month",
                    "Record them to see your savings rate and monthly surplus.",
                )
                st.page_link(
                    "views/monthly.py", label="Record this month", icon=":material/edit_calendar:"
                )

    with right:
        with st.container(border=True):
            ui.caption("What changed")
            ui.insight_list(insights.month_narrative(dataset))

            attribution = performance.latest_attribution(dataset)
            if attribution and attribution.total and attribution.total.is_complete:
                with st.expander("See the breakdown"):
                    st.plotly_chart(
                        charts.attribution_waterfall(attribution.total, symbol),
                        width="stretch",
                        config=charts.CHART_CONFIG,
                    )


def _goals(dataset, symbol: str) -> None:
    headline = goals.headline_goals(dataset, limit=3)
    if not headline:
        return

    ui.section("Goals", "The targets closest to a deadline.")
    columns = st.columns(len(headline))
    for column, progress in zip(columns, headline):
        with column:
            ui.goal_card(progress, symbol)

    if len(dataset.goals) > len(headline):
        ui.spacer(0.4)
        st.page_link(
            "views/goals.py",
            label=f"All {len(dataset.goals)} goals",
            icon=":material/arrow_forward:",
        )


def _position(dataset, symbol: str) -> None:
    standing = insights.position_insights(dataset)
    gaps = insights.data_gaps(dataset)
    trajectory = projections.trajectory_check(dataset)

    if not (standing or gaps or trajectory):
        return

    ui.section("Your position", "Standing observations, not just this month.")
    left, right = st.columns([1.3, 1], gap="medium")

    with left:
        with st.container(border=True):
            ui.insight_list(standing + gaps)

    with right:
        with st.container(border=True):
            ui.caption("Trajectory")
            if trajectory is None:
                ui.empty_state(
                    "Not enough history",
                    "A few more months and this will compare your actual pace with your "
                    "projected pace.",
                )
            else:
                difference = trajectory["difference"]
                ahead = difference >= 0
                ui.metric_card(
                    "Actual vs projected",
                    signed_money(difference, symbol) + " / month",
                    delta="ahead of plan" if ahead else "behind plan",
                    delta_tone="positive" if ahead else "warning",
                    caption=(
                        f"Averaged {money(trajectory['actual_monthly'], symbol)} a month over "
                        f"{trajectory['months_observed']} months against a projected "
                        f"{money(trajectory['projected_monthly'], symbol)}."
                    ),
                    provenance="assumption",
                )
                ui.spacer(0.5)
                st.page_link(
                    "views/projections.py",
                    label="Explore projections",
                    icon=":material/arrow_forward:",
                )


render()
