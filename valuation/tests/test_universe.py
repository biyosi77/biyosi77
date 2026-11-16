import json

from valuation.run import TEMPLATE
from valuation.workbook import records, RAW, MAIN


def test_november_additions_preserve_existing_records_without_duplicate_oci():
    previous, old_rows = records(TEMPLATE.parent / "2027_valuation_20261020_133.xlsx")
    current, rows = records(TEMPLATE)
    requested = json.loads((TEMPLATE.parent / "additions_20261116.json").read_text(encoding="utf-8"))["stocks"]
    assert len(rows) == 149 and len(set(rows) - set(old_rows)) == 16
    for stock in requested:
        assert current[RAW].cell(rows[stock["code"]], 1).value == stock["name"]
    assert sum(current[RAW].cell(r, 2).value == "010060" for r in rows.values()) == 1
    for code, row in old_rows.items():
        assert rows[code] == row
        for col in range(1, 25):
            assert current[RAW].cell(row, col).value == previous[RAW].cell(row, col).value
    for code in set(rows) - set(old_rows):
        row = rows[code]
        assert all(current[RAW].cell(row, col).value is None for col in (4, 5, 9, 10, 15, 20, 21))
        assert current[MAIN].cell(row, 3).value == code
    assert current[MAIN].tables["ValuationTable"].ref == "A9:Q158"
