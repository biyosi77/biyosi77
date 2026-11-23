import json

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.table import Table

from valuation.returns import append_returns, load_snapshot, DATES, price_return
from valuation.api import DataError


@pytest.mark.parametrize("start,end,expected", [
    (100, 125, .25), (100, 80, -.2), (100, 100, 0),
    (None, 100, "미확인"), (0, 100, "미확인"), (100, None, "미확인"),
])
def test_returns_are_endpoint_changes_not_drawdowns(start, end, expected):
    if isinstance(expected, str):
        assert price_return(start, end) == expected
    else:
        assert price_return(start, end) == pytest.approx(expected)


def test_snapshot_contains_the_149_approved_codes_and_four_exact_dates():
    from valuation.workbook import records
    from valuation.run import TEMPLATE
    _, codes = records(TEMPLATE)
    snapshot = load_snapshot()
    assert all(set(snapshot["days"][d]) == set(codes) for d in DATES)
    prices = [snapshot["days"][d]["005930"]["close"] for d in DATES]
    assert price_return(prices[2], prices[3]) == pytest.approx(-.3268382352941176)
    assert price_return(prices[0], prices[3]) == pytest.approx(-.11545893719806766)


def test_missing_new_stock_does_not_borrow_another_stock_baseline():
    snapshot = load_snapshot()
    wb = Workbook()
    main, raw = wb.active, wb.create_sheet()
    main.add_table(Table(displayName="ValuationTable", ref="A9:AC10"))
    raw.add_table(Table(displayName="SourceTable", ref="A9:BM10"))
    cache = {}
    expected = append_returns(main, raw, ["999999"], {"999999": 10}, cache, snapshot=snapshot)
    assert expected["999999"] == ["미확인"] * 4
    assert all(cache[f"{col}10"] == "미확인" for col in ("AD", "AE", "AF", "AG"))
    assert "기준 종가 미확인" in raw["BU10"].value


def test_invalid_snapshot_cannot_silently_produce_a_report(monkeypatch, tmp_path):
    import valuation.returns as returns
    snapshot = load_snapshot()
    snapshot["days"][DATES[0]]["005930"]["source"] = "NXT"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(returns, "SNAPSHOT", path)
    with pytest.raises(DataError):
        load_snapshot()
