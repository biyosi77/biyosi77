"""Collect verified KOSPI/KOSDAQ cash and program flows for a trading day.

The resulting JSON deliberately has no derivative data. The PDF generator will
reject it until the derivative close and investor flow have been verified.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from valuation.api import DataError, MarketData
try:
    from market_flow.collect_derivatives import collect_derivatives
except ModuleNotFoundError:
    from collect_derivatives import collect_derivatives

KST = ZoneInfo("Asia/Seoul")
KRX_BASE = "https://data-dbg.krx.co.kr/svc/apis/"
INVESTOR_PATH = "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market"
PROGRAM_PATH = "/uapi/domestic-stock/v1/quotations/comp-program-trade-daily"


def number(row, field):
    try:
        return float(str(row[field]).replace(",", ""))
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError(f"Invalid field {field}") from exc


def one_for_day(rows, ymd, label):
    matches = [r for r in rows if r.get("stck_bsop_date") == ymd]
    if len(matches) != 1:
        raise DataError(f"{label}: expected one row for {ymd}, got {len(matches)}")
    return matches[0]


def index_close(market, endpoint, index_name, ymd):
    payload = market._request("GET", KRX_BASE + endpoint,
                              headers={"AUTH_KEY": market.krx_key}, params={"basDd": ymd})
    rows = payload.get("OutBlock_1")
    if not isinstance(rows, list):
        raise DataError("KRX index response invalid")
    matches = [r for r in rows if r.get("IDX_NM") == index_name
               and r.get("BAS_DD") == ymd]
    if len(matches) != 1:
        raise DataError(f"KRX {index_name} close unavailable for {ymd}")
    return number(matches[0], "CLSPRC_IDX")


def collect(day, now=None, market=None):
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("now must have a timezone")
    now = now.astimezone(KST)
    if day > now.date() or (day == now.date() and now.time() < time(15, 45)):
        raise DataError("Derivative day session has not ended")
    market = market or MarketData()
    if not market.is_open(day):
        raise DataError(f"{day} is not a KRX trading day")
    ymd = day.strftime("%Y%m%d")
    out = {"date": day.isoformat(), "asof_kst": now.isoformat(timespec="seconds"),
           "demo": False, "markets": {}, "derivatives": {},
           "sources": [{"name": "KRX Open API 지수 일별시세", "asof_kst": now.isoformat(timespec="seconds"),
                        "url": "https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd"},
                       {"name": "KIS 시장별 투자자 및 프로그램매매", "asof_kst": now.isoformat(timespec="seconds"),
                        "url": "https://github.com/koreainvestment/open-trading-api"}]}
    for name, index_name, endpoint, code, venue in (
        ("KOSPI", "코스피", "idx/kospi_dd_trd", "0001", "KSP"),
        ("KOSDAQ", "코스닥", "idx/kosdaq_dd_trd", "1001", "KSQ"),
    ):
        close = index_close(market, endpoint, index_name, ymd)
        investor = market.kis(INVESTOR_PATH, "FHPTJ04040000", {
            "FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": ymd, "FID_INPUT_ISCD_1": venue,
            "FID_INPUT_DATE_2": ymd, "FID_INPUT_ISCD_2": code})
        investor_row = one_for_day(investor.get("output", []), ymd, name + " investor")
        if abs(close - number(investor_row, "bstp_nmix_prpr")) > 0.011:
            raise DataError(f"{name} KRX/KIS close mismatch")
        program = market.kis(PROGRAM_PATH, "FHPPG04600001", {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_MRKT_CLS_CODE": "K" if name == "KOSPI" else "Q",
            "FID_INPUT_DATE_1": ymd, "FID_INPUT_DATE_2": ymd})
        program_row = one_for_day(program.get("output", []), ymd, name + " program")
        # KIS *_pbmn fields are in millions of KRW; the report uses billions.
        out["markets"][name] = {
            "close": close, "prev_close": number(investor_row, "stck_prdy_clpr"),
            "foreign_net_bn": number(investor_row, "frgn_ntby_tr_pbmn") / 1000,
            "institution_net_bn": number(investor_row, "orgn_ntby_tr_pbmn") / 1000,
            "program_arb_net_bn": number(program_row, "arbt_smtn_ntby_tr_pbmn") / 1000,
            "program_nonarb_net_bn": number(program_row, "nabt_smtn_ntby_tr_pbmn") / 1000,
        }
    out["derivatives"] = collect_derivatives(market, day)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()

