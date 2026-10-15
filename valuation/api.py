"""Date and venue checked KIS/KRX market data clients."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
KIS = "https://openapi.koreainvestment.com:9443"
KRX = "https://data-dbg.krx.co.kr/svc/apis/sto"


class DataError(RuntimeError):
    pass


@dataclass(frozen=True)
class Quote:
    price: int | None
    shares: int | None
    source: str
    basis: str
    checked_at: str
    reason: str = ""


def positive_int(value):
    try:
        number = int(str(value).replace(",", ""))
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def choose_minute(rows: list[dict], day: date):
    """Use the 11:30 KRX minute close, else the latest regular minute before it."""
    chosen = None
    for row in rows:
        stamp = str(row.get("stck_cntg_hour", ""))
        if str(row.get("stck_bsop_date", "")) != day.strftime("%Y%m%d"):
            continue
        if not (len(stamp) == 6 and stamp.isdigit() and "090000" <= stamp <= "113000"):
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
        self.app_key = os.environ.get("KIS_APP_KEY", "")
        self.app_secret = os.environ.get("KIS_APP_SECRET", "")
        self.krx_key = os.environ.get("KRX_API_KEY", "")
        if not all((self.app_key, self.app_secret, self.krx_key)):
            raise DataError("KIS_APP_KEY, KIS_APP_SECRET, KRX_API_KEY 설정 필요")

    def _request(self, method, url, *, headers=None, params=None, json=None):
        for attempt in range(3):
            try:
                response = self.session.request(method, url, headers=headers, params=params,
                                                json=json, timeout=(5, 15))
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt == 2:
                    # Never print the URL: the Telegram token is not used here, but keep logs clean.
                    raise DataError(f"market API request failed ({type(exc).__name__})") from None
                self.sleep(2 ** attempt)
        raise DataError("market API retries exhausted")

    def _access_token(self):
        if self.token is None:
            payload = self._request("POST", KIS + "/oauth2/tokenP", json={
                "grant_type": "client_credentials", "appkey": self.app_key,
                "appsecret": self.app_secret})
            self.token = payload.get("access_token")
            if not self.token:
                raise DataError("KIS access token unavailable")
        return self.token

    def kis(self, path, tr_id, params):
        payload = self._request("GET", KIS + path, headers={
            "authorization": "Bearer " + self._access_token(),
            "appkey": self.app_key, "appsecret": self.app_secret,
            "tr_id": tr_id, "custtype": "P"}, params=params)
        if str(payload.get("rt_cd")) != "0":
            raise DataError(f"KIS rejected {tr_id}: {payload.get('msg_cd', 'unknown')}")
        return payload

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
            raise DataError("KRX confirmed close dataset empty or not yet published")
        return result

    def minute(self, code, day):
        payload = self.kis("/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice",
                           "FHKST03010230", {"FID_COND_MRKT_DIV_CODE": "J",
                           "FID_INPUT_ISCD": code, "FID_INPUT_HOUR_1": "113000",
                           "FID_INPUT_DATE_1": day.strftime("%Y%m%d"),
                           "FID_PW_DATA_INCU_YN": "N", "FID_FAKE_TICK_INCU_YN": ""})
        return choose_minute(payload.get("output2", []), day)

    def current_shares(self, code):
        payload = self.kis("/uapi/domestic-stock/v1/quotations/inquire-price",
                           "FHKST01010100", {"FID_COND_MRKT_DIV_CODE": "J",
                                                "FID_INPUT_ISCD": code})
        return positive_int(payload.get("output", {}).get("lstn_stcn"))

    def collect(self, codes, day, slot):
        if slot == "close":
            for attempt in range(3):
                daily = self.closes(day)
                if all(c in daily and all(daily[c][0:2]) for c in codes) or attempt == 2:
                    break
                self.sleep(10 * (attempt + 1))
            checked = datetime.now(KST).isoformat(timespec="seconds")
            return {code: Quote(*(daily[code][0:2]),
                         source="KRX " + daily[code][2], basis="15:30 KST 정규장 종가",
                         checked_at=checked) if code in daily and all(daily[code][0:2]) else
                    Quote(None, None, "KRX", "", checked, "당일 확정 종가/상장주식 수 미확인")
                    for code in codes}
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
                    minute = self.minute(code, day)
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
                    (minute_error or "당일 11:30 이전 정규장 분봉 없음") if not minute else "상장주식 수 미확인")
            self.sleep(0.12)
        return quotes
