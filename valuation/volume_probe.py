"""One-off read-only market response comparison; diagnostic branch only."""
import json
import time
from datetime import datetime
from pathlib import Path

from .api import MarketData, KST, DataError

market = MarketData()
day = datetime.now(KST).date()
result = {"day": day.isoformat(), "checked": datetime.now(KST).isoformat(), "stocks": {}}
for code in ("005930", "033160", "420770"):
    observations = {}
    result["stocks"][code] = observations
    requests = (
        ("trades_153001", "inquire-time-itemconclusion", "FHPST01060000", {"FID_INPUT_HOUR_1": "153001"}),
        ("trades_153100", "inquire-time-itemconclusion", "FHPST01060000", {"FID_INPUT_HOUR_1": "153100"}),
    )
    for label, endpoint, tr_id, params in requests:
        time.sleep(0.4)
        try:
            payload = market.kis("/uapi/domestic-stock/v1/quotations/" + endpoint, tr_id, {
                "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code, **params})
            keep = ("stck_bsop_date", "stck_cntg_hour", "stck_prpr", "stck_clpr", "acml_vol", "cntg_vol")
            observations[label] = {
                "summary": {key: payload.get("output1", {}).get(key) for key in keep},
                "rows": [{key: row.get(key) for key in keep} for row in payload.get("output2", [])[:3]],
            }
        except DataError as exc:
            observations[label] = {"error": str(exc)}
folder = Path("valuation-output")
folder.mkdir(exist_ok=True)
(folder / "volume-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
