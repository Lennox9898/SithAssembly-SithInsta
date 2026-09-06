# Contributing

Contributions are welcome for review through GitHub issues and pull requests.
Keep changes focused, document security-sensitive behavior, and include tests
for behavioral changes where practical.

## Contribution terms

By intentionally submitting a contribution to this repository, you certify
that you have the right to submit it and agree that:

1. The contribution is submitted under GNU AGPL v3.0 only and may be used and
   distributed as part of this project under those terms.
2. You retain ownership of your contribution and attribution remains intact.
3. The contribution is provided without warranty unless separately agreed in
   writing.

Add the following certification to every commit:

```text
Signed-off-by: Your Name <your.email@example.com>
```

The sign-off confirms that you accept these contribution terms. Maintainers
may decline a contribution that does not include it.

## Before opening a pull request

- Run `python -m unittest discover -s tests`.
- Do not commit credentials, evidence, databases, logs, private keys, model
  caches, or account configuration.
- Explain the purpose, operational impact, and tests performed.
- Call out new network access, subprocess execution, authentication, storage,
  or model downloads explicitly.
