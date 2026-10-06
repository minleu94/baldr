from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.promotion_authority_secret_store import (
    PromotionAuthoritySecretStore,
)


def test_dpapi_secret_round_trip_is_stable_and_never_plaintext(
    tmp_path: Path,
) -> None:
    path = tmp_path / "authority-secret.dpapi.json"
    store = PromotionAuthoritySecretStore(path)

    first = store.load_or_create()
    second = store.load_or_create()
    serialized = path.read_text(encoding="utf-8")

    assert first.signing_key == second.signing_key
    assert first.key_fingerprint == second.key_fingerprint
    assert first.public_descriptor()["protection"] == (
        "windows_user_scope_dpapi"
    )
    assert first.signing_key.hex() not in serialized
    assert "signing_key" not in serialized


def test_dpapi_secret_store_rejects_tamper(tmp_path: Path) -> None:
    path = tmp_path / "authority-secret.dpapi.json"
    store = PromotionAuthoritySecretStore(path)
    store.load_or_create()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["issuer_id"] = "attacker"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        store.load()


def test_dpapi_secret_store_rejects_wrong_identity(tmp_path: Path) -> None:
    path = tmp_path / "authority-secret.dpapi.json"
    PromotionAuthoritySecretStore(path).load_or_create()

    with pytest.raises(ValueError, match="identity mismatch"):
        PromotionAuthoritySecretStore(
            path,
            issuer_id="different-authority",
        ).load()
