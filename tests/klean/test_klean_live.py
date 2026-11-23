"""Live paper deployments (klean/live.py): deploying, trading days, summaries. The plugin itself
(klean/plugin, C#) runs in LEAN: tests/e2e-demo.sh checks it against a backtest."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parent), str(_HERE.parents[2])]

from klean import live, projects
from klean.workspace import KleanError, Workspace

DAYS = ["2026-09-22", "2026-09-23", "2026-09-28", "2026-09-29", "2026-09-30"]


class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name).resolve()
        self.ws = Workspace(root=root / "ws", lean_root=str(root / "Lean"))
        index = self.ws.data / "index" / "krx" / "daily"
        index.mkdir(parents=True)
        with zipfile.ZipFile(index / "kospi.zip", "w") as z:
            z.writestr("kospi.csv", "".join(f"{d.replace('-', '')} 00:00,1,1,1,1,0\n" for d in DAYS))
        self.ws.save()
        self.project = projects.create(self.ws, "P", "python", "buy-hold")
        p = mock.patch("klean.results.is_demo_data", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_trading_days_from_the_index(self):
        self.assertEqual(live.trading_days(self.ws), DAYS)

    def test_deploy_starts_after_the_latest_data(self):
        dep = live.deploy(self.ws, self.project, "a", {"slippage_ticks": "1"}, cash=50_000_000)
        record, book = live.load(dep), live.ledger(dep)
        self.assertEqual((record["first_session"], record["backdated"]), ("2026-10-01", False))
        self.assertEqual((book["cash"], book["slippage_ticks"], book["last_session"]), (50_000_000, 1, "2026-09-30"))
        self.assertTrue((dep / "code" / "main.py").exists())
        self.assertEqual(live.pending_sessions(self.ws, dep), [])        # waiting for new days
        self.assertEqual(live.summary(self.ws, dep)["state"], "waiting for data")

    def test_backdated_deploy_runs_the_days_in_order(self):
        dep = live.deploy(self.ws, self.project, start="2026-09-23")
        self.assertTrue(live.load(dep)["backdated"])
        self.assertEqual(live.ledger(dep)["last_session"], "2026-09-22")
        self.assertEqual(live.pending_sessions(self.ws, dep), DAYS[1:])
        calls = []

        def fake_session(ws, d, session, log=print, timeout=900):
            calls.append(session)
            book = live.ledger(d)
            book["last_session"] = session
            book["equity"].append({"session": session, "cash": 1, "holdings_value": 0, "equity": 101_000_000})
            (d / live.LEDGER).write_text(json.dumps(book))
            return {"session": session, "ok": session != "2026-09-29"}

        with mock.patch.object(live, "ensure_plugin"), mock.patch.object(live, "run_session", side_effect=fake_session):
            done = live.run(self.ws, dep, log=lambda *a: None)
        # stops at the first failure; the next run starts from there
        self.assertEqual(calls, ["2026-09-23", "2026-09-28", "2026-09-29"])
        self.assertEqual([e["ok"] for e in done], [True, True, False])
        sm = live.summary(self.ws, dep)
        self.assertEqual((sm["days"], round(sm["net_profit"], 6)), (3, 1.0))

    def test_stop_and_find(self):
        dep = live.deploy(self.ws, self.project)
        self.assertEqual(live.find(self.project, dep.name), dep)
        with self.assertRaisesRegex(KleanError, "no live deployment"):
            live.find(self.project, "../../x")
        live.stop(dep)
        with mock.patch.object(live, "ensure_plugin") as build:
            self.assertEqual(live.run(self.ws, dep), [])
        build.assert_not_called()
        self.assertEqual(live.summary(self.ws, dep)["state"], "stopped")

    def test_gui_shows_the_account(self):
        from klean import gui
        daily = self.ws.data / "equity" / "krx" / "daily"
        daily.mkdir(parents=True)
        with zipfile.ZipFile(daily / "d00010.zip", "w") as z:
            z.writestr("d00010.csv", "20260928 00:00,1000000000,1010000000,990000000,1050000000,10\n"
                                     "20260929 00:00,1050000000,1100000000,1040000000,1100000000,10\n")
        index = self.ws.data / "index" / "krx" / "daily"
        with zipfile.ZipFile(index / "kospi200.zip", "w") as z:
            z.writestr("kospi200.csv", "20260928 00:00,1,1,1,400,0\n20260929 00:00,1,1,1,420,0\n")
        dep = live.deploy(self.ws, self.project, "g", start="2026-09-28")
        book = live.ledger(dep)
        book.update(cash=50_000_000, holdings={"D00010": {"quantity": 500, "average_price": 100_000}},
                    last_session="2026-09-29",
                    fills=[{"order_id": 1, "session": "2026-09-29", "symbol": "D00010", "quantity": 500, "price": 100_000,
                            "commission": 7500, "tax": 0, "type": "MarketOnOpen", "tag": ""}],
                    equity=[{"session": "2026-09-28", "cash": 100_000_000, "holdings_value": 0, "equity": 100_000_000},
                            {"session": "2026-09-29", "cash": 50_000_000, "holdings_value": 55_000_000, "equity": 105_000_000}])
        (dep / live.LEDGER).write_text(json.dumps(book))
        d = gui.api_live_deployment(self.ws, {"project": ["P"], "id": [dep.name]})
        pos = d["positions"][0]
        self.assertEqual((pos["last"], pos["value"], pos["pnl"]), (110_000, 55_000_000, 5_000_000))
        self.assertEqual((round(d["net_profit"], 6), d["days"], d["state"]), (5.0, 2, "running"))
        self.assertEqual([v for _, v in d["equity_curve"]], [100_000_000, 105_000_000])
        self.assertEqual([round(v) for _, v in d["benchmark"]], [100_000_000, 105_000_000])   # KOSPI 200 +5%
        row = next(p for p in gui.api_workspace(self.ws, {})["projects"] if p["name"] == "P")
        self.assertEqual((row["live_runs"], row["last_live"]["id"]), (1, dep.name))
        self.assertEqual(gui.api_live(self.ws, {"project": ["P"]})["deployments"][0]["id"], dep.name)

    def test_older_csharp_projects_are_upgraded(self):
        cs = projects.create(self.ws, "C", "csharp", "buy-hold")
        csproj = next(cs.glob("*.csproj"))
        new = csproj.read_text()
        self.assertIn("live/**", new)
        self.assertIn("QuantConnect.Krx.dll", new)
        old = new.replace(";live/**", "").replace(";$(LeanBin)/QuantConnect.Krx.dll", "")
        csproj.write_text(old)
        projects.upgrade_csproj(csproj)
        self.assertEqual(csproj.read_text(), new)
        (cs / "live" / "x" / "code").mkdir(parents=True)                       # frozen copies don't count
        (cs / "live" / "x" / "code" / "Main.cs").write_text("class Other : QCAlgorithm {}")
        self.assertEqual(projects.csharp_algorithm_class(cs), "C")

    def test_live_config_uses_the_plugin(self):
        self.assertEqual(live.LIVE_CONFIG["live-mode-brokerage"], "KrxPaperBrokerage")
        self.assertEqual(live.LIVE_CONFIG["data-queue-handler"], ["QuantConnect.Krx.KrxDailyDataQueue"])
        sources = {p.name for p in live.PLUGIN_SRC.iterdir()}
        self.assertTrue({"Krx.Lean.csproj", "KrxPaperBrokerage.cs", "KrxDailyDataQueue.cs", "KrxLedger.cs"} <= sources)


if __name__ == "__main__":
    unittest.main()
