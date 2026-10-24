"""Local regression tests; Snowflake transaction behavior still needs live testing."""
import copy
import json
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from app import db, services
from app import repositories as repo


class FakeSession:
    """Records every statement. fail: {substring: [exceptions to raise, in order]};
    rows: {substring: result rows}. CURRENT_TRANSACTION() is NULL unless rows say otherwise."""

    def __init__(self, fail=None, rows=None):
        self.calls, self.results = [], []
        self.fail = {k: list(v) for k, v in (fail or {}).items()}
        self.rows = {"CURRENT_TRANSACTION": [[None]], **(rows or {})}

    @property
    def statements(self):
        return [text for text, _ in self.calls]

    def sql(self, text, params=None):
        result = Mock()
        self.calls.append((text, params))
        self.results.append(result)
        for key, errors in self.fail.items():
            if key in text and errors:
                result.collect.side_effect = errors.pop(0)
                return result
        result.collect.return_value = next((v for k, v in self.rows.items() if k in text), [[1]])
        return result


class Interrupt(BaseException):
    """Stands in for Streamlit's StopException, which escapes `except Exception`."""


def keyup_as_text_input(label, value="", key=None, placeholder="", **_):
    """AppTest can't drive custom components; the search box behaves like a text input."""
    import streamlit as st
    return st.text_input(label, value, key=key, placeholder=placeholder)


def fresh_state(test):
    db._state.clear()
    test.addCleanup(db._state.clear)


STORED = [None, 1, "Old", None, None, None, None]  # replay marker, then the metric at its expected revision


def call_save(s, metric=None, calcs=(), op_id="op1", note=None, check="x", stored=STORED):
    """repo.save_metric against a FakeSession whose first read returns stored."""
    s.rows.setdefault("TRY_TO_NUMBER", [stored])
    s.rows.setdefault("SELECT status, metric_id, full_name", [])
    with patch.object(db, "session", return_value=s):
        return repo.save_metric(op_id, "viewer", metric or {"id": 1, "expected_revision": 3,
                                "fields": {"full_name": "X", "category": ""}}, list(calcs), note, check)


def params_of(s, needle):
    return next(p for text, p in s.calls if needle in text)


FACT = "AC.FINANCE.MRR"
FACT_STORED = [False, True, None, None, None, None, None, "daily", None, None, None, "active"]


def call_fact_save(s, expected=3, fields=None, stored=FACT_STORED):
    """repo.save_fact_table against a FakeSession whose first read returns stored
    (replayed, found, then the editable fields)."""
    s.rows.setdefault("> 0,", [stored])
    with patch.object(db, "session", return_value=s):
        return repo.save_fact_table("op1", "viewer", {"table_name": FACT, "expected_revision": expected,
                                    "fields": fields or {"grain": "weekly", "gotchas": "", "status": "active"}}, "why")


