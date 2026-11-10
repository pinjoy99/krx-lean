import unittest
from unittest import mock

import requests

from krx_lean import cli, dividends, rights
from krx_lean.client import redact

KEY = "abc+DEF/123=="          # data.go.kr keys contain characters that get URL-encoded


class RedactTest(unittest.TestCase):
    def test_redact(self):
        url = "https://apis.data.go.kr/x?serviceKey=abc%2BDEF%2F123%3D%3D&pageNo=1"
        self.assertEqual(redact(f"Max retries exceeded with url: {url} (Caused by ...)"),
                         "Max retries exceeded with url: https://apis.data.go.kr/x?serviceKey=***&pageNo=1 (Caused by ...)")
        self.assertNotIn("DEF", redact(f"key {KEY} and abc%2BDEF%2F123%3D%3D", KEY))
        self.assertEqual(redact("AUTH_KEY=SECRET1 ok"), "AUTH_KEY=*** ok")
        self.assertEqual(redact("nothing secret", ""), "nothing secret")

    def test_download_errors_do_not_show_the_key(self):
        session = mock.Mock()
        session.get.side_effect = requests.ConnectionError(
            "HTTPSConnectionPool(host='apis.data.go.kr'): Max retries exceeded with url: "
            "/1160100/svc?serviceKey=abc%2BDEF%2F123%3D%3D&pageNo=1")
        for module, error in ((dividends, dividends.DividendApiError), (rights, rights.RightsApiError)):
            with mock.patch.object(module.time, "sleep"), self.assertLogs(level="WARNING"):
                with self.assertRaises(error) as e:
                    module.fetch_page(session, KEY, 1, attempts=2)
            self.assertNotIn("DEF", str(e.exception))
            self.assertIn("serviceKey=***", str(e.exception))

    def test_cli_network_error_does_not_show_the_key(self):
        err = requests.exceptions.ReadTimeout(f"timed out: https://x/?serviceKey={KEY}&p=1 and header {KEY}")
        with mock.patch.object(cli, "_main", side_effect=err), mock.patch.dict("os.environ", {"DATA_GO_KR_KEY": KEY}):
            with self.assertLogs(level="ERROR") as logs:
                self.assertEqual(cli.main(["dividends"]), 1)
        self.assertNotIn("DEF", logs.output[0])


if __name__ == "__main__":
    unittest.main()
