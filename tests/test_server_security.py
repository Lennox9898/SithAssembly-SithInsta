from __future__ import annotations

import os
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from src.repository import Repository
from src.server import SignalDeskHandler, run


class ServerSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_repository = SignalDeskHandler.repository
        self.original_web_root = SignalDeskHandler.web_root
        self.original_api_token = SignalDeskHandler.api_token
        self.original_allowed_hosts = SignalDeskHandler.allowed_hosts
        self.web_root = self.root / "web"
        self.web_root.mkdir()
        (self.web_root / "index.html").write_text("<html>safe</html>", encoding="utf-8")
        private_root = self.root / "web-private"
        private_root.mkdir()
        (private_root / "secret.txt").write_text("not public", encoding="utf-8")
        SignalDeskHandler.repository = Repository(self.root / "security.db")
        SignalDeskHandler.web_root = self.web_root
        SignalDeskHandler.api_token = None
        SignalDeskHandler.allowed_hosts = frozenset({"127.0.0.1", "localhost", "::1"})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SignalDeskHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        SignalDeskHandler.repository = self.original_repository
        SignalDeskHandler.web_root = self.original_web_root
        SignalDeskHandler.api_token = self.original_api_token
        SignalDeskHandler.allowed_hosts = self.original_allowed_hosts
        self.temp_dir.cleanup()

    def test_static_path_cannot_escape_the_web_root(self) -> None:
        response = self._request("GET", "/static/../web-private/secret.txt")

        self.assertEqual(response.status, 403)

    def test_network_token_protects_api_but_not_minimal_health_check(self) -> None:
        SignalDeskHandler.api_token = "t" * 32

        unauthenticated = self._request("GET", "/api/cases")
        health = self._request("GET", "/api/health")
        authenticated = self._request("GET", "/api/cases", {"Authorization": "Bearer " + ("t" * 32)})

        self.assertEqual(unauthenticated.status, 401)
        self.assertEqual(health.status, 200)
        self.assertEqual(authenticated.status, 200)
        self.assertEqual(unauthenticated.getheader("Cache-Control"), "no-store")
        self.assertEqual(authenticated.getheader("X-Content-Type-Options"), "nosniff")

    def test_network_bind_requires_explicit_flag_and_token(self) -> None:
        with patch.dict(os.environ, {"SITH_API_TOKEN": ""}):
            with self.assertRaisesRegex(ValueError, "allow-network"):
                run(host="0.0.0.0")
            with self.assertRaisesRegex(ValueError, "SITH_API_TOKEN"):
                run(host="0.0.0.0", allow_network=True)

    def test_rejects_unlisted_host_header(self) -> None:
        response = self._request("GET", "/api/health", {"Host": "rebind.attacker.example"})

        self.assertEqual(response.status, 421)

    def test_network_bind_requires_explicit_host_allowlist(self) -> None:
        with patch.dict(os.environ, {"SITH_API_TOKEN": "t" * 32, "SITH_ALLOWED_HOSTS": ""}):
            with self.assertRaisesRegex(ValueError, "SITH_ALLOWED_HOSTS"):
                run(host="0.0.0.0", allow_network=True)

    def test_string_confirmation_does_not_activate_depth_model(self) -> None:
        with patch.object(
            SignalDeskHandler.repository,
            "run_depth",
            return_value={"state": "confirmation_required"},
        ) as run_depth:
            response = self._request(
                "POST",
                "/api/cases/1/evidence/2/depth",
                {"Content-Type": "application/json"},
                json.dumps({"confirm_depth_analysis": "true"}),
            )

        self.assertEqual(response.status, 201)
        run_depth.assert_called_once_with(1, 2, False)

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
    ):
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        response.read()
        connection.close()
        return response


if __name__ == "__main__":
    unittest.main()
