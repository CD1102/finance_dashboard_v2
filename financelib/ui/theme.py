"""Visual system: colour tokens and global CSS.

Everything visual is defined once here so that pages never hand-roll styles.
Both a dark and a light palette are provided and selected from Streamlit's own
theme setting, so the app follows the user's preference rather than forcing a
look.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from financelib.models import CASH, INVESTMENT, LIABILITY, OTHER, PENSION, PROPERTY


@dataclass(frozen=True)
class Palette:
    name: str
    background: str
    surface: str
    surface_raised: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_soft: str
    positive: str
    negative: str
    warning: str
    info: str
    grid: str
    hero_from: str
    hero_to: str
    hero_glow: str


DARK = Palette(
    name="dark",
    background="#0A0E14",
    surface="#131923",
    surface_raised="#1A212D",
    border="#232C3A",
    border_strong="#313D4F",
    text="#E8EDF4",
    text_muted="#8A96A8",
    text_subtle="#616E80",
    accent="#3DDC97",
    accent_soft="rgba(61,220,151,0.12)",
    positive="#3DDC97",
    negative="#FF6B6B",
    warning="#FFB86B",
    info="#5AC8FA",
    grid="#1C2431",
    hero_from="#122A22",
    hero_to="#0C131B",
    hero_glow="rgba(61,220,151,0.22)",
)

LIGHT = Palette(
    name="light",
    background="#F6F8FB",
    surface="#FFFFFF",
    surface_raised="#FFFFFF",
    border="#E2E8F0",
    border_strong="#CBD5E1",
    text="#0F172A",
    text_muted="#64748B",
    text_subtle="#94A3B8",
    accent="#0F9D6B",
    accent_soft="rgba(15,157,107,0.10)",
    positive="#0F9D6B",
    negative="#D93A3A",
    warning="#B45309",
    info="#0369A1",
    grid="#EEF2F7",
    hero_from="#E8F7F0",
    hero_to="#FFFFFF",
    hero_glow="rgba(15,157,107,0.14)",
)

CATEGORY_COLORS: dict[str, str] = {
    INVESTMENT: "#3DDC97",
    CASH: "#5AC8FA",
    PENSION: "#A78BFA",
    PROPERTY: "#F0A868",
    OTHER: "#94A3B8",
    LIABILITY: "#FF6B6B",
}

#: Ordered palette for charts that need arbitrary distinct series.
SERIES_COLORS: tuple[str, ...] = (
    "#3DDC97",
    "#5AC8FA",
    "#A78BFA",
    "#F0A868",
    "#FF6B9D",
    "#FFD166",
    "#7DD3FC",
    "#C4B5FD",
    "#94A3B8",
)

CATEGORY_ICONS: dict[str, str] = {
    INVESTMENT: "trending_up",
    CASH: "savings",
    PENSION: "account_balance",
    PROPERTY: "home",
    OTHER: "category",
    LIABILITY: "credit_card",
}


def active_palette() -> Palette:
    """The palette matching Streamlit's current theme."""
    try:
        base = st.get_option("theme.base") or "dark"
    except Exception:  # noqa: BLE001 - option lookup can fail outside a script run
        base = "dark"
    return LIGHT if str(base).lower() == "light" else DARK


def _css(p: Palette) -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
    --bg: {p.background};
    --surface: {p.surface};
    --surface-raised: {p.surface_raised};
    --border: {p.border};
    --border-strong: {p.border_strong};
    --text: {p.text};
    --muted: {p.text_muted};
    --subtle: {p.text_subtle};
    --accent: {p.accent};
    --accent-soft: {p.accent_soft};
    --positive: {p.positive};
    --negative: {p.negative};
    --warning: {p.warning};
    --info: {p.info};
    --radius-lg: 16px;
    --radius-md: 12px;
    --radius-sm: 8px;
}}

html, body, [class*="st-"], button, input, textarea, select {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-feature-settings: 'tnum' 1, 'cv05' 1;
}}

/* Without this, the rule above wins over the icon font and every Material
   ligature renders as literal text overlapping its label. */
span[data-testid="stIconMaterial"],
[class*="material-symbols"],
.material-symbols-rounded {{
    font-family: 'Material Symbols Rounded' !important;
    font-feature-settings: 'liga' !important;
}}

#MainMenu, footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}

.block-container {{
    padding-top: 2.4rem;
    padding-bottom: 4rem;
    max-width: 1340px;
}}

/* ---------------------------------------------------------------- Typography */

