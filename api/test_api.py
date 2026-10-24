"""API wiring tests: identity from the trusted header, outcomes passed through.
Repositories are faked (as in tests/); this proves nothing about Snowflake or SPCS ingress."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import main, spcs

BODY = {"candidate": {"id": 7, "expected_revision": 3, "fields": {"full_name": "Net New ARR", "description": "New"}}}
URL = "/api/metrics/save"
COMMITTED = {"outcome": "committed", "candidate_id": 7, "candidate_revision": 4}


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.api)
        patches = [mock.patch.object(main.repo, "save_metric", return_value=COMMITTED),
                   mock.patch.object(main.repo, "list_calcs_for_candidate", return_value=[]),
                   mock.patch.object(spcs, "IN_SPCS", True)]
        self.save = [p.start() for p in patches][0]
        self.addCleanup(mock.patch.stopall)

    def post(self, body=BODY, **headers):
        return self.client.post(URL, json=body, headers=headers)

    def test_edit_is_one_call_attributed_to_header_user(self):
        r = self.post(**{spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual((r.json()["status"], r.json()["candidate_revision"]), ("saved", 4))
        self.save.assert_called_once()
        self.assertEqual(self.save.call_args.args[1], "CLENZINI")

    def test_edit_without_identity_is_refused(self):
        self.assertEqual(self.post().status_code, 401)
        self.save.assert_not_called()

    def test_dev_user_is_ignored_inside_spcs(self):
        with mock.patch.dict("os.environ", {"KW_DEV_USER": "someone"}):
            self.assertEqual(self.post().status_code, 401)

    def test_client_op_id_is_passed_through_for_retries(self):
        self.post({**BODY, "op_id": "op-1"}, **{spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual(self.save.call_args.args[0], "op-1")

    def test_invalid_draft_writes_nothing(self):
        blank = {"candidate": {**BODY["candidate"], "fields": {"full_name": " "}}}
        self.assertEqual(self.post(blank, **{spcs.USER_HEADER: "CLENZINI"}).json()["status"], "invalid")
        self.save.assert_not_called()

    def test_no_change_passes_through(self):
        self.save.return_value = {"outcome": "no_change", "candidate_id": 7, "candidate_revision": 3}
        self.assertEqual(self.post(**{spcs.USER_HEADER: "CLENZINI"}).json()["status"], "no_change")


CALC = {"CALC_ID": 5, "STATUS": "active", "REVISION_NO": 3, "SQL_TEXT": "SELECT 1 AS one;\n"}
USER = {spcs.USER_HEADER: "CLENZINI"}


class FakeCursor:
    def __init__(self, columns, rows, error=None):
        self.description, self.rows, self.error, self.sfqid = [(c,) for c in columns], rows, error, "q1"
        self.executed = []

    def execute(self, sql, params):
        self.executed.append(params)
        if self.error:
            raise self.error

    def fetchall(self):
        return self.rows


class CheckTest(unittest.TestCase):
    """POST /api/pis/{id}/check: runs the saved SQL read-only and stamps only the revision it ran."""

    def setUp(self):
        self.client = TestClient(main.api)
        mock.patch.object(spcs, "IN_SPCS", True).start()
        self.get = mock.patch.object(main.repo, "get_calc", return_value=dict(CALC)).start()
        self.record = mock.patch.object(main.repo, "record_check", return_value=True).start()
        self.cursor = FakeCursor(["ONE"], [(1,)])
        conn = mock.MagicMock()
        conn.__enter__.return_value.cursor.return_value = self.cursor
        self.connect = mock.patch.object(main.app.db, "check_connection", return_value=conn).start()
        self.addCleanup(mock.patch.stopall)

    def check(self, rev=3, **headers):
        return self.client.post("/api/pis/5/check", json={"revision_no": rev}, headers=headers or USER)

    def test_pass_runs_saved_sql_and_stamps_that_revision(self):
        out = self.check().json()
        self.assertEqual((out["status"], out["message"], out["rows"]), ("passed", "✓ Runs · rev 3", [["1"]]))
        self.assertEqual(self.cursor.executed, [["SELECT 1 AS one", 100]])  # stored SQL, trailing ; dropped
        self.assertEqual(self.record.call_args.args[:3], (5, 3, True))

    def test_sql_error_is_a_failed_check_with_snowflake_message(self):
        self.cursor.description, self.cursor.rows = [("KW_CHECK",), ("CODE",), ("MESSAGE",)], \
            [("KW_CHECK_FAILED", 2003, "Object 'X' does not exist")]
        out = self.check().json()
        self.assertEqual((out["status"], out["error"]), ("failed", "Object 'X' does not exist"))
        self.assertEqual(self.record.call_args.args[:4], (5, 3, False, "Object 'X' does not exist"))

    def test_timeout_is_a_failed_check(self):
        self.cursor.error = main.repo.ProgrammingError("canceled", errno=630)
        self.assertEqual(self.check().json()["error"], "Stopped after 30 s.")

    def test_check_that_cannot_run_records_nothing(self):
        self.cursor.error = main.repo.ProgrammingError("Unknown procedure RUN_CHECK", errno=2140)
        self.assertEqual(self.check().json()["status"], "unavailable")
        self.record.assert_not_called()

    def test_stale_revision_never_runs(self):
        self.assertEqual(self.check(rev=2).json()["status"], "moved")
        self.connect.assert_not_called()

    def test_result_landing_after_a_newer_save_is_not_claimed(self):
        self.record.return_value = False
        self.assertEqual(self.check().json()["status"], "moved")

    def test_check_needs_identity(self):
        self.assertEqual(self.client.post("/api/pis/5/check", json={"revision_no": 3}).status_code, 401)
        self.connect.assert_not_called()

    def test_open_candidate_includes_its_active_pis(self):
        with mock.patch.object(main.repo, "get_candidate", return_value={"CANDIDATE_ID": 7}), \
             mock.patch.object(main.repo, "list_calcs_for_candidate", return_value=[CALC]):
            self.assertEqual(self.client.get("/api/candidates/7").json()["CALCS"][0]["CALC_ID"], 5)


class ConnectionTest(unittest.TestCase):
    def test_spcs_connection_binds_qmark(self):
        with mock.patch.object(spcs.snowflake.connector, "connect") as connect, \
             mock.patch.dict("os.environ", {"SNOWFLAKE_HOST": "h", "SNOWFLAKE_ACCOUNT": "a", "SNOWFLAKE_WAREHOUSE": "w"}):
            spcs._connect("t")
        self.assertEqual(connect.call_args.kwargs["paramstyle"], "qmark")


if __name__ == "__main__":
    unittest.main()
