# Local Agent Models

`config/local_model_registry.json` is the human-editable source for local LLM runtimes and model profiles. The server does not download a model or start a runtime. Set a provider to `enabled: true` only after its local server is running.

## Runtimes

| Runtime | Best first use | Local contract |
| --- | --- | --- |
| Ollama | Simple local setup and structured chat output | `POST /api/chat` at `127.0.0.1:11434` |
| llama.cpp | Local GGUF files, CPU/GPU inference and OpenAI-compatible endpoint | `POST /v1/chat/completions` |
| vLLM | Dedicated GPU serving and higher-throughput OpenAI-compatible deployment | `POST /v1/chat/completions` |

Ollama documents a local chat API and JSON-schema structured outputs. [Chat API](https://docs.ollama.com/api/chat), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs). llama.cpp documents `llama-server` with OpenAI-compatible chat, response and embedding routes. [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md). Qwen documents local serving through Transformers, llama.cpp, vLLM and other runtimes. [Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B).

## Local API

```text
GET  /api/llm/providers
POST /api/llm/generate
```

Request example:

```json
{
  "provider_id": "ollama-local",
  "model_profile": "qwen3-8b",
  "temperature": 0.2,
  "max_output_tokens": 900,
  "messages": [
    {"role": "system", "content": "Return the requested Qwen contract."},
    {"role": "user", "content": "Use the supplied evidence excerpts only."}
  ]
}
```

The normalized response always contains readable `content`, optional `thinking`, `usage`, selected provider/model and the configured response contract. For `qwen3-8b`, render the response through `docs/QWEN_OUTPUT.md` and validate evidence references before saving it as a draft.

## Add A Local Model

1. Add or edit a provider in `config/local_model_registry.json` with a loopback URL and set `enabled` only after its server is running.
2. Add a model profile with a provider-specific `runtime_models` name.
3. Call `GET /api/llm/providers` to confirm the configuration is visible.
4. Send one controlled request to `POST /api/llm/generate`.
5. Persist only the output, model profile, provider, usage and evidence references required by the selected contract; do not put tokens or raw secrets into messages or logs.

The bridge accepts only `127.0.0.1`, `localhost` and `::1` provider URLs. It disables environment proxies, rejects redirects, caps registry/request/response sizes, and exposes only allowlisted registry fields. It does not make cloud inference requests. These controls protect the bridge boundary; the selected local model runtime still needs its own access controls and resource limits.