h1, h2, h3, h4 {{
    font-weight: 700 !important;
    letter-spacing: -0.021em;
    color: var(--text);
}}
h1 {{ font-size: 1.8rem !important; line-height: 1.2; }}
h2 {{ font-size: 1.3rem !important; }}
h3 {{ font-size: 1.05rem !important; }}

/* ---------------------------------------------------------------- Sidebar */

section[data-testid="stSidebar"] {{
    background: var(--surface);
    border-right: 1px solid var(--border);
}}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1.6rem; }}

/* ---------------------------------------------------------------- Page header */

.fc-page-head {{
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.4rem;
}}
.fc-page-title {{
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: -0.024em;
    color: var(--text);
    line-height: 1.15;
}}
.fc-page-sub {{
    color: var(--muted);
    font-size: 0.9rem;
    margin-top: 0.3rem;
    max-width: 62ch;
    line-height: 1.5;
}}

.fc-eyebrow {{
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--subtle);
}}

.fc-section {{ margin: 1.9rem 0 0.85rem 0; }}
.fc-section-title {{
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.01em;
}}
.fc-section-sub {{ font-size: 0.82rem; color: var(--muted); margin-top: 0.15rem; }}

.fc-rule {{ height: 1px; background: var(--border); margin: 1.6rem 0; border: 0; }}

/* ---------------------------------------------------------------- Hero */

.fc-hero {{
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 1.7rem 1.9rem;
    background:
        radial-gradient(900px circle at 88% -30%, {p.hero_glow}, transparent 62%),
        linear-gradient(145deg, {p.hero_from} 0%, {p.hero_to} 100%);
}}
.fc-hero-label {{
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: var(--muted);
}}
.fc-hero-value {{
    font-size: 3.1rem;
    font-weight: 800;
    letter-spacing: -0.042em;
    line-height: 1.02;
    margin-top: 0.35rem;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}}
.fc-hero-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.55rem 1.1rem;
    margin-top: 0.85rem;
}}
.fc-hero-delta {{
    display: inline-flex;
    align-items: center;
    gap: 0.38rem;
    font-size: 0.92rem;
    font-weight: 650;
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
    font-variant-numeric: tabular-nums;
}}
.fc-hero-note {{ color: var(--muted); font-size: 0.85rem; }}

.tone-positive {{ color: var(--positive); background: {p.accent_soft}; }}
.tone-negative {{ color: var(--negative); background: rgba(255,107,107,0.12); }}
.tone-neutral  {{ color: var(--muted);   background: rgba(138,150,168,0.12); }}
.tone-warning  {{ color: var(--warning); background: rgba(255,184,107,0.12); }}

/* ---------------------------------------------------------------- Metric cards */

.fc-card {{
    border: 1px solid var(--border);
    background: var(--surface);
    border-radius: var(--radius-lg);
    padding: 1.05rem 1.15rem;
    height: 100%;
    transition: border-color 140ms ease, transform 140ms ease;
}}
.fc-card:hover {{ border-color: var(--border-strong); }}

.fc-metric-label {{
    font-size: 0.72rem;
    font-weight: 650;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 0.35rem;
}}
.fc-metric-value {{
    font-size: 1.55rem;
    font-weight: 700;
    letter-spacing: -0.028em;
    color: var(--text);
    margin-top: 0.3rem;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}}
.fc-metric-value.is-muted {{ color: var(--subtle); font-weight: 600; }}
.fc-metric-foot {{
    margin-top: 0.42rem;
    font-size: 0.78rem;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
}}
.fc-metric-delta {{ font-weight: 650; font-variant-numeric: tabular-nums; }}
.fc-delta-positive {{ color: var(--positive); }}
.fc-delta-negative {{ color: var(--negative); }}
.fc-delta-neutral  {{ color: var(--muted); }}

.fc-bar-track {{
    height: 5px;
    border-radius: 999px;
    background: var(--border);
    margin-top: 0.7rem;
    overflow: hidden;
}}
.fc-bar-fill {{ height: 100%; border-radius: 999px; }}

/* ---------------------------------------------------------------- Allocation */

.fc-alloc-row {{
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.52rem 0;
    border-bottom: 1px solid var(--border);
}}
.fc-alloc-row:last-child {{ border-bottom: 0; }}
.fc-alloc-dot {{ width: 9px; height: 9px; border-radius: 3px; flex: none; }}
.fc-alloc-name {{ flex: 1; font-size: 0.87rem; color: var(--text); font-weight: 550; }}
.fc-alloc-amount {{ font-size: 0.87rem; font-weight: 650; font-variant-numeric: tabular-nums; }}
.fc-alloc-pct {{
    font-size: 0.78rem;
    color: var(--muted);
    width: 3.2rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
}}

