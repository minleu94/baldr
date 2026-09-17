"""Windows DPAPI-backed Promotion Authority trust secret.

The HMAC key is generated once, encrypted for the current Windows user, and
never serialized in plaintext.  Both the independent authority task and the
read-only promotion consumer may load the same key through this module without
placing it in source code, command-line arguments, status artifacts, or logs.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

import win32crypt  # type: ignore[import-untyped]


SECRET_SCHEMA_VERSION = "baldr-promotion-authority-secret.v1"
DEFAULT_ISSUER_ID = "baldr-local-promotion-authority-v1"
DEFAULT_CUSTODY_ID = "baldr-release-v4-promotion-custody"
_DPAPI_DESCRIPTION = "baldr ML promotion authority v1"
_DPAPI_FLAGS = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
_MINIMUM_KEY_BYTES = 32


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_hash(payload: object) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _require_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


@dataclass(frozen=True)
class PromotionAuthoritySecret:
    """Decrypted in-memory authority identity.

    ``signing_key`` must never be included in a DTO, log, exception, or
    persisted artifact.
    """

    issuer_id: str
    custody_id: str
    key_fingerprint: str
    signing_key: bytes

    def __post_init__(self) -> None:
        if len(self.signing_key) < _MINIMUM_KEY_BYTES:
            raise ValueError("promotion authority signing key is too short")
        expected = "sha256:" + hashlib.sha256(self.signing_key).hexdigest()
        if self.key_fingerprint != expected:
            raise ValueError("promotion authority key fingerprint mismatch")

    def public_descriptor(self) -> dict[str, str]:
        return {
            "schema_version": SECRET_SCHEMA_VERSION,
            "issuer_id": self.issuer_id,
            "custody_id": self.custody_id,
            "key_fingerprint": self.key_fingerprint,
            "protection": "windows_user_scope_dpapi",
        }


class PromotionAuthoritySecretStore:
    """Fail-closed DPAPI secret store with atomic first-run initialization."""

    def __init__(
        self,
        path: str | Path,
        *,
        issuer_id: str = DEFAULT_ISSUER_ID,
        custody_id: str = DEFAULT_CUSTODY_ID,
    ) -> None:
        self.path = Path(path)
        self.issuer_id = _require_text(issuer_id, label="issuer_id")
        self.custody_id = _require_text(custody_id, label="custody_id")

    def load_or_create(self) -> PromotionAuthoritySecret:
        if self.path.exists():
            return self.load()
        signing_key = secrets.token_bytes(_MINIMUM_KEY_BYTES)
        protected = win32crypt.CryptProtectData(
            signing_key,
            _DPAPI_DESCRIPTION,
            None,
            None,
            None,
            _DPAPI_FLAGS,
        )
        body: dict[str, object] = {
            "schema_version": SECRET_SCHEMA_VERSION,
            "issuer_id": self.issuer_id,
            "custody_id": self.custody_id,
            "key_fingerprint": (
                "sha256:" + hashlib.sha256(signing_key).hexdigest()
            ),
            "protection": "windows_user_scope_dpapi",
            "ciphertext_b64": base64.b64encode(protected).decode("ascii"),
        }
        payload = {**body, "store_hash": _payload_hash(body)}
        self._atomic_write(payload)
        return self.load()

    def load(self) -> PromotionAuthoritySecret:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("promotion authority secret store is unreadable") from exc
        payload = _require_mapping(raw, label="authority secret store")
        body = {
            key: value
            for key, value in payload.items()
            if key != "store_hash"
        }
        if payload.get("store_hash") != _payload_hash(body):
            raise ValueError("promotion authority secret store hash mismatch")
        if body.get("schema_version") != SECRET_SCHEMA_VERSION:
            raise ValueError("promotion authority secret schema is unsupported")
        issuer_id = _require_text(body.get("issuer_id"), label="issuer_id")
        custody_id = _require_text(body.get("custody_id"), label="custody_id")
        if issuer_id != self.issuer_id or custody_id != self.custody_id:
            raise ValueError("promotion authority identity mismatch")
        if body.get("protection") != "windows_user_scope_dpapi":
            raise ValueError("promotion authority protection mode mismatch")
        fingerprint = _require_text(
            body.get("key_fingerprint"),
            label="key_fingerprint",
        )
        ciphertext_text = _require_text(
            body.get("ciphertext_b64"),
            label="ciphertext_b64",
        )
        try:
            ciphertext = base64.b64decode(
                ciphertext_text,
                validate=True,
            )
            _description, signing_key = win32crypt.CryptUnprotectData(
                ciphertext,
                None,
                None,
                None,
                _DPAPI_FLAGS,
            )
        except Exception as exc:  # noqa: BLE001 - native DPAPI errors vary
            raise ValueError(
                "promotion authority DPAPI decryption failed"
            ) from exc
        return PromotionAuthoritySecret(
            issuer_id=issuer_id,
            custody_id=custody_id,
            key_fingerprint=fingerprint,
            signing_key=bytes(signing_key),
        )

    def _atomic_write(self, payload: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
