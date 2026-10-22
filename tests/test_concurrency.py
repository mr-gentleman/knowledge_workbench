"""Local regression tests; Snowflake transaction behavior still needs live testing."""
import copy
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest
from app import repositories as repo
from app import services


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(CANDIDATE_ID=1, FULL_NAME='Test', DESCRIPTION='Original',
                        DISAMBIG='', CATEGORY='', DEPARTMENT=None, REVISION_NO=1,
                        STATUS='open', ORIGINAL_AUTHOR='tester', UPDATED_BY='tester',
                        UPDATED_AT=datetime(2026, 10, 21))
        self.writes = []
        def update(cid, expected, fields, actor, note):
            if expected != self.row['REVISION_NO']:
                raise repo.StaleEdit(cid)
            self.row.update({k.upper(): v for k, v in fields.items()})
            self.row['REVISION_NO'] += 1
            self.writes.append(expected)
            return self.row['REVISION_NO']
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch.object(repo, 'list_candidates', side_effect=lambda search: [copy.deepcopy(self.row)]),
                   patch.object(repo, 'get_candidate', side_effect=lambda cid: copy.deepcopy(self.row)),
                   patch.object(repo, 'history', return_value=[]),
                   patch.object(repo, 'find_by_exact_name', return_value=[]),
                   patch.object(repo, 'update_candidate', side_effect=update)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = AppTest.from_file('../streamlit_app.py').run()
        self.app.sidebar.radio[0].set_value(1).run()
        self.assertFalse(self.app.exception)

    def save(self, description):
        self.app.text_area[0].set_value(description)
        next(b for b in self.app.button if b.label == 'Save').click().run()
        self.assertFalse(self.app.exception)

    def test_stale_draft_survives_and_reload_discards_it(self):
        self.row.update(DESCRIPTION='Other editor', REVISION_NO=2)
        self.save('My unsaved draft')
        self.assertTrue(self.app.error)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.row['DESCRIPTION'], 'Other editor')
        self.assertEqual(self.app.text_area[0].value, 'My unsaved draft')
        self.app.run()
        self.assertEqual(self.app.session_state['candidate-editor:1']['baseline']['REVISION_NO'], 1)
        next(b for b in self.app.button if b.label.startswith('Reload latest')).click().run()
        self.assertEqual(self.app.text_area[0].value, 'Other editor')
        self.save('Reconciled')
        self.assertEqual(self.writes, [2])
        self.assertEqual(self.app.session_state['candidate-editor:1']['baseline']['REVISION_NO'], 3)

    def test_success_refresh_and_noop(self):
        self.save('Saved')
        self.assertEqual(self.writes, [1])
        self.assertEqual(self.app.text_area[0].value, 'Saved')
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


class CreateTests(unittest.TestCase):
    """REL-02: a successful create opens the new record and drops the create form."""

    def setUp(self):
        self.rows, self.inserts = [], []
        def insert(fields, actor):
            cid = len(self.rows) + 1
            self.rows.append(dict(CANDIDATE_ID=cid, FULL_NAME=fields['full_name'],
                                  DESCRIPTION=fields.get('description'), DISAMBIG=None,
                                  CATEGORY=None, DEPARTMENT=None, REVISION_NO=1, STATUS='open',
                                  ORIGINAL_AUTHOR=actor, UPDATED_BY=actor,
                                  UPDATED_AT=datetime(2026, 10, 22)))
            self.inserts.append(cid)
            return cid
        by_id = lambda cid: next((copy.deepcopy(r) for r in self.rows if r['CANDIDATE_ID'] == cid), None)
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch.object(repo, 'list_candidates', side_effect=lambda search: [
                       copy.deepcopy(r) for r in self.rows
                       if search.lower() in r['FULL_NAME'].lower()]),
                   patch.object(repo, 'get_candidate', side_effect=by_id),
                   patch.object(repo, 'history', return_value=[]),
                   patch.object(repo, 'find_by_exact_name', return_value=[]),
                   patch.object(repo, 'insert_candidate', side_effect=insert)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = AppTest.from_file('../streamlit_app.py').run()

    def test_create_opens_new_record_once(self):
        self.app.text_input(key='new:full_name').set_value('Fresh metric')
        next(b for b in self.app.button if b.label == 'Save').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.inserts, [1])
        self.assertEqual(self.app.sidebar.radio[0].value, 1)  # listed and selected
        self.assertEqual(self.app.header[0].value, 'Fresh metric')
        self.assertTrue(self.app.success)  # "Saved" feedback survives the rerun
        self.assertNotIn('new:full_name', [w.key for w in self.app.text_input])
        self.app.run()  # a later rerun must not create anything again
        self.assertEqual(self.inserts, [1])

    def test_create_hidden_by_search_does_not_jump_later(self):
        self.app.sidebar.text_input[0].set_value('zzz').run()
        self.app.text_input(key='new:full_name').set_value('Fresh metric')
        next(b for b in self.app.button if b.label == 'Save').click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.inserts, [1])
        self.assertIn('Saved as #1', self.app.sidebar.info[0].value)
        self.assertNotIn('just_created', self.app.session_state)
        self.app.sidebar.text_input[0].set_value('').run()  # clear the search
        self.assertIsNone(self.app.sidebar.radio[0].value)  # no surprise jump


