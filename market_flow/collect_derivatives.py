"""KRX regular-session index derivatives; model Greeks are gross proxies only."""
from __future__ import annotations

import math
import re
from datetime import date, timedelta

from valuation.api import DataError

KRX_BASE = "https://data-dbg.krx.co.kr/svc/apis/"
PRODUCTS = {
    "KOSPI200": ("코스피 200", "코스피200 선물", "코스피200 옵션", "코스피200 위클리", 250000,
                 "idx/kospi_dd_trd"),
    "KOSDAQ150": ("코스닥 150", "코스닥150 선물", "코스닥150 옵션", "코스닥150 위클리", 10000,
                   "idx/kosdaq_dd_trd"),
}


def numeric(value, label):
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise DataError(f"Invalid {label}") from exc
    if not math.isfinite(result):
        raise DataError(f"Invalid {label}")
    return result


def krx_rows(market, endpoint, day):
    payload = market._request("GET", KRX_BASE + endpoint,
                              headers={"AUTH_KEY": market.krx_key},
                              params={"basDd": day.strftime("%Y%m%d")})
    rows = payload.get("OutBlock_1")
    if not isinstance(rows, list):
        raise DataError(f"KRX response invalid: {endpoint}")
    return [row for row in rows if row.get("BAS_DD") == day.strftime("%Y%m%d")]


def nth_weekday(year, month, weekday, ordinal):
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (ordinal - 1))


def parse_option(row):
    product = str(row.get("PROD_NM", ""))
    name = str(row.get("ISU_NM", ""))
    if "야간" in name:
        return None
    weekly = "위클리" in product
    pattern = r"(?<!\d)(\d{4}W[1-5]|20\d{4})\s+([\d,]+(?:\.\d+)?)"
    match = re.search(pattern, name)
    if not match:
        raise DataError(f"Unrecognized KRX option contract: {name[:60]}")
    code, strike_text = match.groups()
    if weekly:
        year, month, ordinal = 2000 + int(code[:2]), int(code[2:4]), int(code[-1])
        weekday = 0 if "(월)" in product else 3 if "(목)" in product else None
        if weekday is None:
            raise DataError(f"Unknown weekly product: {product}")
    else:
        year, month, ordinal, weekday = int(code[:4]), int(code[4:6]), 2, 3
    expiry = nth_weekday(year, month, weekday, ordinal)
    kind = {"CALL": "C", "PUT": "P"}.get(row.get("RGHT_TP_NM"))
    if kind is None:
        raise DataError("Unknown option right type")
    return {"series": "weekly" if weekly else "monthly", "kind": kind,
            "strike": numeric(strike_text, "strike"), "expiry": expiry,
            "oi": numeric(row.get("ACC_OPNINT_QTY"), "option OI"),
            "close": row.get("TDD_CLSPRC"), "iv": row.get("IMP_VOLT"),
            "contract": row.get("ISU_CD")}


def _normal_cdf(value):
    return 0.5 * (1 + math.erf(value / math.sqrt(2)))


def model_greeks(spot, strike, iv_pct, days_to_expiry, kind):
    """Zero-carry Black-Scholes approximation, with annualized IV in percent."""
    sigma = iv_pct / 100
    years = days_to_expiry / 365
    if not (spot > 0 and strike > 0 and sigma > 0 and years > 0):
        raise DataError("Cannot calculate option Greeks")
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * years) / (sigma * math.sqrt(years))
    call_delta = _normal_cdf(d1)
    delta = call_delta if kind == "C" else call_delta - 1
    gamma = math.exp(-0.5 * d1 * d1) / (spot * sigma * math.sqrt(2 * math.pi * years))
    return delta, gamma


def build_derivatives(day, index_rows, futures_rows, options_rows):
    result = {}
    for key, (index_name, futures_name, monthly_name, weekly_prefix,
              multiplier, endpoint) in PRODUCTS.items():
        index_matches = [r for r in index_rows[endpoint] if r.get("IDX_NM") == index_name]
        if len(index_matches) != 1:
            raise DataError(f"Missing {key} index close")
        spot = numeric(index_matches[0].get("CLSPRC_IDX"), f"{key} index close")
        futures = [r for r in futures_rows if r.get("PROD_NM") == futures_name
                   and r.get("MKT_NM") == "정규" and r.get("TDD_CLSPRC")]
        futures.sort(key=lambda r: re.search(r"20\d{4}", str(r.get("ISU_NM", ""))).group(0)
                     if re.search(r"20\d{4}", str(r.get("ISU_NM", ""))) else "999999")
        if not futures:
            raise DataError(f"Missing {key} regular futures close")
        future = futures[0]
        future_close = numeric(future.get("TDD_CLSPRC"), "future close")
        previous_close = future_close - numeric(future.get("CMPPREVDD_PRC"), "future change")
        selected = []
        for row in options_rows:
            product = str(row.get("PROD_NM", ""))
            if product != monthly_name and not product.startswith(weekly_prefix):
                continue
            parsed = parse_option(row)
            if parsed and parsed["expiry"] > day and parsed["oi"] > 0:
                selected.append(parsed)
        chain = []
        for series in ("monthly", "weekly"):
            choices = [o for o in selected if o["series"] == series]
            if not choices:
                raise DataError(f"Missing {key} {series} options")
            expiry = min(o["expiry"] for o in choices)
            for option in choices:
                if option["expiry"] != expiry or not option["close"]:
                    continue
                try:
                    close = numeric(option["close"], "option close")
                    iv = numeric(option["iv"], "option IV")
                except DataError:
                    continue
                if close <= 0 or iv <= 0:
                    continue
                delta, gamma = model_greeks(spot, option["strike"], iv,
                                            (expiry - day).days, option["kind"])
                chain.append({"series": series, "kind": option["kind"],
                              "strike": option["strike"], "expiry": expiry.isoformat(),
                              "oi": option["oi"], "delta": delta, "gamma": gamma,
                              "option_multiplier_krw": multiplier,
                              "close": close, "iv_pct": iv, "contract": option["contract"]})
            if not any(o["series"] == series for o in chain):
                raise DataError(f"No priced {key} {series} options with valid IV")
        result[key] = {"underlying_close": spot, "future_close": future_close,
                       "prev_future_close": previous_close,
                       "future_oi": numeric(future.get("ACC_OPNINT_QTY"), "future OI"),
                       "future_contract": future.get("ISU_CD"),
                       "future_multiplier_krw": multiplier,
                       "foreign_future_net_contracts": None,
                       "greeks_method": "zero_carry_black_scholes_proxy",
                       "options": chain}
    return result


def collect_derivatives(market, day):
    index_rows = {endpoint: krx_rows(market, endpoint, day) for endpoint in
                  {item[-1] for item in PRODUCTS.values()}}
    futures_rows = krx_rows(market, "drv/fut_bydd_trd", day)
    options_rows = krx_rows(market, "drv/opt_bydd_trd", day)
    return build_derivatives(day, index_rows, futures_rows, options_rows)

