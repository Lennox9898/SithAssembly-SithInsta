# Private Hugging Face Model Bucket

## Purpose

`Lennox9898/sithassembly-model-store` is a private working mirror for approved model snapshots and non-sensitive model evaluation artifacts. It lets a separate Gradio Space or GPU test environment mount the same model inputs without mirroring the main GitHub project.

## Boundaries

- GitHub remains the source of truth for application code, configuration, tests, and documentation.
- The bucket contains only entries approved in `config/model_mirror_registry.json`.
- Case evidence, account credentials, local databases, vault files, agent reports, and general project files are excluded.
- Final released models should later be promoted to a dedicated model repository with a model card, license, evaluation report, and immutable version tag.

## Sync

Review `config/model_mirror_registry.json` before every upload. The helper is preview-only by default:

```powershell
.\tools\Sync-ModelBucket.ps1
```

Run the approved upload explicitly:

```powershell
.\tools\Sync-ModelBucket.ps1 -Apply
```

The helper only accepts paths inside `.runtime`, uploads only `mirror_enabled` entries, and excludes local Hugging Face cache metadata and Python bytecode.

## Gradio Model Lab

The future private Gradio Space should mount this bucket read-only at `/models` and load only the selected snapshot. The Space must keep all evidence handling disabled; it is for isolated model tests, benchmark images, and visual result inspection only.
