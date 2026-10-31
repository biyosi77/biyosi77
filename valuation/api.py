"""Date and venue checked KIS/KRX market data clients."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
KIS = "https://openapi.koreainvestment.com:9443"
KRX = "https://data-dbg.krx.co.kr/svc/apis/sto"


class DataError(RuntimeError):
    pass


class KRXCloseEmpty(DataError):
    """Both KRX daily market datasets contain no rows for the requested date."""


@dataclass(frozen=True)
class Quote:
    price: int | None
    shares: int | None
    source: str
    basis: str
    checked_at: str
    reason: str = ""
    trade_date: str = ""


def positive_int(value):
    try:
        number = int(str(value).replace(",", ""))
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def credential(name):
    """Ignore accidental whitespace or wrapping quotes in a GitHub Secret."""
    value = os.environ.get(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value


def choose_minute(rows: list[dict], day: date, cutoff: str = "113000"):
    """Use the requested KRX minute close, else the latest regular minute before it."""
    chosen = None
    for row in rows:
        stamp = str(row.get("stck_cntg_hour", ""))
        if str(row.get("stck_bsop_date", "")) != day.strftime("%Y%m%d"):
            continue
        if not (len(stamp) == 6 and stamp.isdigit() and "090000" <= stamp <= cutoff):
            continue
        price = positive_int(row.get("stck_prpr"))
        if price is not None and (chosen is None or stamp > chosen[0]):
            chosen = (stamp, price)
    return chosen


class MarketData:
    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.sleep = sleep
        self.token = None
        self.app_key = credential("KIS_APP_KEY")
        self.app_secret = credential("KIS_APP_SECRET")
        self.krx_key = credential("KRX_API_KEY")
        if not self.krx_key:
            raise DataError("KRX_API_KEY 설정 필요")

    def _request(self, method, url, *, headers=None, params=None, json=None):
        service = ("KIS token" if url.endswith("/oauth2/tokenP") else
                   "KIS market" if url.startswith(KIS) else "KRX market")
        for attempt in range(3):
            try:
                response = self.session.request(method, url, headers=headers, params=params,
                                                json=json, timeout=(5, 15))
                if response.status_code == 429:
                    raise DataError(f"{service} rate limited; defer to next scheduled attempt")
                if response.status_code in (500, 502, 503, 504) and attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt == 2 or (status is not None and status not in (429, 500, 502, 503, 504)):
                    # Service and HTTP code identify a configuration failure without
                    # exposing the request URL, authorization header, or response body.
                    detail = f"HTTP {status}" if status else type(exc).__name__
                    response = getattr(exc, "response", None)
                    code = ""
                    if response is not None and "json" in response.headers.get("Content-Type", ""):
                        try:
                            body = response.json()
                            code = str(body.get("error_code") or body.get("msg_cd") or "")
                            if re.fullmatch(r"[A-Za-z0-9_]{1,24}", code):
                                detail += f", code {code}"
                        except (ValueError, AttributeError):
                            pass
                    if service == "KIS token" and code == "EGW00133" and attempt == 0:
                        # KIS limits token issuance to once per minute. A fresh
                        # Actions runner cannot reuse the preceding run's token.
                        self.sleep(65)
                        continue
                    raise DataError(f"{service} request failed ({detail})") from None
                self.sleep(2 ** attempt)
        raise DataError("market API retries exhausted")

    def _access_token(self):
        if self.token is None:
            if not self.app_key or not self.app_secret:
                raise DataError("KIS_APP_KEY, KIS_APP_SECRET 설정 필요")
            payload = self._request("POST", KIS + "/oauth2/tokenP", headers={
                "Accept": "text/plain", "charset": "UTF-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36"}, json={
                "grant_type": "client_credentials", "appkey": self.app_key,
                "appsecret": self.app_secret})
            self.token = payload.get("access_token")
            if not self.token:
                raise DataError("KIS access token unavailable")
        return self.token

    def kis(self, path, tr_id, params):
        for attempt in range(3):
            payload = self._request("GET", KIS + path, headers={
                "authorization": "Bearer " + self._access_token(),
                "appkey": self.app_key, "appsecret": self.app_secret,
                "tr_id": tr_id, "custtype": "P"}, params=params)
            if str(payload.get("rt_cd")) == "0":
                return payload
            code = str(payload.get("msg_cd", "unknown"))
            if code == "OPSQ1002" and attempt < 2:
                self.sleep(2 ** attempt)
                continue
            raise DataError(f"KIS rejected {tr_id}: {code}")
        raise DataError("KIS session retries exhausted")

    def krx(self, endpoint, day):
        payload = self._request("GET", KRX + "/" + endpoint,
                                headers={"AUTH_KEY": self.krx_key},
                                params={"basDd": day.strftime("%Y%m%d")})
        rows = payload.get("OutBlock_1")
        if not isinstance(rows, list):
            raise DataError(f"KRX invalid response: {endpoint}")
        return rows

    def is_open(self, day):
        payload = self.kis("/uapi/domestic-stock/v1/quotations/chk-holiday", "CTCA0903R",
                           {"BASS_DT": day.strftime("%Y%m%d"),
                            "CTX_AREA_FK": "", "CTX_AREA_NK": ""})
        rows = payload.get("output", [])
        if isinstance(rows, dict):
            rows = [rows]
        matching = [r for r in rows if str(r.get("bass_dt")) == day.strftime("%Y%m%d")]
        if len(matching) != 1 or matching[0].get("opnd_yn") not in ("Y", "N"):
            raise DataError("KIS trading calendar did not confirm the requested date")
        return matching[0]["opnd_yn"] == "Y"

    @staticmethod
    def _code(row):
        code = str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "")
        return code if len(code) == 6 and code.isdigit() else None

    def shares(self, day):
        result = {}
        for endpoint in ("stk_isu_base_info", "ksq_isu_base_info"):
            for row in self.krx(endpoint, day):
                code = self._code(row)
                if code:
                    if code in result:
                        raise DataError("KRX duplicate listed share code")
                    result[code] = (positive_int(row.get("LIST_SHRS")), endpoint)
        if not result:
            raise DataError("KRX listed share dataset empty")
        return result

    def closes(self, day):
        result = {}
        for endpoint in ("stk_bydd_trd", "ksq_bydd_trd"):
            for row in self.krx(endpoint, day):
                code = self._code(row)
                if not code:
                    continue
                if code in result:
                    raise DataError("KRX duplicate close code")
                if str(row.get("BAS_DD", "")).replace("-", "") != day.strftime("%Y%m%d"):
                    continue
                result[code] = (positive_int(row.get("TDD_CLSPRC")),
                                positive_int(row.get("LIST_SHRS")), endpoint)
        if not result:
            raise KRXCloseEmpty("KRX confirmed close dataset empty or not yet published")
        return result

    def minute(self, code, day, cutoff="113000"):
        if cutoff in ("150000", "153000") and day == datetime.now(KST).date():
            # KIS's dedicated same-day endpoint is the live intraday source.
            payload = self.kis("/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                               "FHKST03010200", {"FID_COND_MRKT_DIV_CODE": "J",
                               "FID_INPUT_ISCD": code, "FID_INPUT_HOUR_1": cutoff,
                               "FID_PW_DATA_INCU_YN": "Y", "FID_ETC_CLS_CODE": ""})
        else:
            payload = self.kis("/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice",
                               "FHKST03010230", {"FID_COND_MRKT_DIV_CODE": "J",
                               "FID_INPUT_ISCD": code, "FID_INPUT_HOUR_1": cutoff,
                               "FID_INPUT_DATE_1": day.strftime("%Y%m%d"),
                               "FID_PW_DATA_INCU_YN": "N", "FID_FAKE_TICK_INCU_YN": ""})
        return choose_minute(payload.get("output2", []), day, cutoff)

    def current_shares(self, code):
        payload = self.kis("/uapi/domestic-stock/v1/quotations/inquire-price",
                           "FHKST01010100", {"FID_COND_MRKT_DIV_CODE": "J",
                                                "FID_INPUT_ISCD": code})
        return positive_int(payload.get("output", {}).get("lstn_stcn"))

    def kis_regular_close_snapshot(self, code, day):
        """Exact 15:30 KRX(J) bar plus listed shares; never use daily last price."""
        bar = self.minute(code, day, "153000")
        if bar is None or bar[0] != "153000":
            reason = (f"15:30 KRX 정규장 분봉 미확인 (마지막 {bar[0][:2]}:{bar[0][2:4]})"
                      if bar else "15:30 KRX 정규장 분봉 미확인")
            return Quote(None, None, "KIS KRX(J) 15:30 분봉; KIS 상장주식수", "",
                         datetime.now(KST).isoformat(timespec="seconds"), reason,
                         day.isoformat())
        shares = self.current_shares(code)
        return Quote(bar[1], shares, "KIS KRX(J) 15:30 분봉; KIS 상장주식수",
                     "15:30 KST 정규장 종가", datetime.now(KST).isoformat(timespec="seconds"),
                     "" if shares else "상장주식 수 미확인", day.isoformat())

    def collect_same_day_close(self, codes, day, *, now=None):
        """Poll one sentinel until published, then collect each stock once."""
        now = now or (lambda: datetime.now(KST))
        ordered = list(codes)
        if not ordered:
            raise DataError("empty stock universe")
        deadline = clock_time(16, 45)
        first_code = ordered[0]
        for attempt in range(13):
            first = self.kis_regular_close_snapshot(first_code, day)
            if first.price and first.shares:
                break
            if now().time() >= deadline or attempt == 12:
                raise DataError("KIS same-day KRX close not confirmed by 16:45 KST")
            self.sleep(300)
        quotes = {first_code: first}
        for code in ordered[1:]:
            self.sleep(0.2)  # Well below KIS's real-account requests/second limit.
            try:
                quotes[code] = self.kis_regular_close_snapshot(code, day)
            except DataError as exc:
                if any(term in str(exc) for term in ("rate limited", "EGW00201", "HTTP 401", "HTTP 403", "token")):
                    raise
                quotes[code] = Quote(None, None, "KIS KRX(J) 15:30 분봉; KIS 상장주식수",
                                     "", datetime.now(KST).isoformat(timespec="seconds"),
                                     "KIS 종가/주식 수 조회 실패", day.isoformat())
        missing = [code for code, quote in quotes.items()
                   if quote.price is None or quote.shares is None]
        if missing and now().time() < deadline:
            self.sleep(20)
            for code in missing:
                self.sleep(0.2)
                try:
                    quotes[code] = self.kis_regular_close_snapshot(code, day)
                except DataError as exc:
                    if any(term in str(exc) for term in ("rate limited", "EGW00201", "HTTP 401", "HTTP 403", "token")):
                        raise
        if not any(q.price is not None and q.shares is not None for q in quotes.values()):
            raise DataError("KIS same-day KRX close collection failed for all stocks")
        return quotes

    def collect_verified_close(self, codes, day):
        """Two market-wide daily requests; never substitute minute/current prices."""
        daily = self.closes(day)  # BAS_DD must match day for every accepted row.
        missing = [code for code in codes
                   if code not in daily or not all(daily[code][:2])]
        if missing:
            raise DataError(f"confirmed KRX close/share data incomplete ({len(missing)}/{len(codes)})")
        checked = datetime.now(KST).isoformat(timespec="seconds")
        return {code: Quote(daily[code][0], daily[code][1],
                            "KRX " + daily[code][2], "15:30 KST 정규장 종가",
                            checked, trade_date=day.isoformat()) for code in codes}

    def collect(self, codes, day, slot):
        if slot not in ("1130", "1500"):
            raise DataError("invalid price slot")
        shares = {}
        for attempt in range(3):
            try:
                shares = self.shares(day)
            except DataError:
                shares = {}
            if all(c in shares and shares[c][0] for c in codes) or attempt == 2:
                break
            self.sleep(10 * (attempt + 1))
        quotes = {}
        for code in codes:
            minute = None
            minute_error = ""
            for attempt in range(3):
                try:
                    minute = self.minute(code, day, "150000" if slot == "1500" else "113000")
                except DataError as exc:
                    minute = None
                    minute_error = str(exc)
                if minute or attempt == 2:
                    break
                self.sleep(3 * (attempt + 1))
            share, share_endpoint = shares.get(code, (None, ""))
            if not share and day == datetime.now(KST).date():
                try:
                    share = self.current_shares(code)
                    share_endpoint = "KIS KRX 현재가 상장주식수(lstn_stcn)"
                except DataError:
                    share = None
            checked = datetime.now(KST).isoformat(timespec="seconds")
            if minute and share:
                quotes[code] = Quote(minute[1], share,
                    "KIS KRX 분봉; " + (share_endpoint if share_endpoint.startswith("KIS") else "KRX " + share_endpoint),
                    f"{minute[0][:2]}:{minute[0][2:4]} KST", checked)
            else:
                quotes[code] = Quote(None, None, "KIS KRX; KRX", "", checked,
                    (minute_error or f"당일 {'15:00' if slot == '1500' else '11:30'} 이전 정규장 분봉 없음") if not minute else "상장주식 수 미확인")
            self.sleep(0.12)
        return quotes
