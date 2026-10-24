"""Fact-table save (UX-04): services.save_fact_table against a faked repository, and source checks
on the procedure (sql/005), which can't run locally — the live smoke test is in
docs/fact-tables-handoff.md."""
import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app import db, services
from app import repositories as repo
from tests.test_concurrency import FakeSession

SQL = (Path(__file__).resolve().parents[1] / "sql/005_save_fact_table_proc.sql").read_text()
NAME = "AC.FINANCE.MRR"


def row(revision=1, by="tester", **fields):
    base = {k.upper(): None for k in services.FACT_EDITABLE}
    return {**base, "TABLE_NAME_FULL": NAME, "STATUS": "active", "REVISION_NO": revision,
            "UPDATED_BY": by, "UPDATED_AT": datetime(2026, 10, 23), **{k.upper(): v for k, v in fields.items()}}


def save(fields, expected=1, name=NAME, result=None):
    with patch.object(repo, "save_fact_table", return_value=result or
                      {"outcome": "committed", "table_name": NAME, "revision_no": (expected or 0) + 1}) as call:
        out = services.save_fact_table("tester", "op1", {"table_name": name, "expected_revision": expected,
                                                         "fields": fields})
    return out, call


class SaveFactTableTests(unittest.TestCase):
    def test_name_is_stored_upper_case_three_part(self):
        out, call = save({"grain": " one row per account "}, expected=None, name=" ac.finance.mrr ")
        self.assertEqual((out.status, out.revision_no), ("saved", 1))
        sent = call.call_args.args[2]
        self.assertEqual((sent["table_name"], sent["fields"]["grain"], sent["fields"]["status"]),
                         (NAME, "one row per account", "active"))

    def test_two_part_name_or_bad_status_writes_nothing(self):
        for name, fields in (("FINANCE.MRR", {}), ("AC.FINANCE.MRR; DROP", {}), (NAME, {"status": "gone"})):
            out, call = save(fields, name=name)
            self.assertEqual(out.status, "invalid", name)
            call.assert_not_called()

    def test_create_of_registered_name_is_marked_on_the_name(self):
        out, _ = save({}, expected=None, result={"outcome": "exists", "table_name": NAME})
        self.assertEqual((out.status, out.problems[0]["field"]), ("invalid", "table_name"))

    def test_conflict_names_who_and_which_fields(self):
        with patch.object(repo, "get_fact_table", return_value=row(2, by="ALICE", grain="daily")), \
             patch.object(repo, "snapshot_at", return_value=row(1)) as snap:
            out, _ = save({"grain": "weekly"}, result={"outcome": "conflict", "table_name": NAME})
        snap.assert_called_once_with("fact_table_core", NAME, 1)
        self.assertEqual((out.status, out.conflict["changed_fields"]), ("conflict", ["Grain"]))
        self.assertIn("ALICE changed AC.FINANCE.MRR (Grain)", out.message)

    def test_replay_reports_the_revision_that_landed(self):
        with patch.object(repo, "get_fact_table", return_value=row(2)):
            out, _ = save({}, result={"outcome": "replayed", "table_name": NAME})
        self.assertEqual((out.status, out.revision_no), ("saved", 2))

    def test_no_change_keeps_the_revision(self):
        out, _ = save({}, expected=4, result={"outcome": "no_change", "table_name": NAME, "revision_no": 4})
        self.assertEqual((out.status, out.revision_no), ("no_change", 4))

    def test_unconfirmed_save_keeps_the_draft(self):
        with patch.object(repo, "save_fact_table", side_effect=RuntimeError("down")):
            out = services.save_fact_table("tester", "op1", {"table_name": NAME, "fields": {}})
        self.assertEqual(out.status, "failed")
        self.assertIn("saving again is safe", out.message)


class RepositoryCallTests(unittest.TestCase):
    def setUp(self):
        db._state.clear()
        self.addCleanup(db._state.clear)

    def test_one_call_with_nulls_for_blanks_and_tag(self):
        s = FakeSession(rows={"CALL": [[json.dumps({"outcome": "committed", "revision_no": 2})]]})
        with patch.object(db, "session", return_value=s):
            repo.save_fact_table("op1", "viewer", {"table_name": NAME, "expected_revision": 1,
                                                   "fields": {"grain": "", "status": "active"}}, "why")
        self.assertEqual(s.statements, ["CALL AI_PLATFORM.WORKBENCH.save_fact_table(?)"])
        req = json.loads(s.calls[0][1][0])
        self.assertEqual((req["actor"], req["change_note"], req["table"]["fields"]["grain"]), ("viewer", "why", None))
        tag = json.loads(s.results[0].collect.call_args.kwargs["statement_params"]["QUERY_TAG"])
        self.assertEqual((tag["op"], tag["record_id"]), ("fact_table.save", NAME))


class ProcedureSourceTests(unittest.TestCase):
    def body(self):
        return SQL.split("$$")[1]

    def test_invariants_are_present(self):
        for needle in ("EXECUTE AS OWNER", "revision_no = :v_exp", "OBJECT_CONSTRUCT_KEEP_NULL(*)",
                       "WHERE NOT EXISTS", "'fact_table_core'", "'fact_table.save'", "'exists'",
                       "'conflict'", "'replayed'", "'committed'", "'no_change'", "'rolled_back'",
                       "BEGIN TRANSACTION", "COMMIT", "ROLLBACK", "TO ROLE WORKBENCH_APP"):
            self.assertIn(needle, SQL)
        self.assertNotIn("CURRENT_USER", self.body())

    def test_every_name_is_fully_qualified(self):
        targets = re.findall(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([\w.]+)", self.body())
        self.assertTrue(targets)
        for name in targets:
            self.assertTrue(name.startswith("AI_PLATFORM.WORKBENCH."), name)

    def test_every_editable_field_is_compared_and_written(self):
        for f in services.FACT_EDITABLE:
            self.assertIn(f"r.j:{f}::VARCHAR", self.body())
            self.assertIn(f"{f} = r.j:{f}::VARCHAR", self.body())


if __name__ == "__main__":
    unittest.main()
