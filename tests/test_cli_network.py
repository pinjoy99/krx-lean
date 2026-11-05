import unittest
from unittest import mock

import requests

from krx_lean import cli


class NetworkErrorTest(unittest.TestCase):
    def test_timeout_is_a_resumable_error_not_a_traceback(self):
        with mock.patch.object(cli, "_main", side_effect=requests.exceptions.ReadTimeout("read timed out")):
            with self.assertLogs(level="ERROR") as logs:
                self.assertEqual(cli.main(["krx"]), 1)
        self.assertIn("re-run the same command to resume", logs.output[0])


if __name__ == "__main__":
    unittest.main()
