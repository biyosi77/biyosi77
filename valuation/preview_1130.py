"""One-off 11:30 preview. Never sends Telegram or touches the delivery ledger."""
import json
import time
from datetime import date, datetime
from pathlib import Path

from .api import DataError, KST, MarketData, Quote
from .run import TEMPLATE
from .workbook import records, build
from .expanded import prior_close, build_expanded
from .consensus import fetch_consensus


def main():
    day = date(2026, 11, 25)
    if datetime.now(KST).date() != day or datetime.now(KST).strftime("%H%M") < "1135":
        raise DataError("11:30 preview must be run on 2026-11-25 after 11:35 KST")
    market = MarketData()
    if not market.is_open(day):
        raise DataError("preview day is not a KRX trading day")
    _, rows = records(TEMPLATE)
    folder = Path("valuation-output")
    folder.mkdir(exist_ok=True)
    quotes = {}
    for code in rows:
        time.sleep(.2)
        bar = market.minute(code, day, "113000")
        shares = market.current_shares(code) if bar else None
        checked = datetime.now(KST).isoformat(timespec="seconds")
        quotes[code] = Quote(
            bar[1] if bar else None, shares,
            "KIS KRX(J) 날짜 검증 11:30 이전 분봉; KIS 상장주식수",
            f"{bar[0][:2]}:{bar[0][2:4]} KST KRX 분봉" if bar else "",
            checked, "" if bar and shares else "당일 11:30 이전 분봉 또는 상장주식수 미확인",
            day.isoformat(), volume_reason="임시 11:30 파일: 거래량 수집 대상 아님")
    if not any(q.price for q in quotes.values()):
        raise DataError("all 11:30 preview prices unavailable")
    previous_day, previous = prior_close(market, rows, day)
    consensus = fetch_consensus(rows, day)
    baseline = folder / ".1130-baseline.xlsx"
    build(TEMPLATE, baseline, day, "1130", quotes)
    output = folder / "valuation_20261125_1130_daily_returns_preview.xlsx"
    try:
        summary = build_expanded(baseline, output, day, quotes, previous_day, previous, consensus,
            price_label="11:30 주가", basis_label="임시 11:30 KST 또는 이전 마지막 KRX 분봉 (실제시각은 원자료)")
    finally:
        baseline.unlink(missing_ok=True)
    summary.update({"status": "validated_preview", "trade_date": day.isoformat(),
        "basis": "11:30 KST KRX 분봉 (종가 아님)", "telegram_sent": False,
        "price_times": {c: q.basis for c, q in quotes.items()},
        "price_data": {c: {"price": q.price, "shares": q.shares, "source": q.source,
                           "basis": q.basis, "checked": q.checked_at} for c,q in quotes.items()}})
    (folder / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("price_data","price_times")},ensure_ascii=False))


if __name__ == "__main__":
    main()
