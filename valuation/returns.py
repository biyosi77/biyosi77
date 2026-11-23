"""Approved fixed-date price returns, joined by stock code."""
import json
from copy import copy
from pathlib import Path

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import TableColumn

from .api import DataError

SNAPSHOT = Path(__file__).parent / "template" / "approved_return_closes_2026.json"
DATES = ("2026-07-30", "2026-08-28", "2026-10-06", "2026-11-20")
PAIRS = ((0, 1), (0, 2), (2, 3), (0, 3))
HEADERS = ("07/30→08/28\n종가 상승률", "07/30→10/06\n종가 상승률",
           "10/06→11/20\n종가 수익률", "07/30→11/20\n종가 수익률")


def price_return(start, end):
    valid = lambda x: type(x) in (int, float) and x > 0
    return end / start - 1 if valid(start) and valid(end) else "미확인"


def load_snapshot():
    value = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if tuple(value["dates"]) != DATES or set(value["days"]) != set(DATES):
        raise DataError("approved return snapshot dates mismatch")
    for day in DATES:
        for code, item in value["days"][day].items():
            if (len(code) != 6 or not code.isdigit()
                    or type(item["close"]) is not int or item["close"] <= 0
                    or item["source"] not in ("KRX stk_bydd_trd", "KRX ksq_bydd_trd")):
                raise DataError("approved return snapshot price/source invalid")
    return value


def append_returns(main, raw, ordered, rows, cache, *, snapshot=None):
    snapshot = snapshot if snapshot is not None else load_snapshot()
    last = 9 + len(ordered)
    raw_headers = [d + " KRX 종가" for d in DATES] + [
        "고정일 종가 출처", "고정일 종가 조회시각", "고정일 종가 기준", "고정일 종가 예외 사유"]
    for col, header in enumerate(raw_headers, 66):
        cell = raw.cell(9, col, header)
        cell._style = copy(raw["BM9"]._style)
        raw.column_dimensions[cell.column_letter].width = 30
        raw.tables["SourceTable"].tableColumns.append(TableColumn(id=col, name=header))
    expected = {}
    for code in ordered:
        rr = rows[code]
        data = [snapshot["days"][d].get(code, {}) for d in DATES]
        prices = [item.get("close") for item in data]
        for col, value in enumerate(prices, 66):
            cell = raw.cell(rr, col, value if value is not None else "미확인")
            cell._style = copy(raw.cell(rr, 54)._style)
            cell.number_format = "#,##0"
        reason = ", ".join(d for d, p in zip(DATES, prices) if p is None)
        for col, value in enumerate((
            "; ".join(sorted({item["source"] for item in data if item.get("source")})),
            snapshot["checked_at"], "2026년 KRX 정규장 비수정 종가 (원/주)",
            "기준 종가 미확인: " + reason if reason else "",
        ), 70):
            raw.cell(rr, col, value)._style = copy(raw.cell(rr, 65)._style)
        expected[code] = [price_return(prices[a], prices[b]) for a, b in PAIRS]
    main["AD6"] = "고정 기준일: 2026년 KRX 종가"
    main["AD7"] = "종가 수익률 = 종료일 / 시작일 − 1"
    main.merge_cells("AD6:AG6")
    main.merge_cells("AD7:AG7")
    for address in ("AD6", "AD7"):
        main[address].font = Font(name="맑은 고딕", size=11)
    main.merge_cells("AD8:AG8")
    main["AD8"] = "기간 수익률 · %"
    main["AD8"]._style = copy(main["AA8"]._style)
    raw_letters = ("BN", "BO", "BP", "BQ")
    for col, header in enumerate(HEADERS, 30):
        cell = main.cell(9, col, header)
        cell._style = copy(main["AC9"]._style)
        cell.fill = PatternFill("solid", fgColor="305F68")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        main.column_dimensions[cell.column_letter].width = 22
        main.tables["ValuationTable"].tableColumns.append(TableColumn(id=col, name=header))
    for row, code in enumerate(ordered, 10):
        rr = rows[code]
        for offset, (a, b) in enumerate(PAIRS):
            col = 30 + offset
            start, end = f"원자료!{raw_letters[a]}{rr}", f"원자료!{raw_letters[b]}{rr}"
            cell = main.cell(row, col)
            cell._style = copy(main.cell(row, 29)._style)
            cell.number_format = "0.00%;-0.00%;0.00%"
            cell.value = f'=IF(AND(ISNUMBER({start}),ISNUMBER({end}),{start}>0),{end}/{start}-1,"미확인")'
            cache[cell.coordinate] = expected[code][offset]
    for sheet, name, column in ((main, "ValuationTable", "AG"), (raw, "SourceTable", "BU")):
        table = sheet.tables[name]
        table.ref = f"A9:{column}{last}"
        if table.autoFilter is not None:
            table.autoFilter.ref = table.ref
    return expected
