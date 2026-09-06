from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


SENSITIVE_KEY_MARKERS = {
    "authorization",
    "cookie",
    "credential",
    "passphrase",
    "password",
    "private_key",
    "secret",
    "session",
    "token",
}
SENSITIVE_KEYS = {"content_base64", "image_base64"}
MAX_LOG_VALUE_CHARS = 4096
MAX_LOG_TAIL_BYTES = 2 * 1024 * 1024
MAX_LOG_EXPORT_BYTES = 6 * 1024 * 1024


class _PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


def _is_sensitive_key(value: object) -> bool:
    normalized = str(value).strip().lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): "[redacted]" if _is_sensitive_key(key) else _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value[:MAX_LOG_VALUE_CHARS]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


class RuntimeLogger:
    def __init__(self, log_directory: Path, dev_mode: bool = False) -> None:
        self.log_directory = log_directory
        self.dev_mode = dev_mode
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_directory / ("instawatch.dev.jsonl" if dev_mode else "instawatch.jsonl")
        self.logger = logging.getLogger(f"sithassembly.runtime.{id(self)}")
        self.logger.setLevel(logging.DEBUG if dev_mode else logging.INFO)
        self.logger.propagate = False
        self.handler = _PrivateRotatingFileHandler(self.log_path, maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(self.handler)

    def event(self, name: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": name,
            "mode": "dev" if self.dev_mode else "normal",
            **_safe_value(fields),
        }
        self.logger.info(json.dumps(record, ensure_ascii=True, separators=(",", ":")))

    def request(self, method: str, path: str, **fields: Any) -> None:
        if self.dev_mode:
            self.event("http_request", method=method, path=path, **fields)

    def response(self, method: str, path: str, status: int, byte_count: int) -> None:
        if self.dev_mode or status >= 400:
            self.event("http_response", method=method, path=path, status=status, byte_count=byte_count)

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        if not self.log_path.exists():
            return []
        with self.log_path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - MAX_LOG_TAIL_BYTES)
            handle.seek(start)
            content = handle.read(MAX_LOG_TAIL_BYTES)
        if start:
            separator = content.find(b"\n")
            content = content[separator + 1:] if separator >= 0 else b""
        entries: list[dict[str, Any]] = []
        for raw_line in content.splitlines()[-limit:]:
            try:
                entries.append(json.loads(raw_line.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                entries.append({"event": "unparseable_log_line"})
        return entries

    def export_bytes(self) -> bytes:
        if not self.log_path.exists():
            return b""
        self.handler.flush()
        with self.log_path.open("rb") as handle:
            payload = handle.read(MAX_LOG_EXPORT_BYTES + 1)
        if len(payload) > MAX_LOG_EXPORT_BYTES:
            raise ValueError("runtime log export is limited to 6 MB")
        return payload

    def close(self) -> None:
        self.logger.removeHandler(self.handler)
        self.handler.close()
