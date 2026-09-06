from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_CLIENT_REQUEST_BYTES = 2 * 1024 * 1024
MAX_CLIENT_RESPONSE_BYTES = 20 * 1024 * 1024
MAX_CLIENT_URL_CHARS = 2048


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def open_local_request(request: urllib.request.Request, timeout: int):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectRedirects()).open(request, timeout=timeout)


def request(url: str, method: str = "GET", payload: dict | None = None) -> bytes:
    _validate_loopback_url(url, root_only=False)
    if method not in {"GET", "POST"}:
        raise ValueError("runtime client supports GET and POST requests only")
    try:
        body = json.dumps(payload, allow_nan=False).encode("utf-8") if payload is not None else None
    except (TypeError, ValueError) as error:
        raise ValueError("runtime client payload must contain JSON-compatible values") from error
    if body is not None and len(body) > MAX_CLIENT_REQUEST_BYTES:
        raise ValueError("local server request is limited to 2 MB")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    api_token = os.environ.get("SITH_API_TOKEN")
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    call = urllib.request.Request(url, data=body, method=method, headers=headers)
    with open_local_request(call, timeout=10) as response:
        response_body = response.read(MAX_CLIENT_RESPONSE_BYTES + 1)
    if len(response_body) > MAX_CLIENT_RESPONSE_BYTES:
        raise ValueError("local server response is limited to 20 MB")
    return response_body


def local_server_url(value: str) -> str:
    _validate_loopback_url(value, root_only=True)
    return value.rstrip("/")


def _validate_loopback_url(value: str, root_only: bool) -> None:
    if not isinstance(value, str) or not value or len(value) > MAX_CLIENT_URL_CHARS:
        raise ValueError("runtime client accepts HTTP loopback server URLs only")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("runtime client accepts HTTP loopback server URLs only")
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (root_only and (parsed.query or parsed.path not in {"", "/"}))
        or (not root_only and (not parsed.path.startswith("/api/") or parsed.path.startswith("//")))
    ):
        raise ValueError("runtime client accepts HTTP loopback server URLs only")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("runtime client URL has an invalid port") from error
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("runtime client URL has an invalid port")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local SithAssembly runtime client")
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="local server URL")
    subparsers = parser.add_subparsers(dest="action", required=True)

    def add_url_option(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--url", dest="command_url", help="local server URL")

    status = subparsers.add_parser("status", help="show runtime and module status")
    add_url_option(status)
    command = subparsers.add_parser("command", help="run an allowlisted local command")
    add_url_option(command)
    command.add_argument("text", help="for example: /context")
    command.add_argument("--case-id", type=int)
    logs = subparsers.add_parser("logs", help="show recent local runtime events")
    add_url_option(logs)
    logs.add_argument("--limit", type=int, default=100)
    logs.add_argument("--export", type=Path, help="write the current JSONL log to a file")
    doctor = subparsers.add_parser("doctor", help="show read-only runtime, configuration, and acceleration diagnostics")
    add_url_option(doctor)
    models = subparsers.add_parser("models", help="show configured local LLM providers and profiles")
    add_url_option(models)
    deployment = subparsers.add_parser("deployment", help="show read-only prepared deployment readiness")
    add_url_option(deployment)
    llm = subparsers.add_parser("llm", help="send one explicit request to an enabled local LLM provider")
    add_url_option(llm)
    llm.add_argument("--provider", required=True, help="provider id from the local model registry")
    llm.add_argument("--profile", required=True, help="model profile id from the local model registry")
    llm.add_argument("--prompt", required=True, help="user prompt sent to the selected local runtime")
    llm.add_argument("--system", help="optional system instruction")
    llm.add_argument("--temperature", type=float, default=0.2)
    llm.add_argument("--max-output-tokens", type=int)
    args = parser.parse_args()

    try:
        server_url = local_server_url(args.command_url or args.url)
        if args.action == "status":
            print(request(f"{server_url}/api/runtime").decode("utf-8"))
        elif args.action == "command":
            print(request(f"{server_url}/api/commands", "POST", {"command": args.text, "case_id": args.case_id}).decode("utf-8"))
        elif args.action == "logs":
            if args.export:
                args.export.parent.mkdir(parents=True, exist_ok=True)
                args.export.write_bytes(request(f"{server_url}/api/logs/export"))
                print(f"Log export written to {args.export}")
            else:
                print(request(f"{server_url}/api/logs?limit={args.limit}").decode("utf-8"))
        elif args.action == "doctor":
            print(request(f"{server_url}/api/diagnostics").decode("utf-8"))
        elif args.action == "models":
            print(request(f"{server_url}/api/llm/providers").decode("utf-8"))
        elif args.action == "deployment":
            print(request(f"{server_url}/api/deployment/readiness").decode("utf-8"))
        elif args.action == "llm":
            messages = []
            if args.system:
                messages.append({"role": "system", "content": args.system})
            messages.append({"role": "user", "content": args.prompt})
            payload = {"provider_id": args.provider, "model_profile": args.profile, "messages": messages, "temperature": args.temperature}
            if args.max_output_tokens is not None:
                payload["max_output_tokens"] = args.max_output_tokens
            print(request(f"{server_url}/api/llm/generate", "POST", payload).decode("utf-8"))
    except (urllib.error.URLError, ValueError) as error:
        detail = error.reason if isinstance(error, urllib.error.URLError) else str(error)
        print(f"Local server is not reachable: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
