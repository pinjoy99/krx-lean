"""Korea Investment & Securities (KIS) Open API for klean's KIS-PAPER broker: 모의투자 (paper)
accounts only; klean never connects to KIS's real-trading server. The parts the Python side
needs: checking credentials (`klean live kis-check`), the account balance and a day's prices.
Orders are sent by the C# plugin (klean/plugin/KisClient.cs), which shares this token cache.

Credentials come from the environment (klean loads ~/.config/krx-lean.env): KIS_PAPER_APP_KEY,
KIS_PAPER_APP_SECRET, KIS_PAPER_ACCOUNT ("12345678-01"), KIS_PAPER_BASE_URL (tests). They are never written to
klean's files or logs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from klean.workspace import KleanError

PAPER_URL = "https://openapivts.koreainvestment.com:29443"      # KIS 모의투자: the only server klean uses
OLD_NAMES = ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT", "KIS_MOCK")     # names used by earlier klean versions
KST = dt.timezone(dt.timedelta(hours=9))


def configured() -> bool:
    return bool(os.environ.get("KIS_PAPER_APP_KEY"))


class Kis:
    def __init__(self):
        old = [n for n in OLD_NAMES if os.environ.get(n)]
        if old:
            raise KleanError(f"{', '.join(old)}: klean now reads only KIS-PAPER keys. In ~/.config/krx-lean.env rename "
                             "KIS_APP_KEY to KIS_PAPER_APP_KEY, KIS_APP_SECRET to KIS_PAPER_APP_SECRET, KIS_ACCOUNT to "
                             "KIS_PAPER_ACCOUNT (your 모의투자 account's) and remove KIS_MOCK")
        missing = [n for n in ("KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET", "KIS_PAPER_ACCOUNT") if not os.environ.get(n)]
        if missing:
            raise KleanError(f"{', '.join(missing)} not set: put the KIS 모의투자 (paper) account's KIS_PAPER_APP_KEY=..., "
                             "KIS_PAPER_APP_SECRET=..., KIS_PAPER_ACCOUNT=12345678-01 in ~/.config/krx-lean.env")
        self.key, self.secret = os.environ["KIS_PAPER_APP_KEY"], os.environ["KIS_PAPER_APP_SECRET"]
        account = os.environ["KIS_PAPER_ACCOUNT"].replace(" ", "")
        self.cano, _, product = account.partition("-")
        if not product and len(account) == 10:
            self.cano, product = account[:8], account[8:]
        self.product = product or "01"
        self.base = (os.environ.get("KIS_PAPER_BASE_URL") or PAPER_URL).rstrip("/")
        self.gap = 0.55                              # KIS limits calls per second, lower for 모의투자
        self._last = 0.0
        self._token = ""

    def account_id(self) -> str:
        """Which account, without its number: masked, plus a short hash (server, account)."""
        digest = hashlib.sha256(f"{self.base}|{self.cano}-{self.product}".encode()).hexdigest()[:10]
        return f"{self.cano[:2]}******-{self.product} paper {digest}"

    # ------------------------------------------------------------ plumbing

    def token_path(self) -> Path:
        digest = hashlib.sha256((self.base + self.key).encode()).hexdigest()[:12]
        folder = Path.home() / ".klean"
        folder.mkdir(exist_ok=True)
        return folder / f"kis-token-paper-{digest}.json"

    def token(self) -> str:
        if self._token:
            return self._token
        path = self.token_path()
        if path.exists():
            cached = json.loads(path.read_text())
            expires = _parse_utc(cached["expires_utc"])
            if expires > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30):
                self._token = cached["token"]
                return self._token
        body = json.dumps({"grant_type": "client_credentials", "appkey": self.key, "appsecret": self.secret}).encode()
        data = self._http("POST", self.base + "/oauth2/tokenP", body, {"Content-Type": "application/json"})
        if "access_token" not in data:
            raise KleanError(f"KIS {data.get('error_code', '')}: token: {data.get('error_description', data)}")
        self._token = data["access_token"]
        hours = int(data.get("expires_in", 86400)) / 3600
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)
        path.write_text(json.dumps({"token": self._token, "expires_utc": expires.isoformat()}))
        path.chmod(0o600)
        return self._token

    def _http(self, method: str, url: str, body: bytes | None, headers: dict) -> dict:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read() or b"{}")
            except ValueError:
                raise KleanError(f"KIS: HTTP {e.code} from {url.split('?')[0]}") from None
        except OSError as e:
            raise KleanError(f"KIS: can't reach {self.base}: {e}") from None

    def call(self, path: str, tr_id: str, params: dict, cont: str = "") -> dict:
        for attempt in range(6):
            wait = self.gap - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            headers = {"Content-Type": "application/json", "authorization": f"Bearer {self.token()}",
                       "appkey": self.key, "appsecret": self.secret, "tr_id": tr_id, "tr_cont": cont, "custtype": "P"}
            query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
            data = self._http("GET", f"{self.base}{path}?{query}", None, headers)
            if data.get("rt_cd") == "0":
                return data
            code, msg = data.get("msg_cd", ""), str(data.get("msg1", data)).strip()
            if code == "EGW00201" and attempt < 5:
                time.sleep(attempt + 1)
                continue
            if code == "EGW00123" and attempt == 0:
                self._token = ""
                self.token_path().unlink(missing_ok=True)
                continue
            raise KleanError(f"KIS {code}: {msg}")
        raise KleanError("KIS: too many calls per second")

    # ------------------------------------------------------------ account and prices

    def balance(self) -> dict:
        """{"cash": D+2 deposit, "total": evaluation, "holdings": [{code, name, quantity, average_price, price}]}"""
        holdings, fk, nk, cont, summary = [], "", "", "", {}
        for _ in range(20):
            data = self.call("/uapi/domestic-stock/v1/trading/inquire-balance", "VTTC8434R", {
                "CANO": self.cano, "ACNT_PRDT_CD": self.product, "AFHR_FLPR_YN": "N", "OFL_YN": "",
                "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00", "CTX_AREA_FK100": fk, "CTX_AREA_NK100": nk}, cont)
            for h in data.get("output1", []):
                if float(h.get("hldg_qty") or 0):
                    holdings.append({"code": h.get("pdno", ""), "name": h.get("prdt_name", ""),
                                     "quantity": float(h["hldg_qty"]), "average_price": float(h.get("pchs_avg_pric") or 0),
                                     "price": float(h.get("prpr") or 0)})
            out2 = data.get("output2") or [{}]
            summary = out2[0] if isinstance(out2, list) else out2
            fk, nk = data.get("ctx_area_fk100", "").strip(), data.get("ctx_area_nk100", "").strip()
            if not nk or not data.get("output1"):
                break
            cont = "N"
        cash = float(summary.get("prvs_rcdl_excc_amt") or 0) or float(summary.get("dnca_tot_amt") or 0)
        return {"cash": cash, "total": float(summary.get("tot_evlu_amt") or 0), "holdings": holdings}

    def daily_bar(self, code: str, day: str) -> dict | None:
        """A day's raw prices (day: YYYY-MM-DD), or None if the stock didn't trade."""
        key = day.replace("-", "")
        data = self.call("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code, "FID_INPUT_DATE_1": key, "FID_INPUT_DATE_2": key,
            "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1"})
        for r in data.get("output2") or []:
            if r.get("stck_bsop_date") == key and float(r.get("stck_clpr") or 0):
                return {k: float(r.get(f) or 0) for k, f in (("open", "stck_oprc"), ("high", "stck_hgpr"),
                                                              ("low", "stck_lwpr"), ("close", "stck_clpr"),
                                                              ("volume", "acml_vol"))}
        return None


def _parse_utc(text: str) -> dt.datetime:
    """An ISO time from either side of the shared cache (.NET writes 7 fraction digits and "Z")."""
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.replace("Z", "+00:00"))
    t = dt.datetime.fromisoformat(text)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def now_kst() -> dt.datetime:
    """Korean time; KLEAN_KIS_NOW ("2026-10-02T08:35") fixes it, for tests."""
    fixed = os.environ.get("KLEAN_KIS_NOW")
    return dt.datetime.fromisoformat(fixed).replace(tzinfo=KST) if fixed else dt.datetime.now(KST)


def in_pre_open(t: dt.datetime) -> bool:
    """KRX's pre-open auction, when orders join the opening price (same window as the plugin)."""
    return dt.time(8, 30) <= t.time() < dt.time(8, 59, 30)
