"""Contract tests for index derivatives and regular-session selection."""
from __future__ import annotations

import sys
import types
import unittest
from datetime import date

try:
    from valuation.api import DataError
except ModuleNotFoundError:
    valuation = types.ModuleType("valuation")
    api = types.ModuleType("valuation.api")
    class DataError(RuntimeError):
        pass
    api.DataError = DataError
    valuation.api = api
    sys.modules["valuation"] = valuation
    sys.modules["valuation.api"] = api

try:
    from market_flow.collect_derivatives import build_derivatives, parse_option
except ModuleNotFoundError:
    from collect_derivatives import build_derivatives, parse_option

DAY = date(2026, 11, 4)


def option(product, name, code, right="CALL", oi="100", iv="35.00"):
    return {"BAS_DD": "20261104", "PROD_NM": product, "ISU_NM": name,
            "ISU_CD": code, "RGHT_TP_NM": right, "TDD_CLSPRC": "5.00",
            "IMP_VOLT": iv, "ACC_OPNINT_QTY": oi}


class DerivativeTests(unittest.TestCase):
    def test_option_name_monthly_and_weekly(self):
        monthly = parse_option(option("코스닥150 옵션", "코스닥150 C 202611 1,125 (정규)", "A"))
        weekly = parse_option(option("코스피200 위클리(월) 옵션",
                                     "코스피위클리M P 2611W2   887.5 (정규)", "B", "PUT"))
        self.assertEqual(monthly["expiry"], date(2026, 11, 12))
        self.assertEqual(monthly["strike"], 1125)
        self.assertEqual(weekly["expiry"], date(2026, 11, 9))
        self.assertEqual(weekly["kind"], "P")

    def test_regular_contract_and_both_series(self):
        indexes = {"idx/kospi_dd_trd": [{"IDX_NM": "코스피 200", "CLSPRC_IDX": "889.25"}],
                   "idx/kosdaq_dd_trd": [{"IDX_NM": "코스닥 150", "CLSPRC_IDX": "1184.68"}]}
        futures = [
            {"PROD_NM": "코스피200 선물", "MKT_NM": "야간", "ISU_NM": "코스피200 F 202612 (야간)",
             "TDD_CLSPRC": "900.20", "CMPPREVDD_PRC": "15.05", "ACC_OPNINT_QTY": "150000"},
            {"PROD_NM": "코스피200 선물", "MKT_NM": "정규", "ISU_NM": "코스피200 F 202612 (주간)",
             "TDD_CLSPRC": "889.85", "CMPPREVDD_PRC": "4.70", "ACC_OPNINT_QTY": "152348"},
            {"PROD_NM": "코스닥150 선물", "MKT_NM": "정규", "ISU_NM": "코스닥150 F 202612 (주간)",
             "TDD_CLSPRC": "1196.00", "CMPPREVDD_PRC": "27.70", "ACC_OPNINT_QTY": "438479"},
        ]
        options = [
            option("코스피200 옵션", "코스피200 C 202611   890.0 (정규)", "K1"),
            option("코스피200 위클리(목) 옵션", "코스피위클리 P 2611W1   890.0 (정규)", "K2", "PUT"),
            option("코스닥150 옵션", "코스닥150 C 202611 1,175 (정규)", "Q1"),
            option("코스닥150 위클리(목) 옵션", "코스닥위클리 P 2611W1 1,175", "Q2", "PUT"),
            option("미니코스피200 옵션", "미니코스피 C 202611 890.0 (정규)", "MINI"),
        ]
        data = build_derivatives(DAY, indexes, futures, options)
        self.assertEqual(data["KOSPI200"]["future_close"], 889.85)
        self.assertAlmostEqual(data["KOSPI200"]["prev_future_close"], 885.15)
        self.assertEqual(len(data["KOSPI200"]["options"]), 2)
        self.assertEqual(data["KOSPI200"]["options"][1]["series"], "weekly")
        self.assertLess(data["KOSPI200"]["options"][1]["delta"], 0)
        self.assertGreater(data["KOSDAQ150"]["options"][0]["gamma"], 0)
        self.assertIsNone(data["KOSDAQ150"]["foreign_future_net_contracts"])


if __name__ == "__main__":
    unittest.main()

