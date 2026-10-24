"""API wiring tests: identity from the trusted header, outcomes passed through.
Repositories are faked (as in tests/); this proves nothing about Snowflake or SPCS ingress."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from snowflake.snowpark import Row

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


class FactTablesTest(unittest.TestCase):
    def test_list_has_lower_case_keys(self):
        rows = [Row(TABLE_NAME="AC.FINANCE.MRR", GRAIN="one row per account per day", STATUS="active")]
        with mock.patch.object(main.repo, "list_fact_tables", return_value=rows):
            r = TestClient(main.api).get("/api/fact-tables")
        self.assertEqual(r.json(), [{"table_name": "AC.FINANCE.MRR", "grain": "one row per account per day",
                                     "status": "active"}])

    def test_save_is_attributed_to_header_user_and_conflict_rows_are_lower_case(self):
        latest = {**{k.upper(): None for k in main.services.FACT_EDITABLE},
                  "TABLE_NAME_FULL": "AC.FINANCE.MRR", "GRAIN": "daily", "REVISION_NO": 2, "UPDATED_BY": "ALICE"}
        with mock.patch.object(spcs, "IN_SPCS", True), \
             mock.patch.object(main.repo, "save_fact_table", return_value={"outcome": "conflict"}) as call, \
             mock.patch.object(main.repo, "get_fact_table", return_value=latest), \
             mock.patch.object(main.repo, "snapshot_at", return_value=None):
            r = TestClient(main.api).post("/api/fact-tables/save", headers={spcs.USER_HEADER: "CLENZINI"},
                                          json={"table": {"table_name": "AC.FINANCE.MRR", "expected_revision": 1,
                                                          "fields": {"grain": "weekly"}}})
        self.assertEqual(call.call_args.args[1], "CLENZINI")
        self.assertEqual((r.json()["status"], r.json()["conflict"]["latest"]["grain"]), ("conflict", "daily"))


class ConnectionTest(unittest.TestCase):
    def test_spcs_connection_binds_qmark(self):
        with mock.patch.object(spcs.snowflake.connector, "connect") as connect, \
             mock.patch.dict("os.environ", {"SNOWFLAKE_HOST": "h", "SNOWFLAKE_ACCOUNT": "a", "SNOWFLAKE_WAREHOUSE": "w"}):
            spcs._connect("t")
        self.assertEqual(connect.call_args.kwargs["paramstyle"], "qmark")


if __name__ == "__main__":
    unittest.main()
