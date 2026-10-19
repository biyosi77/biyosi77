from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests
from openpyxl import load_workbook

from valuation.api import DataError, KIS, MarketData, Quote, choose_minute, credential
from valuation.delivery import DeliveryError, Ledger
from valuation.run import enforce_time, latest_scheduled_day
from valuation.workbook import MAIN, RAW, build, records


TEMPLATE = Path(__file__).parents[1] / "template" / "2027_valuation_20261015_close.xlsx"
DAY = date(2026, 10, 15)


def test_price_time_selects_latest_prior_bar_on_requested_day():
    bars = [
        {"stck_bsop_date": "20261014", "stck_cntg_hour": "113000", "stck_prpr": "999"},
        {"stck_bsop_date": "20261015", "stck_cntg_hour": "113100", "stck_prpr": "888"},
        {"stck_bsop_date": "20261015", "stck_cntg_hour": "112900", "stck_prpr": "101"},
        {"stck_bsop_date": "20261015", "stck_cntg_hour": "113000", "stck_prpr": "102"},
    ]
    assert choose_minute(bars, DAY) == ("113000", 102)
    assert choose_minute(bars[:-1], DAY) == ("112900", 101)
    assert choose_minute(bars[:2], DAY) is None


def test_invalid_api_secret_is_not_retried_or_logged():
    class Session:
        calls = 0
        def request(self, *args, **kwargs):
            self.calls += 1
            response = requests.Response()
            response.status_code = 403
            response.headers["Content-Type"] = "application/json"
            response._content = b'{"error_code":"EGW00105","appsecret":"sensitive"}'
            return response
    client = MarketData.__new__(MarketData)
    client.session = Session()
    client.sleep = lambda _: None
    with pytest.raises(DataError, match=r"KIS token request failed \(HTTP 403, code EGW00105\)") as error:
        client._request("POST", KIS + "/oauth2/tokenP", json={})
    assert client.session.calls == 1
    assert "sensitive" not in str(error.value)


def test_secret_copy_format_is_trimmed(monkeypatch):
    monkeypatch.setenv("KIS_APP_SECRET", '  "abc123"  ')
    assert credential("KIS_APP_SECRET") == "abc123"


def test_holiday_requires_exact_day_and_open_flag():
    client = MarketData.__new__(MarketData)
    client.kis = lambda *a: {"output": [{"bass_dt": "20261015", "opnd_yn": "N"}]}
    assert client.is_open(DAY) is False
    client.kis = lambda *a: {"output": [{"bass_dt": "20261014", "opnd_yn": "Y"}]}
    with pytest.raises(Exception, match="requested date"):
        client.is_open(DAY)


def test_minute_request_is_krx_venue_and_requested_day():
    client = MarketData.__new__(MarketData)
    calls = []
    def fake_kis(path, tr_id, params):
        calls.append((path, tr_id, params))
        return {"output2": [{"stck_bsop_date": "20261015", "stck_cntg_hour": "113000", "stck_prpr": "100"}]}
    client.kis = fake_kis
    assert client.minute("005930", DAY) == ("113000", 100)
    assert calls[0][2]["FID_COND_MRKT_DIV_CODE"] == "J"
    assert calls[0][2]["FID_INPUT_DATE_1"] == "20261015"
    assert calls[0][2]["FID_INPUT_HOUR_1"] == "113000"


def test_close_rejects_wrong_date():
    client = MarketData.__new__(MarketData)
    client.krx = lambda *a: [{"ISU_CD": "005930", "BAS_DD": "20261014",
                              "TDD_CLSPRC": "100", "LIST_SHRS": "1000"}]
    with pytest.raises(Exception, match="empty"):
        client.closes(DAY)


def test_reference_time_guard():
    kst = ZoneInfo("Asia/Seoul")
    with pytest.raises(ValueError):
        enforce_time(DAY, "close", datetime(2026, 10, 15, 15, 59, tzinfo=kst))
    enforce_time(DAY, "1130", datetime(2026, 10, 15, 12, 0, tzinfo=kst))
    assert latest_scheduled_day(datetime(2026, 10, 16, 0, 30, tzinfo=kst), "close") == DAY
    assert latest_scheduled_day(datetime(2026, 10, 17, 13, 0, tzinfo=kst), "1130") == date(2026, 10, 16)


def test_calculation_code_mapping_sort_and_missing(tmp_path):
    original, rows = records(TEMPLATE)
    source = original[RAW]
    quotes = {code: Quote(source.cell(row, 9).value, source.cell(row, 10).value,
                          "fixture KRX", "11:30 KST", "2026-10-15T12:01:00+09:00")
              for code, row in rows.items()}
    missing = "005930"
    quotes[missing] = Quote(None, None, "fixture KRX", "", "2026-10-15T12:01:00+09:00", "no bar")
    output = tmp_path / "valuation_20261015_1130.xlsx"
    summary = build(TEMPLATE, output, DAY, "1130", quotes, test=True)
    formulas = load_workbook(output, data_only=False)
    values = load_workbook(output, data_only=True)
    assert formulas.sheetnames == original.sheetnames
    assert formulas[MAIN]["J9"].value == "27E ROE"
    assert formulas[MAIN]["D9"].value == "10/15 11:30 주가"
    assert formulas[RAW]["I9"].value == "10/15 11:30 주가"
    assert formulas[RAW]["W9"].value == "예외 사유"
    assert missing in summary["missing"]
    ordered = [formulas[MAIN].cell(r, 3).value for r in range(10, 100)]
    assert ordered[-1] == missing or missing in ordered[-4:]
    row = 10 + ordered.index(missing)
    assert values[MAIN].cell(row, 4).value == "미확인"
    assert values[MAIN].cell(row, 5).value == "미산출"
    assert values[MAIN].cell(row, 8).value == "미산출"
    assert values[RAW].cell(rows[missing], 23).value == "no bar"
    for code in rows:
        raw_row = rows[code]
        main_row = 10 + ordered.index(code)
        assert values[MAIN].cell(main_row, 6).value == source.cell(raw_row, 4).value or (
            source.cell(raw_row, 4).value is None and values[MAIN].cell(main_row, 6).value == "미확인")
        assert formulas[MAIN].cell(main_row, 13).value == next(
            original[MAIN].cell(r, 13).value for r in range(10, 100)
            if original[MAIN].cell(r, 3).value == code)


def test_delivery_claim_blocks_rerun_and_marks_after_success():
    class MemoryLedger(Ledger):
        def __init__(self):
            self.value = None
        def ensure_branch(self):
            pass
        def read(self, key):
            return self.value, "sha" if self.value else None
        def write(self, key, value, sha=None):
            self.value = value
    ledger = MemoryLedger()
    claim = ledger.claim("20261015_1130")
    assert ledger.value["status"] == "sending"
    with pytest.raises(DeliveryError):
        ledger.claim("20261015_1130")
    ledger.complete("20261015_1130", claim, 123)
    assert ledger.value["status"] == "sent"
    assert ledger.value["telegram_message_id"] == 123
    with pytest.raises(DeliveryError):
        ledger.claim("20261015_1130")
    ledger.claim("20261015_1130", force=True)
    assert ledger.value["status"] == "sending"
