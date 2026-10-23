"""API wiring tests: identity from the trusted header, outcomes passed through.
Repositories are faked (as in tests/); this proves nothing about Snowflake or SPCS ingress."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import main, spcs

ROW = {"CANDIDATE_ID": 7, "FULL_NAME": "Net New ARR", "DESCRIPTION": None, "DISAMBIG": None,
       "DEPARTMENT": "finance", "CATEGORY": "", "REVISION_NO": 3}
BODY = {"expected_revision": 3, "fields": {"full_name": "Net New ARR", "description": "New"}}


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
        r = self.client.put("/api/candidates/7", json=BODY, headers={spcs.USER_HEADER: "CLENZINI"})
        self.assertEqual(r.json()["revision_no"], 4)
        self.assertEqual(self.mocks[1].call_args.args[3], "CLENZINI")

    def test_edit_without_identity_is_refused(self):
        r = self.client.put("/api/candidates/7", json=BODY)
        self.assertEqual(r.status_code, 401)
        self.mocks[1].assert_not_called()

    def test_dev_user_is_ignored_inside_spcs(self):
        with mock.patch.dict("os.environ", {"KW_DEV_USER": "someone"}):
            self.assertEqual(self.client.put("/api/candidates/7", json=BODY).status_code, 401)

    def test_stale_revision_returns_conflict_outcome(self):
        r = self.client.put("/api/candidates/7", json={**BODY, "expected_revision": 2},
                            headers={spcs.USER_HEADER: "CLENZINI"})
        self.assertFalse(r.json()["ok"])
        self.assertIn("newer version", r.json()["message"])
        self.mocks[1].assert_not_called()


if __name__ == "__main__":
    unittest.main()
