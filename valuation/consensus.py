"""Annual FnGuide consensus with one paced request per stock."""
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

from .api import KST, DataError


def _number(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_consensus(codes, day, session=None):
    session = session or requests.Session()
    result = {}
    for index, code in enumerate(codes):
        if index:
            time.sleep(0.6)
        url = "https://comp.wisereport.co.kr/company/ajax/c1050001_data.aspx?" + urlencode({
            "flag": "2", "cmp_cd": code, "finGubun": "MAIN", "frq": "0",
            "sDT": day.strftime("%Y%m%d"), "chartType": "image"})
        checked = datetime.now(KST).isoformat(timespec="seconds")
        try:
            response = session.get(url, headers={"User-Agent": "Mozilla/5.0",
                "Referer": f"https://comp.wisereport.co.kr/company/c1050001.aspx?cmp_cd={code}"}, timeout=15)
            if response.status_code in (401, 403, 429):
                raise DataError(f"FnGuide access restricted: HTTP {response.status_code}")
            response.raise_for_status()
            data = response.json()["JsonData"]
            if not isinstance(data, list):
                raise ValueError("invalid annual consensus")
        except (requests.RequestException, ValueError, KeyError) as exc:
            result[code] = {"years": {}, "source": url, "checked": checked,
                            "reason": type(exc).__name__}
            continue
        years = {}
        for item in data:
            match = re.fullmatch(r"(202[5-8])\.(\d\d)\(([AE])\)", item.get("YYMM", ""))
            if not match or match[3] != ("A" if match[1] == "2025" else "E"):
                continue
            year = int(match[1])
            if year in years:
                raise DataError("FnGuide duplicate annual period")
            roe = _number(item.get("ROE"))
            years[year] = {"period": item["YYMM"], "month": match[2],
                           "basis": item.get("MAIN"), "net": _number(item.get("NP_TIP", item.get("NP"))),
                           "op": _number(item.get("OP_TIP", item.get("OP"))),
                           "roe": roe / 100 if roe is not None else None}
        result[code] = {"years": years, "source": url, "checked": checked,
                        "reason": "" if years else "연간 컨센서스 없음"}
    if not any(item["years"] for item in result.values()):
        raise DataError("FnGuide annual consensus unavailable for all stocks")
    return result