class FactTableTransactionTests(unittest.TestCase):
    """DEC-025 / PLAT-11: fact tables save with the same pattern as metrics."""

    def setUp(self):
        fresh_state(self)

    def test_edit_writes_row_history_and_log_in_one_transaction(self):
        s = FakeSession()
        res = call_fact_save(s)
        self.assertEqual((res["outcome"], res["revision_no"]), ("committed", 4))
        self.assertEqual([q.split()[0] for q in s.statements], ["SELECT", "BEGIN", "UPDATE", "INSERT", "COMMIT"])
        update = params_of(s, "SET display_name")
        self.assertEqual(update[-3:], ["viewer", FACT, 3])  # conditional on the expected revision
        self.assertIsNone(update[3])  # gotchas "" saved as NULL
        history = params_of(s, "INSERT ALL")
        self.assertEqual(history[:4], ["edit", repo.SNAPSHOT_VERSION, "viewer", "why"])
        tag = json.loads(s.results[0].collect.call_args.kwargs["statement_params"]["QUERY_TAG"])
        self.assertEqual((tag["op"], tag["record_id"]), ("fact_table.save", FACT))
        self.assertFalse(db.is_dirty())

    def test_retire_is_recorded_as_retire(self):
        s = FakeSession()
        call_fact_save(s, fields={"grain": "daily", "status": "retired"})
        self.assertEqual(params_of(s, "INSERT ALL")[0], "retire")

    def test_create_inserts_only_if_the_name_is_free(self):
        s = FakeSession()
        res = call_fact_save(s, expected=None, stored=[False, False] + [None] * 10)
        self.assertEqual((res["outcome"], res["revision_no"]), ("committed", 1))
        self.assertIn("WHERE NOT EXISTS", next(q for q in s.statements if q.startswith("INSERT INTO")))
        self.assertEqual(params_of(s, "INSERT ALL")[0], "create")

    def test_outcomes_that_write_nothing(self):
        cases = (([True, True] + FACT_STORED[2:], 3, "replayed"),          # this op already committed
                 ([False, False] + [None] * 10, 3, "conflict"),            # not at the expected revision
                 (FACT_STORED, None, "exists"),                            # create of a registered name
                 ([False, True, None, "", None, None, None, "weekly", None, None, None, "active"], 3, "no_change"))
        for stored, expected, outcome in cases:
            s = FakeSession()
            res = call_fact_save(s, expected=expected, stored=stored)
            self.assertEqual(res["outcome"], outcome)
            self.assertNotIn("BEGIN", s.statements)
            self.assertIn(FACT, params_of(s, "INSERT INTO AI_PLATFORM.WORKBENCH.op_log"))

    def test_race_lost_after_the_check_rolls_back(self):
        for expected, rows, outcome in ((3, {"SET display_name": [[0]]}, "conflict"),
                                        (None, {"WHERE NOT EXISTS": [[0]]}, "exists")):
            s = FakeSession(rows=rows)
            stored = FACT_STORED if expected else [False, False] + [None] * 10
            self.assertEqual(call_fact_save(s, expected=expected, stored=stored)["outcome"], outcome)
            self.assertIn("ROLLBACK", s.statements)
            self.assertNotIn("COMMIT", s.statements)
            self.assertFalse(db.is_dirty())

    def test_failed_commit_quarantines(self):
        with self.assertRaises(RuntimeError):
            call_fact_save(FakeSession(fail={"COMMIT": [RuntimeError("lost ack")]}))
        self.assertTrue(db.is_dirty())


