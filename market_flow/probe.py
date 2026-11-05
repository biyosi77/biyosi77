"""Read-only schema probe for the user's KRX/KIS entitlements.

Runs on the feature branch PR. Never logs credentials or sends Telegram messages.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

from valuation.api import MarketData
from market_flow.collect import collect
from market_flow.collect_derivatives import collect_derivatives

KRX_BASE = "https://data-dbg.krx.co.kr/svc/apis/"


def compact(rows, columns, count=4):
    if not isinstance(rows, list):
        return {"type": type(rows).__name__}
    return {"count": len(rows), "fields": sorted(rows[0]) if rows else [],
            "samples": [{key: row.get(key) for key in columns if key in row}
                        for row in rows[:count]]}


def main():
    day = date.fromisoformat(os.environ.get("PROBE_DATE", "2026-11-04"))
    market = MarketData()
    result = {"date": day.isoformat(), "krx": {}, "kis": {}, "errors": {}}
    for label, endpoint in {
        "kospi_index": "idx/kospi_dd_trd",
        "kosdaq_index": "idx/kosdaq_dd_trd",
        "futures": "drv/fut_bydd_trd",
        "options": "drv/opt_bydd_trd",
    }.items():
        try:
            payload = market._request("GET", KRX_BASE + endpoint,
                                      headers={"AUTH_KEY": market.krx_key},
                                      params={"basDd": day.strftime("%Y%m%d")})
            rows = payload.get("OutBlock_1", [])
            if label == "options":
                rows = [r for r in rows if any(term in str(r.get("PROD_NM", ""))
                        for term in ("코스피200", "코스닥150", "위클리"))]
            elif label == "futures":
                rows = [r for r in rows if any(term in str(r.get("PROD_NM", ""))
                        for term in ("코스피200", "코스닥150"))]
            result["krx"][label] = compact(rows, ("IDX_NM", "CLSPRC_IDX", "PROD_NM", "MKT_NM",
                                                   "ISU_NM", "TDD_CLSPRC", "CMPPREVDD_PRC",
                                                   "SPOT_PRC", "IMP_VOLT", "ACC_OPNINT_QTY"), 12)
            if label in ("futures", "options"):
                representatives = {}
                for row in rows:
                    key = (row.get("PROD_NM", ""), row.get("MKT_NM", "")
                           if label == "futures" else
                           "정규" if "(정규)" in row.get("ISU_NM", "") else "야간")
                    if key not in representatives and row.get("TDD_CLSPRC"):
                        representatives[key] = {field: row.get(field) for field in (
                            "PROD_NM", "MKT_NM", "ISU_CD", "ISU_NM", "RGHT_TP_NM",
                            "TDD_CLSPRC", "CMPPREVDD_PRC", "ACC_OPNINT_QTY", "IMP_VOLT")}
                result["krx"][label]["representatives"] = list(representatives.values())
        except Exception as exc:
            result["errors"][label] = type(exc).__name__ + ": " + str(exc)[:120]
    ymd = day.strftime("%Y%m%d")
    for label, code, index_code in (("KOSPI", "KSP", "0001"),
                                    ("KOSDAQ", "KSQ", "1001")):
        try:
            payload = market.kis("/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
                                 "FHPTJ04040000", {"FID_COND_MRKT_DIV_CODE": "U",
                                 "FID_INPUT_ISCD": index_code, "FID_INPUT_DATE_1": ymd,
                                 "FID_INPUT_ISCD_1": code, "FID_INPUT_DATE_2": ymd,
                                 "FID_INPUT_ISCD_2": index_code})
            result["kis"][label + "_investor"] = compact(payload.get("output", []),
                ("stck_bsop_date", "bstp_nmix_prpr", "stck_prdy_clpr",
                 "frgn_ntby_tr_pbmn", "orgn_ntby_tr_pbmn"))
        except Exception as exc:
            result["errors"][label + "_investor"] = type(exc).__name__ + ": " + str(exc)[:120]
        try:
            payload = market.kis("/uapi/domestic-stock/v1/quotations/comp-program-trade-daily",
                                 "FHPPG04600001", {"FID_COND_MRKT_DIV_CODE": "J",
                                 "FID_MRKT_CLS_CODE": "K" if label == "KOSPI" else "Q",
                                 "FID_INPUT_DATE_1": ymd, "FID_INPUT_DATE_2": ymd})
            result["kis"][label + "_program"] = compact(payload.get("output", []),
                ("stck_bsop_date", "arbt_smtn_ntby_tr_pbmn", "nabt_smtn_ntby_tr_pbmn"))
        except Exception as exc:
            result["errors"][label + "_program"] = type(exc).__name__ + ": " + str(exc)[:120]
    try:
        payload = market.kis("/uapi/domestic-futureoption/v1/quotations/display-board-callput",
                             "FHPIF05030100", {"FID_COND_MRKT_DIV_CODE": "O",
                             "FID_COND_SCR_DIV_CODE": "20503", "FID_MRKT_CLS_CODE": "CO",
                             "FID_MTRT_CNT": day.strftime("%Y%m"),
                             "FID_MRKT_CLS_CODE1": "PO",
                             "FID_COND_MRKT_CLS_CODE": ""})
        for key in ("output1", "output2"):
            rows = payload.get(key, [])
            if isinstance(rows, dict):
                rows = [rows]
            result["kis"]["option_board_" + key] = compact(rows,
                ("optn_shrn_iscd", "nmix_sdpr", "optn_prpr", "delta_val",
                 "gama", "hts_ints_vltl", "acml_vol", "hts_otst_stpl_qty"), 8)
    except Exception as exc:
        result["errors"]["option_board"] = type(exc).__name__ + ": " + str(exc)[:120]
    time.sleep(1.1)
    try:
        payload = market.kis("/uapi/domestic-futureoption/v1/quotations/display-board-futures",
                             "FHPIF05030200", {"FID_COND_MRKT_DIV_CODE": "F",
                             "FID_COND_SCR_DIV_CODE": "20503",
                             "FID_COND_MRKT_CLS_CODE": "MKI"})
        result["kis"]["futures_board"] = compact(payload.get("output", []),
            ("futs_shrn_iscd", "hts_kor_isnm", "futs_prpr", "futs_prdy_vrss",
             "hts_otst_stpl_qty", "acml_vol"), 20)
    except Exception as exc:
        result["errors"]["futures_board"] = type(exc).__name__ + ": " + str(exc)[:120]
    time.sleep(1.1)
    try:
        payload = market.kis("/uapi/domestic-futureoption/v1/quotations/display-board-option-list",
                             "FHPIO056104C0", {"FID_COND_SCR_DIV_CODE": "509",
                             "FID_COND_MRKT_DIV_CODE": "",
                             "FID_COND_MRKT_CLS_CODE": ""})
        result["kis"]["option_month_list"] = compact(payload.get("output", []),
            ("hts_kor_isnm", "futs_shrn_iscd", "optn_shrn_iscd", "futs_mtrt_cnt"), 20)
    except Exception as exc:
        result["errors"]["option_month_list"] = type(exc).__name__ + ": " + str(exc)[:120]
    try:
        partial = collect(day, market=market)
        result["collector"] = {"markets": partial["markets"],
                               "derivatives_ready": bool(partial["derivatives"])}
    except Exception as exc:
        result["errors"]["collector"] = type(exc).__name__ + ": " + str(exc)[:120]
    try:
        derivatives = collect_derivatives(market, day)
        result["derivative_collector"] = {
            key: {"future_close": value["future_close"],
                  "future_oi": value["future_oi"],
                  "options": len(value["options"]),
                  "monthly": sum(o["series"] == "monthly" for o in value["options"]),
                  "weekly": sum(o["series"] == "weekly" for o in value["options"]),
                  "first_option": value["options"][0]}
            for key, value in derivatives.items()}
    except Exception as exc:
        result["errors"]["derivative_collector"] = type(exc).__name__ + ": " + str(exc)[:120]
    sanitized = {
        "date": result["date"],
        "krx": {name: {"available": True, "fields": value.get("fields", [])}
                for name, value in result["krx"].items()},
        "kis": {name: {"available": True, "fields": value.get("fields", [])}
                for name, value in result["kis"].items()},
        "cash_collector_ready": "collector" in result,
        "derivative_collector_ready": "derivative_collector" in result,
        "errors": result["errors"],
    }
    out = Path(os.environ.get("PROBE_OUTPUT", "market-flow-probe.json"))
    out.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(sanitized, ensure_ascii=False))


if __name__ == "__main__":
    main()

