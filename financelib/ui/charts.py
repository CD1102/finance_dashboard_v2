"""Plotly chart builders.

Charts exist to answer a question, so each builder is named after the question
it answers. Styling is applied centrally by :func:`_style` so every chart in
the app shares one visual language.
"""

from __future__ import annotations

import plotly.graph_objects as go

from financelib.calculations.cashflow import MonthSummary, PeriodTotals
from financelib.calculations.networth import AccountSeries, AllocationSlice, NetWorthPoint
from financelib.calculations.performance import Attribution
from financelib.calculations.projections import Projection
from financelib.formatting import compact_money, month_axis_label
from financelib.ui.theme import active_palette, category_color, series_color

TRANSPARENT = "rgba(0,0,0,0)"


def _style(fig: go.Figure, height: int = 320, legend: bool = False) -> go.Figure:
    p = active_palette()
    fig.update_layout(
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font=dict(color=p.text_muted, family="Inter, sans-serif", size=12),
        margin=dict(l=6, r=6, t=18, b=6),
        height=height,
        showlegend=legend,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=p.surface_raised,
            bordercolor=p.border_strong,
            font=dict(color=p.text, family="Inter, sans-serif", size=12),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=11),
            bgcolor=TRANSPARENT,
        ),
        dragmode=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=p.border, tickcolor=p.border)
    fig.update_yaxes(gridcolor=p.grid, zeroline=False, showline=False, tickcolor=p.border)
    return fig


def _money_axis(fig: go.Figure, symbol: str = "£") -> go.Figure:
    fig.update_yaxes(tickprefix=symbol, separatethousands=True)
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# ----------------------------------------------------------------------
# Net worth
# ----------------------------------------------------------------------


def net_worth_chart(points: list[NetWorthPoint], symbol: str = "£") -> go.Figure:
    """How has my net worth moved over time?"""
    p = active_palette()
    fig = go.Figure()

    months = [point.month for point in points]
    totals = [point.total for point in points]

    # Month-on-month deltas in the tooltip answer "what changed" without a click.
    deltas = [None] + [round(b - a, 2) for a, b in zip(totals, totals[1:])]
    custom = [
        [compact_money(d, symbol) if d is not None else "—", month_axis_label(m)]
        for d, m in zip(deltas, months)
    ]

    fig.add_trace(
        go.Scatter(
            x=months,
            y=totals,
            mode="lines",
            line=dict(color=p.accent, width=2.5, shape="spline", smoothing=0.5),
            fill="tozeroy",
            fillcolor=_rgba(p.accent, 0.10),
            customdata=custom,
            hovertemplate=(
                f"<b>{symbol}%{{y:,.0f}}</b><br>"
                "Change: %{customdata[0]}<extra></extra>"
            ),
            name="Net worth",
        )
    )

    fig.update_xaxes(
        tickmode="array",
        tickvals=months,
        ticktext=[month_axis_label(m) for m in months],
        nticks=10,
    )
    fig.update_yaxes(rangemode="tozero")
    return _money_axis(_style(fig, height=340), symbol)


def net_worth_by_category_chart(points: list[NetWorthPoint], symbol: str = "£") -> go.Figure:
    """Which parts of my wealth have grown?"""
    fig = go.Figure()
    months = [point.month for point in points]
    categories = sorted({key for point in points for key, value in point.by_category.items() if value})

    from financelib.models import CATEGORY_LABELS, LIABILITY

    for key in categories:
        if key == LIABILITY:
            continue
        colour = category_color(key)
        fig.add_trace(
            go.Scatter(
                x=months,
                y=[point.by_category.get(key, 0.0) for point in points],
                mode="lines",
                stackgroup="assets",
                line=dict(width=0.5, color=colour),
                fillcolor=_rgba(colour, 0.55),
                name=CATEGORY_LABELS.get(key, key.title()),
                hovertemplate=f"{symbol}%{{y:,.0f}}<extra>%{{fullData.name}}</extra>",
            )
        )

    fig.update_xaxes(
        tickmode="array",
        tickvals=months,
        ticktext=[month_axis_label(m) for m in months],
        nticks=10,
    )
    return _money_axis(_style(fig, height=320, legend=True), symbol)


