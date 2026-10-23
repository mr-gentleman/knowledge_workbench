"""Physical implementations (SQL): repository and service rules for add, edit, conflict, retry."""
import unittest
from datetime import datetime
from unittest.mock import patch

from test_concurrency import FakeSession, fresh_state

from app import db, services
from app import repositories as repo


def calc_row(calc_id, sql, disambig=None, revision=1, is_default=False, by="tester"):
    return dict(CALC_ID=calc_id, ORIGIN_CANDIDATE_ID=1, METRIC_ID=None, SQL_TEXT=sql,
                SOURCE_TABLE=None, DISAMBIG=disambig, IS_DEFAULT=is_default, STATUS="active",
                REVISION_NO=revision, VALIDATED_REVISION_NO=None, VALIDATION_STATUS=None,
                UPDATED_BY=by, UPDATED_AT=datetime(2026, 10, 23))


class CalcRepositoryTests(unittest.TestCase):
    def setUp(self):
        fresh_state(self)

    def test_create_links_to_candidate_and_snapshots(self):
        s = FakeSession(rows={"SELECT calc_id FROM": []})
        with patch.object(db, "session", return_value=s):
            self.assertTrue(repo.insert_calc(9, 1, {"sql_text": "SELECT 1"}, True, "tester"))
        text, params = next(c for c in s.calls if "INSERT INTO AI_PLATFORM.WORKBENCH.metric_calc" in c[0])
        self.assertIn("origin_candidate_id", text)
        self.assertNotIn("metric_id", text)  # authored with a candidate → metric_id stays NULL
        self.assertEqual(params[:2], [9, 1])
        self.assertIn("sme", params)
        snap = next(p for t, p in s.calls if "INTO AI_PLATFORM.WORKBENCH.revision" in t)
        self.assertEqual(snap[:2], ["metric_calc", "create"])
        self.assertIn('"op": "calc.create"', s.tags[0])
        self.assertEqual(s.op_log()[0][4], "committed")

    def test_retried_create_with_same_id_inserts_nothing(self):
        s = FakeSession(rows={"SELECT calc_id FROM": [[9]]})
        with patch.object(db, "session", return_value=s):
            self.assertFalse(repo.insert_calc(9, 1, {"sql_text": "SELECT 1"}, True, "tester"))
        self.assertFalse(any("INSERT INTO AI_PLATFORM.WORKBENCH.metric_calc" in q for q in s.statements))
        self.assertEqual(s.op_log()[0][4], "replayed")

    def test_stale_edit_is_a_conflict_without_snapshot(self):
        s = FakeSession(rows={"UPDATE": [[0]]})
        with patch.object(db, "session", return_value=s), self.assertRaises(repo.StaleEdit):
            repo.update_calc(9, 1, {"sql_text": "SELECT 2"}, "tester")
        self.assertFalse(any("INTO AI_PLATFORM.WORKBENCH.revision" in q for q in s.statements))
        self.assertEqual(s.op_log()[0][4], "conflict")


    def test_retire_is_versioned_and_snapshotted(self):
        s = FakeSession()
        with patch.object(db, "session", return_value=s):
            self.assertEqual(repo.retire_calc(9, 1, "tester"), 2)
        text, params = next(c for c in s.calls if c[0].lstrip().startswith("UPDATE"))
        self.assertIn("status = 'retired'", text)
        self.assertEqual(params[1:], [9, 1])
        snap = next(p for t, p in s.calls if "INTO AI_PLATFORM.WORKBENCH.revision" in t)
        self.assertEqual(snap[:2], ["metric_calc", "retire"])

    def test_retire_of_a_changed_pi_is_a_conflict(self):
        s = FakeSession(rows={"UPDATE": [[0]]})
        with patch.object(db, "session", return_value=s), self.assertRaises(repo.StaleEdit):
            repo.retire_calc(9, 1, "tester")
        self.assertFalse(any("INTO AI_PLATFORM.WORKBENCH.revision" in q for q in s.statements))

