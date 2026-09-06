# SithAssembly Module Runtime

The project runtime remains `app.py` with the local HTTP server. `src/assembly_manifest.py` is the central machine-readable registry of the available modules and profiles.

Names adopted from the attached runtime concept map to existing components:

- `VantaIndex` maps to the local evidence registry and `EvidenceIntegrity`.
- `BlackSignal` maps to the text heuristic, while `SignalForge` provides separate comment-outlier review.
- `GhostCluster`, `ShadowGraph`, `Traceborne`, and `SpectreReport` map to graph, timeline, and report components.
- `SpectreNet.Identity` remains a manual hypothesis and review module, not automated person identification.
- `EvidenceVault` is active for signed and encrypted local export packages with manifests.

Automatic platform capture, account creation, posting, direct messages, external notifications, face or person identification, and blanket bot determinations are not implemented or enabled.

Every executed component must return evidence references, warnings, and a review state, or skip processing. A score or model response is not a factual claim.
