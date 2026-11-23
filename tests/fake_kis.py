"""A simulated Korea Investment (KIS) 모의투자 Open API server for tests of klean's KIS-PAPER
broker: the endpoints klean uses, with the same paths, tr_ids, headers and field names, a paper
account in memory, and two test-only endpoints. No KIS account or key is involved.

    python tests/fake_kis.py --port 18080 [--cash 100000000] [--data WORKSPACE/data]

Test endpoints: POST /fake/open {"date": "2026-10-02"} fills every waiting order at that day's
open; GET /fake/state shows the account, the orders and every call's tr_id.
Prices: a day in the workspace's daily files is served as it is; a later day is made up from the
last close (open +1%, close +2%), like a day KRX hasn't published yet.
"""

from __future__ import annotations

import argparse
import json
import socketserver
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class FakeKis:
    def __init__(self, cash: float = 100_000_000, data: Path | None = None):
        self.cash, self.data = cash, data
        self.holdings: dict[str, dict] = {}
        self.orders: list[dict] = []
        self.calls: list[dict] = []
        self.tokens = 0
        self.lock = threading.Lock()

    # ------------------------------------------------------------ prices

    def _rows(self, code: str) -> list[list[str]]:
        if not self.data:
            return []
        path = self.data / "equity" / "krx" / "daily" / f"{code.lower()}.zip"
        if not path.exists():
            return []
        with zipfile.ZipFile(path) as z:
            return [line.split(",") for line in z.read(z.namelist()[0]).decode().splitlines() if line]

    def bar(self, code: str, day: str) -> dict | None:
        rows = self._rows(code)
        for r in rows:
            if r[0][:8] == day:
                o, h, lo, c = (float(x) / 10000 for x in r[1:5])
                return {"open": o, "high": h, "low": lo, "close": c, "volume": float(r[5])}
        earlier = [r for r in rows if r[0][:8] < day]
        if not earlier:
            return None
        last = float(earlier[-1][4]) / 10000
        return {"open": round(last * 1.01), "high": round(last * 1.03), "low": round(last * 0.99),
                "close": round(last * 1.02), "volume": 1000.0}

    # ------------------------------------------------------------ account

    def balance(self) -> dict:
        held = [{"pdno": c, "prdt_name": f"STOCK {c}", "hldg_qty": str(int(h["quantity"])),
                 "pchs_avg_pric": f"{h['average_price']:.4f}", "prpr": str(int(h["price"]))}
                for c, h in sorted(self.holdings.items()) if h["quantity"]]
        value = sum(h["quantity"] * h["price"] for h in self.holdings.values())
        return {"rt_cd": "0", "msg_cd": "KIOK0000", "msg1": "OK", "ctx_area_fk100": "", "ctx_area_nk100": "",
                "output1": held, "output2": [{"dnca_tot_amt": str(int(self.cash)), "prvs_rcdl_excc_amt": str(int(self.cash)),
                                              "tot_evlu_amt": str(int(self.cash + value))}]}

    def open_market(self, day: str) -> list[dict]:
        """Fill every waiting order at ``day``'s open (limit orders when the open is good enough)."""
        filled = []
        for o in self.orders:
            if o["status"] != "waiting":
                continue
            bar = self.bar(o["code"], day.replace("-", ""))
            if not bar:
                continue
            price = bar["open"]
            if o["limit"] and ((o["buy"] and price > o["limit"]) or (not o["buy"] and price < o["limit"])):
                o["status"] = "expired"
                continue
            qty = o["quantity"]
            h = self.holdings.setdefault(o["code"], {"quantity": 0, "average_price": 0.0, "price": price})
            if o["buy"]:
                h["average_price"] = (h["quantity"] * h["average_price"] + qty * price) / (h["quantity"] + qty)
                h["quantity"] += qty
                self.cash -= qty * price
            else:
                qty = min(qty, h["quantity"])
                h["quantity"] -= qty
                self.cash += qty * price
            h["price"] = bar["close"]
            o.update(status="filled", filled=qty, fill_price=price, fill_date=day.replace("-", ""))
            filled.append(o)
        return filled