class SaveTransactionTests(unittest.TestCase):
    """DEC-025: the save is one transaction on the shared connection, opened and ended inside
    repo.save_metric; history and the committed op_log row are one statement; a failure can't leak an
    uncertain state into the next viewer's work (DEC-007, DEC-008)."""

    def setUp(self):
        fresh_state(self)

    def test_edit_writes_metric_history_and_log_in_one_transaction(self):
        s = FakeSession()
        res = call_save(s, note="why")
        self.assertEqual((res["outcome"], res["metric_revision"]), ("committed", 4))
        self.assertEqual([q.split()[0] for q in s.statements],
                         ["SELECT", "SELECT", "BEGIN", "UPDATE", "INSERT", "COMMIT"])  # read, name check, txn
        history = next(q for q in s.statements if q.lstrip().startswith("INSERT ALL"))
        self.assertIn("INTO AI_PLATFORM.WORKBENCH.revision", history)
        self.assertIn("INTO AI_PLATFORM.WORKBENCH.op_log", history)
        update = params_of(s, "SET full_name")
        self.assertEqual(update, ["X", None, None, None, None, "viewer", 1, 3])  # "" saved as NULL; viewer
        self.assertIn("why", params_of(s, "INSERT ALL"))
        for r in s.results:  # every statement carries the op_id that op_log records
            tag = json.loads(r.collect.call_args.kwargs["statement_params"]["QUERY_TAG"])
            self.assertEqual((tag["op_id"], tag["actor"]), ("op1", "viewer"))
        self.assertFalse(db.is_dirty())

    def test_stale_revision_writes_nothing(self):
        s = FakeSession()
        res = call_save(s, stored=[None] * 7)
        self.assertEqual(res["outcome"], "conflict")
        self.assertNotIn("BEGIN", s.statements)
        self.assertIn("conflict", params_of(s, "INSERT INTO AI_PLATFORM.WORKBENCH.op_log"))

    def test_same_op_id_again_is_replayed_without_writes(self):
        s = FakeSession()
        res = call_save(s, stored=[5] + [None] * 6)
        self.assertEqual((res["outcome"], res["metric_id"]), ("replayed", 5))
        self.assertNotIn("BEGIN", s.statements)

    def test_blank_and_null_are_the_same_content(self):
        s = FakeSession()
        res = call_save(s, stored=[None, 1, "X", None, None, None, ""])
        self.assertEqual((res["outcome"], res["metric_revision"]), ("no_change", 3))
        self.assertNotIn("BEGIN", s.statements)

    def test_race_lost_after_the_check_rolls_back_as_a_conflict(self):
        s = FakeSession(rows={"SET full_name": [[0]]})
        res = call_save(s)
        self.assertEqual(res["outcome"], "conflict")
        self.assertIn("ROLLBACK", s.statements)
        self.assertNotIn("COMMIT", s.statements)
        self.assertFalse(db.is_dirty())

    def test_pi_edit_keeps_its_check_unless_the_sql_changes_and_new_pi_resets_default(self):
        pi = {"SELECT calc_id, revision_no": [[7, 2, "SELECT 1", None, "daily"]]}
        s = FakeSession(rows=dict(pi))
        res = call_save(s, stored=[None, 1, "X", None, None, None, None], calcs=[
            {"calc_id": 7, "expected_revision": 2, "retire": False, "fields": {"sql_text": "SELECT 1", "disambig": "d"}}])
        self.assertEqual((res["changed_calcs"], res["checks_due"]), ([7], []))  # label edit: check still counts
        self.assertIn("validated_revision_no = IFF(", next(q for q in s.statements if "SET sql_text" in q))
        self.assertFalse(any("SET is_default" in q for q in s.statements))  # same PIs active: default can't move
        s = FakeSession(rows=dict(pi))
        res = call_save(s, stored=[None, 1, "X", None, None, None, None], calcs=[
            {"calc_id": 7, "expected_revision": 2, "retire": False, "fields": {"sql_text": "SELECT 2", "disambig": "daily"}},
            {"calc_id": 9, "expected_revision": None, "retire": False, "fields": {"sql_text": "SELECT 3"}}])
        self.assertEqual((res["changed_calcs"], res["new_calcs"], res["checks_due"]), ([7], [9], [7, 9]))
        self.assertTrue(any("SET is_default" in q for q in s.statements))

    def test_pi_not_at_its_revision_refuses_the_whole_save(self):
        s = FakeSession(rows={"SELECT calc_id, revision_no": [[7, 3, "SELECT 1", None, None]]})
        res = call_save(s, calcs=[{"calc_id": 7, "expected_revision": 2, "retire": False, "fields": {}}])
        self.assertEqual(res["outcome"], "conflict")
        self.assertNotIn("BEGIN", s.statements)

    def test_failed_or_interrupted_transaction_quarantines(self):
        for exc in (RuntimeError("lost ack"), Interrupt()):
            db._state.clear()
            with self.assertRaises(type(exc)):
                call_save(FakeSession(fail={"COMMIT": [exc]}))
            self.assertTrue(db.is_dirty())

    def test_quarantine_is_healed_before_the_next_save(self):
        s = FakeSession(fail={"COMMIT": [RuntimeError("lost ack")]})
        with self.assertRaises(RuntimeError):
            call_save(s)
        first = len(s.calls)
        call_save(s)
        self.assertEqual(s.statements[first:first + 2], ["ROLLBACK", "SELECT CURRENT_TRANSACTION()"])
        self.assertEqual(s.statements[-1], "COMMIT")
        self.assertFalse(db.is_dirty())

    def test_open_transaction_after_heal_blocks_all_work(self):
        db.mark_dirty()
        s = FakeSession(rows={"CURRENT_TRANSACTION": [["1234"]]})
        with self.assertRaises(db.ConnectionQuarantined):
            call_save(s)
        with self.assertRaises(db.ConnectionQuarantined), patch.object(db, "session", return_value=s):
            repo.list_metrics()
        self.assertFalse(any("metric" in q for q in s.statements))

    def test_sidebar_list_is_capped(self):
        s = FakeSession(rows={"FROM AI_PLATFORM.WORKBENCH.metric": []})
        with patch.object(db, "session", return_value=s):
            repo.list_metrics()
        self.assertIn(f"LIMIT {repo.LIST_LIMIT}", s.statements[-1])

    def test_failed_duplicate_check_is_a_warning_not_a_failure(self):
        # REL-11: the procedure omits collisions when its lookup failed; the save still committed.
        row = dict(METRIC_ID=1, REVISION_NO=1, FULL_NAME='a', DESCRIPTION=None, DISAMBIG=None,
                   DEPARTMENT=None, CATEGORY=None)
        with patch.object(repo, 'save_metric', return_value={"outcome": "committed", "metric_id": 1,
                                                              "metric_revision": 2}):
            out = services.save_metric_edit(row, {'full_name': 'b'}, 'tester')
        self.assertTrue(out.ok)
        self.assertEqual(out.revision_no, 2)
        self.assertEqual(out.warnings, ["Couldn't check for duplicate names right now."])

    def test_duplicate_warnings_exclude_the_record_itself(self):
        row = dict(METRIC_ID=1, REVISION_NO=1, FULL_NAME='Same', DESCRIPTION=None, DISAMBIG=None,
                   DEPARTMENT=None, CATEGORY=None)
        hits = [{"KIND": "candidate", "ID": 1, "FULL_NAME": "b"}, {"KIND": "canon", "ID": 9, "FULL_NAME": "B"}]
        with patch.object(repo, 'save_metric', return_value={"outcome": "committed", "metric_id": 1,
                                                              "metric_revision": 2, "collisions": hits}) as save:
            out = services.save_metric_edit(row, {'full_name': ' B '}, 't')
        self.assertEqual(save.call_args.args[5], "b")  # normalized here; the procedure checks renames only
        self.assertEqual(len(out.warnings), 1)
        self.assertIn("canon #9", out.warnings[0])

    def test_legacy_edit_conflict_reports_theirs(self):
        row = dict(METRIC_ID=1, REVISION_NO=1, FULL_NAME='a', DESCRIPTION=None, DISAMBIG=None,
                   DEPARTMENT=None, CATEGORY=None)
        theirs = dict(row, REVISION_NO=2, DESCRIPTION='gabe was here', UPDATED_BY='gabe', UPDATED_AT=None)
        with patch.object(repo, 'save_metric', return_value={"outcome": "conflict", "metric_id": 1}), \
                patch.object(repo, 'get_metric', return_value=theirs):
            out = services.save_metric_edit(row, {'full_name': 'b'}, 'tester')
        self.assertFalse(out.ok)
        self.assertEqual(out.latest, theirs)
        self.assertIn("Changed: Description", out.message)


