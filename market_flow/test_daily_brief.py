"""Check that an incomplete live snapshot stays a review-only report."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market_flow.daily_brief import checked_snapshot, main, market_analysis


class ReviewOnlyTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((Path(__file__).parent / "example_input.json").read_text(encoding="utf-8"))
        self.data["demo"] = False
        for derivative in self.data["derivatives"].values():
            derivative["foreign_future_net_contracts"] = None

    def test_missing_future_flow_is_valid_for_review_and_limits_comment(self):
        checked_snapshot(self.data)
        kospi = market_analysis(self.data["markets"]["KOSPI"],
                                self.data["derivatives"]["KOSPI200"])
        kosdaq = market_analysis(self.data["markets"]["KOSDAQ"],
                                 self.data["derivatives"]["KOSDAQ150"])
        self.assertIn("상승했지만 외국인 현물은 순매도", kospi["headline"])
        self.assertIn("-120.0", kospi["facts"])
        self.assertIn("3,000.00 아래", kospi["confirm"])
        self.assertIn("자료 없음", kospi["futures"])
        self.assertIn("하락했지만 외국인 현물은 순매수", kosdaq["headline"])
        self.assertIn("850.00 위", kosdaq["confirm"])
        self.assertIn("판단 보류", kosdaq["limitation"])

    def test_missing_future_flow_blocks_send_before_pdf_creation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            with patch("sys.argv", ["daily_brief", "--input", str(snapshot),
                                    "--output", str(Path(directory) / "reports"), "--send"]):
                with self.assertRaisesRegex(ValueError, "검토본은 발송할 수 없습니다"):
                    main()
            self.assertFalse((Path(directory) / "reports").exists())

    def test_available_future_flow_is_compared_with_cash_flow(self):
        self.data["derivatives"]["KOSPI200"]["foreign_future_net_contracts"] = -1500
        analysis = market_analysis(self.data["markets"]["KOSPI"],
                                   self.data["derivatives"]["KOSPI200"])
        self.assertIn("같은 방향", analysis["futures"])
        self.assertIn("보유 잔고·헤지 동기를 뜻하지 않음", analysis["limitation"])


if __name__ == "__main__":
    unittest.main()

