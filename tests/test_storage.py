"""Storage safety: atomic writes, corruption handling, backups, merging."""

from __future__ import annotations

import json

import pytest

from financelib.models import Account, Dataset, Goal, MonthlyRecord, Settings
from financelib.storage.base import StorageError
from financelib.storage.json_store import describe_integrity_issues, merge_records
from financelib.storage.migration import looks_like_legacy, migrate_directory


class TestRoundTrip:
    def test_empty_directory_loads_an_empty_dataset(self, repo):
        assert repo.load().is_empty

    def test_saves_and_reloads_everything(self, repo, dataset):
        repo.save(dataset)
        loaded = repo.load()
        assert [a.id for a in loaded.accounts] == [a.id for a in dataset.accounts]
        assert loaded.month_keys == dataset.month_keys
        assert loaded.months[0].contributions == dataset.months[0].contributions

    def test_months_are_stored_in_order(self, repo):
        repo.save_months(
            [MonthlyRecord(month="2026-03"), MonthlyRecord(month="2026-01")]
        )
        assert repo.load().month_keys == ["2026-01", "2026-03"]

    def test_settings_survive(self, repo):
        repo.save_settings(Settings(currency_symbol="$", emergency_fund_months=3))
        assert repo.load().settings.currency_symbol == "$"


class TestCorruption:
    def test_bad_json_raises_rather_than_returning_empty(self, repo):
        repo.save_months([MonthlyRecord(month="2026-01", income=100)])
        (repo.data_dir / "months.json").write_text("{not json", encoding="utf-8")

        with pytest.raises(StorageError) as error:
            repo.load()
        assert "months.json" in str(error.value)

    def test_wrong_shape_raises(self, repo):
        repo.data_dir.mkdir(parents=True, exist_ok=True)
        (repo.data_dir / "months.json").write_text(
            json.dumps({"months": [{"month": "nonsense"}]}), encoding="utf-8"
        )
        with pytest.raises(StorageError):
            repo.load()

    def test_status_reports_the_problem_instead_of_crashing(self, repo):
        repo.save_months([MonthlyRecord(month="2026-01", income=1)])
        (repo.data_dir / "months.json").write_text("[[[", encoding="utf-8")
        status = repo.status()
        assert status.issues

    def test_bare_list_documents_are_still_readable(self, repo):
        """Tolerate files written without the versioned envelope."""
        repo.data_dir.mkdir(parents=True, exist_ok=True)
        (repo.data_dir / "months.json").write_text(
            json.dumps([{"month": "2026-01", "income": 500}]), encoding="utf-8"
        )
        assert repo.load().months[0].income == 500

    def test_write_leaves_no_temporary_files_behind(self, repo, dataset):
        repo.save(dataset)
        assert not list(repo.data_dir.glob("*.tmp"))


class TestUpsert:
    def test_replaces_a_month_by_default(self, repo):
        repo.upsert_month(MonthlyRecord(month="2026-01", income=100, spending=50))
        repo.upsert_month(MonthlyRecord(month="2026-01", income=200))
        record = repo.load().record("2026-01")
        assert record.income == 200
        assert record.spending is None

    def test_merge_preserves_fields_not_supplied(self, repo):
        repo.upsert_month(MonthlyRecord(month="2026-01", income=100, spending=50))
        repo.upsert_month(MonthlyRecord(month="2026-01", balances={"isa": 900}), merge=True)
        record = repo.load().record("2026-01")
        assert record.income == 100
        assert record.spending == 50
        assert record.balances == {"isa": 900}

    def test_delete_removes_only_that_month(self, repo):
        repo.save_months(
            [MonthlyRecord(month="2026-01", income=1), MonthlyRecord(month="2026-02", income=2)]
        )
        repo.delete_month("2026-01")
        assert repo.load().month_keys == ["2026-02"]

    def test_account_upsert_is_idempotent(self, repo):
        account = Account(id="isa", name="ISA", category="investment")
        repo.upsert_account(account)
        repo.upsert_account(account)
        assert len(repo.load().accounts) == 1

    def test_deleting_an_account_detaches_it_from_goals(self, repo, dataset):
        repo.save(dataset)
        repo.delete_account("savings")
        goal = repo.load().goals[0]
        assert "savings" not in goal.account_ids

    def test_deleting_an_account_keeps_balances_by_default(self, repo, dataset):
        repo.save(dataset)
        repo.delete_account("savings")
        assert "savings" in repo.load().months[0].balances

    def test_purge_removes_balances_too(self, repo, dataset):
        repo.save(dataset)
        repo.delete_account("savings", purge_balances=True)
        assert "savings" not in repo.load().months[0].balances


