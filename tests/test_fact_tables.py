"""Fact-table save (UX-04): services.save_fact_table against a faked repository. The transaction
itself is tested in test_concurrency.FactTableTransactionTests."""
import unittest
from datetime import datetime
from unittest.mock import patch

from app import services
from app import repositories as repo

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


if __name__ == "__main__":
    unittest.main()
