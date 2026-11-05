"""Contract tests for date, cross-source close and KRW unit conversion."""
from __future__ import annotations

import sys
import types
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import date, datetime, timezone, timedelta

try:
    from valuation.api import DataError
except ModuleNotFoundError:
    valuation = types.ModuleType("valuation")
    api = types.ModuleType("valuation.api")
    class DataError(RuntimeError):
        pass
    api.DataError = DataError
    api.MarketData = object
    valuation.api = api
    sys.modules["valuation"] = valuation
    sys.modules["valuation.api"] = api

try:
    from market_flow.collect import collect, recent_history
except ModuleNotFoundError:
    from collect import collect, recent_history

KST = timezone(timedelta(hours=9))


class FakeMarket:
    krx_key = "unused"
    mismatch = False

    def is_open(self, day):
        return day == date(2026, 11, 4)

    def _request(self, method, url, **kwargs):
        if "kospi_dd_trd" in url:
            name, close = "코스피", "5683.80"
        else:
            name, close = "코스닥", "714.95"
        return {"OutBlock_1": [{"BAS_DD": "20261104", "IDX_NM": name,
                                "CLSPRC_IDX": close}]}

    def kis(self, path, tr_id, params):
        if "investor" in path:
            kosdaq = params["FID_INPUT_ISCD"] == "1001"
            return {"output": [{"stck_bsop_date": "20261104",
                                "bstp_nmix_prpr": "714.95" if kosdaq else
                                ("5680.00" if self.mismatch else "5683.80"),
                                "stck_prdy_clpr": "704.39" if kosdaq else "5648.79",
                                "frgn_ntby_tr_pbmn": "9895" if kosdaq else "-2452827",
                                "orgn_ntby_tr_pbmn": "71869" if kosdaq else "1133353"}]}
        return {"output": [{"stck_bsop_date": "20261104",
                            "arbt_smtn_ntby_tr_pbmn": "14655",
                            "nabt_smtn_ntby_tr_pbmn": "20613"}]}


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.patch_derivatives = patch.dict(collect.__globals__, {
            "collect_derivatives": lambda market, day: {"KOSPI200": {"foreign_future_net_contracts": None}}
        })
        self.patch_derivatives.start()
        self.addCleanup(self.patch_derivatives.stop)

    def test_verified_market_values_and_units(self):
        result = collect(date(2026, 11, 4),
                         now=datetime(2026, 11, 5, 14, 0, tzinfo=KST),
                         market=FakeMarket())
        self.assertEqual(result["markets"]["KOSPI"]["foreign_net_bn"], -2452.827)
        self.assertEqual(result["markets"]["KOSDAQ"]["foreign_net_bn"], 9.895)
        self.assertEqual(result["markets"]["KOSDAQ"]["close"], 714.95)
        self.assertIsNone(result["derivatives"]["KOSPI200"]["foreign_future_net_contracts"])

    def test_mismatched_close_rejected(self):
        fake = FakeMarket()
        fake.mismatch = True
        with self.assertRaisesRegex(DataError, "close mismatch"):
            collect(date(2026, 11, 4),
                    now=datetime(2026, 11, 5, 14, 0, tzinfo=KST), market=fake)

    def test_preclose_rejected(self):
        with self.assertRaisesRegex(DataError, "has not ended"):
            collect(date(2026, 11, 5),
                    now=datetime(2026, 11, 5, 15, 44, tzinfo=KST), market=FakeMarket())

    def test_history_uses_only_prior_real_snapshots(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            folder = Path(directory)
            base = {"markets": {name: {"close": 100, "prev_close": 99,
                    "foreign_net_bn": 1, "program_arb_net_bn": 2,
                    "program_nonarb_net_bn": 3} for name in ("KOSPI", "KOSDAQ")}}
            for day in ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03",
                        "2026-11-04", "2026-11-05"):
                item = {**base, "date": day, "demo": day == "2026-11-03"}
                (folder / f"{day}.json").write_text(json.dumps(item), encoding="utf-8")
            history = recent_history(folder, date(2026, 11, 5))
            self.assertEqual([item["date"] for item in history],
                             ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-04"])


if __name__ == "__main__":
    unittest.main()

