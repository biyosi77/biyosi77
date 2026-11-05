"""Check that an incomplete live snapshot stays a review-only report."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_flow.daily_brief import checked_snapshot, main, market_comment


class ReviewOnlyTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((Path(__file__).parent / "example_input.json").read_text(encoding="utf-8"))
        self.data["demo"] = False
        for derivative in self.data["derivatives"].values():
            derivative["foreign_future_net_contracts"] = None

    def test_missing_future_flow_is_valid_for_review_and_limits_comment(self):
        checked_snapshot(self.data)
        direction, watch, hypothesis = market_comment(
            "KOSPI", self.data["markets"]["KOSPI"], self.data["derivatives"]["KOSPI200"])
        self.assertIn("미확인", direction)
        self.assertIn("보류", watch)
        self.assertIn("판단할 수 없다", hypothesis)

    def test_missing_future_flow_blocks_send_before_pdf_creation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            with patch("sys.argv", ["daily_brief", "--input", str(snapshot),
                                    "--output", str(Path(directory) / "reports"), "--send"]):
                with self.assertRaisesRegex(ValueError, "검토본은 발송할 수 없습니다"):
                    main()
            self.assertFalse((Path(directory) / "reports").exists())


if __name__ == "__main__":
    unittest.main()

