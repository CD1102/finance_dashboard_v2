"""Projections — what the current pace could lead to, under stated assumptions."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from financelib.calculations import projections as proj
from financelib.formatting import compact_money, money, percent
from financelib.ui import charts, components as ui
from financelib.ui.state import load_dataset


def render() -> None:
    dataset = load_dataset()
    symbol = dataset.settings.currency_symbol

    ui.page_header(
        "Projections",
        "Arithmetic applied to assumptions you choose. Not a forecast, and not advice.",
    )

    base = proj.assumptions_from_dataset(dataset)
    if base.starting_total <= 0 and base.monthly_contribution_total <= 0:
        ui.empty_state(
            "Nothing to project from yet",
            "Record some balances, or set planned contributions on your accounts, and "
            "this page will have somewhere to start.",
        )
        return

    assumptions = _controls(base, symbol)
    scenarios = _scenarios(assumptions, symbol)
    results = proj.compare(scenarios)

    _headline(results, symbol)
    _chart(results, symbol)
    _composition(results[0], symbol)
    _table(results, symbol)
    _transparency(results[0], symbol)


# ----------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------


def _controls(base: proj.Assumptions, symbol: str) -> proj.Assumptions:
    with st.container(border=True):
        ui.caption("Assumptions · adjust anything here")
        ui.spacer(0.4)

        start_col, contrib_col, rate_col = st.columns(3, gap="large")

        with start_col:
            st.markdown("**Starting position**")
            investments = st.number_input(
                f"Investments ({symbol})",
                value=float(base.starting_investments),
                step=500.0,
                key="proj_start_inv",
            )
            cash = st.number_input(
                f"Cash and other ({symbol})",
                value=float(base.starting_cash),
                step=500.0,
                key="proj_start_cash",
            )
            pension = st.number_input(
                f"Pension ({symbol})",
                value=float(base.starting_pension),
                step=500.0,
                key="proj_start_pen",
            )

        with contrib_col:
            st.markdown("**Monthly contributions**")
            invest_monthly = st.number_input(
                f"Into investments ({symbol})",
                value=float(base.monthly_investment_contribution),
                min_value=0.0,
                step=50.0,
                key="proj_c_inv",
            )
            cash_monthly = st.number_input(
                f"Into cash ({symbol})",
                value=float(base.monthly_cash_contribution),
                min_value=0.0,
                step=50.0,
                key="proj_c_cash",
            )
            pension_monthly = st.number_input(
                f"Into pension ({symbol})",
                value=float(base.monthly_pension_contribution),
                min_value=0.0,
                step=50.0,
                key="proj_c_pen",
            )

        with rate_col:
            st.markdown("**Annual rates**")
            investment_return = st.slider(
                "Investment return (%)", 0.0, 15.0, float(base.investment_return), 0.25,
                key="proj_r_inv",
            )
            cash_rate = st.slider(
                "Cash interest (%)", 0.0, 10.0, float(base.cash_rate), 0.25, key="proj_r_cash"
            )
            pension_return = st.slider(
                "Pension return (%)", 0.0, 15.0, float(base.pension_return), 0.25,
                key="proj_r_pen",
            )

        ui.spacer(0.5)
        horizon_col, inflation_col, growth_col = st.columns(3, gap="large")
        years = horizon_col.slider("Years ahead", 1, 40, int(base.years), key="proj_years")
        inflation = inflation_col.slider(
            "Inflation (%)", 0.0, 10.0, float(base.inflation), 0.25, key="proj_inflation"
        )
        contribution_growth = growth_col.slider(
            "Contribution increase each year (%)",
            0.0,
            15.0,
            float(base.contribution_growth),
            0.5,
            key="proj_growth",
            help="Pay rises tend to lift what you can save. Leave at zero to keep "
            "contributions flat.",
        )

    return proj.Assumptions(
        starting_investments=investments,
        starting_cash=cash,
        starting_pension=pension,
        monthly_investment_contribution=invest_monthly,
        monthly_cash_contribution=cash_monthly,
        monthly_pension_contribution=pension_monthly,
        investment_return=investment_return,
        cash_rate=cash_rate,
        pension_return=pension_return,
        inflation=inflation,
        contribution_growth=contribution_growth,
        years=years,
        label="Your assumptions",
    )


def _scenarios(base: proj.Assumptions, symbol: str) -> list[proj.Assumptions]:
    ui.section("Compare scenarios", "See how sensitive the outcome is to what you assume.")

    choice = st.multiselect(
        "Also show",
        ["Pay in more", "Pay in less", "Weaker returns", "Stronger returns", "No contributions"],
        default=["Pay in more", "Weaker returns"],
        key="proj_scenarios",
    )

    step = max(round(base.monthly_contribution_total * 0.25), 50)
    variants = {
        "Pay in more": lambda: base.variant(
            f"+{money(step, symbol)}/mo",
            monthly_investment_contribution=base.monthly_investment_contribution + step,
        ),
        "Pay in less": lambda: base.variant(
            f"−{money(step, symbol)}/mo",
            monthly_investment_contribution=max(
                base.monthly_investment_contribution - step, 0.0
            ),
        ),
        "Weaker returns": lambda: base.variant(
            "Returns 2% lower",
            investment_return=max(base.investment_return - 2, 0.0),
            pension_return=max(base.pension_return - 2, 0.0),
        ),
        "Stronger returns": lambda: base.variant(
            "Returns 2% higher",
            investment_return=base.investment_return + 2,
            pension_return=base.pension_return + 2,
        ),
        "No contributions": lambda: base.variant(
            "Stop paying in",
            monthly_investment_contribution=0.0,
            monthly_cash_contribution=0.0,
            monthly_pension_contribution=0.0,
        ),
    }

    return [base] + [variants[name]() for name in choice if name in variants]


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------


def _headline(results: list[proj.Projection], symbol: str) -> None:
    primary = results[0]
    final = primary.final
    years = primary.assumptions.years

    ui.spacer(0.7)
    columns = st.columns(4)
    with columns[0]:
        ui.metric_card(
            f"Projected in {years} years",
            money(final.total, symbol),
            caption="Nominal, before inflation",
            provenance="assumption",
        )
    with columns[1]:
        ui.metric_card(
            "In today's money",
            money(final.real_total, symbol),
            caption=f"After {percent(primary.assumptions.inflation)} inflation a year",
            provenance="assumption",
        )
    with columns[2]:
        ui.metric_card(
            "You would pay in",
            money(final.contributions, symbol),
            caption="Total contributions over the period",
            provenance="assumption",
        )
    with columns[3]:
        ui.metric_card(
            "Growth and interest",
            money(final.total_growth, symbol),
            caption=(
                f"{final.total_growth / final.total * 100:.0f}% of the projected total"
                if final.total
                else ""
            ),
            provenance="assumption",
        )


def _chart(results: list[proj.Projection], symbol: str) -> None:
    ui.section("Projected trajectory")
    with st.container(border=True):
        real_terms = st.toggle(
            "Show in today's money",
            value=False,
            key="proj_real",
            help="Adjusts every scenario for inflation so the numbers mean something "
            "comparable to prices today.",
        )
        st.plotly_chart(
            charts.projection_chart(results, symbol, real_terms),
            width="stretch",
            config=charts.CHART_CONFIG,
        )

    if len(results) > 1:
        primary_final = results[0].final.total
        rows = []
        for result in results:
            difference = result.final.total - primary_final
            rows.append(
                {
                    "Scenario": result.label,
                    f"After {result.assumptions.years} years": result.final.total,
                    "Difference": difference if result is not results[0] else None,
                    "In today's money": result.final.real_total,
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            width="stretch",
            hide_index=True,
            column_config={
                column: st.column_config.NumberColumn(format=f"{symbol}%.0f")
                for column in rows[0]
                if column != "Scenario"
            },
        )


def _composition(primary: proj.Projection, symbol: str) -> None:
    ui.section(
        "What the total is made of",
        "How much is what you started with, what you pay in, and what growth adds.",
    )
    with st.container(border=True):
        st.plotly_chart(
            charts.projection_composition_chart(primary, symbol),
            width="stretch",
            config=charts.CHART_CONFIG,
        )


def _table(results: list[proj.Projection], symbol: str) -> None:
    primary = results[0]
    with st.expander("Year-by-year figures"):
        rows = [
            {
                "Year": int(point.year_index),
                "Starting wealth": point.starting_wealth,
                "Contributions": point.contributions,
                "Investment growth": point.investment_growth,
                "Interest": point.interest,
                "Total": point.total,
                "In today's money": point.real_total,
            }
            for point in primary.yearly
        ]
        frame = pd.DataFrame(rows)
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
            column_config={
                column: st.column_config.NumberColumn(format=f"{symbol}%.0f")
                for column in frame.columns
                if column != "Year"
            },
        )


def _transparency(primary: proj.Projection, symbol: str) -> None:
    a = primary.assumptions
    monthly_rate = (1 + a.investment_return / 100) ** (1 / 12) - 1

    ui.section("How this is calculated")
    with st.container(border=True):
        st.markdown(
            f"""
