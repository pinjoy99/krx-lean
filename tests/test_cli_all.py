import tempfile
import unittest
from pathlib import Path
from unittest import mock

from krx_lean import cli, krx_api


class AllCommandTest(unittest.TestCase):
    """`krx-lean all` downloads KOSPI and ETF, and KOSDAQ only if the key has those services."""

    def run_all(self, fail):
        calls = []

        def scrape(client, root, markets=None, dataset="price", **kw):
            calls.append((markets[0], dataset))
            error = fail.get((markets[0], dataset))
            if error:
                raise error
            return {}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(krx_api, "scrape_krx", scrape), \
                mock.patch.object(krx_api, "client_from_env", lambda **kw: None), \
                mock.patch.object(cli.build, "build", lambda *a, **k: 0), \
                mock.patch.dict("os.environ", {"DATA_GO_KR_KEY": ""}):
            with self.assertLogs(level="WARNING") as logs:
                code = cli.main(["--root", str(Path(d)), "all"])
        return code, calls, "\n".join(logs.output)

    def test_everything_approved(self):
        code, calls, _ = self.run_all({})
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("KOSPI", "price"), ("ETF", "price"), ("KOSPI", "index"),
                                 ("KOSDAQ", "price"), ("KOSDAQ", "index")])

    def test_kosdaq_not_approved_is_skipped(self):
        not_approved = krx_api.KrxApiError("KOSDAQ 20100104: 401 Unauthorized API Call", not_approved=True)
        code, calls, logs = self.run_all({("KOSDAQ", "price"): not_approved, ("KOSDAQ", "index"): not_approved})
        self.assertEqual(code, 0)                                   # KOSPI and ETF are complete
        self.assertEqual(len(calls), 5)
        self.assertIn("KOSDAQ price skipped", logs)

    def test_other_errors_still_stop(self):
        code, calls, logs = self.run_all({("ETF", "price"): krx_api.KrxApiError("ETF: quota", not_approved=False)})
        self.assertEqual(code, 1)
        self.assertEqual(calls, [("KOSPI", "price"), ("ETF", "price")])
        code, _, _ = self.run_all({("KOSPI", "price"): krx_api.KrxApiError("x", not_approved=True)})
        self.assertEqual(code, 1)                                   # KOSPI isn't optional


if __name__ == "__main__":
    unittest.main()
