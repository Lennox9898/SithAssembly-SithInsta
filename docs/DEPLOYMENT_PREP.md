# Deployment Preparation

This folder prepares a production-shaped topology locally. It does not start containers, install packages, create accounts, migrate evidence, or enable a platform connector.

## Prepared topology

- `api`: compatibility container for the current application. Compose publishes it only to host loopback and the application requires an API token for its container network bind.
- `api-gpu`: optional GPU-OCR compatibility container. It is selected with the `gpu` Compose profile and mounts the same case data and model cache as the normal API profile.
- `worker`: placeholder for future explicit analysis jobs; it must be replaced by a tested queue consumer before activation.
- `postgres`: target relational database after an audited SQLite migration. It lives in the optional `deploy/compose.infrastructure.yml` extension.
- `object-storage`: target S3-compatible evidence store after a content-hash reconciliation. It lives in the optional infrastructure extension.
- `nats`: target durable event bus for agent job subjects. It lives in the optional infrastructure extension.

All infrastructure services are Compose profiles in `deploy/compose.infrastructure.yml` and require explicit image variables. Image tags are deliberately omitted: before use, set a reviewed immutable image digest in `deploy/.env.local`. Separating this extension prevents inactive infrastructure credentials from blocking the local API container.

## Container Boundary

- Code and non-secret configuration are copied into the image.
- The application runs as an unprivileged container user with all Linux capabilities dropped and `no-new-privileges` enabled for API profiles.
- Case database, evidence, logs, encrypted vaults, and agent reports live under `SITH_DATA_DIR` and are mounted at `/var/lib/sithassembly/data`.
- Hugging Face, PaddleX, and temporary model files live under `SITH_RUNTIME_DIR` and are mounted at `/var/lib/sithassembly/runtime`.
- `deploy/.env.example` maps these two paths to the local `data/` and `.runtime/` folders. `SITH_BIND_ADDRESS` defaults to `127.0.0.1`; use `0.0.0.0` only for a trusted private LAN with a scoped host-firewall rule. Keep `deploy/.env.local` out of version control.
- `SITH_API_TOKEN` is required for API containers and must be a randomly generated value of at least 24 characters stored outside version control.
- `SITH_ALLOWED_HOSTS` must list the exact DNS names or IP addresses clients place in the HTTP Host header. Do not use a wildcard.
- The `gpu` profile installs the pinned CUDA-enabled PyTorch pair and GlyphWatch runtime at image build time. It needs an NVIDIA-capable Linux Docker host with the NVIDIA Container Toolkit; it is not activated by default.

## Read-only preflight

```powershell
python SithAssembly.Deploy.py preflight
python app.py --deployment-preflight
```

The preflight only validates local files and reports whether the Docker CLI is found. It does not invoke Docker.

After Docker is installed, render the normal or GPU profile without starting services:

```powershell
docker compose --env-file deploy/.env.example -f deploy/compose.yml --profile compatibility config
docker compose --env-file deploy/.env.example -f deploy/compose.yml --profile gpu config
docker compose --env-file deploy/.env.local -f deploy/compose.yml -f deploy/compose.infrastructure.yml --profile infrastructure config
```

## Activation order

1. Pin and review every container image by digest.
2. Configure secret references outside the repository.
3. Build a PostgreSQL migration and reconcile source row counts, hashes and evidence IDs.
4. Test encrypted backup and restore before transferring production evidence.
5. Implement the worker as an idempotent JetStream consumer with an explicit review state.
6. Place the API behind private VPN or an authenticated TLS reverse proxy before any non-loopback exposure. A production ASGI stack can replace the compatibility server later if required.
7. Add per-user authentication, role and case authorization, edge rate limits, and centralized audit retention before offering access to multiple organizations.

Do not expose the current compatibility container publicly. No service here authorizes platform scraping, automated posting, account management, or identity assertions.