Each month, every pot grows by its own monthly rate and then your contribution is added:

$$\\text{{balance}}_{{n+1}} = \\text{{balance}}_n \\times (1 + r) + c$$

where $r$ is the monthly equivalent of the annual rate, $(1 + \\text{{annual}})^{{1/12}} - 1$,
and $c$ is your monthly contribution.

At {percent(a.investment_return)} a year, $r$ is **{monthly_rate * 100:.4f}%** a month.

- Investments, cash and pension compound separately, at
  {percent(a.investment_return)}, {percent(a.cash_rate)} and {percent(a.pension_return)}.
- Contributions are added **after** growth each month, so no month earns a return on
  money that has not arrived yet.
- Contributions rise by {percent(a.contribution_growth)} once a year, on the anniversary.
- Today's-money figures divide the nominal total by
  {percent(a.inflation)} inflation compounded over the same period.
"""
        )
        ui.spacer(0.4)
        ui.note(
            "Real returns vary year to year and can be negative. A smooth curve is a "
            "simplification, not an expectation.",
            tone="warning",
        )

    starting = a.starting_total
    final = primary.final
    ui.spacer(0.5)
    ui.stat_line(
        [
            ("Start", money(starting, symbol)),
            ("Paid in", money(final.contributions, symbol)),
            ("Growth", money(final.investment_growth, symbol)),
            ("Interest", money(final.interest, symbol)),
            ("Total", money(final.total, symbol)),
        ]
    )
    ui.spacer(0.3)
    ui.caption(
        f"{compact_money(starting, symbol)} + {compact_money(final.contributions, symbol)} + "
        f"{compact_money(final.total_growth, symbol)} = {compact_money(final.total, symbol)}"
    )


render()
