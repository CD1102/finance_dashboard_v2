"""History — long-run trends, annual comparisons and the underlying figures."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from financelib.calculations import cashflow, networth, performance
from financelib.formatting import money, month_label, percent, signed_money
from financelib.models import CATEGORY_LABELS
from financelib.ui import charts, components as ui
from financelib.ui.state import load_dataset, period_selector, trim


def render() -> None:
    dataset = load_dataset()
    symbol = dataset.settings.currency_symbol

    ui.page_header(
        "History",
        "How your position, income, spending and saving have moved over time.",
    )

    if not dataset.months:
        ui.empty_state(
            "No history yet",
            "Record a month, or import your spreadsheet, and this page fills in.",
        )
        st.page_link("views/data.py", label="Import history", icon=":material/upload:")
        return

    net_worth_tab, cashflow_tab, spending_tab, years_tab, table_tab = st.tabs(
        ["Net worth", "Cash flow", "Spending", "Year by year", "All figures"]
    )

    with net_worth_tab:
        _net_worth(dataset, symbol)
    with cashflow_tab:
        _cashflow(dataset, symbol)
    with spending_tab:
        _spending(dataset, symbol)
    with years_tab:
        _years(dataset, symbol)
    with table_tab:
        _table(dataset, symbol)


# ----------------------------------------------------------------------
# Net worth
# ----------------------------------------------------------------------


def _net_worth(dataset, symbol: str) -> None:
    series = networth.net_worth_series(dataset)
    if len(series) < 2:
        ui.empty_state(
            "Two months of balances are needed",
            "Trends need something to compare against.",
        )
        return

    ui.spacer(0.5)
    left, right = st.columns([3, 1.4])
    with right:
        months = period_selector("history_period", default="All")
    with left:
        stacked = st.toggle("Split by category", value=False, key="history_stacked")

    shown = trim(series, months)

    with st.container(border=True):
        figure = (
            charts.net_worth_by_category_chart(shown, symbol)
            if stacked
            else charts.net_worth_chart(shown, symbol)
        )
        st.plotly_chart(figure, width="stretch", config=charts.CHART_CONFIG)

    change = networth.change_over(series, months)
    if change is not None:
        ui.spacer(0.5)
        columns = st.columns(4)
        with columns[0]:
            ui.change_metric("Change", change, symbol)
        with columns[1]:
            ui.metric_card(
                "Average per month",
                signed_money(change.average_per_month, symbol),
                caption=f"Over {change.months_elapsed} months",
                provenance="derived",
            )
        with columns[2]:
            best = max(
                ((b.month, b.total - a.total) for a, b in zip(shown, shown[1:])),
                key=lambda item: item[1],
                default=None,
            )
            ui.metric_card(
                "Best month",
                signed_money(best[1], symbol) if best else "—",
                caption=month_label(best[0]) if best else "",
                provenance="derived",
            )
        with columns[3]:
            worst = min(
                ((b.month, b.total - a.total) for a, b in zip(shown, shown[1:])),
                key=lambda item: item[1],
                default=None,
            )
            ui.metric_card(
                "Worst month",
                signed_money(worst[1], symbol) if worst else "—",
                caption=month_label(worst[0]) if worst else "",
                provenance="derived",
            )

    ui.section("Month-on-month movement")
    with st.container(border=True):
        months_list = [point.month for point in shown[1:]]
        deltas = [round(b.total - a.total, 2) for a, b in zip(shown, shown[1:])]
        st.plotly_chart(
            charts.monthly_change_chart(months_list, deltas, symbol),
            width="stretch",
            config=charts.CHART_CONFIG,
        )

    _attribution_history(dataset, shown, symbol)


def _attribution_history(dataset, shown, symbol: str) -> None:
    if len(shown) < 2:
        return

    result = performance.attribute_total(dataset, shown[0].month, shown[-1].month)
    if result is None:
        return

    ui.section("Where the change came from")
    if not result.is_complete:
        ui.note(
            f"{len(result.missing_months)} month(s) in this period have no contributions "
            "recorded, so growth cannot be separated from money you added.",
            tone="warning",
        )
        return

    left, right = st.columns([1.3, 1], gap="medium")
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
                    ("Total change", signed_money(result.change, symbol)),
                    ("You paid in", money(result.contributions, symbol)),
                ]
            )
            ui.spacer(0.7)
            ui.stat_line(
                [
                    ("Growth & interest", signed_money(result.growth, symbol)),
                    ("Annualised", percent(result.annualised_percent)),
                ]
            )
            ui.spacer(0.6)
            ui.legend_for_provenance()


# ----------------------------------------------------------------------
# Cash flow
# ----------------------------------------------------------------------


def _cashflow(dataset, symbol: str) -> None:
    summaries = cashflow.summaries(dataset)
    usable = [s for s in summaries if s.has_cashflow]

    if not usable:
        ui.empty_state(
            "No income or spending recorded",
            "Add them on the Monthly page, or import them from your spreadsheet.",
        )
        return

    ui.spacer(0.5)
    _, right = st.columns([3, 1.4])
    with right:
        months = period_selector("cashflow_period", default="1Y")

    shown = trim(usable, months)
    totals = cashflow.totals_for([dataset.record(s.month) for s in shown if dataset.record(s.month)])

    columns = st.columns(4)
    with columns[0]:
        ui.metric_card(
            "Average income",
            money(totals.average_income, symbol),
            caption=f"Across {totals.months_counted} months",
            provenance="derived",
        )
    with columns[1]:
        ui.metric_card(
            "Average spending",
            money(totals.average_spending, symbol),
            caption=f"Across {totals.months_counted} months",
            provenance="derived",
        )
    with columns[2]:
        ui.metric_card(
            "Average saved",
            percent(totals.savings_rate, 0),
            caption=f"Surplus {money(totals.surplus, symbol)} in total",
            bar_percent=totals.savings_rate,
            provenance="derived",
        )
    with columns[3]:
        ui.metric_card(
            "Average paid in",
            money(totals.average_contributions, symbol),
            caption="Into your accounts",
            provenance="derived",
            muted=totals.average_contributions is None,
        )

    ui.spacer(0.8)
    with st.container(border=True):
        st.plotly_chart(
            charts.cashflow_chart(shown, symbol),
            width="stretch",
            config=charts.CHART_CONFIG,
        )

    ui.section("Savings rate over time")
    with st.container(border=True):
        st.plotly_chart(
            charts.savings_rate_chart(shown),
            width="stretch",
            config=charts.CHART_CONFIG,
        )


# ----------------------------------------------------------------------
# Spending
# ----------------------------------------------------------------------


def _spending(dataset, symbol: str) -> None:
    categorised = [record for record in dataset.months if record.spending_categories]
    if not categorised:
        ui.empty_state(
            "No spending categories recorded",
            "Categories are optional. Add them on the Monthly page if you want to see "
            "where money goes, rather than only how much.",
        )
        return

    ui.spacer(0.5)
    _, right = st.columns([3, 1.4])
    with right:
        months = period_selector("spending_period", default="1Y")

    breakdown = cashflow.spending_by_category(dataset, months)
    total = sum(breakdown.values())

    left, side = st.columns([1.5, 1], gap="medium")
    with left:
        with st.container(border=True):
            ui.caption(f"Total {money(total, symbol)} across the period")
            st.plotly_chart(
                charts.category_chart(breakdown, symbol),
                width="stretch",
                config=charts.CHART_CONFIG,
            )

    with side:
        with st.container(border=True):
            ui.caption("Share of spending")
            count = len([r for r in trim(categorised, months) if r.spending_categories]) or 1
            rows = sorted(breakdown.items(), key=lambda item: item[1], reverse=True)
            for name, amount in rows:
                share = amount / total * 100 if total else 0
                ui.metric_card(
                    name,
                    money(amount / count, symbol) + " / month",
                    caption=f"{share:.0f}% of spending · {money(amount, symbol)} total",
                    bar_percent=share,
                )
                ui.spacer(0.35)


# ----------------------------------------------------------------------
# Years
# ----------------------------------------------------------------------


def _years(dataset, symbol: str) -> None:
    yearly = [totals for totals in cashflow.all_year_totals(dataset) if totals.months_counted]
    if not yearly:
        ui.empty_state(
            "No annual figures yet",
            "Annual comparisons need income or spending recorded for at least one month.",
        )
        return

    with st.container(border=True):
        st.plotly_chart(
            charts.year_comparison_chart(yearly, symbol),
            width="stretch",
            config=charts.CHART_CONFIG,
        )

    ui.note(
        "Part-years are shown as recorded. A year with fewer months will naturally show "
        "smaller totals.",
    )

    ui.section("Year detail")
    rows = []
    previous_end = None
    for totals in yearly:
        year = int(totals.label)
        year_records = [r for r in dataset.records_with_balances() if r.year == year]
        end_value = (
            networth.net_worth(year_records[-1], dataset.accounts) if year_records else None
        )
        rows.append(
            {
                "Year": totals.label,
                "Months": totals.months_counted,
                "Income": totals.income or None,
                "Spending": totals.spending or None,
                "Surplus": totals.surplus if totals.months_counted else None,
                "Savings rate": totals.savings_rate,
                "Paid in": totals.contributions or None,
                "Net worth at year end": end_value,
                "Net worth change": (
                    round(end_value - previous_end, 2)
                    if end_value is not None and previous_end is not None
                    else None
                ),
            }
        )
        if end_value is not None:
            previous_end = end_value

    frame = pd.DataFrame(rows).iloc[::-1]
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={
            "Income": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
            "Spending": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
            "Surplus": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
            "Savings rate": st.column_config.NumberColumn(format="%.1f%%"),
            "Paid in": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
            "Net worth at year end": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
            "Net worth change": st.column_config.NumberColumn(format=f"{symbol}%.0f"),
        },
    )


# ----------------------------------------------------------------------
# Table
# ----------------------------------------------------------------------


def _table(dataset, symbol: str) -> None:
    ui.spacer(0.5)
    year_filter, account_filter = st.columns([1, 2])

    years = dataset.years()
    with year_filter:
        chosen_years = st.multiselect("Years", years, default=years, key="table_years")
    with account_filter:
        account_names = {a.name: a.id for a in dataset.accounts}
        chosen_accounts = st.multiselect(
            "Accounts",
            list(account_names),
            default=list(account_names),
            key="table_accounts",
        )

    selected_ids = [account_names[name] for name in chosen_accounts]
    records = [r for r in dataset.months if r.year in chosen_years]

    if not records:
        ui.empty_state("Nothing matches those filters")
        return

    rows = []
    for record in records:
        row = {
            "Month": record.month,
            "Income": record.income,
            "Spending": record.effective_spending,
            "Net worth": (
                networth.net_worth(record, dataset.accounts) if record.balances else None
            ),
        }
        for account_id in selected_ids:
            row[dataset.account_name(account_id)] = record.balances.get(account_id)
        rows.append(row)

    frame = pd.DataFrame(rows).iloc[::-1]
    money_format = st.column_config.NumberColumn(format=f"{symbol}%.0f")
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config={
            column: money_format for column in frame.columns if column != "Month"
        },
    )

    ui.spacer(0.5)
    st.download_button(
        "Download as CSV",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="finance-history.csv",
        mime="text/csv",
    )
    ui.caption("This file contains your real financial figures. Keep it somewhere private.")


render()
