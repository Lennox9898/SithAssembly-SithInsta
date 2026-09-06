# Security Policy

## Supported Deployment Boundary

The supported default is local loopback operation. A non-loopback bind requires both `--allow-network` and a `SITH_API_TOKEN` value of at least 24 characters. In that mode, every API route except the minimal health endpoint requires a Bearer token.

For any deployment beyond loopback, place the service behind authenticated TLS or a private VPN. The built-in token is a narrow transport guard, not a replacement for user identity, authorization roles, audit policy, rate limiting at the edge, or TLS termination.

## Handling Sensitive Data

- Do not commit tokens, passwords, session cookies, private keys, case evidence, local databases, logs, or vault material.
- Keep deployment secrets in environment variables or an external secret manager.
- Do not send sensitive case content to issue trackers, public chat, or unreviewed third-party services.
- The private Hugging Face model bucket contains approved model artifacts only, never case data or credentials.

## Reporting a Vulnerability

Do not open a public issue with exploit details or sensitive data. Contact the repository owner privately with a concise description, affected version or commit, reproduction conditions, and suggested impact. Allow time for triage before public disclosure.
