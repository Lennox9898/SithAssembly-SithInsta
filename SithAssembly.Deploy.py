from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.deployment_preflight import DeploymentPreflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SithAssembly deployment preparation client")
    parser.add_argument("action", choices=("preflight",), help="preflight validates local deployment files only")
    options = parser.parse_args()
    report = DeploymentPreflight(Path(__file__).resolve().parent).snapshot()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["readiness"] == "prepared" else 1


if __name__ == "__main__":
    raise SystemExit(main())
