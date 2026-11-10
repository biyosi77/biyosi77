"""Refresh the approved 2026–28 grouped layout from verified market and annual sources."""
from copy import copy
from math import isclose
import re
from datetime import timedelta
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.worksheet.table import TableColumn

from .api import DataError
from .workbook import MAIN, RAW, FIRST, _set_cached_values, metric, yoy, yoy_formula

REFERENCE = Path(__file__).parent / "template" / "valuation_2026_2028.xlsx"
YEARS = (2026, 2027, 2028)
PROFIT_RAW_COLS = {"net": 29, "op": 30}
SITE_RAW_COLS = {"net": 55, "op": 58}
MAIN_YOY_COLS = {"net": 11, "op": 17}  # Before insertion of the volume column.


def comparable_periods(previous, current):
    return bool(previous.get("basis") and previous["basis"] == current.get("basis")
                and previous.get("month") == current.get("month"))


def same_yoy(left, right, tolerance=1e-12):
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return isclose(left, right, rel_tol=0, abs_tol=tolerance)
    return left == right


def use_site_yoy(key, previous, current):
    same_metric = key == "op" or current.get("basis") == "별도"
    return (same_metric and comparable_periods(previous, current)
            and previous.get(key) is not None and current.get(key) is not None
            and current.get("op_yoy" if key == "op" else "net_total_yoy") is not None)


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
        raw.cell(row, 48).value = item.get("roe_source") or "미확인"
        q = previous[code]
        raw.cell(row, 49).value = q.price if q.price is not None else "미확인"
        raw.cell(row, 50).value = previous_day.isoformat()
        raw.cell(row, 51).value = q.source
        raw.cell(row, 52).value = q.checked_at
        raw.cell(row, 53).value = q.reason or ""
        for year in YEARS:
            for key, field in (("net", "net_total_yoy"), ("op", "op_yoy")):
                value = years.get(year, {}).get(field)
                cell = raw.cell(row, SITE_RAW_COLS[key] + year - 2026)
                cell.value = value if value is not None else "미확인"
                cell.number_format = "0.00%"
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
    main["A5"] = "연간 YoY. 연결 순이익은 지배주주 기준. FnGuide 공개값 및 대사는 YoY 대사 시트 참조."
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
        for year in YEARS:
            prev, curr = years.get(year - 1, {}), years.get(year, {})
            for key, field in (("net", "net_total_yoy"), ("op", "op_yoy")):
                offset = year - 2026
                result_col = MAIN_YOY_COLS[key] + offset
                if use_site_yoy(key, prev, curr):
                    source_col = get_column_letter(SITE_RAW_COLS[key] + offset)
                    formula, value = f"=원자료!{source_col}{rr}", curr[field]
                elif comparable_periods(prev, curr):
                    prior_col = PROFIT_RAW_COLS[key] + 2 * offset
                    formula = yoy_formula(f"원자료!{get_column_letter(prior_col)}",
                                          f"원자료!{get_column_letter(prior_col + 2)}", rr)
                    value = yoy(prev.get(key), curr.get(key))
                else:
                    formula, value = '="미확인"', "미확인"
                main.cell(row, result_col).value = formula
                values[result_col] = value
        for income_col, multiple_col in ((8,20),(9,21),(10,22),(14,23),(15,24),(16,25)):
            letter=get_column_letter(income_col)
            main.cell(row,multiple_col).value=f'=IF(AND(ISNUMBER(G{row}),ISNUMBER({letter}{row}),{letter}{row}>0),G{row}/{letter}{row},"미산출")'
            values[multiple_col]=metric(caps[code],values[income_col])
        for col,value in values.items():
            cache[f"{get_column_letter(col)}{row}"]=value if value is not None else (
                "미산출" if col in (20,21,22,23,24,25) else "미확인")
    audit["A4"] = "공개값은 FnGuide 연간 표에서 조회. 연결 순이익 공개값은 전체 순이익 기준이며 지배주주 YoY와 구분."
    audit_headers = {
        16: "FnGuide 공개 YoY", 17: "공개값 이익 기준", 18: "조회시각 (KST)",
        19: "FnGuide 비교 전기 이익 (억원)", 20: "FnGuide 비교 당기 이익 (억원)",
    }
    audit_table = audit.tables["YoyAuditTable"]
    audit_table.ref = "A6:T804"
    if audit_table.autoFilter:
        audit_table.autoFilter.ref = audit_table.ref
    for col, label in audit_headers.items():
        audit.cell(6, col).value = label
        audit.column_dimensions[get_column_letter(col)].width = 26
        audit_table.tableColumns.append(TableColumn(id=col, name=label))
    audit_cache = {}
    index = 7
    for main_row, code in enumerate(ordered, FIRST):
        item = consensus[code]
        years, raw_row = item["years"], codes[code]
        for key, label, field in (("net", "순이익", "net_total_yoy"), ("op", "영업이익", "op_yoy")):
            for year in YEARS:
                prev, cur = years.get(year - 1, {}), years.get(year, {})
                comparable = comparable_periods(prev, cur)
                # Recompute from the two values placed in the audit sheet.
                prior = raw.cell(raw_row, PROFIT_RAW_COLS[key] + 2 * (year - 2026)).value
                current = raw.cell(raw_row, PROFIT_RAW_COLS[key] + 2 * (year - 2025)).value
                recalc = yoy(prior, current) if comparable else "미확인"
                site_value = cur.get(field)
                col_before_volume = MAIN_YOY_COLS[key] + year - 2026
                report_value = cache[f"{get_column_letter(col_before_volume)}{main_row}"]
                site_used = use_site_yoy(key, prev, cur)
                if not same_yoy(report_value, site_value if site_used else recalc):
                    raise DataError(f"YoY report reconciliation failed for {code} {year} {key}")
                if recalc == "미확인":
                    verdict, note = "미확인", "전기·당기 이익 또는 같은 결산월·회계 기준 확인 필요"
                elif site_value is None:
                    verdict, note = "공개값 없음", "연간 이익으로 재계산"
                elif key == "net" and cur.get("basis") == "연결":
                    verdict, note = "비교 기준 다름", "본표는 지배주주순이익, 공개 YoY는 전체 당기순이익"
                elif same_yoy(recalc, site_value, tolerance=0.000100001):
                    verdict, note = "일치", "공개값과 재계산값 차이 0.01%p 이내"
                else:
                    verdict, note = "공개값 차이", "공개 YoY를 표시하고 이익 재계산값과의 차이를 기록"
                main_address = f"{get_column_letter(col_before_volume + 1)}{main_row}"
                site_profit_key = "net_total" if key == "net" else "op"
                values = (
                    code, raw.cell(raw_row, 1).value, label, f"{year}E",
                    prev.get("period"), cur.get("period"), prev.get("basis"), cur.get("basis"),
                    prior, current, f"='{main.title}'!{main_address}",
                    yoy_formula("I", "J", index) if comparable else '="미확인"',
                    verdict, note, item["source"], site_value,
                    ("전체 당기순이익" if key == "net" and cur.get("basis") == "연결" else label),
                    item["checked"], prev.get(site_profit_key), cur.get(site_profit_key),
                )
                for col, value in enumerate(values, 1):
                    audit.cell(index, col).value = value if value is not None else "미확인"
                audit.cell(index, 16).number_format = "0.00%"
                for col in (19, 20):
                    audit.cell(index, col).number_format = "#,##0.00"
                audit_cache[f"K{index}"] = report_value
                audit_cache[f"L{index}"] = recalc
                index += 1
    # Add the KRX regular-session volume beside the stock code. Shift only
    # references to main-sheet cells; references to 원자료 retain their columns.
    main.insert_cols(4)
    for row in range(FIRST, last + 1):
        code = ordered[row - FIRST]
        raw_row = codes[code]
        volume = quotes[code].volume
        raw.cell(raw_row, 54).value = volume if volume is not None else "미확인"
        main.cell(row, 4)._style = copy(main.cell(row, 5)._style)
        main.cell(row, 4).number_format = '#,##0'
        main.cell(row, 4).value = f'=IF(ISNUMBER(원자료!BB{raw_row}),원자료!BB{raw_row},"미확인")'
        for col in range(5, 30):
            cell = main.cell(row, col)
            if cell.data_type == "f":
                cell.value = re.sub(
                    r'(?<![!A-Za-z0-9_])([A-Z]{1,3})(\d+)\b',
                    lambda match: f'{get_column_letter(column_index_from_string(match[1]) + 1)}{match[2]}',
                    cell.value)
    raw["BB9"] = "당일 KRX 정규장 거래량"
    raw.column_dimensions["BB"].width = 23
    raw.tables["SourceTable"].ref = f"A9:BH{last}"
    if raw.tables["SourceTable"].autoFilter is not None:
        raw.tables["SourceTable"].autoFilter.ref = raw.tables["SourceTable"].ref
    raw.tables["SourceTable"].tableColumns.append(TableColumn(id=54, name=raw["BB9"].value))
    for key, label in (("net", "전체 당기순이익"), ("op", "영업이익")):
        for year in YEARS:
            col = SITE_RAW_COLS[key] + year - 2026
            header = f"{year}E FnGuide {label} YoY"
            raw.cell(9, col).value = header
            raw.column_dimensions[get_column_letter(col)].width = 32
            raw.tables["SourceTable"].tableColumns.append(TableColumn(id=col, name=header))
    main["D9"]._style = copy(main["E9"]._style)
    main["D9"] = "거래량"
    main.column_dimensions["D"].width = 17
    main.tables["ValuationTable"].ref = f"A9:AC{last}"
    if main.tables["ValuationTable"].autoFilter is not None:
        main.tables["ValuationTable"].autoFilter.ref = main.tables["ValuationTable"].ref
    main.tables["ValuationTable"].tableColumns.insert(3, TableColumn(id=4, name="거래량"))
    for col, table_col in enumerate(main.tables["ValuationTable"].tableColumns, 1):
        table_col.id = col
        table_col.name = str(main.cell(9, col).value)
    cache = {f"{get_column_letter(column_index_from_string(re.match(r'[A-Z]+', address).group()) + 1)}{re.search(r'\d+$', address).group()}": value
             for address, value in cache.items()}
    for row, code in enumerate(ordered, FIRST):
        cache[f"D{row}"] = quotes[code].volume if quotes[code].volume is not None else "미확인"
    audit["A2"]=f"133종목 · 798항목 | {day.isoformat()} 기준"
    from openpyxl.workbook.properties import CalcProperties
    book.calculation = CalcProperties(fullCalcOnLoad=True)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    book.save(output)
    _set_cached_values(output, cache, audit_cache=audit_cache)
    check=load_workbook(output,data_only=True)
    assert len({str(check[MAIN].cell(r,3).value) for r in range(FIRST,last+1)})==133
    assert all(check[MAIN].cell(r,5).value == quotes[str(check[MAIN].cell(r,3).value)].price for r in range(FIRST,last+1))
    assert all(check[MAIN].cell(r,4).value == (quotes[str(check[MAIN].cell(r,3).value)].volume or "미확인") for r in range(FIRST,last+1))
    if any(not same_yoy(check[audit.title][address].value, value) for address, value in audit_cache.items()):
        raise DataError("saved YoY audit values could not be verified")
    return {"total_stocks":133,"successful_prices":sum(q.price is not None and q.shares is not None for q in quotes.values()),
        "missing":[c for c in ordered if quotes[c].price is None or quotes[c].shares is None],
        "missing_volume":[c for c in ordered if quotes[c].volume is None],
        "uncomputed_per":[c for c in ordered if per[c] is None],
        "uncomputed_por":[c for c in ordered if metric(caps[c],consensus[c]["years"].get(2027,{}).get("op")) is None]}

