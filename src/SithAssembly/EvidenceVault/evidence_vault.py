from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAGIC = "SITHASSEMBLY-EVIDENCE-VAULT"
VERSION = "1.0"


class VaultError(ValueError):
    pass


class EvidenceVault:
    """Creates signed, encrypted local case packages from existing evidence only."""

    def __init__(self, output_dir: Path, key_dir: Path) -> None:
        self.output_dir = output_dir
        self.key_dir = key_dir

    def status(self) -> dict[str, str]:
        try:
            import cryptography  # noqa: F401
        except ImportError:
            return {"module": "SithAssembly//EvidenceVault", "state": "not_installed", "dependency": "cryptography"}
        return {"module": "SithAssembly//EvidenceVault", "state": "available", "dependency": "cryptography"}

    def create(
        self,
        case_id: int,
        report: dict[str, Any],
        evidence_files: list[dict[str, Any]],
        passphrase: str,
        operator: str,
    ) -> dict[str, Any]:
        self._require_runtime()
        if len(passphrase) < 16:
            raise VaultError("vault passphrase must contain at least 16 characters")
        operator = " ".join(operator.split()) or "local analyst"
        files = {"case.json": self._canonical_json(report)}
        for item in evidence_files:
            path = Path(item["path"])
            archive_name = str(item["archive_name"])
            if path.exists() and path.is_file():
                files[archive_name] = path.read_bytes()

        manifest = self._manifest(case_id, operator, files)
        plaintext = self._zip_payload(files, manifest)
        salt = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        key = self._derive_key(passphrase, salt)
        aad = self._canonical_json({"magic": MAGIC, "version": VERSION, "case_id": case_id})

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
        signing_key = self._load_or_create_signing_key()
        header = {
            "magic": MAGIC,
            "version": VERSION,
            "case_id": case_id,
            "operator": operator,
            "created_at": self._timestamp(),
            "encryption": {
                "algorithm": "AES-256-GCM",
                "kdf": {"name": "scrypt", "n": 32768, "r": 8, "p": 1, "length": 32},
                "salt": self._b64(salt),
                "nonce": self._b64(nonce),
                "aad": self._b64(aad),
            },
            "integrity": {
                "manifest_sha256": self._sha256(self._canonical_json(manifest)),
                "plaintext_sha256": self._sha256(plaintext),
                "ciphertext_sha256": self._sha256(ciphertext),
            },
            "signature": {"algorithm": "Ed25519", "public_key": self._public_key(signing_key)},
        }
        signature = signing_key.sign(self._signing_payload(header, ciphertext))
        container = {"header": header, "signature": self._b64(signature), "ciphertext": self._b64(ciphertext)}

        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"case-{case_id}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.sifvault.json"
        output_path = self.output_dir / filename
        output_path.write_bytes(self._canonical_json(container))
        return {
            "path": output_path,
            "filename": filename,
            "manifest": manifest,
            "ciphertext_sha256": header["integrity"]["ciphertext_sha256"],
            "file_count": len(manifest["files"]),
        }

    def verify(self, path: Path) -> dict[str, Any]:
        self._require_runtime()
        if not path.exists() or not path.is_file():
            raise VaultError("vault package is unavailable")
        try:
            container = json.loads(path.read_text(encoding="utf-8"))
            header = container["header"]
            ciphertext = self._b64decode(container["ciphertext"])
            signature = self._b64decode(container["signature"])
            if header.get("magic") != MAGIC:
                raise VaultError("unsupported vault format")
            if self._sha256(ciphertext) != header["integrity"]["ciphertext_sha256"]:
                raise VaultError("ciphertext hash mismatch")
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = Ed25519PublicKey.from_public_bytes(self._b64decode(header["signature"]["public_key"]))
            public_key.verify(signature, self._signing_payload(header, ciphertext))
        except (KeyError, TypeError, ValueError) as error:
            raise VaultError("invalid vault package") from error
        except Exception as error:
            if error.__class__.__name__ == "InvalidSignature":
                raise VaultError("vault signature verification failed") from error
            raise
        return {
            "state": "valid",
            "case_id": header["case_id"],
            "created_at": header["created_at"],
            "ciphertext_sha256": header["integrity"]["ciphertext_sha256"],
        }

    def _manifest(self, case_id: int, operator: str, files: dict[str, bytes]) -> dict[str, Any]:
        entries = [
            {"path": name, "size_bytes": len(payload), "sha256": self._sha256(payload)}
            for name, payload in sorted(files.items())
        ]
        return {
            "magic": MAGIC,
            "version": VERSION,
            "case_id": case_id,
            "operator": operator,
            "created_at": self._timestamp(),
            "files": entries,
            "chain_of_custody": [{"at": self._timestamp(), "actor": operator, "action": "vault_created"}],
            "notice": "Cryptographic integrity does not establish legal admissibility. Review collection, access, and process separately.",
        }

    def _zip_payload(self, files: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", self._canonical_json(manifest))
            for name, payload in sorted(files.items()):
                archive.writestr(name, payload)
        return output.getvalue()

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(passphrase.encode("utf-8"))

    def _load_or_create_signing_key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_path = self.key_dir / "sithassembly_ed25519_private.pem"
        if key_path.exists():
            return serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        self.key_dir.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return key

    @staticmethod
    def _public_key(private_key: Any) -> str:
        from cryptography.hazmat.primitives import serialization

        return EvidenceVault._b64(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )

    @staticmethod
    def _signing_payload(header: dict[str, Any], ciphertext: bytes) -> bytes:
        return EvidenceVault._canonical_json(header) + b"\n" + EvidenceVault._sha256(ciphertext).encode("ascii")

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _sha256(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        return base64.b64decode(value.encode("ascii"), validate=True)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _require_runtime() -> None:
        try:
            import cryptography  # noqa: F401
        except ImportError as error:
            raise VaultError("cryptography is required for EvidenceVault") from error