def allocation_donut(
    slices: list[AllocationSlice],
    colors: dict[str, str],
    centre_value: str,
    centre_label: str = "net worth",
) -> go.Figure:
    """Where does my money sit right now?"""
    p = active_palette()
    fig = go.Figure(
        go.Pie(
            labels=[item.label for item in slices],
            values=[item.amount for item in slices],
            hole=0.72,
            sort=False,
            direction="clockwise",
            textinfo="none",
            marker=dict(
                colors=[colors.get(item.key, p.text_muted) for item in slices],
                line=dict(color=p.surface, width=3),
            ),
            hovertemplate="<b>%{label}</b><br>£%{value:,.0f} · %{percent}<extra></extra>",
        )
    )
    fig.add_annotation(
        text=(
            f"<span style='font-size:21px;font-weight:700;color:{p.text}'>{centre_value}</span>"
            f"<br><span style='font-size:11px;color:{p.text_muted}'>{centre_label}</span>"
        ),
        x=0.5,
        y=0.5,
        showarrow=False,
    )
    fig = _style(fig, height=250)
    fig.update_layout(hovermode="closest", margin=dict(l=0, r=0, t=0, b=0))
    return fig


def monthly_change_chart(
    months: list[str], changes: list[float], symbol: str = "£"
) -> go.Figure:
    """Which months moved me forward, and which held me back?"""
    p = active_palette()
    fig = go.Figure(
        go.Bar(
            x=months,
            y=changes,
            marker_color=[p.positive if value >= 0 else p.negative for value in changes],
            marker_line_width=0,
            hovertemplate=f"<b>{symbol}%{{y:+,.0f}}</b><extra></extra>",
            name="Change",
        )
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=months,
        ticktext=[month_axis_label(m) for m in months],
    )
    fig.add_hline(y=0, line_width=1, line_color=p.border_strong)
    return _money_axis(_style(fig, height=250), symbol)


def account_chart(series: AccountSeries, symbol: str = "£") -> go.Figure:
    """How has this one account moved?"""
    p = active_palette()
    colour = category_color(series.account.category)
    months = [month for month, _ in series.points]
    values = [value for _, value in series.points]

    fig = go.Figure(
        go.Scatter(
            x=months,
            y=values,
            mode="lines+markers",
            line=dict(color=colour, width=2.5, shape="spline", smoothing=0.5),
            marker=dict(size=5, color=colour),
            fill="tozeroy",
            fillcolor=_rgba(colour, 0.10),
            hovertemplate=f"<b>{symbol}%{{y:,.0f}}</b><extra></extra>",
            name=series.account.name,
        )
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=months,
        ticktext=[month_axis_label(m) for m in months],
        nticks=10,
    )
    fig.update_yaxes(rangemode="tozero", gridcolor=p.grid)
    return _money_axis(_style(fig, height=280), symbol)


# ----------------------------------------------------------------------
# Cash flow
# ----------------------------------------------------------------------


def cashflow_chart(summaries: list[MonthSummary], symbol: str = "£") -> go.Figure:
    """What came in, what went out, and what did I keep?"""
    p = active_palette()
    usable = [s for s in summaries if s.has_cashflow]
    months = [s.month for s in usable]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=months,
            y=[s.income for s in usable],
            name="Income",
            marker_color=_rgba(p.info, 0.75),
            marker_line_width=0,
            hovertemplate=f"{symbol}%{{y:,.0f}}<extra>Income</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=[s.spending for s in usable],
            name="Spending",
            marker_color=_rgba(p.negative, 0.72),
            marker_line_width=0,
            hovertemplate=f"{symbol}%{{y:,.0f}}<extra>Spending</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=months,
            y=[s.contributions for s in usable],
            name="Contributions",
            mode="lines+markers",
            line=dict(color=p.accent, width=2, dash="dot"),
            marker=dict(size=5),
            hovertemplate=f"{symbol}%{{y:,.0f}}<extra>Contributions</extra>",
        )
    )

    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.08)
    fig.update_xaxes(
        tickmode="array",
        tickvals=months,
        ticktext=[month_axis_label(m) for m in months],
    )
    return _money_axis(_style(fig, height=330, legend=True), symbol)


