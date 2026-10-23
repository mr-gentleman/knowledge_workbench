"""Local regression tests; Snowflake transaction behavior still needs live testing."""
import copy
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
        self.calls, self.tags = [], []
        self.fail = {k: list(v) for k, v in (fail or {}).items()}
        self.rows = {"CURRENT_TRANSACTION": [[None]], **(rows or {})}

    @property
    def query_tag(self):
        return self.tags[-1] if self.tags else ""

    @query_tag.setter
    def query_tag(self, value):
        self.tags.append(value)

    @property
    def statements(self):
        return [text for text, _ in self.calls]

    def sql(self, text, params=None):
        self.calls.append((text, params))
        result = Mock()
        for key, errors in self.fail.items():
            if key in text and errors:
                result.collect.side_effect = errors.pop(0)
                return result
        result.collect.return_value = next((v for k, v in self.rows.items() if k in text), [[1]])
        return result

    def op_log(self):
        return [params for text, params in self.calls if "INTO AI_PLATFORM.WORKBENCH.op_log" in text]


class Interrupt(BaseException):
    """Stands in for Streamlit's StopException, which escapes `except Exception`."""


def fresh_state(test):
    db._state.clear()
    test.addCleanup(db._state.clear)


class TransactionTests(unittest.TestCase):
    """DEC-007: a failed or interrupted transaction can't leak into the next viewer's save."""

    def setUp(self):
        fresh_state(self)

    def run_update(self, s, expected=1):
        with patch.object(db, "session", return_value=s):
            return repo.update_candidate(1, expected, {"full_name": "Test"}, "tester")

    def test_snapshot_failure_rolls_back_and_logs(self):
        s = FakeSession(fail={"INTO AI_PLATFORM.WORKBENCH.revision": [RuntimeError("snapshot failed")]})
        with self.assertRaisesRegex(RuntimeError, "snapshot failed"):
            self.run_update(s)
        self.assertEqual(s.statements[0], "BEGIN")
        self.assertIn("ROLLBACK", s.statements)
        self.assertNotIn("COMMIT", s.statements)
        self.assertEqual(s.op_log()[0][4], "rolled_back")
        self.assertFalse(db.is_dirty())

    def test_zero_rows_is_a_conflict_without_snapshot(self):
        s = FakeSession(rows={"UPDATE": [[0]]})
        with self.assertRaises(repo.StaleEdit):
            self.run_update(s)
        self.assertFalse(any("INTO AI_PLATFORM.WORKBENCH.revision" in q for q in s.statements))
        self.assertEqual(s.op_log()[0][4], "conflict")

    def test_failed_rollback_quarantines_until_proven_clean(self):
        # REL-08: snapshot fails + ROLLBACK fails → the next save must not COMMIT the abandoned change.
        s = FakeSession(fail={"INTO AI_PLATFORM.WORKBENCH.revision": [RuntimeError("snapshot failed")],
                              "ROLLBACK": [RuntimeError("rollback failed")]})
        with self.assertRaises(RuntimeError) as caught:
            self.run_update(s)
        self.assertIn("ROLLBACK also failed", "".join(caught.exception.__notes__))
        self.assertTrue(db.is_dirty())
        self.assertEqual(s.op_log(), [])  # an INSERT now would join the abandoned transaction
        self.assertNotIn("", s.tags[1:])  # nor may the tag be unset (ALTER SESSION)
        first = len(s.calls)
        self.assertEqual(self.run_update(s), 2)
        after = s.statements[first:]
        self.assertEqual(after[:2], ["ROLLBACK", "SELECT CURRENT_TRANSACTION()"])
        self.assertLess(after.index("ROLLBACK"), after.index("BEGIN"))
        self.assertFalse(db.is_dirty())

    def test_open_transaction_after_heal_blocks_all_work(self):
        db.mark_dirty()
        s = FakeSession(rows={"CURRENT_TRANSACTION": [["1234"]]})
        with self.assertRaises(db.ConnectionQuarantined):
            self.run_update(s)
        with self.assertRaises(db.ConnectionQuarantined), patch.object(db, "session", return_value=s):
            repo.list_candidates()
        self.assertNotIn("BEGIN", s.statements)
        self.assertFalse(any("metric_candidate" in q for q in s.statements))

    def test_interrupt_rolls_back_reraises_and_quarantines(self):
        s = FakeSession()

        def work(execute, meta):
            execute("UPDATE something")
            raise Interrupt()

        with patch.object(db, "session", return_value=s), self.assertRaises(Interrupt):
            repo._in_txn(work, "test.op", "tester", 1)
        self.assertIn("ROLLBACK", s.statements)
        self.assertNotIn("COMMIT", s.statements)
        self.assertEqual(s.op_log()[0][4], "interrupted")
        self.assertTrue(db.is_dirty())

    def test_failed_commit_is_uncertain(self):
        s = FakeSession(fail={"COMMIT": [RuntimeError("lost ack")]})
        with self.assertRaises(RuntimeError):
            self.run_update(s)
        self.assertEqual(s.op_log()[0][4], "commit_uncertain")
        self.assertTrue(db.is_dirty())

    def test_begin_failure_still_rolls_back(self):
        s = FakeSession(fail={"BEGIN": [RuntimeError("begin failed")]})
        with self.assertRaises(RuntimeError):
            self.run_update(s)
        self.assertIn("ROLLBACK", s.statements)

    def test_op_log_failure_does_not_change_outcome(self):
        s = FakeSession(fail={"INTO AI_PLATFORM.WORKBENCH.op_log": [RuntimeError("log down")]})
        self.assertEqual(self.run_update(s), 2)
        self.assertIn("COMMIT", s.statements)

    def test_tag_carries_op_id_and_is_cleared_after(self):
        s = FakeSession()
        self.run_update(s)
        self.assertIn('"op": "candidate.edit"', s.tags[0])
        self.assertIn(s.op_log()[0][0], s.tags[0])  # same op_id in tag and op_log
        self.assertEqual(s.tags[-1], "")
        self.assertEqual(s.op_log()[0][4], "committed")

    def test_create_retry_with_same_token_returns_first_row(self):
        s = FakeSession(rows={"create_token = ?": [[7]]})
        with patch.object(db, "session", return_value=s):
            self.assertEqual(repo.insert_candidate({"full_name": "X"}, "tester", "tok"), 7)
        self.assertFalse(any("INSERT INTO AI_PLATFORM.WORKBENCH.metric_candidate" in q for q in s.statements))
        self.assertEqual(s.op_log()[0][4], "replayed")

    def test_snapshot_keeps_nulls_and_records_version(self):
        s = FakeSession(rows={"create_token = ?": []})
        with patch.object(db, "session", return_value=s):
            repo.insert_candidate({"full_name": "X"}, "tester", "tok")
        text, params = next(c for c in s.calls if "INTO AI_PLATFORM.WORKBENCH.revision" in c[0])
        self.assertIn("OBJECT_CONSTRUCT_KEEP_NULL(*)", text)
        self.assertIn(repo.SNAPSHOT_VERSION, params)

    def test_sidebar_list_is_capped(self):
        s = FakeSession(rows={"FROM AI_PLATFORM.WORKBENCH.metric_candidate": []})
        with patch.object(db, "session", return_value=s):
            repo.list_candidates()
        self.assertIn(f"LIMIT {repo.LIST_LIMIT}", s.statements[-1])


