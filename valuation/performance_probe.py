"""One-off historical price collection. No Telegram or ledger operations."""
import json
import time
from datetime import date, timedelta, datetime
from pathlib import Path
from .api import MarketData, KST
from .run import TEMPLATE
from .workbook import records

_, codes = records(TEMPLATE)
market = MarketData()
dates = []
candidate = date(2026, 7, 31)
while candidate <= date(2026, 10, 5):
    if candidate.weekday() < 5 and candidate != date(2026, 8, 28):
        dates.append(candidate)
    candidate += timedelta(days=1)
result = {"checked_at": datetime.now(KST).isoformat(), "days": {}, "closed": [], "codes": list(codes)}
for day in dates:
    time.sleep(.3)
    if not market.is_open(day):
        result["closed"].append(day.isoformat())
        continue
    prices = market.closes(day)
    result["days"][day.isoformat()] = {
        code: {"close": prices[code][0], "source": "KRX " + prices[code][2]}
        if code in prices else {"close": None, "source": "", "reason": "KRX 해당일 종목 없음"}
        for code in codes}
folder = Path("valuation-output")
folder.mkdir(exist_ok=True)
(folder / "history.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Collected {len(codes)} stocks for {len(result['days'])} trading days")
