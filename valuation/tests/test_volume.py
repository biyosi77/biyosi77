"""Regression cases shaped from the 2026-11-10 live KIS responses."""
from datetime import datetime, timedelta

import pytest

from valuation.api import DataError, KST, MarketData, Quote, reconcile_closing_volume


def trades(day):
    return [
        {"stck_cntg_hour": "153019", "stck_prpr": "198900", "acml_vol": "14480594"},
        {"stck_cntg_hour": "151959", "stck_prpr": "198500", "acml_vol": "13039492"},
        {"stck_cntg_hour": "151959", "stck_prpr": "198500", "acml_vol": "13039442"},
    ]


def test_late_snapshot_does_not_replace_closing_volume():
    day = datetime.now(KST).date()
    client = MarketData.__new__(MarketData)
    requests = []
    def kis(path, tr_id, params):
        requests.append((path, tr_id, params))
        return {"output1": {"stck_prpr": "197300", "acml_vol": "15289184"},
                "output2": trades(day)}
    client.kis = kis
    volume, basis, evidence = client.closing_volume("005930", day, 198900, 1441102)
    assert volume == 14480594
    assert "15:30:19" in basis and "1441102" in evidence
    assert requests[0][2] == {"FID_COND_MRKT_DIV_CODE": "J",
                               "FID_INPUT_ISCD": "005930", "FID_INPUT_HOUR_1": "153100"}
    # Even a coincidentally matching current price does not validate output1.
    client.kis = lambda *args: {"output1": {"stck_prpr": "198900", "acml_vol": "15289184"},
                              "output2": trades(day)}
    assert client.closing_volume("005930", day, 198900, 1441102)[0] == 14480594


@pytest.mark.parametrize("case", ["missing_auction", "wrong_price", "wrong_volume",
                                 "wrong_day", "missing_predecessor", "unknown_minute"])
def test_volume_requires_auction_reconciliation(case):
    day = datetime.now(KST).date()
    rows, count = trades(day), 1441102
    if case == "missing_auction":
        rows.pop(0)
    elif case == "wrong_price":
        rows[0]["stck_prpr"] = "197300"
    elif case == "wrong_volume":
        rows[0]["acml_vol"] = "15289184"
    elif case == "wrong_day":
        rows[0]["stck_bsop_date"] = (day - timedelta(days=1)).strftime("%Y%m%d")
    elif case == "missing_predecessor":
        rows = rows[:1]
    else:
        count = None
    with pytest.raises(DataError):
        reconcile_closing_volume(rows, day, 198900, count)


def test_after_hours_ignored_and_no_auction_case_is_explicit():
    day = datetime.now(KST).date()
    rows = trades(day) + [{"stck_cntg_hour": "154000", "stck_prpr": "198900",
                           "acml_vol": "15289184"}]
    assert reconcile_closing_volume(rows, day, 198900, 1441102)[0] == 14480594
    volume, basis, _ = reconcile_closing_volume(rows[1:3], day, 198500, 0)
    assert volume == 13039492 and "15:19:59" in basis


def test_same_day_endpoint_not_used_for_historical_volume():
    client = MarketData.__new__(MarketData)
    client.kis = lambda *args: pytest.fail("historical date called today's endpoint")
    with pytest.raises(DataError, match="날짜"):
        client.closing_volume("005930", datetime.now(KST).date() - timedelta(days=1), 100, 10)


def test_minute_execution_volume_not_summary_total():
    day = datetime.now(KST).date()
    client = MarketData.__new__(MarketData)
    client.kis = lambda *args: {
        "output1": {"stck_prpr": "198900", "acml_vol": "15289184"},
        "output2": [{"stck_bsop_date": day.strftime("%Y%m%d"), "stck_cntg_hour": "153000",
                     "stck_prpr": "198900", "cntg_vol": "1441102"}],
    }
    assert client.minute("005930", day, "153000", include_execution_volume=True) == (
        "153000", 198900, 1441102)


def test_volume_failure_preserves_price_and_records_reason():
    day = datetime.now(KST).date()
    client = MarketData.__new__(MarketData)
    client.minute = lambda *args, **kwargs: ("153000", 198900, 1441102)
    client.current_shares = lambda _: 1000000
    def fail(*args):
        raise DataError("종가 동시호가 체결 미확인")
    client.closing_volume = fail
    quote = client.kis_regular_close_snapshot("005930", day)
    assert quote.price == 198900 and quote.volume is None
    assert quote.volume_reason == "종가 동시호가 체결 미확인"


def test_daily_totals_never_overwrite_timed_volume():
    day = datetime.now(KST).date()
    client = MarketData.__new__(MarketData)
    client.sleep = lambda _: None
    client.kis_regular_close_snapshot = lambda code, _: Quote(
        198900, 1000000, "test", "test", "test", trade_date=day.isoformat(), volume=14480594)
    client.closes = lambda _: pytest.fail("unnecessary same-day KRX fallback")
    assert client.collect_same_day_close(["005930"], day)["005930"].volume == 14480594