def savings_rate_chart(summaries: list[MonthSummary]) -> go.Figure:
    """Is the share of income I keep going up or down?"""
    p = active_palette()
    usable = [s for s in summaries if s.savings_rate is not None]
    months = [s.month for s in usable]
    rates = [s.savings_rate for s in usable]

    fig = go.Figure(
        go.Scatter(
            x=months,
            y=rates,
            mode="lines+markers",
            line=dict(color=p.accent, width=2.5, shape="spline", smoothing=0.5),
            marker=dict(size=5),
            fill="tozeroy",
            fillcolor=_rgba(p.accent, 0.10),
            hovertemplate="<b>%{y:.1f}%</b><extra>Savings rate</extra>",
            name="Savings rate",
        )
    )
    if rates:
        average = sum(rates) / len(rates)
        fig.add_hline(
            y=average,
            line_width=1,
            line_dash="dot",
            line_color=p.text_subtle,
            annotation_text=f"avg {average:.0f}%",
            annotation_position="top left",
            annotation_font_size=10,
            annotation_font_color=p.text_muted,
        )
    fig.update_xaxes(
        tickmode="array",
        tickvals=months,
        ticktext=[month_axis_label(m) for m in months],
    )
    fig.update_yaxes(ticksuffix="%")
    return _style(fig, height=280)


def category_chart(categories: dict[str, float], symbol: str = "£") -> go.Figure:
    """Where is my spending actually going?"""
    ordered = sorted(categories.items(), key=lambda item: item[1])
    labels = [name for name, _ in ordered]
    values = [amount for _, amount in ordered]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=[series_color(index) for index in range(len(labels))],
            marker_line_width=0,
            hovertemplate=f"<b>{symbol}%{{x:,.0f}}</b><extra>%{{y}}</extra>",
        )
    )
    fig.update_xaxes(tickprefix=symbol, separatethousands=True, gridcolor=active_palette().grid)
    fig.update_yaxes(showgrid=False)
    fig = _style(fig, height=max(220, 34 * len(labels) + 60))
    fig.update_layout(hovermode="closest")
    return fig


def year_comparison_chart(totals: list[PeriodTotals], symbol: str = "£") -> go.Figure:
    """How do my years compare?"""
    p = active_palette()
    labels = [item.label for item in totals]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[item.income for item in totals],
            name="Income",
            marker_color=_rgba(p.info, 0.75),
            marker_line_width=0,
            hovertemplate=f"{symbol}%{{y:,.0f}}<extra>Income</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[item.spending for item in totals],
            name="Spending",
            marker_color=_rgba(p.negative, 0.72),
            marker_line_width=0,
            hovertemplate=f"{symbol}%{{y:,.0f}}<extra>Spending</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[item.contributions for item in totals],
            name="Contributions",
            marker_color=_rgba(p.accent, 0.8),
            marker_line_width=0,
            hovertemplate=f"{symbol}%{{y:,.0f}}<extra>Contributions</extra>",
        )
    )
    fig.update_layout(barmode="group", bargap=0.3)
    return _money_axis(_style(fig, height=320, legend=True), symbol)


# ----------------------------------------------------------------------
# Attribution
# ----------------------------------------------------------------------


