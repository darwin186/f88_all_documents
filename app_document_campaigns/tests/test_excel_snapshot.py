import re

from django.test import SimpleTestCase

from documents import excel_snapshot


class ExcelSnapshotTests(SimpleTestCase):
    def test_new_tokens_are_excel_safe_and_round_trip(self):
        value = {"campaign": 3, "uid": "row-554", "reference": ["Nội dung"]}

        token = excel_snapshot.dumps(value, salt="test-salt")

        self.assertTrue(token.startswith("v3."))
        self.assertIsNone(re.search(r"_x[0-9a-fA-F]{4}_", token))
        self.assertEqual(excel_snapshot.loads(token, salt="test-salt"), value)

    def test_digest_is_stable_and_sensitive_to_changes(self):
        self.assertEqual(excel_snapshot.digest(["a", "b"]), excel_snapshot.digest(["a", "b"]))
        self.assertNotEqual(excel_snapshot.digest(["a", "b"]), excel_snapshot.digest(["a", "c"]))

    def test_compact_campaign_snapshot_stays_small(self):
        checksum = excel_snapshot.digest(["Dữ liệu cần bảo vệ"])
        payload = {
            "v": 3,
            "c": 3,
            "u": "480f2fb2de724c5bb85129cf97a9cd18",
            "r": checksum,
            "i": None,
            "e": checksum,
            "p": 0,
        }

        self.assertLess(len(excel_snapshot.dumps(payload, salt="test-salt")), 320)

    def test_legacy_ooxml_unicode_escape_can_be_reconstructed(self):
        candidates = excel_snapshot._legacy_candidates("before\uf9cfafter")

        self.assertIn("before_xF9cf_after", candidates)
