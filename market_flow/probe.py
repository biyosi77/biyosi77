"""Read-only schema probe for the user's KRX/KIS entitlements.

Runs on the feature branch PR. Never logs credentials or sends Telegram messages.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from valuation.api import MarketData

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
        except Exception as exc:
            result["errors"][label] = type(exc).__name__ + ": " + str(exc)[:120]
    ymd = day.strftime("%Y%m%d")
    for label, code in (("KOSPI", "KSP"), ("KOSDAQ", "KSQ")):
        try:
            payload = market.kis("/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
                                 "FHPTJ04040000", {"FID_COND_MRKT_DIV_CODE": "U",
                                 "FID_INPUT_ISCD": "0001", "FID_INPUT_DATE_1": ymd,
                                 "FID_INPUT_ISCD_1": code, "FID_INPUT_DATE_2": ymd,
                                 "FID_INPUT_ISCD_2": "0001"})
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
    out = Path(os.environ.get("PROBE_OUTPUT", "market-flow-probe.json"))
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # The selected market data and field names are public, while credentials are
    # never included in this result. Logs allow reviewing without artifact ZIP access.
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

