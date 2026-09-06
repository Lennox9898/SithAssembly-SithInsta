from __future__ import annotations

import hmac
import ipaddress
import json
import mimetypes
import os
import re
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlsplit

from src.assembly_manifest import public_manifest
from src.agent_coordination import AgentCoordinator, AgentReportJournal
from src.case_manager import CaseManager
from src.clawdbot_adapter import ClawdbotAdapter
from src.command_engine import CommandEngine
from src.database import DATA_DIR
from src.module_runtime import ModuleRuntime
from src.local_llm import LocalLlmBridge, LocalModelRegistry
from src.report_generator import ReportGenerator
from src.repository import Repository
from src.runtime_logging import RuntimeLogger
from src.runtime_doctor import RuntimeDoctor
from src.deployment_preflight import DeploymentPreflight


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
LOOPBACK_BIND_HOSTS = {"127.0.0.1", "::1", "localhost"}
MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024
MAX_STATIC_FILE_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_WORKERS = 16
DNS_HOST_PATTERN = re.compile(
    r"(?=^.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def _normalize_allowed_host(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if not candidate or any(character.isspace() for character in candidate):
        raise ValueError("allowed hosts must contain DNS names or IP addresses without ports")
    try:
        return ipaddress.ip_address(candidate).compressed.lower()
    except ValueError:
        if not DNS_HOST_PATTERN.fullmatch(candidate):
            raise ValueError("allowed hosts must contain DNS names or IP addresses without ports")
        return candidate


def _parse_allowed_hosts(value: str | None, network_bind: bool) -> frozenset[str]:
    if value is None or not value.strip():
        if network_bind:
            raise ValueError("network binding requires SITH_ALLOWED_HOSTS or --allowed-hosts")
        return frozenset(_normalize_allowed_host(host) for host in LOOPBACK_BIND_HOSTS)
    entries = [entry for entry in value.split(",") if entry.strip()]
    if not entries or len(entries) > 32:
        raise ValueError("allowed hosts must contain 1 to 32 comma-separated entries")
    return frozenset(_normalize_allowed_host(entry) for entry in entries)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threaded local server with bounded concurrent request handling."""

    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], max_workers: int) -> None:
        self._request_slots = threading.BoundedSemaphore(max_workers)
        super().__init__(address, handler)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class SignalDeskHandler(BaseHTTPRequestHandler):
    server_version = "SithAssembly"
    sys_version = ""
    repository = Repository()
    case_manager = CaseManager(repository)
    command_engine = CommandEngine(repository)
    report_generator = ReportGenerator()
    web_root = WEB_DIR
    runtime: ModuleRuntime | None = None
    runtime_logger: RuntimeLogger | None = None
    dev_mode = False
    agent_coordinator = AgentCoordinator(ROOT_DIR / "config" / "agent_registry.json")
    agent_journal = AgentReportJournal(DATA_DIR / "agent_reports.jsonl")
    clawdbot_adapter = ClawdbotAdapter(ROOT_DIR / "config" / "clawdbot.local.json")
    local_model_registry = LocalModelRegistry(ROOT_DIR / "config" / "local_model_registry.json")
    local_llm_bridge = LocalLlmBridge(local_model_registry)
    runtime_doctor = RuntimeDoctor(ROOT_DIR)
    deployment_preflight = DeploymentPreflight(ROOT_DIR)
    compute_mode = "auto"
    api_token: str | None = None
    allowed_hosts = frozenset(LOOPBACK_BIND_HOSTS)
    request_timeout_seconds = 15

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.request_timeout_seconds)

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._handle_get()
        except ValueError as error:
            self._log_event("request_rejected", path=urlparse(self.path).path, reason=str(error))
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as error:
            self._log_event("request_error", path=urlparse(self.path).path, error_type=type(error).__name__)
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._is_allowed_host_header():
            self._log_event("host_rejected", method="GET", path=path)
            self._send_misdirected_request()
            return
        query = {
            key: values[-1]
            for key, values in parse_qs(parsed.query, max_num_fields=50).items()
        }
        self._log_request("GET", path, query_keys=sorted(query))

        if not self._is_authorized_api_request(path):
            self._log_event("authentication_rejected", method="GET", path=path)
            self._send_unauthorized()
            return

        if path == "/api/health":
            self._send_json({"status": "ok", "product": "SithAssembly//Instawatch"})
            return
        if path == "/api/assembly":
            self._send_json(public_manifest())
            return
        if path == "/api/runtime":
            runtime = self.runtime.snapshot() if self.runtime else {"loaded": 0, "total": 0, "modules": []}
            self._send_json(
                {
                    "mode": "dev" if self.dev_mode else "normal",
                    "bind": "local-only" if self.server.server_address[0] in {"127.0.0.1", "::1"} else "network",
                    "log_file": str(self.runtime_logger.log_path) if self.runtime_logger else None,
                    **runtime,
                }
            )
            return
        if path == "/api/agents":
            self._send_json(self.agent_coordinator.snapshot())
            return
        if path == "/api/job-queue":
            self._send_json(self.repository.get_job_queue_status())
            return
        if path == "/api/clawdbot":
            self._send_json(self.clawdbot_adapter.status())
            return
        if path == "/api/clawdbot/manifest":
            self._send_json(self.clawdbot_adapter.manifest())
            return
        if path == "/api/llm/providers":
            self._send_json(self.local_model_registry.snapshot())
            return
        if path == "/api/diagnostics":
            self._send_json(self.runtime_doctor.snapshot(self.compute_mode))
            return
        if path == "/api/deployment/readiness":
            self._send_json(self.deployment_preflight.snapshot())
            return
        if path == "/api/agent-reports":
            self._send_json({"entries": self.agent_journal.tail(self._parse_log_limit(query.get("limit")))})
            return
        if path == "/api/logs":
            limit = self._parse_log_limit(query.get("limit"))
            entries = self.runtime_logger.tail(limit) if self.runtime_logger else []
            self._send_json({"entries": entries, "count": len(entries)})
            return
        if path == "/api/logs/export":
            payload = self.runtime_logger.export_bytes() if self.runtime_logger else b""
            self._send_bytes(payload, "application/x-ndjson; charset=utf-8", "sithassembly-runtime.jsonl")
            return
        if path == "/api/models":
            self._send_json(self.repository.get_model_status())
            return
        if path == "/api/vault/status":
            self._send_json(self.repository.get_vault_status())
            return
        if path == "/api/observations":
            self._send_json(self.repository.list_observations())
            return
        if path == "/api/network":
            self._send_json(self.repository.get_network())
            return
        if path == "/api/cases":
            self._send_json(self.repository.list_cases())
            return

        case_match = re.fullmatch(r"/api/cases/(\d+)", path)
        if case_match:
            detail = self.case_manager.overview(int(case_match.group(1)))
            if detail is None:
                self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(detail)
            return

        case_observations_match = re.fullmatch(r"/api/cases/(\d+)/observations", path)
        if case_observations_match:
            self._send_json(self.case_manager.search(int(case_observations_match.group(1)), query))
            return

        case_timeline_match = re.fullmatch(r"/api/cases/(\d+)/timeline", path)
        if case_timeline_match:
            self._send_json(self.repository.get_case_timeline(int(case_timeline_match.group(1))))
            return

        case_graph_match = re.fullmatch(r"/api/cases/(\d+)/graph", path)
        if case_graph_match:
            self._send_json(self.repository.get_case_graph(int(case_graph_match.group(1))))
            return

        case_profiles_match = re.fullmatch(r"/api/cases/(\d+)/profiles", path)
        if case_profiles_match:
            self._send_json(self.repository.get_case_profiles(int(case_profiles_match.group(1))))
            return

        case_processing_match = re.fullmatch(r"/api/cases/(\d+)/processing", path)
        if case_processing_match:
            self._send_json(self.repository.list_processing(int(case_processing_match.group(1))))
            return

        case_jobs_match = re.fullmatch(r"/api/cases/(\d+)/jobs", path)
        if case_jobs_match:
            state = query.get("state")
            self._send_json(self.repository.list_agent_jobs(int(case_jobs_match.group(1)), state))
            return

        job_match = re.fullmatch(r"/api/jobs/(\d+)", path)
        if job_match:
            job = self.repository.get_agent_job(int(job_match.group(1)))
            if job is None:
                self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(job)
            return

        job_events_match = re.fullmatch(r"/api/jobs/(\d+)/events", path)
        if job_events_match:
            self._send_json(self.repository.get_agent_job_events(int(job_events_match.group(1))))
            return

        case_findings_match = re.fullmatch(r"/api/cases/(\d+)/findings", path)
        if case_findings_match:
            self._send_json(self.repository.get_case_findings(int(case_findings_match.group(1))))
            return

        case_imports_match = re.fullmatch(r"/api/cases/(\d+)/imports", path)
        if case_imports_match:
            self._send_json(self.repository.list_import_batches(int(case_imports_match.group(1))))
            return

        case_anomalies_match = re.fullmatch(r"/api/cases/(\d+)/comment-anomalies", path)
        if case_anomalies_match:
            self._send_json(self.repository.get_comment_anomalies(int(case_anomalies_match.group(1))))
            return

        case_vaults_match = re.fullmatch(r"/api/cases/(\d+)/vaults", path)
        if case_vaults_match:
            self._send_json(self.repository.list_vault_exports(int(case_vaults_match.group(1))))
            return

        vault_verify_match = re.fullmatch(r"/api/vaults/(\d+)/verify", path)
        if vault_verify_match:
            self._send_json(self.repository.verify_evidence_vault(int(vault_verify_match.group(1))))
            return

        vault_download_match = re.fullmatch(r"/api/vaults/(\d+)/download", path)
        if vault_download_match:
            vault = self.repository.read_evidence_vault(int(vault_download_match.group(1)))
            if vault is None:
                self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_bytes(vault[1], "application/json; charset=utf-8", vault[0])
            return

        case_export_match = re.fullmatch(r"/api/cases/(\d+)/export", path)
        if case_export_match:
            report = self.repository.export_case(int(case_export_match.group(1)))
            if report is None:
                self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            export_format = query.get("format", "json")
            if export_format == "pdf":
                self._send_bytes(
                    self.report_generator.pdf_bytes(report),
                    "application/pdf",
                    f"signal-desk-case-{case_export_match.group(1)}.pdf",
                )
                return
            if export_format != "json":
                self._send_json({"error": "invalid_export_format"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_bytes(
                self.report_generator.json_bytes(report),
                "application/json; charset=utf-8",
                f"signal-desk-case-{case_export_match.group(1)}.json",
            )
            return

        observation_match = re.fullmatch(r"/api/observations/(\d+)", path)
        if observation_match:
            detail = self.repository.get_observation(int(observation_match.group(1)))
            if detail is None:
                self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(detail)
            return

        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._is_allowed_host_header():
            self._log_event("host_rejected", method="POST", path=path)
            self._send_misdirected_request()
            return
        self._log_request("POST", path)

        if not self._is_authorized_api_request(path):
            self._log_event("authentication_rejected", method="POST", path=path)
            self._send_unauthorized()
            return

        try:
            payload = self._read_json()
            if path == "/api/commands":
                raw_case_id = payload.get("case_id")
                case_id = int(raw_case_id) if raw_case_id not in (None, "") else None
                result = self.command_engine.execute(str(payload.get("command", "")), case_id)
                self._send_json(result)
                return
            if path == "/api/llm/generate":
                result = self.local_llm_bridge.generate(payload)
                self._log_event("local_llm_response", provider_id=result["provider_id"], model_profile=result["model_profile"])
                self._send_json(result)
                return
            if path == "/api/agent-reports":
                report = self.agent_journal.record(self.agent_coordinator, payload)
                self._log_event("agent_report_recorded", agent_id=report["agent_id"], state=report["state"])
                self._send_json(report, status=HTTPStatus.CREATED)
                return
            if path == "/api/observations":
                created = self.repository.create_observation(payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return
            if path == "/api/cases":
                created = self.repository.create_case(payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return
            if path == "/api/seed":
                seeded = self.repository.seed_demo_data()
                self._send_json(seeded, status=HTTPStatus.CREATED)
                return

            draft_match = re.fullmatch(r"/api/observations/(\d+)/draft", path)
            if draft_match:
                tone = str(payload.get("tone", "firm"))
                detail = self.repository.create_draft(int(draft_match.group(1)), tone=tone)
                if detail is None:
                    self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(detail, status=HTTPStatus.CREATED)
                return

            case_observations_match = re.fullmatch(r"/api/cases/(\d+)/observations", path)
            if case_observations_match:
                payload["case_id"] = int(case_observations_match.group(1))
                created = self.repository.create_observation(payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return

            case_jobs_match = re.fullmatch(r"/api/cases/(\d+)/jobs", path)
            if case_jobs_match:
                result = self.repository.queue_agent_job(int(case_jobs_match.group(1)), payload)
                self._log_event("agent_jobs_queued", case_id=case_jobs_match.group(1), topic=result["topic"], count=len(result["jobs"]))
                self._send_json(result, status=HTTPStatus.CREATED)
                return

            job_transition_match = re.fullmatch(r"/api/jobs/(\d+)/transition", path)
            if job_transition_match:
                result = self.repository.transition_agent_job(int(job_transition_match.group(1)), payload)
                self._log_event("agent_job_transition", job_id=result["id"], state=result["state"], action=payload.get("action"))
                self._send_json(result)
                return

            job_execute_match = re.fullmatch(r"/api/jobs/(\d+)/execute", path)
            if job_execute_match:
                result = self.repository.execute_agent_job(int(job_execute_match.group(1)))
                self._log_event("agent_job_executed", job_id=result["id"], state=result["state"], topic=result["topic"])
                self._send_json(result)
                return

            case_notes_match = re.fullmatch(r"/api/cases/(\d+)/notes", path)
            if case_notes_match:
                created = self.repository.add_note(int(case_notes_match.group(1)), payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return

            case_claims_match = re.fullmatch(r"/api/cases/(\d+)/identity-claims", path)
            if case_claims_match:
                created = self.repository.add_identity_claim(int(case_claims_match.group(1)), payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return

            case_screenshot_match = re.fullmatch(r"/api/cases/(\d+)/screenshots", path)
            if case_screenshot_match:
                created = self.repository.add_screenshot(int(case_screenshot_match.group(1)), payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return

            case_media_match = re.fullmatch(r"/api/cases/(\d+)/local-media", path)
            if case_media_match:
                created = self.repository.add_local_image(int(case_media_match.group(1)), payload)
                self._send_json(created, status=HTTPStatus.CREATED)
                return

            case_ocr_match = re.fullmatch(r"/api/cases/(\d+)/evidence/(\d+)/ocr", path)
            if case_ocr_match:
                result = self.repository.run_ocr(
                    int(case_ocr_match.group(1)),
                    int(case_ocr_match.group(2)),
                    payload.get("confirm_model_download") is True,
                    payload.get("language", "en"),
                )
                self._send_json(result, status=HTTPStatus.CREATED)
                return

            case_depth_match = re.fullmatch(r"/api/cases/(\d+)/evidence/(\d+)/depth", path)
            if case_depth_match:
                result = self.repository.run_depth(
                    int(case_depth_match.group(1)),
                    int(case_depth_match.group(2)),
                    payload.get("confirm_depth_analysis") is True,
                )
                self._send_json(result, status=HTTPStatus.CREATED)
                return

            case_vault_match = re.fullmatch(r"/api/cases/(\d+)/vault", path)
            if case_vault_match:
                if payload.get("confirm") is not True:
                    self._send_json({"state": "confirmation_required", "message": "Passphrase is used once to create a local encrypted vault."})
                    return
                created = self.repository.create_evidence_vault(
                    int(case_vault_match.group(1)),
                    payload.get("passphrase", ""),
                    payload.get("operator", "local analyst"),
                )
                self._send_json(created, status=HTTPStatus.CREATED)
                return

            case_import_match = re.fullmatch(r"/api/cases/(\d+)/import", path)
            if case_import_match:
                result = self.repository.import_case_payload(int(case_import_match.group(1)), payload)
                self._send_json(result, status=HTTPStatus.CREATED)
                return

            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self._log_event("request_rejected", path=path, reason=str(error))
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self._log_event("request_rejected", path=path, reason="invalid_json")
            self._send_json({"error": "invalid_json"}, status=HTTPStatus.BAD_REQUEST)
        except TimeoutError:
            self._log_event("request_rejected", path=path, reason="request_timeout")
            self._send_json({"error": "request_timeout"}, status=HTTPStatus.REQUEST_TIMEOUT)
        except Exception as error:
            self._log_event("request_error", path=path, error_type=type(error).__name__)
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("chunked request bodies are not supported")
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length < 0 or length > MAX_REQUEST_BODY_BYTES:
            raise ValueError("request body is limited to 12 MB")
        if length == 0:
            return {}
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("request body must use application/json")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("incomplete request body")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        self._log_event("request_body_received", path=urlparse(self.path).path, byte_count=length, keys=sorted(payload))
        return payload

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_security_headers(api_response=True)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self._log_response(status, len(response))

    def _send_bytes(self, payload: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self._send_security_headers(api_response=True)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self._log_response(HTTPStatus.OK, len(payload))

    def _serve_static(self, path: str) -> None:
        if path == "/":
            target = self.web_root / "index.html"
        elif path.startswith("/static/"):
            target = self.web_root / path.removeprefix("/static/")
        else:
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        resolved_root = self.web_root.resolve()
        resolved_target = target.resolve()
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError:
            self._send_json({"error": "forbidden"}, status=HTTPStatus.FORBIDDEN)
            return
        if not resolved_target.exists() or not resolved_target.is_file():
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return
        mime_type, _ = mimetypes.guess_type(resolved_target.name)
        with resolved_target.open("rb") as handle:
            content = handle.read(MAX_STATIC_FILE_BYTES + 1)
        if len(content) > MAX_STATIC_FILE_BYTES:
            self._send_json({"error": "file_too_large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        self.send_response(HTTPStatus.OK)
        self._send_security_headers(api_response=False)
        content_type = mime_type or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type = f"{content_type}; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        self._log_response(HTTPStatus.OK, len(content))

    def _parse_log_limit(self, value: str | None) -> int:
        if value is None:
            return 100
        try:
            return int(value)
        except ValueError:
            return 100

    def _is_authorized_api_request(self, path: str) -> bool:
        if not path.startswith("/api/") or path == "/api/health" or self.api_token is None:
            return True
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return False
        supplied = authorization.removeprefix("Bearer ")
        return hmac.compare_digest(supplied.encode("utf-8"), self.api_token.encode("utf-8"))

    def _is_allowed_host_header(self) -> bool:
        raw_host = self.headers.get("Host", "")
        if not raw_host or len(raw_host) > 320 or any(character.isspace() for character in raw_host):
            return False
        try:
            parsed = urlsplit(f"//{raw_host}")
            if parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment:
                return False
            _ = parsed.port
            hostname = _normalize_allowed_host(parsed.hostname or "")
        except ValueError:
            return False
        return hostname in self.allowed_hosts

    def _send_misdirected_request(self) -> None:
        response = b'{"error":"host_not_allowed"}'
        self.send_response(HTTPStatus.MISDIRECTED_REQUEST)
        self._send_security_headers(api_response=True)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self._log_response(HTTPStatus.MISDIRECTED_REQUEST, len(response))

    def _send_unauthorized(self) -> None:
        response = b'{"error":"authentication_required"}'
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self._send_security_headers(api_response=True)
        self.send_header("WWW-Authenticate", "Bearer")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self._log_response(HTTPStatus.UNAUTHORIZED, len(response))

    def _send_security_headers(self, api_response: bool) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if api_response:
            self.send_header("Cache-Control", "no-store")
            return
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data: blob:",
        )

    def _log_request(self, method: str, path: str, **fields: object) -> None:
        if self.runtime_logger:
            self.runtime_logger.request(method, path, **fields)

    def _log_response(self, status: HTTPStatus | int, byte_count: int) -> None:
        if self.runtime_logger:
            self.runtime_logger.response(self.command, urlparse(self.path).path, int(status), byte_count)

    def _log_event(self, name: str, **fields: object) -> None:
        if self.runtime_logger:
            self.runtime_logger.event(name, **fields)


def run(
    host: str = "127.0.0.1",
    port: int = 8080,
    dev_mode: bool = False,
    compute_mode: str = "auto",
    allow_network: bool = False,
    max_workers: int = DEFAULT_MAX_WORKERS,
    allowed_hosts: str | None = None,
) -> None:
    normalized_host = host.strip().lower()
    network_bind = normalized_host not in LOOPBACK_BIND_HOSTS
    if not 1 <= port <= 65535:
        raise ValueError("port must be an integer from 1 to 65535")
    if not 1 <= max_workers <= 64:
        raise ValueError("max_workers must be an integer from 1 to 64")
    api_token = os.environ.get("SITH_API_TOKEN") or None
    if network_bind and not allow_network:
        raise ValueError("network binding requires --allow-network")
    if network_bind and (api_token is None or len(api_token) < 24):
        raise ValueError("network binding requires SITH_API_TOKEN with at least 24 characters")
    if api_token is not None and len(api_token) < 24:
        raise ValueError("SITH_API_TOKEN must contain at least 24 characters")
    configured_allowed_hosts = allowed_hosts if allowed_hosts is not None else os.environ.get("SITH_ALLOWED_HOSTS")
    host_allowlist = _parse_allowed_hosts(configured_allowed_hosts, network_bind)
    runtime_logger = RuntimeLogger(DATA_DIR / "logs", dev_mode=dev_mode)
    runtime = ModuleRuntime(ROOT_DIR / "config" / "module_registry.json", runtime_logger)
    try:
        runtime.startup()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        runtime_logger.event("module_runtime_registry_error", error_type=type(error).__name__)
        raise RuntimeError(f"Could not start module runtime: {error}") from error

    try:
        agent_snapshot = SignalDeskHandler.agent_coordinator.load()
        runtime_logger.event("agent_registry_loaded", active_agents=agent_snapshot["active_agents"])
    except (OSError, ValueError, json.JSONDecodeError) as error:
        runtime_logger.event("agent_registry_error", error_type=type(error).__name__)
        raise RuntimeError(f"Could not load agent registry: {error}") from error

    SignalDeskHandler.runtime_logger = runtime_logger
    SignalDeskHandler.runtime = runtime
    SignalDeskHandler.dev_mode = dev_mode
    SignalDeskHandler.compute_mode = compute_mode
    SignalDeskHandler.api_token = api_token
    SignalDeskHandler.allowed_hosts = host_allowlist
    server = BoundedThreadingHTTPServer((host, port), SignalDeskHandler, max_workers=max_workers)
    runtime_logger.event(
        "server_started",
        host=host,
        port=port,
        network_bind=network_bind,
        authenticated=api_token is not None,
        allowed_hosts=sorted(host_allowlist),
        max_workers=max_workers,
    )
    print(f"SithAssembly//Instawatch running on http://{host}:{port} ({'dev' if dev_mode else 'normal'} mode)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        runtime_logger.event("server_interrupt")
    finally:
        server.server_close()
        runtime_logger.event("server_stopped")
        runtime_logger.close()