class TransactionTests(unittest.TestCase):
    def test_snapshot_failure_rolls_back_on_same_session(self):
        s = Mock()
        statements = []
        def sql(text, **kwargs):
            statements.append(text)
            result = Mock()
            if 'INSERT INTO' in text:
                result.collect.side_effect = RuntimeError('snapshot failed')
            else:
                result.collect.return_value = [[1]]
            return result
        s.sql.side_effect = sql
        with patch.object(repo, 'session', return_value=s) as connection, patch.object(repo, 'query') as unrelated:
            with self.assertRaisesRegex(RuntimeError, 'snapshot failed'):
                repo.update_candidate(1, 1, {'full_name': 'Test'}, 'tester')
        connection.assert_called_once()
        unrelated.assert_not_called()
        self.assertEqual(statements[0], 'BEGIN')
        self.assertEqual(statements[-1], 'ROLLBACK')
        self.assertNotIn('COMMIT', statements)

    def test_zero_rows_rolls_back_without_snapshot(self):
        s = Mock()
        s.sql.return_value.collect.return_value = [[0]]
        with patch.object(repo, 'session', return_value=s):
            with self.assertRaises(repo.StaleEdit):
                repo.update_candidate(1, 1, {'full_name': 'Test'}, 'tester')
        statements = [call.args[0] for call in s.sql.call_args_list]
        self.assertFalse(any('INSERT INTO' in q for q in statements))
        self.assertEqual(statements[-1], 'ROLLBACK')


class LockTests(unittest.TestCase):
    """DEC-004: all viewers share one connection, so transactions and baseline reads take db_lock."""

    def test_baseline_read_waits_for_open_transaction(self):
        in_txn, release, order = threading.Event(), threading.Event(), []

        def write(execute):
            in_txn.set()
            release.wait(2)
            order.append('write')

        with patch.object(repo, 'session', return_value=Mock()), \
                patch.object(repo, 'query', side_effect=lambda *a: order.append('read') or []):
            writer = threading.Thread(target=repo._in_txn, args=(write,))
            writer.start()
            self.assertTrue(in_txn.wait(2))
            reader = threading.Thread(target=repo.get_candidate, args=(1,))
            reader.start()
            reader.join(0.2)
            self.assertTrue(reader.is_alive())  # blocked behind the open transaction
            release.set()
            writer.join(2)
            reader.join(2)
        self.assertEqual(order, ['write', 'read'])

    def test_transactions_only_start_in_in_txn(self):
        root = Path(__file__).resolve().parents[1]
        sources = [*root.glob('app/*.py'), root / 'streamlit_app.py']
        hits = {p.name: p.read_text().count('"BEGIN"') for p in sources if '"BEGIN"' in p.read_text()}
        self.assertEqual(hits, {'repositories.py': 1})


if __name__ == '__main__':
    unittest.main()
