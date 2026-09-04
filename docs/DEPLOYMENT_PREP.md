# Deployment Preparation

This folder prepares a production-shaped topology locally. It does not start containers, install packages, create accounts, migrate evidence, or enable a platform connector.

## Prepared topology

- `api`: compatibility container for the current local application. It is loopback-bound and is not a production HTTP stack yet.
- `worker`: placeholder for future explicit analysis jobs; it must be replaced by a tested queue consumer before activation.
- `postgres`: target relational database after an audited SQLite migration.
- `object-storage`: target S3-compatible evidence store after a content-hash reconciliation.
- `nats`: target durable event bus for agent job subjects.

All infrastructure services are Compose profiles and require explicit image variables. Image tags are deliberately omitted: before use, set a reviewed immutable image digest in `deploy/.env.local`.

## Read-only preflight

```powershell
python SithAssembly.Deploy.py preflight
python app.py --deployment-preflight
```

The preflight only validates local files and reports whether the Docker CLI is found. It does not invoke Docker.

## Activation order

1. Pin and review every container image by digest.
2. Configure secret references outside the repository.
3. Build a PostgreSQL migration and reconcile source row counts, hashes and evidence IDs.
4. Test encrypted backup and restore before transferring production evidence.
5. Implement the worker as an idempotent JetStream consumer with an explicit review state.
6. Replace the compatibility API container with FastAPI/Uvicorn and place it behind private VPN or authenticated TLS reverse proxy.

Do not expose the current compatibility container publicly. No service here authorizes platform scraping, automated posting, account management, or identity assertions.