class LockTests(unittest.TestCase):
    """DEC-007: all viewers share one connection, so every database operation takes db_lock."""

    def setUp(self):
        fresh_state(self)

    def test_any_read_waits_for_open_transaction(self):
        in_txn, release, order = threading.Event(), threading.Event(), []

        def write(execute, meta):
            in_txn.set()
            release.wait(2)
            order.append("write")

        with patch.object(db, "session", return_value=FakeSession(rows={"metric_candidate": []})):
            writer = threading.Thread(target=repo._in_txn, args=(write, "test.op", "tester"))
            writer.start()
            self.assertTrue(in_txn.wait(2))
            reader = threading.Thread(target=lambda: repo.list_candidates() or order.append("read"))
            reader.start()
            reader.join(0.2)
            self.assertTrue(reader.is_alive())  # a plain list read is blocked behind the transaction
            release.set()
            writer.join(2)
            reader.join(2)
        self.assertEqual(order, ["write", "read"])

    def test_database_reached_only_through_db(self):
        root = Path(__file__).resolve().parents[1]
        sources = {p.name: p.read_text() for p in [*root.glob("app/*.py"), root / "streamlit_app.py"]}
        self.assertEqual({n for n, t in sources.items() if '"BEGIN"' in t}, {"repositories.py"})
        # session() hands out the raw connection; only db.py may call it (via locked_session).
        self.assertEqual({n for n, t in sources.items() if "session()" in t.replace("locked_session()", "")},
                         {"db.py"})


