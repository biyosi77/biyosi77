"""Refresh the approved 2026–28 grouped layout from verified market and annual sources."""
from copy import copy
from datetime import timedelta
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import TableColumn

from .api import DataError
from .workbook import MAIN, RAW, FIRST, _set_cached_values, metric, yoy, yoy_formula

REFERENCE = Path(__file__).parent / "template" / "valuation_2026_2028.xlsx"


def prior_close(market, codes, day):
    candidate = day - timedelta(days=1)
    for _ in range(10):
        if candidate.weekday() < 5 and market.is_open(candidate):
            quotes = market.collect_verified_close(codes, candidate)
            return candidate, quotes
        candidate -= timedelta(days=1)
    raise DataError("previous trading day not verified")


def build_expanded(old_file, output, day, quotes, previous_day, previous, consensus):
    old = load_workbook(old_file, data_only=True)
    book = load_workbook(REFERENCE)
    main, raw, audit = book.worksheets
    original = old[RAW]
    codes = {str(original.cell(row, 2).value): row for row in range(FIRST, original.max_row + 1)}
    if set(codes) != set(quotes) or set(codes) != set(previous) or set(codes) != set(consensus):
        raise ValueError("expanded stock mapping mismatch")
    last = FIRST + len(codes) - 1
    if last != 142:
        raise ValueError("expected 133 stocks")
    for row in range(FIRST, last + 1):
        for col in range(1, 29):
            raw.cell(row, col).value = original.cell(row, col).value
    raw["A4"] = f"{day.isoformat()} KRX 정규장 15:30 종가 기준."
    raw["I9"] = day.strftime("%m/%d") + " 당일 종가"
    raw["AW9"] = "직전 거래일 종가"
    raw["AX9"] = "직전 거래일"
    raw["AY9"] = "전일 종가 출처"
    raw["AZ9"] = "전일 종가 조회시각 (KST)"
    raw["BA9"] = "전일 종가 예외 사유"
    raw_headers = ["2025A 순이익", "2025A 영업이익", "2026E 순이익", "2026E 영업이익",
                   "2027E 순이익", "2027E 영업이익", "2028E 순이익", "2028E 영업이익"]
    for col, label in enumerate(raw_headers, 29):
        raw.cell(9, col).value = label
    for row in range(FIRST, last + 1):
        code = str(raw.cell(row, 2).value)
        item = consensus[code]
        years = item["years"]
        for year, cols in ((2025, (29, 30)), (2026, (31, 32)),
                           (2027, (33, 34)), (2028, (35, 36))):
            for key, col in zip(("net", "op"), cols):
                value = years.get(year, {}).get(key)
                raw.cell(row, col).value = value if value is not None else "미확인"
        raw.cell(row, 37).value = " / ".join(
            f"{years[y]['period']} {years[y]['basis']}" for y in sorted(years))
        raw.cell(row, 38).value = item["source"]
        raw.cell(row, 39).value = item["checked"]
        raw.cell(row, 40).value = item["reason"]
        raw.cell(row, 41).value = " / ".join(years[y]["period"] for y in sorted(years))
        old_net, old_op = original.cell(row, 4).value, original.cell(row, 5).value
        new_net, new_op = years.get(2027, {}).get("net"), years.get(2027, {}).get("op")
        raw.cell(row, 42).value = new_net / old_net - 1 if isinstance(old_net, (int, float)) and old_net and new_net is not None else "미확인"
        raw.cell(row, 43).value = new_op / old_op - 1 if isinstance(old_op, (int, float)) and old_op and new_op is not None else "미확인"
        for year, col in ((2026, 45), (2027, 46), (2028, 47)):
            value = years.get(year, {}).get("roe")
            raw.cell(row, col).value = value if value is not None else "미확인"
        raw.cell(row, 48).value = item["source"]
        q = previous[code]
        raw.cell(row, 49).value = q.price if q.price is not None else "미확인"
        raw.cell(row, 50).value = previous_day.isoformat()
        raw.cell(row, 51).value = q.source
        raw.cell(row, 52).value = q.checked_at
        raw.cell(row, 53).value = q.reason or ""
    raw.tables["SourceTable"].ref = f"A9:BA{last}"
    if raw.tables["SourceTable"].autoFilter:
        raw.tables["SourceTable"].autoFilter.ref = f"A9:BA{last}"
    for col in range(1, 54):
        raw.tables["SourceTable"].tableColumns[col-1].name = str(raw.cell(9, col).value)
    caps = {code: quotes[code].price * quotes[code].shares / 100_000_000
            if quotes[code].price is not None and quotes[code].shares is not None else None
            for code in codes}
    per = {code: metric(caps[code], consensus[code]["years"].get(2027, {}).get("net"))
           for code in codes}
    ordered = sorted(codes, key=lambda c: (per[c] is None, per[c] if per[c] is not None else float("inf"), c))
    main["A3"] = f"{day.isoformat()} 15:30 KST KRX 정규장 종가. 단위: 억원, 원, %, 배."
    main["A5"] = "이익 YoY는 연간 기준. 종목별 원자료와 YoY 대사 시트 참조."
    main["D9"] = day.strftime("%m/%d") + " 당일 종가"
    main["E9"] = previous_day.strftime("%m/%d") + " 전일 종가"
    cache = {}
    for index, code in enumerate(ordered):
        row, rr = FIRST + index, codes[code]
        q, pq, years = quotes[code], previous[code], consensus[code]["years"]
        main.cell(row, 1).value = index+1 if per[code] is not None else "미산출"
        main.cell(row, 2).value = raw.cell(rr, 1).value
        main.cell(row, 3).value = code
        direct = {4: (9, q.price), 5: (49, pq.price),
                  8: (31, years.get(2026, {}).get("net")),
                  9: (33, years.get(2027, {}).get("net")),
                  10: (35, years.get(2028, {}).get("net")),
                  14: (32, years.get(2026, {}).get("op")),
                  15: (34, years.get(2027, {}).get("op")),
                  16: (36, years.get(2028, {}).get("op")),
                  26: (45, years.get(2026, {}).get("roe")),
                  27: (46, years.get(2027, {}).get("roe")),
                  28: (47, years.get(2028, {}).get("roe"))}
        values = {4:q.price,5:pq.price,6:q.price/pq.price-1 if q.price and pq.price else None,
                  7:caps[code],26:years.get(2026,{}).get("roe"),
                  27:years.get(2027,{}).get("roe"),28:years.get(2028,{}).get("roe")}
        for col,(raw_col,value) in direct.items():
            main.cell(row,col).value = f'=IF(ISNUMBER(원자료!{get_column_letter(raw_col)}{rr}),원자료!{get_column_letter(raw_col)}{rr},"미확인")'
            values[col] = value
        main.cell(row,6).value = f'=IF(AND(ISNUMBER(D{row}),ISNUMBER(E{row}),E{row}>0),D{row}/E{row}-1,"미확인")'
        main.cell(row,7).value = f'=IF(AND(ISNUMBER(D{row}),ISNUMBER(원자료!J{rr})),D{row}*원자료!J{rr}/100000000,"미확인")'
        for year, income_cols, result_cols in ((2026,(8,14),(11,17)),(2027,(9,15),(12,18)),(2028,(10,16),(13,19))):
            for key, income_col, result_col in zip(("net","op"), income_cols,result_cols):
                prev = years.get(year-1,{})
                curr = years.get(year,{})
                comparable = bool(prev.get("basis") and prev.get("basis")==curr.get("basis") and prev.get("month")==curr.get("month"))
                prior_value = prev.get(key)
                current = curr.get(key)
                previous_column = ("원자료!AC" if key == "net" else "원자료!AD") if year == 2026 else get_column_letter(income_col-1)
                main.cell(row,result_col).value = (yoy_formula(previous_column,get_column_letter(income_col),row)
                                                   if comparable else '="미확인"')
                values[result_col] = yoy(prior_value,current) if comparable else "미확인"
        for income_col, multiple_col in ((8,20),(9,21),(10,22),(14,23),(15,24),(16,25)):
            letter=get_column_letter(income_col)
            main.cell(row,multiple_col).value=f'=IF(AND(ISNUMBER(G{row}),ISNUMBER({letter}{row}),{letter}{row}>0),G{row}/{letter}{row},"미산출")'
            values[multiple_col]=metric(caps[code],values[income_col])
        for col,value in values.items():
            cache[f"{get_column_letter(col)}{row}"]=value if value is not None else (
                "미산출" if col in (20,21,22,23,24,25) else "미확인")
    # The audit follows the currently fetched annual periods and sorted stock codes.
    for row in range(7, 805):
        for col in range(1, 16):
            audit.cell(row,col).value = None
    index = 7
    for code in ordered:
        years = consensus[code]["years"]
        for key,label in (("net","순이익"),("op","영업이익")):
            for year in (2026,2027,2028):
                prev,cur=years.get(year-1,{}),years.get(year,{})
                comparable=bool(prev.get("basis") and prev.get("basis")==cur.get("basis") and prev.get("month")==cur.get("month"))
                value=yoy(prev.get(key),cur.get(key)) if comparable else "미확인"
                rr=codes[code]
                audit.cell(index,1).value=code
                audit.cell(index,2).value=raw.cell(rr,1).value
                audit.cell(index,3).value=label
                audit.cell(index,4).value=f"{year}E"
                for col,v in ((5,prev.get("period")),(6,cur.get("period")),(7,prev.get("basis")),(8,cur.get("basis")),(9,prev.get(key)),(10,cur.get(key)),(11,value),(12,value),(13,"미확인" if value=="미확인" else "재계산 일치"),(14,"연간 이익으로 독립 재계산"),(15,consensus[code]["source"])):
                    audit.cell(index,col).value=v if v is not None else "미확인"
                index+=1
    audit["A2"]=f"133종목 · 798항목 | {day.isoformat()} 기준"
    from openpyxl.workbook.properties import CalcProperties
    book.calculation = CalcProperties(fullCalcOnLoad=True)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    book.save(output)
    _set_cached_values(output,cache)
    check=load_workbook(output,data_only=True)
    assert len({str(check[MAIN].cell(r,3).value) for r in range(FIRST,last+1)})==133
    assert all(check[MAIN].cell(r,4).value == quotes[str(check[MAIN].cell(r,3).value)].price for r in range(FIRST,last+1))
    return {"total_stocks":133,"successful_prices":sum(q.price is not None and q.shares is not None for q in quotes.values()),
        "missing":[c for c in ordered if quotes[c].price is None or quotes[c].shares is None],
        "uncomputed_per":[c for c in ordered if per[c] is None],
        "uncomputed_por":[c for c in ordered if metric(caps[c],consensus[c]["years"].get(2027,{}).get("op")) is None]}

