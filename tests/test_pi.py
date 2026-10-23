"""Physical implementations (SQL) on the candidate page: add, edit, conflict, retry."""
import copy
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
from test_concurrency import FakeSession, fresh_state, keyup_as_text_input

from app import db, services
from app import repositories as repo


def code_editor_as_text_area(code, key=None, **_):
    """AppTest can't drive custom components; the SQL editor behaves like a text area."""
    import streamlit as st
    return {"id": "edit", "text": st.text_area("SQL editor", code, key=key)}


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

    def test_validation_counts_only_for_the_checked_revision(self):
        row = calc_row(9, "SELECT 1", revision=2)
        row.update(VALIDATION_STATUS="passed", VALIDATED_REVISION_NO=2)
        self.assertEqual(services.validation_state(row), "✓ Validated")
        row["REVISION_NO"] = 3
        self.assertEqual(services.validation_state(row), "Not validated")


class PiPageTests(unittest.TestCase):
    """The SQL section against a fake repository with the real contract."""

    def setUp(self):
        fresh_state(self)
        self.cand = dict(CANDIDATE_ID=1, FULL_NAME='Net New ARR', DESCRIPTION='d', DISAMBIG='',
                         CATEGORY='', DEPARTMENT=None, REVISION_NO=1, STATUS='open',
                         ORIGINAL_AUTHOR='tester', UPDATED_BY='tester', UPDATED_AT=datetime(2026, 10, 23))
        self.calcs, self.inserts, self.updates, self.next_id = {}, [], [], [100]

        def reserve():
            self.next_id[0] += 1
            return self.next_id[0]

        def insert(calc_id, cid, fields, is_default, actor):
            if calc_id in self.calcs:
                return False
            self.calcs[calc_id] = calc_row(calc_id, fields["sql_text"], fields.get("disambig"),
                                           is_default=is_default)
            self.inserts.append(calc_id)
            return True

        def update(calc_id, expected, fields, actor):
            row = self.calcs[calc_id]
            if expected != row['REVISION_NO']:
                raise repo.StaleEdit(calc_id)
            row.update({k.upper(): v for k, v in fields.items()}, REVISION_NO=expected + 1)
            self.updates.append((calc_id, expected))
            return expected + 1

        self.insert = Mock(side_effect=insert)
        patches = [patch('app.db.viewer', return_value='tester'),
                   patch('st_keyup.st_keyup', keyup_as_text_input),
                   patch('code_editor.code_editor', code_editor_as_text_area),
                   patch.object(repo, 'list_candidates', side_effect=lambda search: [copy.deepcopy(self.cand)]),
                   patch.object(repo, 'get_candidate', side_effect=lambda cid: copy.deepcopy(self.cand)),
                   patch.object(repo, 'find_by_exact_name', return_value=[]),
                   patch.object(repo, 'list_calcs_for_candidate',
                                side_effect=lambda cid: [copy.deepcopy(r) for r in self.calcs.values()]),
                   patch.object(repo, 'get_calc', side_effect=lambda i: copy.deepcopy(self.calcs.get(i))),
                   patch.object(repo, 'reserve_calc_id', side_effect=reserve),
                   patch.object(repo, 'insert_calc', self.insert),
                   patch.object(repo, 'update_calc', side_effect=update)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def open_page(self):
        self.app = AppTest.from_file('../streamlit_app.py', default_timeout=30).run()
        self.app.sidebar.radio[0].set_value(1).run()
        self.assertFalse(self.app.exception)

    def button(self, label):
        return next((b for b in self.app.button if b.label == label), None)

    def click(self, label):
        self.button(label).click().run()
        self.assertFalse(self.app.exception)

    def editors(self):
        return [t for t in self.app.text_area if t.label == 'SQL editor']

    def type_sql(self, sql, i=0):
        self.editors()[i].set_value(sql)

    def test_add_first_sql_saves_once_as_default(self):
        self.open_page()
        self.assertEqual(self.editors(), [])  # empty state: just the button
        self.click('+ Add SQL')
        self.assertEqual(len(self.editors()), 1)
        self.assertFalse([t for t in self.app.text_input if t.label.startswith('How it differs')])
        self.type_sql('SELECT SUM(arr) FROM t')
        self.click('Save SQL')
        self.assertEqual(self.inserts, [101])
        self.assertTrue(self.calcs[101]['IS_DEFAULT'])
        self.assertIn('SQL saved', self.app.toast[0].value)
        self.assertEqual(self.editors()[0].value, 'SELECT SUM(arr) FROM t')  # still open, now saved
        self.assertIsNone(self.button('Cancel'))
        self.click('Save SQL')  # unchanged → no second write of any kind
        self.assertEqual((self.inserts, self.updates), ([101], []))

    def test_edit_saves_against_the_opened_revision(self):
        self.calcs[5] = calc_row(5, 'SELECT 1', is_default=True)
        self.open_page()
        self.type_sql('SELECT 2')
        self.click('Save SQL')
        self.assertEqual(self.updates, [(5, 1)])
        self.type_sql('SELECT 3')
        self.click('Save SQL')
        self.assertEqual(self.updates, [(5, 1), (5, 2)])  # baseline refreshed after the save

    def test_conflict_keeps_my_sql_then_discard_loads_theirs(self):
        self.calcs[5] = calc_row(5, 'SELECT 1')
        self.open_page()
        self.calcs[5].update(SQL_TEXT='SELECT gabe', REVISION_NO=2, UPDATED_BY='gabe')
        self.type_sql('SELECT mine')
        self.click('Save SQL')
        self.assertEqual(self.updates, [])
        self.assertIn('gabe', self.app.error[0].value)
        self.assertIn('Changed: SQL', self.app.error[0].value)
        self.assertTrue(self.button('Save SQL').disabled)
        self.assertEqual(self.editors()[0].value, 'SELECT mine')
        self.click('Discard mine, load theirs')
        self.assertEqual(self.editors()[0].value, 'SELECT gabe')
        self.assertFalse(self.button('Save SQL').disabled)

    def test_conflict_keep_mine_saves_on_the_latest_revision(self):
        self.calcs[5] = calc_row(5, 'SELECT 1')
        self.open_page()
        self.calcs[5].update(SOURCE_TABLE='AC.FIN.ARR', REVISION_NO=2, UPDATED_BY='gabe')
        self.type_sql('SELECT mine')
        self.click('Save SQL')
        self.click('Keep my edits on the latest version')
        self.assertEqual(self.editors()[0].value, 'SELECT mine')
        self.assertEqual(next(t for t in self.app.text_input if t.label.startswith('Source table')).value,
                         'AC.FIN.ARR')  # their field, untouched by me, kept
        self.click('Save SQL')
        self.assertEqual(self.updates, [(5, 2)])
        self.assertEqual(self.calcs[5]['SOURCE_TABLE'], 'AC.FIN.ARR')

    def test_second_pi_needs_a_label_and_one_card_is_open(self):
        self.calcs[5] = calc_row(5, 'SELECT 1\nFROM a\nWHERE x\nAND y', is_default=True)
        self.open_page()
        self.click('+ Add another implementation')
        self.assertEqual(len(self.editors()), 1)  # the new card is open, the saved one collapsed
        self.assertIn('…', self.app.code[0].value)  # collapsed preview: first 3 lines
        self.type_sql('SELECT 2')
        self.click('Save SQL')
        self.assertEqual(self.inserts, [])
        self.assertIn('differs', self.app.error[0].value)
        self.assertEqual(self.editors()[0].value, 'SELECT 2')  # kept
        next(t for t in self.app.text_input if t.label.startswith('How it differs')).set_value('monthly')
        self.click('Save SQL')
        self.assertEqual(self.inserts, [101])
        self.assertFalse(self.calcs[101]['IS_DEFAULT'])

    def test_collapsed_card_keeps_unsaved_sql(self):
        self.calcs[5] = calc_row(5, 'SELECT 1', 'monthly')
        self.calcs[6] = calc_row(6, 'SELECT 2', 'by cohort')
        self.open_page()
        self.assertEqual(self.editors(), [])  # two cards: both start collapsed
        self.app.button(key='pi-toggle:1:5').click().run()
        self.type_sql('SELECT unsaved')
        self.app.button(key='pi-toggle:1:6').click().run()  # open the other one
        self.assertEqual(self.editors()[0].value, 'SELECT 2')
        self.assertTrue(any('Unsaved changes' in m.value for m in self.app.markdown))  # on card 5's header
        self.app.button(key='pi-toggle:1:5').click().run()
        self.assertEqual(self.editors()[0].value, 'SELECT unsaved')

    def test_retry_after_unconfirmed_create_reuses_the_id(self):
        real = self.insert.side_effect

        def lost_ack(*args):
            self.insert.side_effect = real
            real(*args)  # the row lands; only the acknowledgement is lost
            raise RuntimeError('connection dropped')
        self.insert.side_effect = lost_ack
        self.open_page()
        self.click('+ Add SQL')
        self.type_sql('SELECT 1')
        self.click('Save SQL')
        self.assertIn('Save again is safe', self.app.error[0].value)
        self.assertEqual(self.editors()[0].value, 'SELECT 1')
        self.type_sql('SELECT 1 -- tweaked')
        self.click('Save SQL')
        self.assertEqual(self.inserts, [101])  # one row, not two
        self.assertIn('did go through', self.app.warning[0].value)
        self.assertEqual(self.editors()[0].value, 'SELECT 1 -- tweaked')  # newer edit kept as a draft
        self.click('Save SQL')
        self.assertEqual(self.updates, [(101, 1)])


if __name__ == '__main__':
    unittest.main()
