from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def request(url: str, method: str = "GET", payload: dict | None = None) -> bytes:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    call = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(call, timeout=10) as response:
        return response.read()


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
    server_url = args.command_url or args.url

    try:
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
    except urllib.error.URLError as error:
        print(f"Local server is not reachable: {error.reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
