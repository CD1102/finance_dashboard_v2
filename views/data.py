"""Data and settings — import, export, backup, and how the app behaves.

Kept deliberately separate from the analytical pages so that housekeeping
never clutters the dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from financelib.formatting import file_size, month_label, pluralise
from financelib.importers import tabular
from financelib.models import DEFAULT_SPENDING_CATEGORIES, Settings, ValidationError
from financelib.storage import StorageError, resolve_data_dir
from financelib.storage.migration import looks_like_legacy, migrate_directory
from financelib.ui import components as ui
from financelib.ui.state import commit, confirm_button, get_repo, load_dataset, mark_changed

IMPORT_KEY = "import_state"


def render() -> None:
    dataset = load_dataset()

    ui.page_header(
        "Data and settings",
        "Where your figures live, how to get more in, and how to get them out.",
    )

    status_tab, import_tab, export_tab, settings_tab = st.tabs(
        ["Status", "Import", "Export and backup", "Settings"]
    )

    with status_tab:
        _status(dataset)
    with import_tab:
        _import(dataset)
    with export_tab:
        _export(dataset)
    with settings_tab:
        _settings(dataset)


# ----------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------


def _status(dataset) -> None:
    try:
        status = get_repo().status()
    except StorageError as exc:
        st.error(str(exc), icon="⚠")
        return

    ui.spacer(0.4)
    columns = st.columns(4)
    with columns[0]:
        ui.metric_card("Accounts", str(status.account_count), provenance="recorded")
    with columns[1]:
        ui.metric_card(
            "Months recorded",
            str(status.month_count),
            caption=(
                f"{month_label(status.first_month)} to {month_label(status.last_month)}"
                if status.first_month and status.last_month
                else "Nothing yet"
            ),
            provenance="recorded",
        )
    with columns[2]:
        ui.metric_card("Goals", str(status.goal_count), provenance="recorded")
    with columns[3]:
        ui.metric_card(
            "Backups",
            str(status.backup_count),
            caption=file_size(status.size_bytes) + " of data",
        )

    ui.spacer(0.8)
    with st.container(border=True):
        ui.caption("Storage")
        ui.stat_line(
            [
                ("Backend", status.backend.upper()),
                ("Writable", "Yes" if status.writable else "No"),
                (
                    "Last change",
                    status.last_modified.strftime("%d %b %Y, %H:%M")
                    if status.last_modified
                    else "—",
                ),
            ]
        )
        ui.spacer(0.5)
        st.code(status.location, language=None)
        ui.caption(
            "Set the FINANCE_DATA_DIR environment variable to point this somewhere else — "
            "a mounted volume in Docker, for instance."
        )

    if status.issues:
        ui.section("Things worth fixing")
        for issue in status.issues:
            st.warning(issue, icon="⚠")
    else:
        ui.spacer(0.6)
        ui.note("No problems found in your data.", tone="positive")

    _legacy_offer()


def _legacy_offer() -> None:
    data_dir = resolve_data_dir()
    if not looks_like_legacy(data_dir):
        return

    ui.section("Older data found")
    st.info(
        "This folder contains files from the previous version of the app "
        "(accounts.json, history.json, contributions.json). They can be converted "
        "into the current format. The original files are left untouched.",
        icon="ℹ",
    )

    if st.button("Preview conversion", key="legacy_preview"):
        dataset, report = migrate_directory(data_dir)
        st.session_state["legacy_preview"] = (dataset, report)

    preview = st.session_state.get("legacy_preview")
    if preview:
        converted, report = preview
        ui.stat_line(
            [
                ("Accounts", str(report.accounts)),
                ("Months", str(report.months)),
                ("Goals", str(report.goals)),
                ("Contributions folded in", str(report.contributions_folded)),
            ]
        )
        for warning in report.warnings:
            st.warning(warning, icon="⚠")

        ui.spacer(0.5)
        if confirm_button("Convert and save", key="legacy_commit"):
            if commit(lambda repo: repo.save(converted), "Converted your older data"):
                st.session_state.pop("legacy_preview", None)
                st.rerun()


# ----------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------


def _import(dataset) -> None:
    ui.spacer(0.4)
    st.markdown(
        "Bring in history from a spreadsheet. The file should have **one row per month** "
        "and a column for each figure you track."
    )
    ui.caption(
        "Nothing is written until you confirm at the last step, and your current data is "
        "backed up automatically before any import."
    )
    ui.spacer(0.6)

    uploaded = st.file_uploader(
        "Spreadsheet or CSV",
        type=["xlsx", "xls", "csv"],
        key="import_file",
        help="Your file is read in memory and never leaves this machine.",
    )

    if uploaded is None:
        st.session_state.pop(IMPORT_KEY, None)
        _import_guidance(dataset)
        return

    data = uploaded.getvalue()
    is_csv = uploaded.name.lower().endswith(".csv")

    sheet = None
    header_row = 0
    options = st.columns(2)
    if not is_csv:
        sheets = tabular.list_sheets(data)
        if sheets:
            sheet = options[0].selectbox("Sheet", sheets, key="import_sheet")
    header_row = options[1].number_input(
        "Header row",
        min_value=1,
        max_value=20,
        value=1,
        key="import_header",
        help="Which row holds the column names. Usually the first.",
    )

    try:
        table = tabular.read_table(data, uploaded.name, sheet, header_row=int(header_row) - 1)
    except ValidationError as exc:
        st.error(str(exc), icon="⚠")
        return

    if table.frame.empty:
        st.error("That sheet has no rows once blank lines are removed.", icon="⚠")
        return

    with st.expander(f"What the file looks like · {pluralise(table.row_count, 'row')}"):
        st.dataframe(table.frame.head(12), width="stretch")

    mapping = _mapping_editor(table, dataset)
    problems = mapping.validate()
    if problems:
        ui.spacer(0.5)
        for problem in problems:
            st.warning(problem, icon="⚠")
        return

    preview = tabular.build_preview(table, mapping, dataset)
    _import_preview(dataset, preview)


def _mapping_editor(table: tabular.SourceTable, dataset) -> tabular.ColumnMapping:
    ui.section("Match the columns", "Tell the app what each column means.")

    suggested = tabular.suggest_mapping(table.columns, dataset.accounts)
    account_labels = {a.name: a.id for a in dataset.accounts}
    categories = dataset.known_spending_categories()
    target_options = [""] + list(account_labels) + categories

    rows = []
    for assignment in suggested.assignments:
        target_label = ""
        if assignment.target:
            match = next(
                (name for name, id_ in account_labels.items() if id_ == assignment.target), ""
            )
            target_label = match or assignment.target
        rows.append(
            {
                "Column": assignment.column,
                "Means": tabular.ROLE_LABELS[assignment.role],
                "Which one": target_label,
                "Example": _example_value(table, assignment.column),
            }
        )

    edited = st.data_editor(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        key="import_mapping",
        column_config={
            "Column": st.column_config.TextColumn(disabled=True, width="medium"),
            "Means": st.column_config.SelectboxColumn(
                options=list(tabular.ROLE_LABELS.values()), required=True, width="medium"
            ),
            "Which one": st.column_config.SelectboxColumn(
                options=target_options,
                help="Needed for account balances, contributions and spending categories.",
                width="medium",
            ),
            "Example": st.column_config.TextColumn(disabled=True, width="small"),
        },
    )

    reverse_roles = {label: role for role, label in tabular.ROLE_LABELS.items()}
    assignments = []
    for _, row in edited.iterrows():
        role = reverse_roles.get(str(row["Means"]), "ignore")
        label = str(row["Which one"] or "")
        if role in ("balance", "contribution"):
            target = account_labels.get(label, "")
        elif role == "category":
            target = label or str(row["Column"])
        else:
            target = ""
        assignments.append(
            tabular.ColumnAssignment(column=str(row["Column"]), role=role, target=target)
        )

    return tabular.ColumnMapping(assignments=assignments)


def _example_value(table: tabular.SourceTable, column: str) -> str:
    try:
        series = table.frame[column].dropna()
    except KeyError:
        return ""
    if series.empty:
        return ""
    return str(series.iloc[0])[:20]


def _import_preview(dataset, preview: tabular.ImportPreview) -> None:
    ui.section("Check before importing")

    if not preview.is_importable:
        st.error(
            "No usable months were found. Check that the month column is the right one.",
            icon="⚠",
        )
        for issue in preview.issues[:5]:
            st.warning(issue.message, icon="⚠")
        return

    columns = st.columns(4)
    with columns[0]:
        ui.metric_card("New months", str(len(preview.new_months)), provenance="derived")
    with columns[1]:
        ui.metric_card(
            "Already recorded",
            str(len(preview.existing_months)),
            caption="You choose what happens to these",
            provenance="derived",
        )
    with columns[2]:
        ui.metric_card(
            "Rows skipped",
            str(preview.skipped_rows),
            caption="Blank rows or unreadable months",
            muted=not preview.skipped_rows,
        )
    with columns[3]:
        ui.metric_card(
            "Values skipped",
            str(len(preview.issues)),
            caption="Cells that were not numbers",
            muted=not preview.issues,
        )

    if preview.duplicate_months:
        ui.spacer(0.5)
        ui.note(
            f"{pluralise(len(preview.duplicate_months), 'month')} appeared more than once in the "
            "file and were combined.",
            tone="warning",
        )

    if preview.issues:
        with st.expander(f"Values that could not be read ({len(preview.issues)})"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Row": i.row, "Column": i.column, "Problem": i.message}
                        for i in preview.issues
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    ui.spacer(0.6)
    frame = preview.to_frame(dataset)
    st.dataframe(frame, width="stretch", hide_index=True)

    ui.spacer(0.6)
    mode_col, button_col = st.columns([2, 1])
    with mode_col:
        mode = st.radio(
            "For months already recorded",
            list(tabular.MERGE_MODE_LABELS),
            index=1,
            format_func=lambda key: tabular.MERGE_MODE_LABELS[key],
            key="import_mode",
            horizontal=False,
        )
    with button_col:
        ui.spacer(1.4)
        if confirm_button(
            f"Import {pluralise(len(preview.records), 'month')}", key="import_commit"
        ):
            try:
                result = tabular.apply_preview(get_repo(), preview, mode)
            except StorageError as exc:
                st.error(str(exc), icon="⚠")
                return
            mark_changed(
                f"Imported {result.created} new and updated {result.updated} month(s)"
            )
            st.rerun()


def _import_guidance(dataset) -> None:
    ui.spacer(0.8)
    with st.expander("What the file should look like"):
        st.markdown(
            "One row per month, with whatever columns you already keep. For example:"
        )
        example = pd.DataFrame(
            {
                "Month": ["2026-01", "2026-02", "2026-03"],
                "Income": [3200, 3200, 3450],
                "Spending": [2100, 1950, 2240],
                "S&S ISA": [14200, 15100, 15800],
                "Cash ISA": [8000, 8500, 9000],
            }
        )
        st.dataframe(example, width="stretch", hide_index=True)
        st.markdown(
            """
