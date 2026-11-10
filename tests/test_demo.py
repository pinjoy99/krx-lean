import tempfile
import unittest
import zipfile
from pathlib import Path

from krx_lean import build, demo, lean_install


class DemoDataTest(unittest.TestCase):
    """The synthetic demo data goes through the real build and lean-install."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "demo"
        cls.info = demo.generate(cls.root, holidays={"20180105"}, start="20171201", end="20190731")
        build.build(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_calendar_and_marking(self):
        self.assertEqual(self.info["first"], "20171201")
        self.assertNotIn("20180105", demo.trading_days("20180101", "20180110", {"20180105"}))
        for folder in (self.root, self.root / "lean" / "equity" / "krx", self.root / "lean" / "index" / "krx"):
            self.assertTrue((folder / demo.MARKER).exists(), folder)
        self.assertTrue(demo.is_demo(self.root))
        names = (self.root / "securities.csv").read_text(encoding="utf-8")
        self.assertIn("D00010,SYNTHETIC DEMO 01,KOSPI", names)
        self.assertNotIn("005930", names)       # no real codes

    def test_events(self):
        events = (self.root / "factor_events.csv").read_text()
        self.assertIn("D00020,adjustment,20180504,20180503,0.2,", events)          # 5:1 split
        self.assertIn("D00010,dividend,", events)
        mapf = (self.root / "lean" / "equity" / "krx" / "map_files" / "d00030.csv").read_text()
        self.assertEqual(mapf.splitlines()[-1], "20190628,d00030")                # delisted
        with zipfile.ZipFile(self.root / "lean" / "index" / "krx" / "daily" / "kospi200.zip") as z:
            self.assertTrue(z.read(z.namelist()[0]).decode().startswith("20171201"))

    def test_install_carries_the_marker(self):
        data = Path(self.tmp.name) / "data"
        (data / "market-hours").mkdir(parents=True)
        (data / "market-hours" / "market-hours-database.json").write_text(
            '{"entries": {"Index-krx-[*]": {"holidays": []}}}')
        (data / "symbol-properties").mkdir()
        (data / "symbol-properties" / "symbol-properties-database.csv").write_text("market,symbol\n")
        lean_install.install(self.root, data)
        self.assertTrue((data / "equity" / "krx" / demo.MARKER).exists())
        self.assertTrue((data / "index" / "krx" / demo.MARKER).exists())

    def test_rebuild_is_reproducible_and_reinstall_copies_nothing(self):
        daily = self.root / "lean" / "equity" / "krx" / "daily" / "d00010.zip"
        before, mtime = daily.read_bytes(), daily.stat().st_mtime_ns
        with self.assertLogs(level="INFO"):
            build.build(self.root)
        self.assertEqual(daily.read_bytes(), before)             # same bytes: fixed zip member timestamp
        self.assertEqual(daily.stat().st_mtime_ns, mtime)        # and the unchanged file wasn't rewritten
        data = Path(self.tmp.name) / "data2"
        (data / "market-hours").mkdir(parents=True)
        (data / "market-hours" / "market-hours-database.json").write_text(
            '{"entries": {"Index-krx-[*]": {"holidays": []}}}')
        (data / "symbol-properties").mkdir()
        (data / "symbol-properties" / "symbol-properties-database.csv").write_text("market,symbol\n")
        src = self.root / "lean" / "equity" / "krx"
        first = lean_install.sync_tree(src, data / "equity" / "krx")
        self.assertGreater(first[0], 0)
        self.assertEqual(lean_install.sync_tree(src, data / "equity" / "krx"), (0, first[0]))
        (data / "equity" / "krx" / "daily" / "d00010.zip").write_bytes(b"damaged")
        self.assertEqual(lean_install.sync_tree(src, data / "equity" / "krx"), (1, first[0] - 1))

    def test_deterministic(self):
        other = Path(self.tmp.name) / "again"
        demo.generate(other, holidays={"20180105"}, start="20171201", end="20190731")
        a = sorted((self.root / "raw" / "krx" / "KOSPI").rglob("*.csv.gz"))[100].read_bytes()
        b = sorted((other / "raw" / "krx" / "KOSPI").rglob("*.csv.gz"))[100]
        import gzip
        self.assertEqual(gzip.decompress(a), gzip.decompress(b.read_bytes()))


if __name__ == "__main__":
    unittest.main()
