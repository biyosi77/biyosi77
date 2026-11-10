import json
from datetime import date

import pytest
from openpyxl import load_workbook

from valuation.api import Quote
from valuation.consensus import parse_annual_page
from valuation.expanded import REFERENCE, build_expanded
from valuation.workbook import FIRST


def test_fnguide_uses_the_annual_table_and_keeps_total_net_separate():
    data = {
        "header": [
            {"YYMM": None, "EP_CHK": None, "CD": "VAL1"},
            {"YYMM": "2025/12", "EP_CHK": " ", "CD": "VAL3"},
            {"YYMM": "2026/12", "EP_CHK": "E", "CD": "VAL4"},
        ],
        "data": [
            {"AC_CODE": "121450", "LVL": 1, "NAME": "영업이익", "VAL3": "121.01", "VAL4": "307.30"},
            {"AC_CODE": "121450", "LVL": 2, "NAME": " 전년동기대비", "VAL4": "153.95"},
            {"AC_CODE": "121450", "LVL": 2, "NAME": " 컨센서스대비", "VAL4": None},
            {"AC_CODE": "122700", "LVL": 1, "NAME": "당기순이익", "VAL3": "154.52", "VAL4": "292.76"},
            {"AC_CODE": "122700", "LVL": 2, "NAME": " 전년동기대비", "VAL4": "89.46"},
            {"AC_CODE": "122710", "LVL": 1, "NAME": "당기순이익(지배)", "VAL3": "154.52", "VAL4": "292.80"},
        ],
    }
    page = "consensus.init({cmp_cd: '420770', consol_typ:'C', perforTrend: " + json.dumps(data) + "});"
    years, basis = parse_annual_page(page, "420770")
    assert basis == "C"
    assert years[2025]["period"] == "2025.12(A)"
    assert years[2026]["net"] == 292.8
    assert years[2026]["net_total"] == 292.76
    assert years[2026]["net_total_yoy"] == pytest.approx(0.8946)
    assert years[2026]["op_yoy"] == pytest.approx(1.5395)
    with pytest.raises(ValueError, match="identity"):
        parse_annual_page(page, "005930")


def test_all_yoy_formula_references_follow_stock_code_after_per_sort(tmp_path):
    with REFERENCE.open("rb") as source:
        original = load_workbook(source, read_only=True, data_only=True)
        codes = [row[1] for row in original.worksheets[1].iter_rows(min_row=FIRST, values_only=True)]
        original.close()
    quotes = {code: Quote(1000 + i, 1000000, "test", "test", "test", volume=i,
                          volume_source=f"KIS {code}", volume_basis=f"basis {code}",
                          volume_checked_at="checked", volume_evidence=f"evidence {code}")
              for i, code in enumerate(codes)}
    consensus = {}
    for i, code in enumerate(codes):
        years = {}
        for year in range(2025, 2029):
            net = 100 + i * (year - 2024)
            years[year] = {
                "basis": "연결" if i != 1 else "별도", "month": "12",
                "period": f"{year}.12({'A' if year == 2025 else 'E'})",
                "net": net, "op": net * 2,
                "net_total_yoy": 0.24,
                "op_yoy": None if i == 0 else 0.23,
            }
        consensus[code] = {"years": years, "source": "FnGuide", "checked": "KST", "reason": ""}

    path = tmp_path / "expanded.xlsx"
    build_expanded(REFERENCE, path, date(2026, 11, 9), quotes, date(2026, 11, 6), quotes, consensus)
    formulas = load_workbook(path)
    values = load_workbook(path, data_only=True)
    main, _, audit = formulas.worksheets
    main_values, raw, audit_values = values.worksheets
    assert main["C10"].value != codes[0]
    rows = {main.cell(row, 3).value: row for row in range(FIRST, main.max_row + 1)}
    for code, row in rows.items():
        raw_row = codes.index(code) + FIRST
        assert main_values.cell(row, 4).value == quotes[code].volume
        assert raw.cell(raw_row, 54).value == quotes[code].volume
        assert raw.cell(raw_row, 61).value == f"KIS {code}"
        assert raw.cell(raw_row, 65).value == f"evidence {code}"
    assert raw.tables["SourceTable"].ref == "A9:BM142"
    assert len(raw.tables["SourceTable"].tableColumns) == 65
    for cells in audit.iter_rows(min_row=7, values_only=False):
        code, key, year = cells[0].value, cells[2].value, int(cells[3].value[:4])
        offset = year - 2026
        col = (12 if key == "순이익" else 18) + offset
        main_cell = main.cell(rows[code], col)
        assert cells[10].value == f"='{main.title}'!{main_cell.coordinate}"
        actual = audit_values[cells[10].coordinate].value
        assert actual == pytest.approx(main_values[main_cell.coordinate].value)
        source_row = codes.index(code) + FIRST
        prev_col = (29 if key == "순이익" else 30) + 2 * offset
        previous = raw.cell(source_row, prev_col)
        current = raw.cell(source_row, prev_col + 2)
        assert audit_values[cells[11].coordinate].value == pytest.approx(current.value / previous.value - 1)
        site_used = (key == "순이익" and code == codes[1]) or (key == "영업이익" and code != codes[0])
        if site_used:
            site = raw.cell(source_row, (55 if key == "순이익" else 58) + offset)
            assert main_cell.value == f"=원자료!{site.coordinate}"
            assert actual == pytest.approx(site.value)
        else:
            assert f"원자료!{current.coordinate}/원자료!{previous.coordinate}-1" in main_cell.value
            assert actual == pytest.approx(current.value / previous.value - 1)
