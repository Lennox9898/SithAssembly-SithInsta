# SithAssembly//SithInsta 

It is the Instagram Guardian for protecting vulnerable groups and keeping an eye on suspects.

it is Running on SithAssembly Framework , Allowing easy to use changeable Modules in dynamic use Cases,
SithAssembly will can be used with multiple languages and Finally Fine-Tuned in Assembly code ,

SithAssembly will be the effort to Connect AI with ASM and even Bytecode. 

 # The current repository only holds Python 
 # and for future Updates also Rust.

- `src/report_generator.py`: JSON and local PDF reports.
- `src/agent_controller.py`: visible processing stages.
- `src/job_queue.py`: persistent, registry-routed local job ledger with idempotency and event envelopes.
- `src/job_worker.py`: explicit local worker for registered OCR and depth jobs.
- `src/command_engine.py`: allowlisted slash commands for local cases.
- `src/case_importer.py`: validation for manual and officially exported JSON data.
- `src/evidence_integrity.py`: local content and context fingerprints.
- `src/pattern_engine.py`: evidence-bound candidates for accounts, hashtags, domains, and repeated text.
- `src/analyzer.py`: risk signals and basic classification.
- `src/drafter.py`: concise, source-bound response drafts.
- `src/server.py`: HTTP API and static file delivery.
- `src/module_runtime.py`: explicit JSON registry and controlled module startup hooks.
- `src/runtime_logging.py`: local JSONL runtime logs with sensitive-field redaction.
- `config/module_registry.json`: the allowed `src.*` modules loaded at startup.
- `web/`: local casework interface.

## Import and Patterns

The import surface accepts a JSON list with required `handle` and `body` fields and optional metadata including `platform`, `source_url`, `captured_at`, and `sources`. Every entry is validated and fingerprinted locally before storage.

The Pattern Engine only presents candidates based on case evidence: recurring accounts, shared hashtags or domains, identical normalized text, and central nodes. Every finding links to the underlying observation. A general-purpose server will be integrated later.

## Optional Analysis Models

`SithAssembly//SignalForge` uses PyOD ECOD for local comment-outlier candidates when the optional dependency is installed. `SithAssembly//GlyphWatch` uses PaddleOCR 3 / PP-OCRv6 for explicitly uploaded local image evidence. Both are opt-in: there is no automatic package installation, silent model download, or external content retrieval. See `docs/MODEL_INTEGRATIONS.md` for selection, setup, and limits.

The planned Qwen output separates visible evidence-bound facts from a readable model assessment with confidence and uncertainty. The contract is in `docs/QWEN_OUTPUT.md` and `config/qwen_response_contract.json`.

Local agent models can be connected through Ollama, llama.cpp, or vLLM. The editable provider registry, local LLM API contract, and startup sequence are in `docs/LOCAL_MODELS.md`.

`python app.py --check-config` validates all local registries without starting a server. `python app.py --print-capabilities` and `python SithAssembly.Runtime.py doctor` report whether CUDA and optional accelerators such as xFormers or FlashAttention are present. These diagnostics install and enable nothing automatically.

The Conclave job ledger exposes persistent local job state and event trails for approved registry topics. It does not execute work on its own; see `docs/JOB_QUEUE.md` for the lifecycle and local API.

## Server Preparation

`deploy/` contains an inactive Compose topology for PostgreSQL, S3-compatible evidence storage, NATS JetStream, and separate API and worker roles. `python SithAssembly.Deploy.py preflight` checks preparation without starting Docker. The activation sequence is in `docs/DEPLOYMENT_PREP.md`.

The external agent-stack dossier is stored unchanged at `docs/Agentenstack_Evaluationsdossier_2026-09-04.pdf`. Its derived current-state review, scorecard, and bounded PoC sequence are in `docs/architecture/`; they do not automatically add third-party components.

## EvidenceVault

`SithAssembly//EvidenceVault` creates an opt-in `.sifvault.json` package for an existing case with a ZIP payload, SHA-256 manifest, AES-256-GCM encryption, scrypt key derivation, and Ed25519 signature. The passphrase is used only during package creation and is not persisted. The UI export is opt-in; alternatively run `python SIF_EvidenceVault.py create --case-id <id>`. See `docs/MODULE_RUNTIME.md` and `docs/IMPORTANT_DISCLAIMER.md`.

## Command Console

The interface console executes a local, restricted subset of the stored command catalog. Examples:

```text
/find posts --query "term" --limit 20
/profile connections @account
/graph path @account_a @account_b --max-hops 4
/timeline build
/report generate --format pdf
```

The complete locally available list is in `docs/COMMANDS.md`. `docs/Command-Katalog_Network-Intelligence.pdf` remains an unchanged reference. Platform capture, crawling, watches, alerts, sharing, external communication, and identity consolidation are not enabled.

## Using the Interface

1. Start with `python app.py` and open `http://127.0.0.1:8080`.
2. Create a case or use the local inbox.
3. Record an observation with its source URL and timestamp.
4. Use the timeline, graph, and profile view. Graph edges link to their source URL and display time.
5. Add notes, screenshot references, and clearly marked unconfirmed hypotheses only with evidence.
6. Export the case from the header as JSON or PDF.