class CalcServiceTests(unittest.TestCase):
    def test_first_pi_is_default_and_needs_no_label(self):
        with patch.object(repo, "insert_calc", return_value=True) as insert:
            out = services.save_new_calc(1, 9, {"sql_text": " SELECT 1 "}, 0, "tester")
        self.assertTrue(out.ok)
        self.assertEqual(insert.call_args.args[2]["sql_text"], "SELECT 1")
        self.assertTrue(insert.call_args.args[3])  # is_default

    def test_second_pi_needs_a_label_and_is_not_default(self):
        with patch.object(repo, "insert_calc", return_value=True) as insert:
            self.assertFalse(services.save_new_calc(1, 9, {"sql_text": "SELECT 1"}, 1, "tester").ok)
            insert.assert_not_called()
            self.assertTrue(services.save_new_calc(1, 9, {"sql_text": "SELECT 1", "disambig": "monthly"},
                                                   1, "tester").ok)
        self.assertFalse(insert.call_args.args[3])

    def test_empty_sql_is_refused(self):
        self.assertFalse(services.save_new_calc(1, 9, {"sql_text": "  "}, 0, "tester").ok)

    def test_replayed_create_with_newer_content_says_so(self):
        with patch.object(repo, "insert_calc", return_value=False), \
                patch.object(repo, "get_calc", return_value=calc_row(9, "SELECT 1")):
            same = services.save_new_calc(1, 9, {"sql_text": "SELECT 1"}, 0, "tester")
            newer = services.save_new_calc(1, 9, {"sql_text": "SELECT 2"}, 0, "tester")
        self.assertTrue(same.ok and not same.warnings)
        self.assertTrue(newer.ok and newer.warnings)

    def test_edit_saves_against_the_opened_revision(self):
        with patch.object(repo, "update_calc", return_value=2) as update:
            out = services.save_calc_edit(calc_row(9, "SELECT 1"), {"sql_text": "SELECT 2"}, 0, "tester")
        self.assertTrue(out.ok)
        self.assertEqual(out.revision_no, 2)
        self.assertEqual(update.call_args.args[:2], (9, 1))

    def test_unchanged_edit_writes_nothing(self):
        with patch.object(repo, "update_calc") as update:
            out = services.save_calc_edit(calc_row(9, "SELECT 1"), {"sql_text": "SELECT 1 "}, 0, "tester")
        self.assertEqual(out.message, "No changes to save.")
        update.assert_not_called()

    def test_conflict_returns_theirs_and_what_changed(self):
        theirs = calc_row(9, "SELECT gabe", revision=2, by="gabe")
        with patch.object(repo, "update_calc", side_effect=repo.StaleEdit(9)), \
                patch.object(repo, "get_calc", return_value=theirs):
            out = services.save_calc_edit(calc_row(9, "SELECT 1"), {"sql_text": "SELECT mine"}, 0, "tester")
        self.assertFalse(out.ok)
        self.assertEqual(out.latest, theirs)
        self.assertIn("gabe", out.message)
        self.assertIn("Changed: SQL", out.message)

    def test_keep_mine_keeps_their_untouched_fields(self):
        base = calc_row(9, "SELECT 1")
        theirs = calc_row(9, "SELECT 1", revision=2)
        theirs["SOURCE_TABLE"] = "AC.FIN.ARR"
        mine = {"sql_text": "SELECT mine", "source_table": None, "disambig": None}
        self.assertEqual(services.keep_mine(mine, base, theirs),
                         {"sql_text": "SELECT mine", "source_table": "AC.FIN.ARR", "disambig": None})

    def test_validation_counts_only_for_the_checked_revision(self):
        row = calc_row(9, "SELECT 1", revision=2)
        row.update(VALIDATION_STATUS="passed", VALIDATED_REVISION_NO=2)
        self.assertEqual(services.validation_state(row), "✓ Runs · rev 2")
        row["REVISION_NO"] = 3
        self.assertEqual(services.validation_state(row), "Not run")


if __name__ == '__main__':
    unittest.main()
