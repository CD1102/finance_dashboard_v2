"""Reusable interface pieces.

Pages compose these rather than writing their own markup, which is what keeps
spacing, typography and tone consistent across the app.
"""

from __future__ import annotations

import html
from typing import Iterable, Literal

import streamlit as st

from financelib.calculations.goals import GoalProgress
from financelib.calculations.insights import Insight
from financelib.calculations.networth import AllocationSlice, Change
from financelib.formatting import (
    duration_label,
    money,
    month_label,
    percent,
    signed_money,
    signed_percent,
)
from financelib.ui.theme import active_palette, tone_color

Tone = Literal["positive", "negative", "neutral", "warning"]

PROVENANCE_TEXT = {
    "recorded": ("Recorded", "Taken directly from what you entered."),
    "derived": ("Calculated", "Worked out from your recorded figures."),
    "assumption": ("Projected", "Based on assumptions, not a prediction."),
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _write(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------


def page_header(title: str, subtitle: str = "", eyebrow: str = "") -> None:
    eyebrow_html = f'<div class="fc-eyebrow">{_esc(eyebrow)}</div>' if eyebrow else ""
    subtitle_html = f'<div class="fc-page-sub">{_esc(subtitle)}</div>' if subtitle else ""
    _write(
        f'<div class="fc-page-head"><div>{eyebrow_html}'
        f'<div class="fc-page-title">{_esc(title)}</div>{subtitle_html}</div></div>'
    )


def section(title: str, subtitle: str = "") -> None:
    subtitle_html = f'<div class="fc-section-sub">{_esc(subtitle)}</div>' if subtitle else ""
    _write(
        f'<div class="fc-section"><div class="fc-section-title">{_esc(title)}</div>'
        f"{subtitle_html}</div>"
    )


def rule() -> None:
    _write('<hr class="fc-rule" />')


def spacer(height: float = 1.0) -> None:
    _write(f'<div style="height:{height}rem"></div>')


def provenance_chip(kind: str) -> str:
    """Inline chip markup marking data as recorded, calculated or projected."""
    label, _ = PROVENANCE_TEXT.get(kind, PROVENANCE_TEXT["derived"])
    return f'<span class="fc-chip fc-chip-{_esc(kind)}">{_esc(label)}</span>'


def legend_for_provenance() -> None:
    """One-line key explaining the chips, for pages that mix data types."""
    chips = " ".join(
        f'{provenance_chip(key)}<span style="color:var(--muted);font-size:0.78rem">'
        f"{_esc(description)}</span>"
        for key, (_, description) in PROVENANCE_TEXT.items()
    )
    _write(f'<div style="display:flex;gap:1.1rem;flex-wrap:wrap;align-items:center">{chips}</div>')


# ----------------------------------------------------------------------
# Hero
# ----------------------------------------------------------------------


def hero(
    label: str,
    value: str,
    change: Change | None = None,
    note: str = "",
    symbol: str = "£",
) -> None:
    """The single most important number on a page."""
    parts: list[str] = []

    if change is not None:
        tone = "positive" if change.is_increase else "negative"
        arrow = "&#9650;" if change.is_increase else "&#9660;"
        pct = f" · {signed_percent(change.percent)}" if change.percent is not None else ""
        parts.append(
            f'<span class="fc-hero-delta tone-{tone}">{arrow} '
            f"{signed_money(change.absolute, symbol)}{pct}</span>"
        )
        parts.append(
            f'<span class="fc-hero-note">vs {_esc(month_label(change.from_month))}</span>'
        )
    else:
        parts.append('<span class="fc-hero-delta tone-neutral">No comparison yet</span>')

    if note:
        parts.append(f'<span class="fc-hero-note">{_esc(note)}</span>')

    _write(
        f'<div class="fc-hero"><div class="fc-hero-label">{_esc(label)}</div>'
        f'<div class="fc-hero-value">{_esc(value)}</div>'
        f'<div class="fc-hero-row">{"".join(parts)}</div></div>'
    )


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------


def metric_card(
    label: str,
    value: str,
    *,
    delta: str | None = None,
    delta_tone: Tone = "neutral",
    caption: str = "",
    provenance: str | None = None,
    bar_percent: float | None = None,
    bar_color: str | None = None,
    muted: bool = False,
) -> None:
    """A single figure with optional delta, caption and progress bar."""
    palette = active_palette()

    chip = f" {provenance_chip(provenance)}" if provenance else ""
    foot_parts: list[str] = []
    if delta:
        foot_parts.append(
            f'<span class="fc-metric-delta fc-delta-{delta_tone}">{_esc(delta)}</span>'
        )
    if caption:
        foot_parts.append(f"<span>{_esc(caption)}</span>")
    foot = f'<div class="fc-metric-foot">{"".join(foot_parts)}</div>' if foot_parts else ""

    bar = ""
    if bar_percent is not None:
        width = max(0.0, min(float(bar_percent), 100.0))
        colour = bar_color or palette.accent
        bar = (
            f'<div class="fc-bar-track"><div class="fc-bar-fill" '
            f'style="width:{width:.1f}%;background:{colour}"></div></div>'
        )

    value_class = "fc-metric-value is-muted" if muted else "fc-metric-value"
    _write(
        f'<div class="fc-card"><div class="fc-metric-label">{_esc(label)}{chip}</div>'
        f'<div class="{value_class}">{_esc(value)}</div>{foot}{bar}</div>'
    )


def change_metric(
    label: str,
    change: Change | None,
    symbol: str = "£",
    caption_when_missing: str = "Needs two months of balances",
) -> None:
    """Metric card specialised for a :class:`Change`."""
    if change is None:
        metric_card(label, "—", caption=caption_when_missing, muted=True)
        return

    tone: Tone = "positive" if change.is_increase else "negative"
    metric_card(
        label,
        signed_money(change.absolute, symbol),
        delta=signed_percent(change.percent) if change.percent is not None else None,
        delta_tone=tone,
        caption=f"{month_label(change.from_month)} → {month_label(change.to_month)}",
        provenance="derived",
    )


# ----------------------------------------------------------------------
# Allocation
# ----------------------------------------------------------------------


def allocation_rows(
    slices: Iterable[AllocationSlice],
    colors: dict[str, str],
    symbol: str = "£",
) -> None:
    """Compact legend-style breakdown that reads better than a pie alone."""
    rows = []
    for item in slices:
        colour = colors.get(item.key, active_palette().text_muted)
        rows.append(
            f'<div class="fc-alloc-row">'
            f'<span class="fc-alloc-dot" style="background:{colour}"></span>'
            f'<span class="fc-alloc-name">{_esc(item.label)}</span>'
            f'<span class="fc-alloc-amount">{_esc(money(item.amount, symbol))}</span>'
            f'<span class="fc-alloc-pct">{_esc(percent(item.percent, 0))}</span>'
            f"</div>"
        )
    _write("".join(rows) or '<div class="fc-alloc-row">Nothing recorded yet.</div>')


# ----------------------------------------------------------------------
# Insights
# ----------------------------------------------------------------------


def insight_list(insights: Iterable[Insight], show_provenance: bool = True) -> None:
    items = list(insights)
    if not items:
        _write(
            '<div class="fc-insight-text" style="color:var(--muted)">'
            "Nothing notable to report for this period.</div>"
        )
        return

    rows = []
    for item in items:
        colour = tone_color(item.tone)
        chip = f" {provenance_chip(item.provenance)}" if show_provenance else ""
        detail = (
            f'<div class="fc-insight-detail">{_esc(item.detail)}</div>' if item.detail else ""
        )
        rows.append(
            f'<div class="fc-insight">'
            f'<div class="fc-insight-mark" style="background:{colour}"></div>'
            f'<div class="fc-insight-body"><div class="fc-insight-text">'
            f"{_esc(item.text)}{chip}</div>{detail}</div></div>"
        )
    _write("".join(rows))


# ----------------------------------------------------------------------
# Goals
# ----------------------------------------------------------------------

PACE_LABELS = {
    "ahead": ("On track", "positive"),
    "close": ("Just short", "warning"),
    "behind": ("Behind pace", "negative"),
    "complete": ("Reached", "positive"),
}


def goal_card(progress: GoalProgress, symbol: str = "£", compact: bool = False) -> None:
    """Progress for one goal, stating only what the data supports."""
    palette = active_palette()
    pace = progress.pace
    label, tone = PACE_LABELS.get(pace or "", ("", "neutral"))
    colour = tone_color(tone) if label else palette.accent

    status = (
        f'<span class="fc-chip" style="color:{colour};border-color:{colour}40">{_esc(label)}</span>'
        if label
        else ""
    )

    foot_left = ""
    if progress.is_complete:
        foot_left = "Target reached"
    elif progress.required_monthly is not None:
        foot_left = f"Needs {money(progress.required_monthly, symbol)}/mo"
    elif progress.observed_monthly:
        foot_left = f"Adding {money(progress.observed_monthly, symbol)}/mo"

    foot_right = ""
    if progress.goal.target_date is not None:
        foot_right = (
            f"{month_label(progress.goal.target_date.strftime('%Y-%m'))}"
            f" · {duration_label(progress.months_remaining)} left"
        )
    elif progress.projected_completion is not None and not progress.is_complete:
        foot_right = f"~{month_label(progress.projected_completion.strftime('%Y-%m'))}"

    foot = (
        f'<div class="fc-goal-foot"><span>{_esc(foot_left)}</span>'
        f"<span>{_esc(foot_right)}</span></div>"
        if (foot_left or foot_right) and not compact
        else ""
    )

    _write(
        f'<div class="fc-card">'
        f'<div class="fc-goal-head"><span class="fc-goal-name">{_esc(progress.goal.name)}</span>'
        f'<span class="fc-goal-pct" style="color:{colour}">{progress.percent:.0f}%</span></div>'
        f'<div class="fc-goal-amounts">{_esc(money(progress.current, symbol))} of '
        f"{_esc(money(progress.target, symbol))} · "
        f"{_esc(money(progress.remaining, symbol))} to go</div>"
        f'<div class="fc-bar-track"><div class="fc-bar-fill" '
        f'style="width:{progress.percent:.1f}%;background:{colour}"></div></div>'
        f'{foot}<div style="margin-top:0.5rem">{status}</div>'
        f"</div>"
    )


# ----------------------------------------------------------------------
# States
# ----------------------------------------------------------------------


def empty_state(title: str, body: str = "", icon: str = "") -> None:
    icon_html = (
        f'<div style="font-size:1.6rem;margin-bottom:0.5rem;opacity:0.5">{_esc(icon)}</div>'
        if icon
        else ""
    )
    body_html = f'<div class="fc-empty-body">{_esc(body)}</div>' if body else ""
    _write(
        f'<div class="fc-empty">{icon_html}'
        f'<div class="fc-empty-title">{_esc(title)}</div>{body_html}</div>'
    )


def note(text: str, tone: Tone = "neutral") -> None:
    """A quiet one-line caption, used instead of st.info for minor asides."""
    colour = tone_color(tone)
    _write(
        f'<div style="font-size:0.8rem;color:{colour};line-height:1.5;'
        f'margin-top:0.3rem">{_esc(text)}</div>'
    )


def caption(text: str) -> None:
    _write(
        f'<div style="font-size:0.78rem;color:var(--muted);line-height:1.5">{_esc(text)}</div>'
    )


def stat_line(pairs: list[tuple[str, str]]) -> None:
    """A horizontal run of label/value pairs for dense secondary detail."""
    cells = "".join(
        f'<div><div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;'
        f'color:var(--muted);font-weight:650">{_esc(label)}</div>'
        f'<div style="font-size:1rem;font-weight:650;margin-top:0.15rem;'
        f'font-variant-numeric:tabular-nums">{_esc(value)}</div></div>'
        for label, value in pairs
    )
    _write(f'<div style="display:flex;gap:2.2rem;flex-wrap:wrap">{cells}</div>')