class TestBackups:
    def test_no_backup_when_there_is_nothing_to_back_up(self, repo):
        assert repo.create_backup() is None

    def test_backup_and_restore_round_trip(self, repo, dataset):
        repo.save(dataset)
        backup = repo.create_backup("test")
        assert backup is not None

        repo.save_months([])
        assert repo.load().months == []

        restored = repo.restore_backup(backup.name)
        assert len(restored.months) == 3

    def test_restore_takes_its_own_backup_first(self, repo, dataset):
        repo.save(dataset)
        backup = repo.create_backup("first")
        repo.restore_backup(backup.name)
        assert len(repo.list_backups()) >= 2

    def test_restoring_a_missing_backup_raises(self, repo):
        with pytest.raises(StorageError):
            repo.restore_backup("nope.zip")

    def test_backups_are_listed_newest_first(self, repo, dataset):
        repo.save(dataset)
        repo.create_backup("one")
        repo.create_backup("two")
        backups = repo.list_backups()
        assert backups[0].created_at >= backups[-1].created_at


class TestBundles:
    def test_export_then_import_reproduces_the_dataset(self, repo, dataset):
        repo.save(dataset)
        bundle = repo.export_bundle()

        repo.save_months([])
        repo.import_bundle(bundle, replace=True)
        assert len(repo.load().months) == 3

    def test_import_merges_by_default(self, repo, dataset):
        repo.save(dataset)
        bundle = repo.export_bundle()

        repo.save_months([MonthlyRecord(month="2026-06", income=999)])
        repo.import_bundle(bundle)
        assert repo.load().month_keys == ["2026-01", "2026-02", "2026-03", "2026-06"]

    def test_rejects_a_file_that_is_not_an_export(self, repo):
        with pytest.raises(StorageError):
            repo.import_bundle({"something": "else"})


class TestMergeRecords:
    def test_absent_values_never_erase_known_values(self):
        existing = MonthlyRecord(month="2026-01", income=100, spending=80)
        incoming = MonthlyRecord(month="2026-01", balances={"isa": 5})
        merged = merge_records(existing, incoming)
        assert merged.income == 100
        assert merged.spending == 80
        assert merged.balances == {"isa": 5}


class TestUiState:
    def test_data_fingerprint_changes_when_source_files_change(self, tmp_path):
        from financelib.ui.state import data_fingerprint

        accounts = tmp_path / "accounts.json"
        accounts.write_text('{"schema_version": 2, "accounts": [{"id": "cash"}]}', encoding="utf-8")
        first = data_fingerprint(str(tmp_path))

        accounts.write_text('{"schema_version": 2, "accounts": []}', encoding="utf-8")
        second = data_fingerprint(str(tmp_path))

        assert first != second

    def test_supplied_values_win(self):
        merged = merge_records(
            MonthlyRecord(month="2026-01", income=100),
            MonthlyRecord(month="2026-01", income=250),
        )
        assert merged.income == 250

    def test_zero_is_treated_as_a_real_value(self):
        merged = merge_records(
            MonthlyRecord(month="2026-01", income=100),
            MonthlyRecord(month="2026-01", income=0),
        )
        assert merged.income == 0

    def test_dictionaries_are_combined_not_replaced(self):
        merged = merge_records(
            MonthlyRecord(month="2026-01", balances={"a": 1, "b": 2}),
            MonthlyRecord(month="2026-01", balances={"b": 20, "c": 30}),
        )
        assert merged.balances == {"a": 1, "b": 20, "c": 30}


