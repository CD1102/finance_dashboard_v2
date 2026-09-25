"""Smoke tests: every page must render without raising.

These drive the real Streamlit runtime through ``AppTest``, so they catch the
class of mistake unit tests cannot — a bad widget key, a missing import, a
layout call with the wrong argument.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
SAMPLES = ROOT / "data" / "samples"

PAGES = [
    "views/overview.py",
    "views/monthly.py",
    "views/accounts.py",
    "views/history.py",
    "views/goals.py",
    "views/projections.py",
    "views/data.py",
]


@pytest.fixture
def populated_dir(tmp_path, monkeypatch) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("accounts.json", "months.json", "goals.json", "settings.json"):
        shutil.copyfile(SAMPLES / name, data_dir / name)
    monkeypatch.setenv("FINANCE_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture
def empty_dir(tmp_path, monkeypatch) -> Path:
    data_dir = tmp_path / "empty"
    data_dir.mkdir()
    monkeypatch.setenv("FINANCE_DATA_DIR", str(data_dir))
    return data_dir


def run(page: str | None = None) -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    if page:
        app.switch_page(page)
    app.run()
    return app


def assert_clean(app: AppTest, page: str) -> None:
    assert not app.exception, f"{page} raised: {[e.value for e in app.exception]}"
    assert not app.error, f"{page} showed an error: {[e.value for e in app.error]}"


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_data(populated_dir, page):
    assert_clean(run(page), page)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_with_no_data_at_all(empty_dir, page):
    """Empty states must appear instead of exceptions on a fresh install."""
    assert_clean(run(page), page)


def test_overview_shows_net_worth(populated_dir):
    app = run("views/overview.py")
    rendered = " ".join(block.value for block in app.markdown)
    assert "Total net worth" in rendered


def test_first_run_offers_a_way_forward(empty_dir):
    app = run("views/overview.py")
    labels = [button.label for button in app.button]
    assert any("sample data" in label.lower() for label in labels)


def test_corrupt_data_is_reported_not_crashed(tmp_path, monkeypatch):
    data_dir = tmp_path / "broken"
    data_dir.mkdir()
    (data_dir / "months.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("FINANCE_DATA_DIR", str(data_dir))

    app = run()
    assert not app.exception
    assert app.error, "A corrupt file should surface a readable error"