class EditorTests(unittest.TestCase):
    def setUp(self):
        fresh_state(self)
        self.row = dict(CANDIDATE_ID=1, FULL_NAME='Test', DESCRIPTION='Original',
                        DISAMBIG='', CATEGORY='', DEPARTMENT=None, REVISION_NO=1,
                        STATUS='open', ORIGINAL_AUTHOR='tester', UPDATED_BY='tester',
                        UPDATED_AT=datetime(2026, 10, 21))
        self.writes, self.notes = [], []

        def update(cid, expected, fields, actor, note):
            if expected != self.row['REVISION_NO']:
                raise repo.StaleEdit(cid)
            self.row.update({k.upper(): v for k, v in fields.items()})
            self.row['REVISION_NO'] += 1
            self.writes.append(expected)
            self.notes.append(note)
            return self.row['REVISION_NO']
        self.history = Mock(return_value=[])
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch.object(repo, 'list_candidates', side_effect=lambda search: [copy.deepcopy(self.row)]),
                   patch.object(repo, 'get_candidate', side_effect=lambda cid: copy.deepcopy(self.row)),
                   patch.object(repo, 'history', self.history),
                   patch.object(repo, 'find_by_exact_name', return_value=[]),
                   patch.object(repo, 'update_candidate', side_effect=update)]
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

    def test_stale_draft_survives_and_reload_discards_it(self):
        self.row.update(DESCRIPTION='Other editor', REVISION_NO=2)
        self.save('My unsaved draft', note='why I changed it')
        self.assertTrue(self.app.error)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.row['DESCRIPTION'], 'Other editor')
        self.assertEqual(self.app.text_area[0].value, 'My unsaved draft')
        self.assertEqual(self.note_value(), 'why I changed it')  # REL-12: note kept with the draft
        self.app.run()
        self.assertEqual(self.app.session_state['candidate-editor:1']['baseline']['REVISION_NO'], 1)
        next(b for b in self.app.button if b.label.startswith('Reload latest')).click().run()
        self.assertEqual(self.app.text_area[0].value, 'Other editor')
        self.save('Reconciled')
        self.assertEqual(self.writes, [2])
        self.assertEqual(self.app.session_state['candidate-editor:1']['baseline']['REVISION_NO'], 3)

    def test_success_refresh_and_noop(self):
        self.save('Saved', note='first')
        self.assertEqual(self.writes, [1])
        self.assertEqual(self.notes, ['first'])
        self.assertEqual(self.app.text_area[0].value, 'Saved')
        self.assertEqual(self.note_value(), '')  # note cleared after a successful save
        self.save('Saved')
        self.assertEqual(self.writes, [1])

    def test_write_race_rejected_by_repository(self):
        with patch.object(repo, 'update_candidate', side_effect=repo.StaleEdit(1)):
            self.save('Draft')
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.text_area[0].value, 'Draft')

    def test_database_failure_preserves_draft(self):
        with patch.object(repo, 'update_candidate', side_effect=RuntimeError('database failure')):
            self.save('Retained')
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.text_area[0].value, 'Retained')

    def test_quarantined_connection_says_not_saved(self):
        with patch.object(repo, 'update_candidate', side_effect=db.ConnectionQuarantined('busy')):
            self.save('Retained')
        self.assertIn('Not saved', self.app.error[0].value)
        self.assertEqual(self.app.text_area[0].value, 'Retained')

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
        self.history.assert_called_with('metric_candidate', 1)


class AdvisoryTests(unittest.TestCase):
    def test_duplicate_check_failure_does_not_fail_a_committed_save(self):
        # REL-11: the save committed; a failing advisory lookup must not make it look failed.
        row = dict(REVISION_NO=1, FULL_NAME='a', DESCRIPTION=None, DISAMBIG=None,
                   DEPARTMENT=None, CATEGORY=None)
        with patch.object(repo, 'get_candidate', return_value=row), \
                patch.object(repo, 'update_candidate', return_value=2), \
                patch.object(repo, 'find_by_exact_name', side_effect=RuntimeError('lookup down')):
            out = services.save_candidate_edit(1, 1, {'full_name': 'b'}, 'tester')
        self.assertTrue(out.ok)
        self.assertEqual(out.revision_no, 2)
        self.assertTrue(out.warnings)


class CreateTests(unittest.TestCase):
    """REL-02 / REL-10: a create happens once, however the Save button is pressed."""

    def setUp(self):
        fresh_state(self)
        self.rows, self.inserts, self.tokens = [], [], {}

        def insert(fields, actor, token):
            if token in self.tokens:  # same contract as the repository: idempotent per token
                return self.tokens[token]
            cid = len(self.rows) + 1
            self.rows.append(dict(CANDIDATE_ID=cid, FULL_NAME=fields['full_name'],
                                  DESCRIPTION=fields.get('description'), DISAMBIG=None,
                                  CATEGORY=None, DEPARTMENT=None, REVISION_NO=1, STATUS='open',
                                  ORIGINAL_AUTHOR=actor, UPDATED_BY=actor,
                                  UPDATED_AT=datetime(2026, 10, 22)))
            self.inserts.append(cid)
            self.tokens[token] = cid
            return cid
        self.insert = Mock(side_effect=insert)
        by_id = lambda cid: next((copy.deepcopy(r) for r in self.rows if r['CANDIDATE_ID'] == cid), None)
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch.object(repo, 'list_candidates', side_effect=lambda search: [
                       copy.deepcopy(r) for r in self.rows
                       if search.lower() in r['FULL_NAME'].lower()]),
                   patch.object(repo, 'get_candidate', side_effect=by_id),
                   patch.object(repo, 'history', return_value=[]),
                   patch.object(repo, 'find_by_exact_name', return_value=[]),
                   patch.object(repo, 'insert_candidate', self.insert)]
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
        self.assertTrue(self.app.success)  # "Saved" feedback survives the rerun
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

        def lost_ack(fields, actor, token):  # the row lands; only the acknowledgement is lost
            cid = real(fields, actor, token)
            attempts.append(token)
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


if __name__ == '__main__':
    unittest.main()
