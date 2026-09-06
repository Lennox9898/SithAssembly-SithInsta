# Security Policy

## Supported Deployment Boundary

The supported default is local loopback operation. A non-loopback bind requires `--allow-network`, a `SITH_API_TOKEN` value of at least 24 characters, and an explicit `SITH_ALLOWED_HOSTS` or `--allowed-hosts` allowlist. In that mode, every API route except the minimal health endpoint requires a Bearer token. Setting `SITH_API_TOKEN` also protects API routes on loopback.

For any deployment beyond loopback, place the service behind authenticated TLS or a private VPN. The built-in token is a narrow transport guard, not a replacement for user identity, authorization roles, audit policy, rate limiting at the edge, or TLS termination.

The compatibility HTTP server rejects unlisted Host headers, chunked request bodies, oversized requests, unsafe static paths, and excess concurrent connections. Local LLM and CLI requests accept HTTP loopback targets only, disable environment proxies, reject redirects, and cap request and response sizes. These controls do not make the compatibility server suitable for direct public exposure.

## Handling Sensitive Data

- Do not commit tokens, passwords, session cookies, private keys, case evidence, local databases, logs, or vault material.
- Keep deployment secrets in environment variables or an external secret manager.
- Keep `config/instagram_accounts.local.json` local and untracked. Start from `config/instagram_accounts.example.json` and store environment-variable references rather than passwords.
- Do not send sensitive case content to issue trackers, public chat, or unreviewed third-party services.
- The private Hugging Face model bucket contains approved model artifacts only, never case data or credentials.
- Back up `data/vault_keys/` separately from encrypted vault packages and protect it with host encryption and access controls. Vault verification trusts this installation key; replacing or losing it changes or removes that trust anchor.

## Reporting a Vulnerability

Do not open a public issue with exploit details or sensitive data. Contact the repository owner privately with a concise description, affected version or commit, reproduction conditions, and suggested impact. Allow time for triage before public disclosure.
