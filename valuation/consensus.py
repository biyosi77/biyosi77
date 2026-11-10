"""Read the annual table displayed by FnGuide's public Company Guide."""
import json
import math
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

from .api import KST, DataError

BASE = "https://wcomp.fnguide.com/CompanyInfo/"
ANNUAL_PAGE = BASE + "Consensus"
ROE_ENDPOINT = BASE + "getSnpFinancial"
HEADERS = {"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"}


def _number(value):
    try:
        number = float(str(value).replace(",", ""))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _rate(value):
    number = _number(value)
    if number is not None:
        return number / 100
    return value if value in ("흑자전환", "적자전환", "적자지속", "손익분기") else None


def _periods(dataset):
    periods = {}
    for column in dataset["header"]:
        match = re.fullmatch(r"(202[5-8])/(0[1-9]|1[0-2])", column.get("YYMM") or "")
        if not match:
            continue
        year, month = int(match[1]), match[2]
        status = (column.get("EP_CHK") or "").strip()
        if status not in (("", "A") if year == 2025 else ("E",)):
            continue
        if year in periods:
            raise ValueError("duplicate annual period")
        periods[year] = (month, column["CD"])
    return periods


def parse_annual_page(html, code):
    identity = re.search(
        r"""consensus\.init\(\s*\{\s*cmp_cd:\s*['"](\d{6})['"]\s*,\s*consol_typ:\s*['"]([CP])['"]""",
        html,
    )
    if not identity or identity[1] != code:
        raise ValueError("FnGuide page identity or accounting basis not confirmed")
    start = re.search(r"\bperforTrend\s*:\s*(?=\{)", html[identity.end():])
    if not start:
        raise ValueError("FnGuide annual table not found")
    dataset, _ = json.JSONDecoder().raw_decode(html[identity.end() + start.end():])
    basis = "연결" if identity[2] == "C" else "별도"
    amounts, rates = {}, {}
    for row in dataset["data"]:
        account = row.get("AC_CODE")
        if account not in ("121450", "122700", "122710"):
            continue
        if row["LVL"] == 1:
            target = amounts
        elif row["LVL"] == 2 and row["NAME"].strip() == "전년동기대비":
            target = rates
        else:
            continue
        if account in target:
            raise ValueError("ambiguous FnGuide annual account")
        target[account] = row
    years = {}
    for year, (month, key) in _periods(dataset).items():
        net_account = "122710" if basis == "연결" else "122700"
        years[year] = {
            "period": f"{year}.{month}({'A' if year == 2025 else 'E'})",
            "month": month, "basis": basis,
            "net": _number(amounts.get(net_account, {}).get(key)),
            "op": _number(amounts.get("121450", {}).get(key)),
            "net_total": _number(amounts.get("122700", {}).get(key)),
            "net_total_yoy": _rate(rates.get("122700", {}).get(key)),
            "op_yoy": _rate(rates.get("121450", {}).get(key)),
        }
    return years, identity[2]


def _get(session, url):
    response = session.get(url, headers=HEADERS, timeout=15)
    if response.status_code in (401, 403, 429):
        raise DataError(f"FnGuide access restricted: HTTP {response.status_code}")
    response.raise_for_status()
    return response


def fetch_consensus(codes, day, session=None):
    """Fetch a new FnGuide snapshot. The report trade date is not a historical cutoff."""
    session = session or requests.Session()
    result = {}
    for index, code in enumerate(codes):
        if index:
            time.sleep(0.6)
        source = ANNUAL_PAGE + "?" + urlencode({"cmp_cd": code})
        item = {"years": {}, "source": source, "checked": "", "reason": ""}
        result[code] = item
        try:
            page = _get(session, source)
            item["years"], basis = parse_annual_page(page.text, code)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            item["reason"] = f"FnGuide 연간 표 확인 실패 ({type(exc).__name__})"
        finally:
            item["checked"] = datetime.now(KST).isoformat(timespec="seconds")

        years = item["years"]
        if not any(v.get(metric) is not None for y, v in years.items() if y > 2025
                   for metric in ("net", "op")):
            item["reason"] = item["reason"] or "연간 이익 컨센서스 없음"
            continue
        time.sleep(0.6)
        roe_source = ROE_ENDPOINT + "?" + urlencode({
            "cmp_cd": code, "consol_typ": basis, "freq_typ": "Y",
        })
        try:
            dataset = _get(session, roe_source).json()["dataset"]
            row = next(row for row in dataset["data"] if row["NAME"].strip() == "ROE")
            header = {column["CD"]: column for column in dataset["header"]}
            for year, (month, key) in _periods(dataset).items():
                if (year in years and years[year]["month"] == month
                        and years[year]["basis"] == header[key].get("CONSOL_TYPE")):
                    roe = _number(row.get(key))
                    years[year]["roe"] = roe / 100 if roe is not None else None
            item["roe_source"] = roe_source
        except (requests.RequestException, ValueError, KeyError, TypeError, StopIteration) as exc:
            item["reason"] = f"FnGuide 연간 ROE 확인 실패 ({type(exc).__name__})"
    if not any(v.get(metric) is not None for item in result.values()
               for y, v in item["years"].items() if y > 2025 for metric in ("net", "op")):
        raise DataError("FnGuide annual consensus unavailable for all stocks")
    return result
