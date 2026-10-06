from __future__ import annotations

import re

from data_module.ml_daily_price_revision_gate import (
    KNOWN_MODEL_SOURCE_REVISION_QUARANTINES,
)


def test_legacy_release_manifest_quarantine_pin_matches_reviewed_sha256() -> None:
    quarantine = KNOWN_MODEL_SOURCE_REVISION_QUARANTINES[
        "sha256:5c851d94b4a9385b30317b345ff084cdc47cdc165394e5463061272fbad67a52"
    ]

    assert quarantine["identity"] == (
        "repo:v4_ml_derived_h5_20260907_real/release_manifest.json"
    )
    assert quarantine["release_manifest_hash"] == (
        "sha256:b24e222352106fa91b389410e501a2c5589227eb792ba395463e5c948416482b"
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", quarantine["release_manifest_hash"])
