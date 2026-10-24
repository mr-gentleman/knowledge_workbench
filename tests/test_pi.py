"""Metric page save (DEC-020): the contract's acceptance list, driven through services.save_metric.

The procedure (sql/004) can't run locally. Store below is an in-memory stand-in with the same
contract (outcomes, all-or-nothing, replay markers); the SQL itself gets source checks and the live
smoke test in docs/save-proc-handoff.md.
"""
import copy
import re
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app import services
from app import repositories as repo

SQL = (Path(__file__).resolve().parents[1] / "sql/004_save_metric_proc.sql").read_text()


def calc_row(calc_id, sql, disambig=None, revision=1, is_default=False, by="tester", status="active"):
    return dict(CALC_ID=calc_id, ORIGIN_CANDIDATE_ID=1, METRIC_ID=None, SQL_TEXT=sql,
                SOURCE_TABLE=None, DISAMBIG=disambig, IS_DEFAULT=is_default, STATUS=status,
                REVISION_NO=revision, VALIDATED_REVISION_NO=None, VALIDATION_STATUS=None,
                UPDATED_BY=by, UPDATED_AT=datetime(2026, 10, 23))


class Store:
    """Rows + revisions + op_log, and save_metric with the procedure's contract."""

    def __init__(self):
        self.cand = dict(CANDIDATE_ID=1, FULL_NAME="CSAT", DESCRIPTION="Satisfaction", DISAMBIG=None,
                         DEPARTMENT=None, CATEGORY=None, STATUS="open", REVISION_NO=1,
                         UPDATED_BY="tester", UPDATED_AT=datetime(2026, 10, 23))
        self.calcs = {7: calc_row(7, "SELECT 1", "daily", is_default=True),
                      8: calc_row(8, "SELECT 2", "monthly")}
        self.revisions = [("metric_candidate", 1, 1, copy.deepcopy(self.cand))] + [
            ("metric_calc", i, 1, copy.deepcopy(r)) for i, r in self.calcs.items()]
        self.op_log, self.lose_next_ack = [], False

    def save_metric(self, op_id, actor, cand, calcs, note=None, check_name=None):
        if any(o == (op_id, "committed") for o in self.op_log) or any(
                c["expected_revision"] is None and c["calc_id"] in self.calcs for c in calcs):
            self.op_log.append((op_id, "replayed"))
            return {"outcome": "replayed", "candidate_id": 1}
        f = cand["fields"]
        cand_changed = any((self.cand[k.upper()] or None) != (f[k] or None) for k in services.EDITABLE)
        stale = cand["expected_revision"] != self.cand["REVISION_NO"] or any(
            c["expected_revision"] is not None and (
                c["calc_id"] not in self.calcs or self.calcs[c["calc_id"]]["REVISION_NO"] != c["expected_revision"]
                or self.calcs[c["calc_id"]]["STATUS"] != "active") for c in calcs)
        if stale:
            self.op_log.append((op_id, "conflict"))
            return {"outcome": "conflict", "candidate_id": 1}
        changed = [c["calc_id"] for c in calcs if c["expected_revision"] is not None and (
            c["retire"] or services.calc_changed(self.calcs[c["calc_id"]], c["fields"]))]
        new = [c["calc_id"] for c in calcs if c["expected_revision"] is None and not c["retire"]]
        if not (cand_changed or changed or new):
            self.op_log.append((op_id, "no_change"))
            return {"outcome": "no_change", "candidate_id": 1, "candidate_revision": self.cand["REVISION_NO"]}
        checks = [c["calc_id"] for c in calcs if c["calc_id"] in new or (
            c["calc_id"] in changed and not c["retire"]
            and (self.calcs[c["calc_id"]]["SQL_TEXT"] or None) != c["fields"]["sql_text"])]
        if cand_changed:
            self.cand.update({k.upper(): v for k, v in f.items()}, REVISION_NO=self.cand["REVISION_NO"] + 1)
            self.revisions.append(("metric_candidate", 1, self.cand["REVISION_NO"], copy.deepcopy(self.cand)))
        for c in calcs:
            cid = c["calc_id"]
            if cid in changed:
                row = self.calcs[cid]
                if c["retire"]:
                    row["STATUS"] = "retired"
                else:
                    row.update({k.upper(): v for k, v in c["fields"].items()})
                row["REVISION_NO"] += 1
            elif cid in new:
                self.calcs[cid] = calc_row(cid, c["fields"]["sql_text"], c["fields"]["disambig"],
                                           is_default=c["is_default"])
            else:
                continue
            self.revisions.append(("metric_calc", cid, self.calcs[cid]["REVISION_NO"], copy.deepcopy(self.calcs[cid])))
        self.op_log.append((op_id, "committed"))
        if self.lose_next_ack:
            self.lose_next_ack = False
            raise RuntimeError("connection dropped")
        return {"outcome": "committed", "candidate_id": 1, "candidate_revision": self.cand["REVISION_NO"],
                "changed_calcs": changed, "new_calcs": new, "checks_due": checks, "collisions": []}

    def snapshot_at(self, record_type, record_id, revision_no):
        return next((copy.deepcopy(s) for t, i, r, s in self.revisions
                     if (t, i, r) == (record_type, record_id, revision_no)), None)