- The month column can be `2026-01`, `Jan 2026`, `01/2026` or a real date.
- Amounts may include `£`, commas, or brackets for negatives.
- Blank cells are left as "not recorded" rather than being treated as zero.
- You can import the same file again later; by default it fills gaps rather than
  overwriting what you have.
"""
        )

    ui.spacer(0.4)
    template = pd.DataFrame(
        {
            "Month": ["2026-01"],
            "Income": [0],
            "Spending": [0],
            **{account.name: [0] for account in dataset.accounts},
        }
    )
    st.download_button(
        "Download a blank template",
        template.to_csv(index=False).encode("utf-8"),
        file_name="finance-import-template.csv",
        mime="text/csv",
        disabled=not dataset.accounts,
        help=None if dataset.accounts else "Add some accounts first.",
    )


# ----------------------------------------------------------------------
# Export and backup
# ----------------------------------------------------------------------


def _export(dataset) -> None:
    ui.spacer(0.4)
    left, right = st.columns(2, gap="large")

    with left:
        with st.container(border=True):
            ui.caption("Export everything")
            st.markdown(
                "A single file containing your accounts, months, goals and settings. "
                "Import it back at any time, on any machine."
            )
            ui.spacer(0.5)
            try:
                bundle = get_repo().export_bundle()
            except StorageError as exc:
                st.error(str(exc), icon="⚠")
                return

            stamp = datetime.now().strftime("%Y%m%d")
            st.download_button(
                "Download JSON export",
                json.dumps(bundle, indent=2).encode("utf-8"),
                file_name=f"finance-export-{stamp}.json",
                mime="application/json",
                width="stretch",
            )

            frame = pd.DataFrame(
                [
                    {
                        "Month": record.month,
                        "Income": record.income,
                        "Spending": record.effective_spending,
                        **{
                            f"{dataset.account_name(a)} balance": v
                            for a, v in record.balances.items()
                        },
                        **{
                            f"{dataset.account_name(a)} paid in": v
                            for a, v in record.contributions.items()
                        },
                    }
                    for record in dataset.months
                ]
            )
            st.download_button(
                "Download months as CSV",
                frame.to_csv(index=False).encode("utf-8"),
                file_name=f"finance-months-{stamp}.csv",
                mime="text/csv",
                width="stretch",
                disabled=frame.empty,
            )
            ui.spacer(0.4)
            ui.note(
                "These files contain your real figures. Store them somewhere private.",
                tone="warning",
            )

    with right:
        with st.container(border=True):
            ui.caption("Restore from an export")
            incoming = st.file_uploader(
                "Export file", type=["json"], key="restore_upload", label_visibility="collapsed"
            )
            replace = st.checkbox(
                "Replace everything instead of merging",
                key="restore_replace",
                help="Merging keeps months you already have and fills in anything missing.",
            )
            if incoming is not None:
                try:
                    payload = json.loads(incoming.getvalue().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    st.error("That file is not readable JSON.", icon="⚠")
                else:
                    months = len(payload.get("months", []))
                    ui.note(f"Contains {pluralise(months, 'month')}.")
                    if confirm_button("Restore this file", key="restore_commit"):
                        if commit(
                            lambda repo: repo.import_bundle(payload, replace=replace),
                            "Restored from export",
                        ):
                            st.rerun()

    _backups()


def _backups() -> None:
    ui.section("Backups", "Taken automatically before every import or restore.")

    try:
        backups = get_repo().list_backups()
    except StorageError as exc:
        st.error(str(exc), icon="⚠")
        return

    make, _ = st.columns([1, 3])
    with make:
        if st.button("Back up now", width="stretch"):
            if commit(lambda repo: repo.create_backup("manual"), "Backup created"):
                st.rerun()

    if not backups:
        ui.spacer(0.5)
        ui.empty_state("No backups yet", "One is taken automatically before anything risky.")
        return

    ui.spacer(0.6)
    frame = pd.DataFrame(
        [
            {
                "Taken": backup.created_at.strftime("%d %b %Y, %H:%M"),
                "Name": backup.name,
                "Size": file_size(backup.size_bytes),
            }
            for backup in backups
        ]
    )
    st.dataframe(frame, width="stretch", hide_index=True)

    ui.spacer(0.4)
    pick, action = st.columns([2, 1])
    with pick:
        chosen = st.selectbox(
            "Restore a backup", [b.name for b in backups], key="backup_pick"
        )
    with action:
        ui.spacer(1.7)
        if confirm_button("Restore", key="backup_restore"):
            if commit(lambda repo: repo.restore_backup(chosen), f"Restored {chosen}"):
                st.rerun()

    ui.caption(
        "Restoring replaces your current files, but takes a backup of them first, so it "
        "can always be undone."
    )


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------


def _settings(dataset) -> None:
    ui.spacer(0.4)
    settings = dataset.settings

    with st.form("settings_form"):
        general, emergency = st.columns(2, gap="large")

        with general:
            st.markdown("**General**")
            symbol = st.text_input("Currency symbol", value=settings.currency_symbol, max_chars=3)

            st.markdown("**Default projection assumptions**")
            investment_return = st.number_input(
                "Investment return (% a year)",
                value=float(settings.default_investment_return),
                min_value=0.0,
                max_value=25.0,
                step=0.25,
            )
            cash_rate = st.number_input(
                "Cash interest (% a year)",
                value=float(settings.default_cash_rate),
                min_value=0.0,
                max_value=25.0,
                step=0.25,
            )
            inflation = st.number_input(
                "Inflation (% a year)",
                value=float(settings.default_inflation),
                min_value=0.0,
                max_value=25.0,
                step=0.25,
            )

        with emergency:
            st.markdown("**Emergency fund**")
            months = st.number_input(
                "Months of spending to cover",
                value=float(settings.emergency_fund_months),
                min_value=0.0,
                max_value=36.0,
                step=1.0,
                help="The target is this many months of your recent average spending.",
            )
            use_fixed = st.checkbox(
                "Use a fixed target instead",
                value=settings.emergency_fund_target is not None,
            )
            fixed_target = st.number_input(
                "Fixed target",
                value=float(settings.emergency_fund_target or 0.0),
                min_value=0.0,
                step=500.0,
                disabled=not use_fixed,
            )
            ui.caption(
                "Mark which accounts count toward this on the Accounts page."
            )

            st.markdown("**Spending categories**")
            categories = st.text_area(
                "One per line",
                value="\n".join(settings.spending_categories),
                height=180,
                help="These appear on the Monthly page. Categories already used in your "
                "data always remain available.",
            )

        saved = st.form_submit_button("Save settings", type="primary")

    if saved:
        updated = Settings(
            currency_symbol=symbol.strip() or "£",
            emergency_fund_months=months,
            emergency_fund_target=fixed_target if use_fixed else None,
            spending_categories=[
                line.strip() for line in categories.splitlines() if line.strip()
            ]
            or list(DEFAULT_SPENDING_CATEGORIES),
            default_investment_return=investment_return,
            default_cash_rate=cash_rate,
            default_inflation=inflation,
        )
        if commit(lambda repo: repo.save_settings(updated), "Settings saved"):
            st.rerun()

    _danger_zone(dataset)


def _danger_zone(dataset) -> None:
    ui.section("Clearing data")
    with st.container(border=True):
        ui.caption(
            "Removes every month, account and goal. A backup is taken first, so this can "
            "be undone from the Backups section."
        )
        ui.spacer(0.5)
        clear, _ = st.columns([1, 3])
        with clear:
            if confirm_button("Clear all data", key="clear_all"):

                def wipe(repo):
                    repo.create_backup("pre-clear")
                    repo.save_months([])
                    repo.save_accounts([])
                    repo.save_goals([])

                if commit(wipe, "All data cleared"):
                    st.rerun()


render()
