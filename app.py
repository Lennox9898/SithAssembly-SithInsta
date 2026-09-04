from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.server import run
from src.runtime_doctor import RuntimeDoctor


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SithAssembly//Instawatch locally")
    parser.add_argument("--host", default="127.0.0.1", help="bind address; defaults to local-only")
    parser.add_argument("--port", type=int, default=8080, help="local port")
    parser.add_argument("--dev", action="store_true", help="write detailed local runtime logs")
    parser.add_argument("--compute-mode", choices=("cpu", "auto", "cuda"), default="auto", help="declare the intended local model compute mode; never installs packages")
    parser.add_argument("--check-config", action="store_true", help="validate local registries and exit without starting the server")
    parser.add_argument("--print-capabilities", action="store_true", help="print local AI acceleration and configuration diagnostics, then exit")
    parser.add_argument("--deployment-preflight", action="store_true", help="validate prepared deployment files and exit without starting services")
    options = parser.parse_args()
    doctor = RuntimeDoctor(Path(__file__).resolve().parent)
    if options.deployment_preflight:
        from src.deployment_preflight import DeploymentPreflight

        report = DeploymentPreflight(Path(__file__).resolve().parent).snapshot()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["readiness"] == "prepared" else 1
    if options.check_config or options.print_capabilities:
        report = doctor.snapshot(options.compute_mode)
        if options.check_config and not options.print_capabilities:
            report = report["configuration"]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("state", "ok") == "ok" else 1
    if options.compute_mode == "cuda" and not doctor.snapshot("cuda")["acceleration"]["cuda_available"]:
        parser.error("--compute-mode cuda requires an available local CUDA runtime; use --print-capabilities to inspect it")
    run(host=options.host, port=options.port, dev_mode=options.dev, compute_mode=options.compute_mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
