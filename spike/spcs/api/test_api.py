"""API wiring tests: identity from the trusted header, outcomes passed through.
Repositories are faked (as in tests/); this proves nothing about Snowflake or SPCS ingress."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import main, spcs

ROW = {"CANDIDATE_ID": 7, "FULL_NAME": "Net New ARR", "DESCRIPTION": None, "DISAMBIG": None,
       "DEPARTMENT": "finance", "CATEGORY": "", "REVISION_NO": 3}
BODY = {"candidate": {"id": 7, "expected_revision": 3, "fields": {"full_name": "Net New ARR", "description": "New"}}}
URL = "/api/metrics/save"


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.api)
        patches = [mock.patch.object(main.repo, "get_candidate", return_value=dict(ROW)),
                   mock.patch.object(main.repo, "update_candidate", return_value=4),
                   mock.patch.object(main.repo, "find_by_exact_name", return_value=[]),
                   mock.patch.object(spcs, "IN_SPCS", True)]
        self.mocks = [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)

    def test_edit_is_attributed_to_header_user(self):
        r = self.client.post(URL, json=BODY, headers={spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual((r.json()["status"], r.json()["candidate_revision"]), ("saved", 4))
        self.assertEqual(self.mocks[1].call_args.args[3], "CLENZINI")

    def test_edit_without_identity_is_refused(self):
        r = self.client.post(URL, json=BODY)
        self.assertEqual(r.status_code, 401)
        self.mocks[1].assert_not_called()

    def test_dev_user_is_ignored_inside_spcs(self):
        with mock.patch.dict("os.environ", {"KW_DEV_USER": "someone"}):
            self.assertEqual(self.client.post(URL, json=BODY).status_code, 401)

    def test_stale_revision_returns_conflict_outcome(self):
        stale = {"candidate": {**BODY["candidate"], "expected_revision": 2}}
        r = self.client.post(URL, json=stale, headers={spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual(r.json()["status"], "conflict")
        self.mocks[1].assert_not_called()

    def test_unchanged_draft_is_no_change(self):
        same = {"candidate": {**BODY["candidate"], "fields": {"full_name": "Net New ARR", "department": "finance"}}}
        r = self.client.post(URL, json=same, headers={spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual(r.json()["status"], "no_change")
        self.mocks[1].assert_not_called()

    def test_calcs_are_refused_until_save_metric_exists(self):
        r = self.client.post(URL, json={**BODY, "calcs": [{"calc_id": 1}]}, headers={spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual(r.status_code, 501)


if __name__ == "__main__":
    unittest.main()