def attribution_waterfall(attribution: Attribution, symbol: str = "£") -> go.Figure:
    """How much of the change did I add, and how much did the market?"""
    p = active_palette()

    measures = ["absolute", "relative"]
    labels = ["Starting", "Paid in"]
    values = [attribution.start_balance, attribution.contributions]

    if attribution.growth is not None:
        measures.append("relative")
        labels.append("Growth & interest")
        values.append(attribution.growth)

    measures.append("total")
    labels.append("Now")
    values.append(attribution.end_balance)

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            connector=dict(line=dict(color=p.border_strong, width=1)),
            increasing=dict(marker=dict(color=p.positive)),
            decreasing=dict(marker=dict(color=p.negative)),
            totals=dict(marker=dict(color=p.info)),
            text=[compact_money(v, symbol) for v in values],
            textposition="outside",
            textfont=dict(size=11, color=p.text_muted),
            hovertemplate=f"<b>{symbol}%{{y:,.0f}}</b><extra>%{{x}}</extra>",
        )
    )
    fig = _money_axis(_style(fig, height=300), symbol)
    fig.update_layout(hovermode="closest")
    return fig


# ----------------------------------------------------------------------
# Projections
# ----------------------------------------------------------------------


def projection_chart(
    projections: list[Projection], symbol: str = "£", real_terms: bool = False
) -> go.Figure:
    """What could this become under different assumptions?"""
    fig = go.Figure()

    for index, projection in enumerate(projections):
        points = projection.yearly
        colour = series_color(index)
        values = [p.real_total if real_terms else p.total for p in points]
        fig.add_trace(
            go.Scatter(
                x=[p.year_index for p in points],
                y=values,
                mode="lines",
                name=projection.label,
                line=dict(color=colour, width=2.5 if index == 0 else 2, shape="spline"),
                fill="tozeroy" if index == 0 else None,
                fillcolor=_rgba(colour, 0.08) if index == 0 else None,
                hovertemplate=f"{symbol}%{{y:,.0f}}<extra>%{{fullData.name}}</extra>",
            )
        )

    fig.update_xaxes(title_text="Years from now", dtick=max(1, projections[0].assumptions.years // 10))
    return _money_axis(_style(fig, height=380, legend=True), symbol)


def projection_composition_chart(projection: Projection, symbol: str = "£") -> go.Figure:
    """Of the projected total, how much is mine and how much is growth?"""
    p = active_palette()
    points = projection.yearly
    years = [point.year_index for point in points]

    layers = [
        ("Starting wealth", [point.starting_wealth for point in points], p.info),
        ("Contributions", [point.contributions for point in points], p.accent),
        ("Investment growth", [point.investment_growth for point in points], "#A78BFA"),
        ("Interest", [point.interest for point in points], "#F0A868"),
    ]

    fig = go.Figure()
    for name, values, colour in layers:
        if not any(values):
            continue
        fig.add_trace(
            go.Scatter(
                x=years,
                y=values,
                mode="lines",
                stackgroup="composition",
                name=name,
                line=dict(width=0.5, color=colour),
                fillcolor=_rgba(colour, 0.6),
                hovertemplate=f"{symbol}%{{y:,.0f}}<extra>%{{fullData.name}}</extra>",
            )
        )

    fig.update_xaxes(title_text="Years from now")
    return _money_axis(_style(fig, height=340, legend=True), symbol)


def goal_progress_chart(
    labels: list[str], current: list[float], targets: list[float], symbol: str = "£"
) -> go.Figure:
    """How far through each goal am I?"""
    p = active_palette()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=targets,
            y=labels,
            orientation="h",
            marker_color=_rgba(p.text_muted, 0.18),
            marker_line_width=0,
            hoverinfo="skip",
            name="Target",
        )
    )
    fig.add_trace(
        go.Bar(
            x=current,
            y=labels,
            orientation="h",
            marker_color=p.accent,
            marker_line_width=0,
            hovertemplate=f"<b>{symbol}%{{x:,.0f}}</b><extra>%{{y}}</extra>",
            name="Current",
        )
    )
    fig.update_layout(barmode="overlay", bargap=0.42)
    fig.update_xaxes(tickprefix=symbol, separatethousands=True, gridcolor=p.grid)
    fig.update_yaxes(showgrid=False)
    fig = _style(fig, height=max(200, 46 * len(labels) + 60))
    fig.update_layout(hovermode="closest")
    return fig


#: Passed to ``st.plotly_chart`` so charts stay clean and non-fiddly.
CHART_CONFIG = {"displayModeBar": False, "scrollZoom": False, "staticPlot": False}
