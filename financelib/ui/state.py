"""Page setup, caching and shared session state.

One place decides how data is loaded and when the cache is invalidated, so no
page has to think about it. Every write goes through :func:`mark_changed`,
which bumps a version counter that the cached loader is keyed on — that keeps
reads fast without ever showing a stale figure after a save.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from financelib.models import Dataset
from financelib.storage import (
    SAMPLES_DIR,
    Repository,
    StorageError,
    get_repository,
    resolve_data_dir,
)
from financelib.storage.json_store import copy_samples_into
from financelib.ui import theme

VERSION_KEY = "_data_version"
TOAST_KEY = "_pending_toast"


def get_repo() -> Repository:
    """A repository for the currently configured data directory.

    Deliberately not cached: constructing it is trivial, and caching it would
    hide a change of ``FINANCE_DATA_DIR`` behind a stale handle.
    """
    return get_repository()


def data_version() -> int:
    return st.session_state.get(VERSION_KEY, 0)


def mark_changed(message: str | None = None, icon: str = "✓") -> None:
    """Invalidate cached data after a write, optionally queueing a toast."""
    st.session_state[VERSION_KEY] = data_version() + 1
    if message:
        st.session_state[TOAST_KEY] = (message, icon)


@st.cache_data(show_spinner=False)
def _load_cached(version: int, location: str) -> Dataset:
    """``location`` is part of the cache key, not just documentation."""
    return get_repository(location).load()


def load_dataset() -> Dataset:
    """The current dataset, or an empty one if storage is unreadable.

    A storage failure is reported once, prominently, and the app stops rather
    than continuing with data it could not read.
    """
    try:
        return _load_cached(data_version(), str(resolve_data_dir()))
    except StorageError as exc:
        st.error(str(exc), icon="⚠")
        with st.expander("What to do about this"):
            st.markdown(
                f"""
Your data files live in `{resolve_data_dir()}`.

1. Open **Data & settings** and restore the most recent backup, or
2. Fix the file by hand — the error above names the exact line, or
3. Move the broken file aside and start fresh.

Nothing has been overwritten. The app will not save over a file it could
not read.
"""
            )
        st.stop()


def commit(action: Callable[[Repository], None], success: str | None = None) -> bool:
    """Run a write against the repository, reporting failure cleanly."""
    try:
        action(get_repo())
    except StorageError as exc:
        st.error(str(exc), icon="⚠")
        return False
    mark_changed(success)
    return True


def bootstrap(title: str = "Finance", icon: str = "◆") -> None:
    """Run once per script run, before navigation dispatches to a view.

    Streamlit only allows one ``set_page_config`` call per run, so the entry
    point owns it and individual views stay free of boilerplate.
    """
    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    theme.inject()
    flush_toasts()


def flush_toasts() -> None:
    pending = st.session_state.pop(TOAST_KEY, None)
    if pending:
        message, toast_icon = pending
        # Validate and replace the icon if it's not a valid emoji
        if toast_icon == "✓":
            toast_icon = "✅"  # Replace with a valid emoji
        st.toast(message, icon=toast_icon)


# ----------------------------------------------------------------------
# Shared controls
# ----------------------------------------------------------------------

#: Label to number of trailing months. ``None`` means all available history.
PERIODS: dict[str, int | None] = {
    "1M": 1,
    "3M": 3,
    "6M": 6,
    "1Y": 12,
    "3Y": 36,
    "All": None,
}


def period_selector(key: str, default: str = "1Y", options: list[str] | None = None) -> int | None:
    """Horizontal period picker returning a month count, or ``None`` for all."""
    labels = options or list(PERIODS)
    index = labels.index(default) if default in labels else len(labels) - 1
    choice = st.radio(
        "Period",
        labels,
        index=index,
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )
    return PERIODS[choice]


def trim(items: list, months: int | None) -> list:
    """Last ``months`` entries, or everything when ``months`` is ``None``."""
    if months is None:
        return items
    return items[-(months + 1):] if len(items) > months else items


def confirm_button(label: str, key: str, help_text: str = "") -> bool:
    """Two-step confirmation for destructive actions.

    Returns ``True`` only on the second press, so nothing irreversible
    happens on a single stray click.
    """
    armed_key = f"{key}__armed"
    if st.session_state.get(armed_key):
        col_confirm, col_cancel = st.columns(2)
        confirmed = col_confirm.button(
            "Confirm", key=f"{key}__yes", type="primary", width="stretch"
        )
        if col_cancel.button("Cancel", key=f"{key}__no", width="stretch"):
            st.session_state[armed_key] = False
            st.rerun()
        if confirmed:
            st.session_state[armed_key] = False
            return True
        return False

    if st.button(label, key=key, help=help_text or None, width="stretch"):
        st.session_state[armed_key] = True
        st.rerun()
    return False


def load_sample_data() -> bool:
    """Copy the synthetic sample set into the live data directory.

    Only ever offered when there is nothing to lose, so no confirmation step
    is needed. The sample figures are invented; nothing here is real.
    """
    try:
        copied = copy_samples_into(resolve_data_dir(), SAMPLES_DIR)
    except OSError as exc:
        st.error(f"Could not write the sample data: {exc}", icon="⚠")
        return False

    if not copied:
        st.error("The sample data files are missing from this installation.", icon="⚠")
        return False

    mark_changed("Sample data loaded")
    return True


def sample_data_button(key: str, label: str = "Load sample data") -> None:
    """Offer the sample set, with the caveat attached."""
    if st.button(label, key=key, width="stretch"):
        if load_sample_data():
            st.rerun()