class MetricSaveTests(unittest.TestCase):
    def setUp(self):
        self.store = store = Store()
        patches = [
            patch.object(repo, "save_metric", side_effect=store.save_metric),
            patch.object(repo, "list_calcs_for_candidate", side_effect=lambda cid: [
                copy.deepcopy(r) for r in store.calcs.values() if r["STATUS"] == "active"]),
            patch.object(repo, "get_candidate", side_effect=lambda cid: copy.deepcopy(store.cand)),
            patch.object(repo, "get_calc", side_effect=lambda cid: copy.deepcopy(store.calcs.get(cid))),
            patch.object(repo, "snapshot_at", side_effect=store.snapshot_at),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def save(self, calcs=(), op_id="op1", **cand_fields):
        fields = {"full_name": "CSAT", "description": "Satisfaction", **cand_fields}
        return services.save_metric("tester", op_id, {"id": 1, "expected_revision": 1, "fields": fields},
                                    list(calcs))

    @staticmethod
    def pi(calc_id, sql, disambig, expected=1, retire=False):
        return {"calc_id": calc_id, "expected_revision": expected, "retire": retire,
                "fields": {"sql_text": sql, "disambig": disambig}}

    def revisions_after_setup(self):
        return self.store.revisions[3:]

    def test_edit_definition_and_one_pi_and_add_one_versions_each_once(self):
        out = self.save([self.pi(7, "SELECT 10", "daily"), self.pi(9, "SELECT 3", "weekly", expected=None)],
                        description="Customer satisfaction")
        self.assertEqual(out.status, "saved")
        self.assertEqual((out.candidate_revision, out.calc_revisions), (2, {7: 2, 9: 1}))
        self.assertEqual(sorted((t, i, r) for t, i, r, _ in self.revisions_after_setup()),
                         [("metric_calc", 7, 2), ("metric_calc", 9, 1), ("metric_candidate", 1, 2)])
        self.assertEqual(self.store.calcs[8]["REVISION_NO"], 1)  # untouched PI unchanged
        self.assertFalse(self.store.calcs[9]["IS_DEFAULT"])  # 7 is still the default
        self.assertEqual(sorted(out.checks_due), [7, 9])

    def test_remove_a_pi_retires_it_with_a_snapshot(self):
        out = self.save([self.pi(8, "SELECT 2", "monthly", retire=True)])
        self.assertEqual(out.status, "saved")
        self.assertEqual(self.store.calcs[8]["STATUS"], "retired")
        self.assertEqual([(t, i, r, s["STATUS"]) for t, i, r, s in self.revisions_after_setup()],
                         [("metric_calc", 8, 2, "retired")])
        self.assertNotIn(8, [r["CALC_ID"] for r in repo.list_calcs_for_candidate(1)])  # gone from read mode
        self.assertIsNotNone(self.store.snapshot_at("metric_calc", 8, 1))  # history keeps it
        self.assertEqual(out.checks_due, [])

    def test_a_pi_saved_meanwhile_refuses_the_whole_save(self):
        self.store.calcs[8].update(SQL_TEXT="SELECT gabe", REVISION_NO=2, UPDATED_BY="gabe")
        self.store.revisions.append(("metric_calc", 8, 2, copy.deepcopy(self.store.calcs[8])))
        before = len(self.store.revisions)
        out = self.save([self.pi(7, "SELECT 10", "daily"), self.pi(8, "SELECT mine", "monthly")],
                        description="Mine")
        self.assertEqual(out.status, "conflict")
        self.assertEqual(len(self.store.revisions), before)  # nothing written
        self.assertEqual(self.store.cand["DESCRIPTION"], "Satisfaction")
        self.assertEqual([c["record"] for c in out.conflicts], [8])
        self.assertEqual((out.conflicts[0]["by"], out.conflicts[0]["changed_fields"]), ("gabe", ["SQL"]))
        self.assertIn("gabe changed implementation #8 (SQL)", out.message)

    def test_missing_label_with_two_pis_writes_nothing_and_marks_that_card(self):
        with patch.object(repo, "save_metric") as save:
            out = self.save([self.pi(9, "SELECT 3", None, expected=None)])
        self.assertEqual(out.status, "invalid")
        self.assertEqual(out.problems, [{"record": 9, "field": "disambig", "message":
                                         "With more than one implementation, say how this one differs."}])
        save.assert_not_called()

    def test_untouched_pi_without_a_label_is_flagged_when_a_second_appears(self):
        self.store.calcs = {7: calc_row(7, "SELECT 1", None, is_default=True)}
        out = self.save([self.pi(9, "SELECT 3", "weekly", expected=None)])
        self.assertEqual([(p["record"], p["field"]) for p in out.problems], [(7, "disambig")])

    def test_retry_after_lost_acknowledgement_creates_no_duplicates(self):
        self.store.lose_next_ack = True
        draft = [self.pi(9, "SELECT 3", "weekly", expected=None)]
        first = self.save(draft)
        self.assertEqual(first.status, "failed")
        retry = self.save(draft)  # same op_id, same reserved calc_id
        self.assertEqual((retry.status, retry.warnings), ("saved", []))
        self.assertEqual(retry.calc_revisions, {9: 1})
        self.assertEqual([i for t, i, *_ in self.revisions_after_setup()], [9])  # inserted once

    def test_retry_with_newer_edits_reports_the_earlier_save_and_keeps_the_draft_unsaved(self):
        self.store.lose_next_ack = True
        self.save([self.pi(9, "SELECT 3", "weekly", expected=None)])
        retry = self.save([self.pi(9, "SELECT 4", "weekly", expected=None)])
        self.assertEqual(retry.status, "saved")
        self.assertIn("earlier save did go through", retry.warnings[0])
        self.assertEqual(self.store.calcs[9]["SQL_TEXT"], "SELECT 3")

    def test_no_op_save_is_no_change_without_revisions(self):
        out = self.save([self.pi(7, "SELECT 1 ", "daily")])
        self.assertEqual((out.status, out.calc_revisions), ("no_change", {7: 1}))
        self.assertEqual(self.revisions_after_setup(), [])

    def test_changed_sql_is_saved_and_due_a_run_check(self):
        # Contract: broken SQL still saves; the run check (not built yet) marks the card afterwards.
        out = self.save([self.pi(7, "SELEC broken", "daily")])
        self.assertEqual((out.status, out.checks_due), ("saved", [7]))

    def test_first_pi_of_a_metric_is_default(self):
        self.store.calcs = {}
        with patch.object(repo, "save_metric", return_value={"outcome": "committed", "candidate_id": 1,
                                                              "candidate_revision": 1, "new_calcs": [9]}) as save:
            self.save([self.pi(9, "SELECT 3", None, expected=None)])
        self.assertTrue(save.call_args.args[3][0]["is_default"])

    def test_failed_call_keeps_the_draft(self):
        with patch.object(repo, "save_metric", side_effect=RuntimeError("down")):
            out = self.save(description="x")
        self.assertEqual(out.status, "failed")
        self.assertIn("draft is kept", out.message)


class CalcRuleTests(unittest.TestCase):
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


class ProcedureSourceTests(unittest.TestCase):
    """The DDL isn't run locally; these pin the invariants the live smoke test then exercises."""

    def body(self):
        return SQL.split("$$")[1]

    def test_invariants_are_present(self):
        for needle in ("EXECUTE AS OWNER", "c.revision_no = r.exp_rev", "revision_no = :v_cand_exp",
                       "OBJECT_CONSTRUCT_KEEP_NULL(*)", "OBJECT_CONSTRUCT_KEEP_NULL(c.*)",
                       "create_token = :v_token", "IFF(r.retire, 'retired', c.status)",
                       "'conflict'", "'replayed'", "'committed'", "'no_change'", "'rolled_back'",
                       "BEGIN TRANSACTION", "COMMIT", "ROLLBACK", "TO ROLE WORKBENCH_APP"):
            self.assertIn(needle, SQL)
        self.assertNotIn("CURRENT_USER", self.body())

    def test_every_name_is_fully_qualified(self):
        targets = re.findall(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([\w.]+)", self.body())
        self.assertTrue(targets)
        for name in targets:
            self.assertTrue(name.startswith("AI_PLATFORM.WORKBENCH.") or name == "TABLE", name)

    def test_request_keys_match_what_the_repository_sends(self):
        for key in ("op_id", "actor", "lock_wait_ms", "schema_version", "change_note", "check_name"):
            self.assertIn(f"req:{key}", self.body())
        self.assertEqual(repo._SAVE_METRIC, "CALL AI_PLATFORM.WORKBENCH.save_metric(?)")


if __name__ == "__main__":
    unittest.main()
