from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


MAGIC = "SITHASSEMBLY-EVIDENCE-VAULT"
VERSION = "1.0"
MAX_VAULT_FILES = 256
MAX_VAULT_INPUT_BYTES = 128 * 1024 * 1024
MAX_VAULT_PACKAGE_BYTES = 192 * 1024 * 1024
MAX_SIGNING_KEY_BYTES = 16 * 1024


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
        if not isinstance(passphrase, str) or not 16 <= len(passphrase) <= 1024:
            raise VaultError("vault passphrase must contain 16 to 1024 characters")
        if not isinstance(operator, str):
            raise VaultError("vault operator must be a string")
        operator = " ".join(operator.split()) or "local analyst"
        if len(operator) > 200:
            raise VaultError("vault operator must contain at most 200 characters")
        report_bytes = self._canonical_json(report)
        if len(report_bytes) > MAX_VAULT_INPUT_BYTES:
            raise VaultError("vault input is limited to 128 MB")
        files = {"case.json": report_bytes}
        input_size = len(report_bytes)
        for item in evidence_files:
            path = Path(item["path"])
            archive_name = self._safe_archive_name(str(item["archive_name"]))
            if path.exists() and path.is_file():
                if len(files) >= MAX_VAULT_FILES:
                    raise VaultError(f"vault input is limited to {MAX_VAULT_FILES} files")
                if archive_name in files:
                    raise VaultError("vault archive paths must be unique")
                size = path.stat().st_size
                if size < 0 or input_size + size > MAX_VAULT_INPUT_BYTES:
                    raise VaultError("vault input is limited to 128 MB")
                with path.open("rb") as handle:
                    content = handle.read(size + 1)
                if len(content) != size or input_size + len(content) > MAX_VAULT_INPUT_BYTES:
                    raise VaultError("vault evidence changed while it was being read")
                files[archive_name] = content
                input_size += len(content)

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
        filename = f"case-{case_id}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}.sifvault.json"
        output_path = self.output_dir / filename
        package = self._canonical_json(container)
        if len(package) > MAX_VAULT_PACKAGE_BYTES:
            raise VaultError("vault package is limited to 192 MB")
        self._write_private_file(output_path, package)
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
            container = json.loads(self.read_package(path).decode("utf-8"))
            header = container["header"]
            ciphertext = self._b64decode(container["ciphertext"])
            signature = self._b64decode(container["signature"])
            if header.get("magic") != MAGIC or header.get("version") != VERSION:
                raise VaultError("unsupported vault format")
            if header.get("encryption", {}).get("algorithm") != "AES-256-GCM":
                raise VaultError("unsupported vault encryption")
            if header.get("signature", {}).get("algorithm") != "Ed25519":
                raise VaultError("unsupported vault signature")
            if self._sha256(ciphertext) != header["integrity"]["ciphertext_sha256"]:
                raise VaultError("ciphertext hash mismatch")
            signing_key = self._load_existing_signing_key()
            trusted_public_key = self._public_key_bytes(signing_key)
            embedded_public_key = self._b64decode(header["signature"]["public_key"])
            if not hmac.compare_digest(embedded_public_key, trusted_public_key):
                raise VaultError("vault signing key is not trusted by this installation")
            signing_key.public_key().verify(signature, self._signing_payload(header, ciphertext))
        except (AttributeError, KeyError, TypeError, ValueError) as error:
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

    def read_package(self, path: Path) -> bytes:
        if not path.exists() or not path.is_file():
            raise VaultError("vault package is unavailable")
        size = path.stat().st_size
        if size < 0 or size > MAX_VAULT_PACKAGE_BYTES:
            raise VaultError("vault package is limited to 192 MB")
        with path.open("rb") as handle:
            package = handle.read(MAX_VAULT_PACKAGE_BYTES + 1)
        if len(package) != size:
            raise VaultError("vault package changed while it was being read")
        return package

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

    @staticmethod
    def _safe_archive_name(value: str) -> str:
        if not value or len(value) > 240 or "\\" in value or "\x00" in value:
            raise VaultError("vault archive path is invalid")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise VaultError("vault archive path is invalid")
        return path.as_posix()

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(passphrase.encode("utf-8"))

    def _load_or_create_signing_key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_path = self.key_dir / "sithassembly_ed25519_private.pem"
        if key_path.exists():
            if key_path.is_symlink():
                raise VaultError("vault signing key must not be a symbolic link")
            self._restrict_permissions(key_path, 0o600)
            return serialization.load_pem_private_key(self._read_signing_key(key_path), password=None)
        self.key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._restrict_permissions(self.key_dir, 0o700)
        key = Ed25519PrivateKey.generate()
        key_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        try:
            self._write_private_file(key_path, key_bytes)
        except FileExistsError:
            return self._load_existing_signing_key()
        return key

    def _load_existing_signing_key(self):
        from cryptography.hazmat.primitives import serialization

        key_path = self.key_dir / "sithassembly_ed25519_private.pem"
        if not key_path.exists() or not key_path.is_file() or key_path.is_symlink():
            raise VaultError("trusted vault signing key is unavailable")
        self._restrict_permissions(key_path, 0o600)
        return serialization.load_pem_private_key(self._read_signing_key(key_path), password=None)

    @staticmethod
    def _read_signing_key(path: Path) -> bytes:
        with path.open("rb") as handle:
            payload = handle.read(MAX_SIGNING_KEY_BYTES + 1)
        if not payload or len(payload) > MAX_SIGNING_KEY_BYTES:
            raise VaultError("trusted vault signing key is invalid")
        return payload

    @staticmethod
    def _write_private_file(path: Path, payload: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        EvidenceVault._restrict_permissions(path, 0o600)

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        try:
            os.chmod(path, mode)
        except OSError as error:
            if os.name != "nt":
                raise VaultError(f"could not restrict permissions for {path.name}") from error

    @staticmethod
    def _public_key(private_key: Any) -> str:
        return EvidenceVault._b64(EvidenceVault._public_key_bytes(private_key))

    @staticmethod
    def _public_key_bytes(private_key: Any) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
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