class TestIntegrity:
    def test_flags_balances_for_unknown_accounts(self, accounts):
        data = Dataset(
            accounts=accounts, months=[MonthlyRecord(month="2026-01", balances={"ghost": 10})]
        )
        assert any("ghost" in issue for issue in describe_integrity_issues(data))

    def test_flags_categories_that_do_not_reconcile(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(
                    month="2026-01", spending=1_000, spending_categories={"Food": 400}
                )
            ],
        )
        assert describe_integrity_issues(data)

    def test_small_rounding_differences_are_tolerated(self, accounts):
        data = Dataset(
            accounts=accounts,
            months=[
                MonthlyRecord(
                    month="2026-01", spending=1_000, spending_categories={"Food": 1_000.40}
                )
            ],
        )
        assert not describe_integrity_issues(data)

    def test_flags_goals_without_a_target(self):
        data = Dataset(goals=[Goal(id="g", name="G", target_amount=0)])
        assert describe_integrity_issues(data)

    def test_clean_dataset_reports_nothing(self, dataset):
        assert describe_integrity_issues(dataset) == []


class TestMigration:
    def _write_legacy(self, path):
        path.mkdir(parents=True, exist_ok=True)
        (path / "accounts.json").write_text(
            json.dumps(
                {
                    "accounts": [
                        {"id": "ss_isa", "name": "S&S ISA", "type": "investment", "balance": 1_500},
                        {"id": "lisa", "name": "LISA", "type": "investment", "balance": 800, "lisa": True},
                    ],
                    "last_updated": "2026-02-01",
                }
            ),
            encoding="utf-8",
        )
        (path / "history.json").write_text(
            json.dumps(
                [
                    {"month": "2026-01", "balances": {"ss_isa": 1_000, "lisa": 600}},
                    {"month": "2026-02", "balances": {"ss_isa": 1_500, "lisa": 800}},
                ]
            ),
            encoding="utf-8",
        )
        (path / "contributions.json").write_text(
            json.dumps(
                [
                    {"date": "2026-02-05", "account_id": "ss_isa", "amount": 400},
                    {"date": "2026-02-20", "account_id": "ss_isa", "amount": 50},
                    {"date": "2026-02-10", "account_id": "lisa", "amount": 150},
                ]
            ),
            encoding="utf-8",
        )
        (path / "goals.json").write_text(
            json.dumps(
                [{"id": "home", "name": "Home", "kind": "accumulation", "target": 70_000, "accounts": ["lisa"]}]
            ),
            encoding="utf-8",
        )

    def test_detects_legacy_layout(self, tmp_path):
        self._write_legacy(tmp_path)
        assert looks_like_legacy(tmp_path)

    def test_ignores_a_directory_already_migrated(self, tmp_path):
        self._write_legacy(tmp_path)
        (tmp_path / "months.json").write_text("{}", encoding="utf-8")
        assert not looks_like_legacy(tmp_path)

    def test_folds_contributions_into_monthly_totals(self, tmp_path):
        self._write_legacy(tmp_path)
        dataset, report = migrate_directory(tmp_path)

        february = dataset.record("2026-02")
        assert february.contributions["ss_isa"] == 450
        assert february.contributions["lisa"] == 150
        assert report.contributions_folded == 3

    def test_carries_across_accounts_and_goals(self, tmp_path):
        self._write_legacy(tmp_path)
        dataset, report = migrate_directory(tmp_path)
        assert report.accounts == 2
        assert report.goals == 1
        assert dataset.account("lisa").lisa
        assert dataset.goals[0].target_amount == 70_000

    def test_leaves_the_original_files_alone(self, tmp_path):
        self._write_legacy(tmp_path)
        before = (tmp_path / "history.json").read_text(encoding="utf-8")
        migrate_directory(tmp_path)
        assert (tmp_path / "history.json").read_text(encoding="utf-8") == before

    def test_missing_files_produce_an_empty_report(self, tmp_path):
        dataset, report = migrate_directory(tmp_path)
        assert report.is_empty
        assert dataset.is_empty
