"""Local regression tests; Snowflake transaction behavior still needs live testing."""
import copy
import unittest
from datetime import datetime
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


if __name__ == '__main__':
    unittest.main()
