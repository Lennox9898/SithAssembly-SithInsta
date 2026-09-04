from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AssemblyModule:
    key: str
    codename: str
    model_profile: str
    role: str
    mode: str


MODULES = (
    AssemblyModule("collector", "SithAssembly//VektorZero", "VektorZero.ParseCore/1.0", "Capture normalization and signal extraction", "local deterministic"),
    AssemblyModule("profile_resolver", "SithAssembly//MirrorFace", "MirrorFace.ProfileTrace/1.0", "Profile snapshots and documented changes", "evidence-bound"),
    AssemblyModule("identity_resolver", "SithAssembly//NullMask", "NullMask.HypothesisGate/1.0", "Analyst-entered identity hypotheses", "manual review"),
    AssemblyModule("relationship_engine", "SithAssembly//SpectreNet", "SpectreNet.LinkMesh/1.0", "Mentions, links, and pattern candidates", "evidence-bound"),
    AssemblyModule("timeline_engine", "SithAssembly//ChronoWatch", "ChronoWatch.Sequence/1.0", "Chronology and activity comparison", "local deterministic"),
    AssemblyModule("graph_viewer", "SithAssembly//GhostCluster", "GhostCluster.Topology/1.0", "Graph groups, paths, and centrality", "local deterministic"),
    AssemblyModule("case_manager", "SithAssembly//CaseForge", "CaseForge.Workbench/1.0", "Case structure, notes, and review flow", "local SQLite"),
    AssemblyModule("evidence_integrity", "SithAssembly//CipherLedger", "CipherLedger.Fingerprint/1.0", "Evidence fingerprints and integrity checks", "local SHA-256"),
    AssemblyModule("case_importer", "SithAssembly//Portcullis", "Portcullis.ImportGate/1.0", "Validated JSON import boundary", "local validation"),
    AssemblyModule("report_generator", "SithAssembly//BlackArchive", "BlackArchive.ReportCore/1.0", "Case exports and reports", "local export"),
    AssemblyModule("command_engine", "SithAssembly//CommandDeck", "CommandDeck.Allowlist/1.0", "Allowlisted local command execution", "local only"),
    AssemblyModule("agent_controller", "SithAssembly//AssemblyCore", "AssemblyCore.Telemetry/1.0", "Visible processing orchestration", "human-in-the-loop"),
    AssemblyModule("agent_coordination", "SithAssembly//Conclave", "Conclave.Protocol/1.0", "Capability registry and topic routing", "local deterministic"),
    AssemblyModule("clawdbot_adapter", "SithAssembly//ClawBridge", "ClawBridge.OpenClaw/0.1", "Prepared Clawdbot/OpenClaw gateway bridge", "disabled by default"),
    AssemblyModule("local_llm", "SithAssembly//MindForge", "MindForge.LocalLLM/0.1", "Local LLM provider and response bridge", "opt-in loopback"),
    AssemblyModule("runtime_doctor", "SithAssembly//ForgeProbe", "ForgeProbe.Runtime/0.1", "Read-only configuration and compute diagnostics", "local inspection"),
    AssemblyModule("deployment_preflight", "SithAssembly//Citadel", "Citadel.DeployPrep/0.1", "Read-only production topology preparation", "activation gated"),
    AssemblyModule("comment_anomaly", "SithAssembly//SignalForge", "SignalForge.ECOD/1.0", "Comment feature outlier review candidates", "local optional model"),
    AssemblyModule("ocr_engine", "SithAssembly//GlyphWatch", "GlyphWatch.PP-OCRv6/1.0", "OCR for explicit local image evidence", "local optional model"),
    AssemblyModule("evidence_vault", "SithAssembly//EvidenceVault", "EvidenceVault.SIF/1.0", "Signed and encrypted local evidence packages", "local opt-in"),
)

_BY_KEY = {module.key: module for module in MODULES}


def module_name(key: str) -> str:
    return _BY_KEY[key].codename


def public_manifest() -> list[dict[str, str]]:
    return [asdict(module) for module in MODULES]
