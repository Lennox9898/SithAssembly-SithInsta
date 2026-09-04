from __future__ import annotations

import argparse
import getpass

from src.repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="SithAssembly local EvidenceVault runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create a signed encrypted case vault")
    create.add_argument("--case-id", type=int, required=True)
    create.add_argument("--operator", default="local analyst")
    verify = commands.add_parser("verify", help="Verify an existing local vault signature")
    verify.add_argument("--vault-id", type=int, required=True)
    args = parser.parse_args()
    repository = Repository()

    if args.command == "create":
        passphrase = getpass.getpass("Vault passphrase: ")
        confirmation = getpass.getpass("Confirm passphrase: ")
        if passphrase != confirmation:
            raise SystemExit("Passphrases do not match.")
        result = repository.create_evidence_vault(args.case_id, passphrase, args.operator)
        print(f"Created {result['filename']} with {result['file_count']} files.")
        return

    result = repository.verify_evidence_vault(args.vault_id)
    print(f"Vault {result['id']}: {result['state']}")


if __name__ == "__main__":
    main()
