"""KIS (klean/kis.py and the KIS side of klean/live.py) against the simulated KIS server in
tests/fake_kis.py. The C# plugin's KIS brokerage is checked in tests/e2e-demo.sh."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[1]), str(_HERE.parents[2])]

import fake_kis  # noqa: E402  (tests/fake_kis.py)
from klean import kis, live, projects  # noqa: E402
from klean.workspace import KleanError, Workspace  # noqa: E402


class KisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        daily = self.ws.data / "equity" / "krx" / "daily"
        daily.mkdir(parents=True)
        with zipfile.ZipFile(daily / "005930.zip", "w") as z:
            z.writestr("005930.csv", "20260930 00:00,1000000000,1010000000,990000000,1000000000,10\n")
        index = self.ws.data / "index" / "krx" / "daily"
        index.mkdir(parents=True)
        with zipfile.ZipFile(index / "kospi.zip", "w") as z:
            z.writestr("kospi.csv", "20260929 00:00,1,1,1,1,0\n20260930 00:00,1,1,1,1,0\n")
        hours = self.ws.data / "market-hours"
        hours.mkdir(parents=True)
        (hours / "market-hours-database.json").write_text(json.dumps(
            {"entries": {"Equity-krx-[*]": {"holidays": ["10/5/2026", "10/9/2026"]}}}))
        self.ws.save()
        self.server, self.fake = fake_kis.serve(0, 50_000_000, self.ws.data)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        env = {"KIS_PAPER_APP_KEY": "k", "KIS_PAPER_APP_SECRET": "s", "KIS_PAPER_ACCOUNT": "12345678-01",
               "KIS_PAPER_BASE_URL": f"http://127.0.0.1:{self.server.server_address[1]}", "HOME": str(root)}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch("klean.results.is_demo_data", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_client(self):
        k = kis.Kis()
        self.assertEqual((k.cano, k.product), ("12345678", "01"))
        b = k.balance()
        self.assertEqual((b["cash"], b["holdings"]), (50_000_000, []))
        self.assertEqual(k.daily_bar("005930", "2026-09-30")["close"], 100_000)        # a day in the files
        self.assertEqual(k.daily_bar("005930", "2026-10-01")["close"], 102_000)        # a later day: made up by the fake
        kis.Kis().balance()
        self.assertEqual(self.fake.tokens, 1)                                           # the token is cached
        self.assertEqual({c["tr_id"] for c in self.fake.calls}, {"VTTC8434R", "FHKST03010100"})

    def test_paper_only(self):
        self.assertEqual(kis.PAPER_URL, "https://openapivts.koreainvestment.com:29443")   # KIS 모의투자
        for old in ("KIS_APP_KEY", "KIS_MOCK"):                                         # 0.0.20/0.0.21 names
            with mock.patch.dict(os.environ, {old: "x"}), self.assertRaisesRegex(KleanError, "KIS_PAPER_APP_KEY"):
                kis.Kis()
        with mock.patch.dict(os.environ, {"KIS_PAPER_BASE_URL": ""}):
            self.assertEqual(kis.Kis().base, kis.PAPER_URL)
        self.assertFalse(hasattr(kis, "REAL_URL"))
        # nothing in klean can reach KIS's real-trading server or use a real-account order id
        sources = [Path(kis.__file__), *(Path(kis.__file__).parent / "plugin").glob("*.cs")]
        for path in sources:
            text = path.read_text(encoding="utf-8")
            for banned in ("openapi.koreainvestment.com", ":9443", "TTTC", "CTSC",
                           'environ.get("KIS_MOCK")', 'environ["KIS_APP_KEY"]', 'GetEnvironmentVariable("KIS_MOCK")',
                           'Env("KIS_APP_KEY")'):
                self.assertNotIn(banned, text, f"{path.name} contains {banned!r}")

    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {"KIS_PAPER_APP_KEY": ""}), self.assertRaisesRegex(KleanError, "KIS_PAPER_APP_KEY"):
            kis.Kis()

    def test_expired_token_is_renewed_once(self):
        k = kis.Kis()
        k.token()
        path = k.token_path()
        path.write_text(json.dumps({"token": "stale", "expires_utc": "2099-01-01T00:00:00.0000000Z"}))
        k2 = kis.Kis()
        self.assertEqual(k2.balance()["cash"], 50_000_000)       # EGW00123 for "stale", then a new token
        self.assertEqual(self.fake.tokens, 2)

    def test_pre_open_window(self):
        kst = kis.KST
        self.assertTrue(kis.in_pre_open(dt.datetime(2026, 10, 2, 8, 35, tzinfo=kst)))
        self.assertFalse(kis.in_pre_open(dt.datetime(2026, 10, 2, 9, 0, tzinfo=kst)))
        self.assertFalse(kis.in_pre_open(dt.datetime(2026, 10, 2, 21, 30, tzinfo=kst)))
        self.assertEqual(live.previous_trading_day(self.ws, dt.date(2026, 10, 6)), "2026-10-02")   # 10-05 is a holiday

    def test_deploy_and_sessions(self):
        project = projects.create(self.ws, "P", "python", "buy-hold")
        with mock.patch.dict(os.environ, {"KLEAN_KIS_NOW": "2026-10-01T20:00"}):
            dep = live.deploy(self.ws, project, broker="kis-paper")
            with self.assertRaisesRegex(KleanError, "can't be backdated"):
                live.deploy(self.ws, project, broker="kis-paper", start="2026-09-29")
        record = live.load(dep)
        self.assertEqual((record["broker"], record["first_session"], record["cash"]),
                         ("kis-paper", "2026-10-01", 50_000_000))
        self.assertTrue(record["kis_account"].startswith("12******-01 paper "))     # never the full number
        other = projects.create(self.ws, "Q", "python", "buy-hold")
        with mock.patch.dict(os.environ, {"KLEAN_KIS_NOW": "2026-10-01T20:00"}), \
                self.assertRaisesRegex(KleanError, "already trades this KIS account"):
            live.deploy(self.ws, other, broker="kis-paper")
        self.assertEqual(live.ledger(dep)["broker"], "kis-paper")
        logs = []
        with mock.patch.dict(os.environ, {"KLEAN_KIS_NOW": "2026-10-02T21:30"}), \
             mock.patch.object(live, "ensure_plugin") as build:
            self.assertEqual(live.run(self.ws, dep, log=logs.append), [])           # outside the pre-open window
        build.assert_not_called()
        self.assertIn("skipped", logs[0])
        with mock.patch.dict(os.environ, {"KLEAN_KIS_NOW": "2026-10-02T08:35"}):
            self.assertEqual(live.pending_sessions(self.ws, dep), ["2026-10-01"])   # day T: prices from KIS
        with mock.patch.dict(os.environ, {"KLEAN_KIS_NOW": "2026-10-06T08:35"}):
            self.assertEqual(live.pending_sessions(self.ws, dep), ["2026-10-02"])   # only the latest day, once


if __name__ == "__main__":
    unittest.main()