def make_handler(kis: FakeKis):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            ok = self.headers.get("authorization", "").startswith("Bearer fake-token-") and \
                self.headers.get("appkey") and self.headers.get("appsecret") and self.headers.get("custtype") == "P"
            if not ok:
                self._send({"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}, 500)
            return bool(ok)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
            if url.path == "/fake/state":
                with kis.lock:
                    return self._send({"cash": kis.cash, "holdings": kis.holdings, "orders": kis.orders,
                                       "calls": kis.calls, "tokens": kis.tokens})
            if not self._authorized():
                return
            tr = self.headers.get("tr_id", "")
            with kis.lock:
                kis.calls.append({"path": url.path, "tr_id": tr, "params": q})
                if url.path == "/uapi/domestic-stock/v1/trading/inquire-balance":
                    return self._send(kis.balance())
                if url.path == "/uapi/domestic-stock/v1/trading/inquire-daily-ccld":
                    rows = [{"ord_dt": o["date"], "odno": o["odno"], "pdno": o["code"],
                             "sll_buy_dvsn_cd": "02" if o["buy"] else "01", "ord_qty": str(o["quantity"]),
                             "tot_ccld_qty": str(o.get("filled", 0)), "avg_prvs": str(o.get("fill_price", 0)),
                             "rmn_qty": str(o["quantity"] - o.get("filled", 0) if o["status"] == "waiting" else 0),
                             "cncl_yn": "Y" if o["status"] == "canceled" else "N", "rjct_qty": "0"}
                            for o in kis.orders]                 # (the real API filters by date: all here)
                    return self._send({"rt_cd": "0", "msg_cd": "KIOK0000", "msg1": "OK", "ctx_area_fk100": "",
                                       "ctx_area_nk100": "", "output1": rows, "output2": {}})
                if url.path == "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice":
                    bar = kis.bar(q["FID_INPUT_ISCD"], q["FID_INPUT_DATE_1"])
                    rows = [{"stck_bsop_date": q["FID_INPUT_DATE_1"], "stck_oprc": str(bar["open"]), "stck_hgpr": str(bar["high"]),
                             "stck_lwpr": str(bar["low"]), "stck_clpr": str(bar["close"]), "acml_vol": str(bar["volume"])}] if bar else []
                    return self._send({"rt_cd": "0", "msg_cd": "MCA00000", "msg1": "OK", "output1": {}, "output2": rows})
            self._send({"rt_cd": "1", "msg_cd": "NOTFOUND", "msg1": url.path}, 404)

        def do_POST(self):  # noqa: N802
            url = urlparse(self.path)
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if url.path == "/oauth2/tokenP":
                if body.get("grant_type") != "client_credentials" or not body.get("appkey"):
                    return self._send({"error_code": "EGW00002", "error_description": "bad request"}, 403)
                with kis.lock:
                    kis.tokens += 1
                    return self._send({"access_token": f"fake-token-{kis.tokens}", "token_type": "Bearer", "expires_in": 86400})
            if url.path == "/fake/open":
                with kis.lock:
                    return self._send({"filled": kis.open_market(body["date"])})
            if not self._authorized():
                return
            tr = self.headers.get("tr_id", "")
            with kis.lock:
                kis.calls.append({"path": url.path, "tr_id": tr, "body": body})
                if url.path == "/uapi/domestic-stock/v1/trading/order-cash":
                    if tr not in ("VTTC0012U", "VTTC0011U"):
                        return self._send({"rt_cd": "1", "msg_cd": "OPSQ0002", "msg1": f"없는 서비스 코드 입니다 ({tr})"})
                    missing = [k for k in ("CANO", "ACNT_PRDT_CD", "PDNO", "ORD_DVSN", "ORD_QTY", "ORD_UNPR") if k not in body]
                    if missing or body["ORD_DVSN"] not in ("00", "01"):
                        return self._send({"rt_cd": "1", "msg_cd": "APBK0000", "msg1": f"bad order {missing or body['ORD_DVSN']}"})
                    odno = f"{len(kis.orders) + 1:010d}"
                    kis.orders.append({"odno": odno, "code": body["PDNO"], "buy": tr == "VTTC0012U", "quantity": int(body["ORD_QTY"]),
                                       "limit": float(body["ORD_UNPR"]) if body["ORD_DVSN"] == "00" else None,
                                       "status": "waiting", "date": body.get("_date", ""), "tr_id": tr, "body": body})
                    return self._send({"rt_cd": "0", "msg_cd": "APBK0013", "msg1": "주문 전송 완료 되었습니다.",
                                       "output": {"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": odno, "ORD_TMD": "083500"}})
                if url.path == "/uapi/domestic-stock/v1/trading/order-rvsecncl":
                    for o in kis.orders:
                        if o["odno"] == body.get("ORGN_ODNO") and o["status"] == "waiting":
                            o["status"] = "canceled"
                            return self._send({"rt_cd": "0", "msg_cd": "APBK0013", "msg1": "OK", "output": {"ODNO": o["odno"]}})
                    return self._send({"rt_cd": "1", "msg_cd": "APBK0918", "msg1": "정정/취소할 수량이 없습니다."})
            self._send({"rt_cd": "1", "msg_cd": "NOTFOUND", "msg1": url.path}, 404)

    return Handler


class Server(ThreadingHTTPServer):
    """No reverse DNS lookup of 127.0.0.1 at start (it can hang on macOS; see klean.gui.LocalServer)."""
    daemon_threads = True

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(port: int = 0, cash: float = 100_000_000, data: Path | None = None) -> tuple[ThreadingHTTPServer, FakeKis]:
    kis = FakeKis(cash, data)
    server = Server(("127.0.0.1", port), make_handler(kis))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, kis


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--cash", type=float, default=100_000_000)
    ap.add_argument("--data", type=Path)
    a = ap.parse_args()
    server, _ = serve(a.port, a.cash, a.data)
    print(f"fake KIS on http://127.0.0.1:{server.server_address[1]}", flush=True)
    threading.Event().wait()
