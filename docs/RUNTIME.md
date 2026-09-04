# Local Runtime

## Start

From the project folder, start the normal local server:

```powershell
.\RUN.bat
```

For detailed local development telemetry:

```powershell
.\DEV.bat
```

`RUN.bat dev` is equivalent. Both bind to `127.0.0.1:8080` by default, so the service is not exposed to the local network. The browser interface is available at `http://127.0.0.1:8080`.

For an alternate port or host, use the Python entry point directly:

```powershell
python app.py --dev --port 8090
python app.py --check-config
python app.py --print-capabilities
```

Only set `--host` to a non-loopback address after reviewing local network access.

`--compute-mode auto` is the default and only declares the intended compute policy in runtime status. `--compute-mode cpu` keeps the policy CPU-oriented. `--compute-mode cuda` refuses to start unless local PyTorch reports CUDA as available. None of these flags installs PyTorch, xFormers, FlashAttention, model weights, or starts a model runtime.

## Runtime Commands

With the server running, the terminal client can query runtime state, send an already allowlisted local command, or export the current log file:

```powershell
python SithAssembly.Runtime.py status
python SithAssembly.Runtime.py command "/context" --case-id 1
python SithAssembly.Runtime.py logs --limit 50
python SithAssembly.Runtime.py logs --export data\logs\runtime-export.jsonl
python SithAssembly.Runtime.py doctor
python SithAssembly.Runtime.py models
python SithAssembly.Runtime.py llm --provider ollama-local --profile qwen3-8b --prompt "Fasse diesen lokalen Befund zusammen."
```

The client calls the local HTTP API only. Commands still pass through `SithAssembly//CommandDeck`; it does not execute arbitrary shell commands.

`doctor` is read-only and reports configuration validity plus optional CUDA, xFormers and FlashAttention availability. `models` only shows the editable registry. `llm` sends one visible request only to a provider that has been explicitly enabled in `config/local_model_registry.json`; its normalized readable response is printed directly in the terminal.

## Logs

Normal mode writes `data/logs/instawatch.jsonl`. Dev mode writes `data/logs/instawatch.dev.jsonl` and includes every request, response, request size and payload field-name list. Files rotate at 5 MiB and retain four older files.

No raw request bodies, passphrases, tokens, passwords or base64 evidence content are logged. The log API is local:

```text
GET /api/logs?limit=100
GET /api/logs/export
GET /api/runtime
GET /api/diagnostics
```

## Module Registry

`config/module_registry.json` is the startup registry. Each module declares a `key`, `import_path` and `enabled` flag. The runtime accepts only explicitly declared `src.*` import paths, imports them at startup, and reports `loaded`, `disabled`, `missing` or `error` through `/api/runtime`.

An optional module can expose a zero-argument `runtime_probe()` function. The runtime invokes that probe after the allowed import and records its JSON-compatible result. It never installs packages, downloads model weights, scans arbitrary files or executes external commands.
