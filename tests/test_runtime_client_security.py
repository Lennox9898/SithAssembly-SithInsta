from __future__ import annotations

import runpy
import unittest
from unittest.mock import patch
from pathlib import Path


class RuntimeClientSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        runtime_path = Path(__file__).resolve().parent.parent / "SithAssembly.Runtime.py"
        cls.runtime = runpy.run_path(str(runtime_path))

    def test_accepts_only_loopback_server_urls(self) -> None:
        self.assertEqual(self.runtime["local_server_url"]("http://127.0.0.1:8080"), "http://127.0.0.1:8080")
        with self.assertRaisesRegex(ValueError, "loopback"):
            self.runtime["local_server_url"]("https://example.org")

    def test_redirect_handler_rejects_token_redirects(self) -> None:
        handler = self.runtime["_RejectRedirects"]()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://example.org"))

    def test_request_revalidates_url_before_reading_api_token(self) -> None:
        with patch.dict("os.environ", {"SITH_API_TOKEN": "must-not-leak"}):
            with self.assertRaisesRegex(ValueError, "loopback"):
                self.runtime["request"]("https://example.org/api/cases")

    def test_request_payload_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "2 MB"):
            self.runtime["request"](
                "http://127.0.0.1:8080/api/commands",
                "POST",
                {"command": "x" * (2 * 1024 * 1024)},
            )


if __name__ == "__main__":
    unittest.main()