class LockTests(unittest.TestCase):
    """DEC-007: all viewers share one connection, so every database operation takes db_lock."""

    def setUp(self):
        fresh_state(self)

    def test_any_read_waits_for_a_save_in_progress(self):
        in_call, release, order = threading.Event(), threading.Event(), []
        s = FakeSession(rows={"metric": []})
        real_sql = s.sql

        def sql(text, params=None):
            result = real_sql(text, params)
            if "TRY_TO_NUMBER" in text:  # the save's first read
                def slow(**_):
                    in_call.set()
                    release.wait(2)
                    order.append("write")
                    return [[None] * 7]  # the metric moved: conflict, nothing else to write
                result.collect.side_effect = slow
            return result
        s.sql = sql

        with patch.object(db, "session", return_value=s):
            writer = threading.Thread(target=repo.save_metric,
                                      args=("op", "tester", {"id": 1, "fields": {}}, []))
            writer.start()
            self.assertTrue(in_call.wait(2))
            reader = threading.Thread(target=lambda: repo.list_metrics() or order.append("read"))
            reader.start()
            reader.join(0.2)
            self.assertTrue(reader.is_alive())  # a plain list read is blocked behind the save
            release.set()
            writer.join(2)
            reader.join(2)
        self.assertEqual(order, ["write", "read"])

    def test_database_reached_only_through_db(self):
        root = Path(__file__).resolve().parents[1]
        sources = {p.name: p.read_text() for p in [*root.glob("app/*.py"), root / "streamlit_app.py"]}
        # The save is the only transaction, and it opens and ends inside repo.save_metric (DEC-025).
        self.assertEqual({n for n, t in sources.items() if '"BEGIN"' in t}, {"repositories.py"})
        # session() hands out the raw connection; only db.py may call it (via locked_session).
        self.assertEqual({n for n, t in sources.items() if "session()" in t.replace("locked_session()", "")},
                         {"db.py"})


