from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests
from openpyxl import load_workbook

from valuation.api import DataError, KIS, MarketData, Quote, choose_minute, credential
from valuation.delivery import DeliveryError, Ledger
from valuation.run import enforce_time, latest_scheduled_day, scheduled_target
from valuation.workbook import MAIN, RAW, build, records, yoy, yoy_formula


TEMPLATE = Path(__file__).parents[1] / "template" / "2027_valuation_20261016_yoy.xlsx"
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


def test_kis_token_rate_limit_waits_once_then_retries():
    class Session:
        calls = 0
        def request(self, *args, **kwargs):
            self.calls += 1
            response = requests.Response()
            response.headers["Content-Type"] = "application/json"
            if self.calls == 1:
                response.status_code = 403
                response._content = b'{"error_code":"EGW00133"}'
            else:
                response.status_code = 200
                response._content = b'{"access_token":"ok"}'
            return response
    client = MarketData.__new__(MarketData)
    client.session = Session()
    waits = []
    client.sleep = waits.append
    assert client._request("POST", KIS + "/oauth2/tokenP") == {"access_token": "ok"}
    assert client.session.calls == 2
    assert waits == [65]


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


def test_kis_close_fallback_requires_exact_day_and_krx_venue():
    client = MarketData.__new__(MarketData)
    calls = []
    def fake_kis(path, tr_id, params):
        calls.append((path, tr_id, params))
        return {"output2": [
            {"stck_bsop_date": "20261018", "stck_clpr": "999999"},
            {"stck_bsop_date": "20261019", "stck_clpr": "105000"},
        ]}
    client.kis = fake_kis
    day = date(2026, 10, 19)
    assert client.daily_close("005930", day) == 105000
    assert calls[0][2]["FID_COND_MRKT_DIV_CODE"] == "J"
    assert calls[0][2]["FID_INPUT_DATE_1"] == calls[0][2]["FID_INPUT_DATE_2"] == "20261019"
    assert calls[0][2]["FID_ORG_ADJ_PRC"] == "1"
    client.kis = lambda *a: {"output2": [{"stck_bsop_date": "20261018", "stck_clpr": "999999"}]}
    assert client.daily_close("005930", day) is None


def test_close_uses_exact_date_kis_fallback_when_krx_daily_is_empty():
    client = MarketData.__new__(MarketData)
    client.closes = lambda day: (_ for _ in ()).throw(DataError("KRX confirmed close dataset empty or not yet published"))
    client.shares = lambda day: {"005930": (5969782550, "stk_isu_base_info")}
    client.daily_close = lambda code, day: 105000
    client.sleep = lambda _: None
    quote = client.collect(["005930"], date(2026, 10, 19), "close")["005930"]
    assert quote.price == 105000 and quote.shares == 5969782550
    assert "KIS KRX 일봉" in quote.source
    assert quote.basis == "15:30 KST 정규장 종가"


def test_reference_time_guard():
    kst = ZoneInfo("Asia/Seoul")
    with pytest.raises(ValueError):
        enforce_time(DAY, "close", datetime(2026, 10, 15, 15, 59, tzinfo=kst))
    enforce_time(DAY, "1130", datetime(2026, 10, 15, 12, 0, tzinfo=kst))
    assert latest_scheduled_day(datetime(2026, 10, 16, 0, 30, tzinfo=kst), "close") == DAY
    assert latest_scheduled_day(datetime(2026, 10, 17, 13, 0, tzinfo=kst), "1130") == date(2026, 10, 16)


def test_schedule_retry_targets_expected_trading_session():
    kst = ZoneInfo("Asia/Seoul")
    tuesday = datetime(2026, 10, 20, 12, 50, tzinfo=kst)
    assert scheduled_target(tuesday, "17 12 * * 1-5") == ("1130", date(2026, 10, 20))
    assert scheduled_target(tuesday, "47 12 * * 1-6") == ("close", date(2026, 10, 19))
    assert scheduled_target(datetime(2026, 10, 24, 12, 50, tzinfo=kst),
                            "47 12 * * 1-6") == ("close", date(2026, 10, 23))
    assert scheduled_target(datetime(2026, 10, 20, 18, 20, tzinfo=kst),
                            "17 18 * * 1-5") == ("close", date(2026, 10, 20))
    with pytest.raises(ValueError, match="unrecognized"):
        scheduled_target(tuesday, "unexpected")


def test_yoy_calculation_matches_new_template():
    assert yoy(100, 125) == pytest.approx(0.25)
    assert yoy(100, 0) == -1
    assert yoy(100, -1) == "적자전환"
    assert yoy(-100, 10) == "흑자전환"
    assert yoy(-100, -50) == "적자지속"
    assert yoy(0, 10) == "흑자전환"
    assert yoy(0, 0) == "손익분기"
    assert yoy(0, -10) == "미확인"
    assert yoy(None, 10) == "미확인"
    assert "F10" in yoy_formula("F", "G", 10)
    assert "G10/F10-1" in yoy_formula("F", "G", 10)


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
    assert formulas[MAIN]["N9"].value == "27E ROE"
    assert formulas[MAIN]["D9"].value == "10/15 11:30 주가"
    assert formulas[RAW]["I9"].value == "10/15 11:30 주가"
    assert formulas[RAW]["AB9"].value == "예외 사유"
    assert formulas[RAW]["T9"].value == original[RAW]["T9"].value
    assert formulas[RAW].tables["SourceTable"].ref == "A9:AB99"
    assert missing in summary["missing"]
    ordered = [formulas[MAIN].cell(r, 3).value for r in range(10, 100)]
    assert ordered[-1] == missing or missing in ordered[-4:]
    row = 10 + ordered.index(missing)
    assert values[MAIN].cell(row, 4).value == "미확인"
    assert values[MAIN].cell(row, 5).value == "미산출"
    assert values[MAIN].cell(row, 12).value == "미산출"
    assert values[RAW].cell(rows[missing], 28).value == "no bar"
    for code in rows:
        raw_row = rows[code]
        main_row = 10 + ordered.index(code)
        assert values[MAIN].cell(main_row, 6).value == source.cell(raw_row, 20).value or (
            source.cell(raw_row, 20).value is None and values[MAIN].cell(main_row, 6).value == "미확인")
        assert values[MAIN].cell(main_row, 7).value == source.cell(raw_row, 4).value or (
            source.cell(raw_row, 4).value is None and values[MAIN].cell(main_row, 7).value == "미확인")
        assert values[MAIN].cell(main_row, 14).value == source.cell(raw_row, 15).value or (
            source.cell(raw_row, 15).value is None and values[MAIN].cell(main_row, 14).value == "미확인")
        assert values[RAW].cell(raw_row, 20).value == source.cell(raw_row, 20).value
        assert values[RAW].cell(raw_row, 24).value == source.cell(raw_row, 24).value
        assert formulas[MAIN].cell(main_row, 17).value == next(
            original[MAIN].cell(r, 17).value for r in range(10, 100)
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
