from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.assembly_manifest import public_manifest
from src.agent_coordination import AgentCoordinator, AgentReportJournal
from src.case_manager import CaseManager
from src.clawdbot_adapter import ClawdbotAdapter
from src.command_engine import CommandEngine
from src.module_runtime import ModuleRuntime
from src.local_llm import LocalLlmBridge, LocalModelRegistry
from src.report_generator import ReportGenerator
from src.repository import Repository
from src.runtime_logging import RuntimeLogger
from src.runtime_doctor import RuntimeDoctor
from src.deployment_preflight import DeploymentPreflight


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"


class SignalDeskHandler(BaseHTTPRequestHandler):
    repository = Repository()
    case_manager = CaseManager(repository)
    command_engine = CommandEngine(repository)
    report_generator = ReportGenerator()
    web_root = WEB_DIR
    runtime: ModuleRuntime | None = None
    runtime_logger: RuntimeLogger | None = None
    dev_mode = False
    agent_coordinator = AgentCoordinator(ROOT_DIR / "config" / "agent_registry.json")
    agent_journal = AgentReportJournal(ROOT_DIR / "data" / "agent_reports.jsonl")
    clawdbot_adapter = ClawdbotAdapter(ROOT_DIR / "config" / "clawdbot.local.json")
    local_model_registry = LocalModelRegistry(ROOT_DIR / "config" / "local_model_registry.json")
    local_llm_bridge = LocalLlmBridge(local_model_registry)
    runtime_doctor = RuntimeDoctor(ROOT_DIR)
    deployment_preflight = DeploymentPreflight(ROOT_DIR)
    compute_mode = "auto"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        self._log_request("GET", path, query_keys=sorted(query))

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
        self._log_request("POST", path)

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
                    bool(payload.get("confirm_model_download")),
                    str(payload.get("language", "en")),
                )
                self._send_json(result, status=HTTPStatus.CREATED)
                return

            case_vault_match = re.fullmatch(r"/api/cases/(\d+)/vault", path)
            if case_vault_match:
                if not bool(payload.get("confirm")):
                    self._send_json({"state": "confirmation_required", "message": "Passphrase is used once to create a local encrypted vault."})
                    return
                created = self.repository.create_evidence_vault(
                    int(case_vault_match.group(1)),
                    str(payload.get("passphrase", "")),
                    str(payload.get("operator", "local analyst")),
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
        except Exception as error:
            self._log_event("request_error", path=path, error_type=type(error).__name__)
            self._send_json({"error": "internal_error"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 12 * 1024 * 1024:
            raise ValueError("request body is limited to 12 MB")
        if length == 0:
            return {}
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        self._log_event("request_body_received", path=urlparse(self.path).path, byte_count=length, keys=sorted(payload))
        return payload

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self._log_response(status, len(response))

    def _send_bytes(self, payload: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
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
        if not str(resolved_target).startswith(str(resolved_root)):
            self._send_json({"error": "forbidden"}, status=HTTPStatus.FORBIDDEN)
            return
        if not resolved_target.exists() or not resolved_target.is_file():
            self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(resolved_target.name)
        content = resolved_target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
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

    def _log_request(self, method: str, path: str, **fields: object) -> None:
        if self.runtime_logger:
            self.runtime_logger.request(method, path, **fields)

    def _log_response(self, status: HTTPStatus | int, byte_count: int) -> None:
        if self.runtime_logger:
            self.runtime_logger.response(self.command, urlparse(self.path).path, int(status), byte_count)

    def _log_event(self, name: str, **fields: object) -> None:
        if self.runtime_logger:
            self.runtime_logger.event(name, **fields)


def run(host: str = "127.0.0.1", port: int = 8080, dev_mode: bool = False, compute_mode: str = "auto") -> None:
    runtime_logger = RuntimeLogger(ROOT_DIR / "data" / "logs", dev_mode=dev_mode)
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
    server = ThreadingHTTPServer((host, port), SignalDeskHandler)
    runtime_logger.event("server_started", host=host, port=port)
    print(f"SithAssembly//Instawatch running on http://{host}:{port} ({'dev' if dev_mode else 'normal'} mode)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        runtime_logger.event("server_interrupt")
    finally:
        server.server_close()
        runtime_logger.event("server_stopped")
        runtime_logger.close()