class EditorTests(unittest.TestCase):
    def setUp(self):
        fresh_state(self)
        self.row = dict(METRIC_ID=1, FULL_NAME='Test', DESCRIPTION='Original',
                        DISAMBIG='', CATEGORY='', DEPARTMENT=None, REVISION_NO=1,
                        STATUS='open', ORIGINAL_AUTHOR='tester', UPDATED_BY='tester',
                        UPDATED_AT=datetime(2026, 10, 21))
        self.writes, self.notes = [], []

        def update(op_id, actor, cand, calcs, note=None, check_name=None):
            expected = cand['expected_revision']
            if expected != self.row['REVISION_NO']:
                return {"outcome": "conflict", "metric_id": cand['id']}
            self.row.update({k.upper(): v for k, v in cand['fields'].items()})
            self.row['REVISION_NO'] += 1
            self.writes.append(expected)
            self.notes.append(note)
            return {"outcome": "committed", "metric_id": cand['id'],
                    "metric_revision": self.row['REVISION_NO'], "collisions": []}
        self.history = Mock(return_value=[])
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch('st_keyup.st_keyup', keyup_as_text_input),
                   patch.object(repo, 'list_metrics', side_effect=lambda search: [copy.deepcopy(self.row)]),
                   patch.object(repo, 'get_metric', side_effect=lambda cid: copy.deepcopy(self.row)),
                   patch.object(repo, 'history', self.history),
                   patch.object(repo, 'save_metric', side_effect=update)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = AppTest.from_file('../streamlit_app.py').run()
        self.app.sidebar.radio[0].set_value(1).run()
        self.assertFalse(self.app.exception)

    def save(self, description, note=None):
        self.app.text_area[0].set_value(description)
        if note is not None:
            next(t for t in self.app.text_input if t.label.startswith('Change note')).set_value(note)
        next(b for b in self.app.button if b.label == 'Save').click().run()
        self.assertFalse(self.app.exception)

    def note_value(self):
        return next(t for t in self.app.text_input if t.label.startswith('Change note')).value

    def button(self, prefix):
        return next((b for b in self.app.button if b.label.startswith(prefix)), None)

    def test_no_discard_action_without_a_conflict(self):
        self.assertIsNone(self.button('Discard mine'))
        self.save('Fine')
        self.assertIsNone(self.button('Discard mine'))

    def conflict(self):
        self.row.update(DESCRIPTION='Other editor', REVISION_NO=2, UPDATED_BY='gabe')
        self.save('My unsaved draft', note='why I changed it')
        self.assertIn('gabe', self.app.error[0].value)
        self.assertIn('Changed: Description', self.app.error[0].value)
        self.assertTrue(next(b for b in self.app.button if b.label == 'Save').disabled)

    def test_stale_draft_survives_and_discard_loads_theirs(self):
        self.conflict()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.row['DESCRIPTION'], 'Other editor')
        self.assertEqual(self.app.text_area[0].value, 'My unsaved draft')
        self.assertEqual(self.note_value(), 'why I changed it')  # REL-12: note kept with the draft
        self.app.run()
        self.assertEqual(self.app.session_state['candidate-editor:1']['baseline']['REVISION_NO'], 1)
        self.button('Discard mine').click().run()
        self.assertEqual(self.app.text_area[0].value, 'Other editor')
        self.assertIsNone(self.button('Discard mine'))
        self.save('Reconciled')
        self.assertEqual(self.writes, [2])
        self.assertEqual(self.app.session_state['candidate-editor:1']['baseline']['REVISION_NO'], 3)

    def test_keep_my_edits_merges_onto_theirs(self):
        self.row.update(FULL_NAME='Renamed by gabe', REVISION_NO=2, UPDATED_BY='gabe')
        self.save('My description')
        self.button('Keep my edits').click().run()
        self.assertEqual(self.app.text_area[0].value, 'My description')  # mine kept
        self.assertEqual(next(t for t in self.app.text_input if t.label == 'Name *').value,
                         'Renamed by gabe')  # their untouched-by-me field kept
        self.save('My description')
        self.assertEqual(self.writes, [2])
        self.assertEqual(self.row['FULL_NAME'], 'Renamed by gabe')

    def test_success_refresh_and_noop(self):
        self.save('Saved', note='first')
        self.assertEqual(self.writes, [1])
        self.assertEqual(self.notes, ['first'])
        self.assertEqual(self.app.text_area[0].value, 'Saved')
        self.assertEqual(self.note_value(), '')  # note cleared after a successful save
        self.save('Saved')
        self.assertEqual(self.writes, [1])

    def test_write_race_rejected_by_repository(self):
        with patch.object(repo, 'save_metric', return_value={'outcome': 'conflict', 'metric_id': 1}):
            self.save('Draft')
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.text_area[0].value, 'Draft')

    def test_database_failure_preserves_draft(self):
        with patch.object(repo, 'save_metric', side_effect=RuntimeError('database failure')):
            self.save('Retained')
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.text_area[0].value, 'Retained')

    def test_quarantined_connection_says_not_saved(self):
        with patch.object(repo, 'save_metric', side_effect=db.ConnectionQuarantined('busy')):
            self.save('Retained')
        self.assertIn('Not saved', self.app.error[0].value)
        self.assertEqual(self.app.text_area[0].value, 'Retained')

    def test_quarantine_on_first_read_shows_retry_not_a_crash(self):
        self.app.session_state['recent'] = (0, [])  # expired: the next run reads the list
        with patch.object(repo, 'list_metrics', side_effect=db.ConnectionQuarantined('busy')):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertIn('recovering', self.app.error[0].value)
        self.assertTrue([b for b in self.app.button if b.label == 'Retry'])
        self.app.run()  # recovered
        self.assertEqual(self.app.header[0].value, 'Test')

    def test_reopening_a_record_shows_saves_made_meanwhile(self):
        # REL-07: leave #1, someone else saves it, come back → their version, no false conflict.
        self.app.sidebar.radio[0].set_value(None).run()
        self.row.update(DESCRIPTION='Saved elsewhere', REVISION_NO=2)
        self.app.sidebar.radio[0].set_value(1).run()
        self.assertEqual(self.app.text_area[0].value, 'Saved elsewhere')
        self.save('Mine on top')
        self.assertEqual(self.writes, [2])

    def test_history_loads_only_on_request(self):
        # PLAT-05: tabs render every rerun; full snapshots shouldn't.
        self.app.run()
        self.history.assert_not_called()
        self.app.toggle(key='hist:1').set_value(True).run()
        self.history.assert_called_with('metric', 1)