/* ---------------------------------------------------------------- Insights */

.fc-insight {{
    display: flex;
    gap: 0.75rem;
    padding: 0.7rem 0;
    border-bottom: 1px solid var(--border);
}}
.fc-insight:last-child {{ border-bottom: 0; }}
.fc-insight-mark {{
    width: 3px;
    border-radius: 999px;
    flex: none;
    margin: 0.15rem 0;
}}
.fc-insight-body {{ flex: 1; }}
.fc-insight-text {{ font-size: 0.89rem; color: var(--text); line-height: 1.5; }}
.fc-insight-detail {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.22rem; }}

/* ---------------------------------------------------------------- Chips */

.fc-chip {{
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.055em;
    text-transform: uppercase;
    padding: 0.16rem 0.45rem;
    border-radius: 5px;
    border: 1px solid var(--border-strong);
    color: var(--subtle);
    white-space: nowrap;
}}
.fc-chip-recorded   {{ color: var(--info);     border-color: rgba(90,200,250,0.35); }}
.fc-chip-derived    {{ color: var(--muted); }}
.fc-chip-assumption {{ color: var(--warning);  border-color: rgba(255,184,107,0.35); }}

/* ---------------------------------------------------------------- Goals */

.fc-goal-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 0.6rem; }}
.fc-goal-name {{ font-size: 0.97rem; font-weight: 650; color: var(--text); }}
.fc-goal-pct  {{ font-size: 0.97rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
.fc-goal-amounts {{
    font-size: 0.83rem;
    color: var(--muted);
    margin-top: 0.15rem;
    font-variant-numeric: tabular-nums;
}}
.fc-goal-foot {{
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    font-size: 0.78rem;
    color: var(--muted);
    margin-top: 0.6rem;
}}

/* ---------------------------------------------------------------- Empty state */

.fc-empty {{
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    padding: 2.4rem 1.6rem;
    text-align: center;
    background: var(--surface);
}}
.fc-empty-title {{ font-size: 1.02rem; font-weight: 650; color: var(--text); }}
.fc-empty-body {{
    font-size: 0.87rem;
    color: var(--muted);
    margin: 0.4rem auto 0;
    max-width: 48ch;
    line-height: 1.55;
}}

/* ---------------------------------------------------------------- Streamlit overrides */

div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: var(--radius-lg) !important;
    border-color: var(--border) !important;
    background: var(--surface);
}}

.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: 0.86rem;
    min-height: 2.4rem;
    border-color: var(--border-strong);
    transition: border-color 120ms ease, background 120ms ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: var(--accent); }}

div[data-testid="stPopover"] button {{ border-radius: var(--radius-sm); font-weight: 600; }}

div[data-baseweb="tab-list"] {{ gap: 0.3rem; border-bottom: 1px solid var(--border); }}
button[data-baseweb="tab"] {{ font-weight: 600; font-size: 0.87rem; }}

div[role="radiogroup"] label {{ font-size: 0.85rem; }}

[data-testid="stMetricValue"] {{
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.025em;
}}
[data-testid="stMetricLabel"] {{
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    font-weight: 650;
}}

[data-testid="stDataFrame"] {{ border-radius: var(--radius-md); overflow: hidden; }}
[data-testid="stExpander"] details {{
    border-radius: var(--radius-md);
    border-color: var(--border);
    background: var(--surface);
}}
[data-testid="stProgress"] > div > div {{ height: 7px; border-radius: 999px; }}

div[data-testid="stAlert"] {{ border-radius: var(--radius-md); font-size: 0.87rem; }}

.stSelectbox div[data-baseweb="select"] > div,
.stNumberInput div[data-baseweb="input"],
.stTextInput div[data-baseweb="input"] {{
    border-radius: var(--radius-sm);
    border-color: var(--border-strong);
}}

/* Tighten the gap Plotly leaves above charts inside cards. */
.stPlotlyChart {{ margin-top: -0.35rem; }}

@media (max-width: 900px) {{
    .fc-hero-value {{ font-size: 2.3rem; }}
    .block-container {{ padding-top: 1.4rem; }}
}}
</style>
"""


def inject() -> None:
    """Apply the global stylesheet. Safe to call on every page."""
    st.markdown(_css(active_palette()), unsafe_allow_html=True)


def category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS[OTHER])


def series_color(index: int) -> str:
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def tone_color(tone: str) -> str:
    p = active_palette()
    return {
        "positive": p.positive,
        "negative": p.negative,
        "warning": p.warning,
        "neutral": p.text_muted,
        "info": p.info,
    }.get(tone, p.text_muted)
