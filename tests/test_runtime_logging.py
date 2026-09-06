from __future__ import annotations

import unittest

from src.runtime_logging import MAX_LOG_VALUE_CHARS, _safe_value


class RuntimeLoggingTests(unittest.TestCase):
    def test_redacts_extended_secret_key_names_and_bounds_strings(self) -> None:
        record = _safe_value(
            {
                "api_token": "hidden",
                "Authorization": "Bearer hidden",
                "nested": {"session_cookie": "hidden"},
                "message": "x" * (MAX_LOG_VALUE_CHARS + 10),
            }
        )

        self.assertEqual(record["api_token"], "[redacted]")
        self.assertEqual(record["Authorization"], "[redacted]")
        self.assertEqual(record["nested"]["session_cookie"], "[redacted]")
        self.assertEqual(len(record["message"]), MAX_LOG_VALUE_CHARS)