class DepartmentTests(unittest.TestCase):
    def test_old_values_map_to_current_names(self):
        self.assertEqual(services.department('finance'), 'Finance')
        self.assertEqual(services.department('bi_meta'), 'Analytics')
        self.assertEqual(services.department('misc'), 'Other')
        self.assertEqual(services.department('Finance'), 'Finance')
        self.assertIsNone(services.department(''))


class CreateTests(unittest.TestCase):
    """REL-02 / REL-10: a create happens once, however the Save button is pressed."""

    def setUp(self):
        fresh_state(self)
        self.rows, self.inserts, self.tokens = [], [], {}

        def insert(op_id, actor, cand, calcs, note=None, check_name=None):
            fields, token = cand['fields'], cand['create_token']
            if token in self.tokens:  # same contract as the repository: idempotent per token
                return {"outcome": "replayed", "metric_id": self.tokens[token], "collisions": []}
            cid = len(self.rows) + 1
            self.rows.append(dict(METRIC_ID=cid, FULL_NAME=fields['full_name'],
                                  DESCRIPTION=fields.get('description'), DISAMBIG=None,
                                  CATEGORY=None, DEPARTMENT=None, REVISION_NO=1, STATUS='open',
                                  ORIGINAL_AUTHOR=actor, UPDATED_BY=actor,
                                  UPDATED_AT=datetime(2026, 10, 22)))
            self.inserts.append(cid)
            self.tokens[token] = cid
            return {"outcome": "committed", "metric_id": cid, "collisions": []}
        self.insert = Mock(side_effect=insert)
        by_id = lambda cid: next((copy.deepcopy(r) for r in self.rows if r['METRIC_ID'] == cid), None)
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch('st_keyup.st_keyup', keyup_as_text_input),
                   patch.object(repo, 'list_metrics', side_effect=lambda search: [
                       copy.deepcopy(r) for r in self.rows
                       if search.lower() in r['FULL_NAME'].lower()]),
                   patch.object(repo, 'get_metric', side_effect=by_id),
                   patch.object(repo, 'history', return_value=[]),
                   patch.object(repo, 'save_metric', self.insert)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = AppTest.from_file('../streamlit_app.py').run()

    def name_input(self):
        return next(t for t in self.app.text_input if t.label == 'Name *')

    def click_save(self):
        next(b for b in self.app.button if b.label == 'Save').click().run()
        self.assertFalse(self.app.exception)

    def test_create_opens_new_record_once(self):
        self.name_input().set_value('Fresh metric')
        self.click_save()
        self.assertEqual(self.inserts, [1])
        self.assertEqual(self.app.sidebar.radio[0].value, 1)  # listed and selected
        self.assertEqual(self.app.header[0].value, 'Fresh metric')
        self.assertIn('Saved', self.app.toast[0].value)  # feedback survives the rerun
        self.assertIn('✓ Saved · rev 1', self.app.caption[0].value)
        self.assertFalse([w for w in self.app.text_input if (w.key or '').startswith('new-')])  # create form gone
        self.app.run()  # a later rerun must not create anything again
        self.assertEqual(self.inserts, [1])

    def test_create_hidden_by_search_resets_form(self):
        # Astra's repro: search hides the new record, then a normal second Save.
        self.app.sidebar.text_input[0].set_value('zzz').run()
        self.name_input().set_value('Fresh metric')
        self.click_save()
        self.assertIn('Saved as #1', self.app.sidebar.info[0].value)
        self.assertEqual(self.name_input().value, '')  # fresh, empty form
        self.click_save()  # empty name → refused, nothing inserted
        self.assertEqual(self.inserts, [1])
        self.app.sidebar.text_input[0].set_value('').run()  # clear the search
        self.assertIsNone(self.app.sidebar.radio[0].value)  # no surprise jump

    def test_retry_after_unconfirmed_create_reuses_token(self):
        real, attempts = self.insert.side_effect, []

        def lost_ack(*args, **kw):  # the row lands; only the acknowledgement is lost
            cid = real(*args, **kw)
            attempts.append(args[2]['create_token'])
            if len(attempts) == 1:
                raise RuntimeError('connection dropped')
            return cid
        self.insert.side_effect = lost_ack
        self.name_input().set_value('Fresh metric')
        self.click_save()
        self.assertTrue(self.app.error)
        self.assertEqual(self.name_input().value, 'Fresh metric')  # entries kept
        self.click_save()  # user retries
        self.assertEqual(self.inserts, [1])  # same token → the first row, not a second
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(self.app.sidebar.radio[0].value, 1)

    def lose_first_ack(self, landed):
        real = self.insert.side_effect

        def flaky(*args, **kw):
            self.insert.side_effect = real
            if landed:
                real(*args, **kw)
            raise RuntimeError('connection dropped')
        self.insert.side_effect = flaky

    def test_changed_entries_after_unconfirmed_create_never_replay_the_token(self):
        # Astra 2026-10-23: the first attempt landed; the user edits and saves again.
        self.lose_first_ack(landed=True)
        self.name_input().set_value('First name')
        self.click_save()
        with patch.object(repo, 'metric_for_token', side_effect=lambda t: self.tokens.get(t)):
            self.name_input().set_value('Second name')
            self.click_save()
        self.assertEqual(self.inserts, [1])
        self.assertEqual(self.app.sidebar.radio[0].value, 1)
        self.assertIn('did go through as #1', self.app.warning[0].value)

    def test_changed_entries_after_a_create_that_did_not_land_save_normally(self):
        self.lose_first_ack(landed=False)
        self.name_input().set_value('First name')
        self.click_save()
        with patch.object(repo, 'metric_for_token', side_effect=lambda t: self.tokens.get(t)):
            self.name_input().set_value('Second name')
            self.click_save()
        self.assertEqual(self.inserts, [1])
        self.assertEqual(self.rows[0]['FULL_NAME'], 'Second name')


if __name__ == '__main__':
    unittest.main()
