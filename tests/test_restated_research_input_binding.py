from __future__ import annotations

import base64
from dataclasses import asdict, replace
import hashlib
import inspect
from pathlib import Path
import subprocess
import sys
from typing import Sequence, get_type_hints

import pytest

from artifact_contracts.restated_research_contract import (
    OFFICIAL_MARKET_CONTRACT_HASH as SHARED_OFFICIAL_MARKET_CONTRACT_HASH,
    RESTATED_RESEARCH_PROFILE as SHARED_RESTATED_RESEARCH_PROFILE,
    RestatedResearchInputBinding as SharedRestatedResearchInputBinding,
    _hash as shared_hash,
    hash_canonical_research_row_payloads,
    require_compatible_market_sources as shared_require_compatible_market_sources,
)
from ml_module.allocation_contracts import (
    PortfolioMLDatasetRow,
    post_freeze_shadow_decision_scope,
)
from ml_module.restated_research_input_contract import (
    OFFICIAL_MARKET_CONTRACT_HASH,
    RESTATED_RESEARCH_PROFILE,
    RestatedResearchInputBinding,
    require_compatible_market_sources,
    research_rows_hash,
)
from tests.test_ml_allocation_inference_service import _research_rows, _service
from tests.fixtures.ml_allocation_training_support import folds, samples, training_result  # noqa: F401


_NEW_IDENTITY = "sha256:" + "e" * 64


def _prepared():
    with post_freeze_shadow_decision_scope():
        rows = tuple(replace(row, dataset_identity_hash=_NEW_IDENTITY) for row in _research_rows())
    binding = RestatedResearchInputBinding(
        dataset_id="current-input-v2", dataset_identity_hash=_NEW_IDENTITY,
        dataset_manifest_file_hash="sha256:" + "f" * 64,
        feature_registry_hash=rows[0].feature_registry_hash,
        source_manifest_hashes=rows[0].source_manifest_hashes,
        ordered_features=tuple((feature.feature_id, feature.scale) for feature in rows[0].features),
        prepared_rows_hash=research_rows_hash(rows), captured_at=rows[0].decision_at,
    )
    return rows, binding


def _infer(service, rows, binding, *, research=True):
    return service.infer(
        rows=rows, model_id="allocator-v4-test", universe_id="test-current-universe",
        policy_id="balanced-v1", policy_hash="sha256:" + "d" * 64,
        allow_research_shadow=research, research_input_binding=binding,
    )


def test_binding_keeps_training_identity_and_actual_input_identity_separate(training_result) -> None:
    service = _service(training_result)
    service._artifact = replace(service._artifact, training_profile=RESTATED_RESEARCH_PROFILE)
    rows, binding = _prepared()
    result = _infer(service, rows, binding)
    audit = result.audit_payload()
    assert audit["dataset_identity_hash"] == training_result.dataset_identity_hash
    assert audit["research_input_binding"]["dataset_identity_hash"] == _NEW_IDENTITY
    assert audit["research_input_binding"]["prepared_rows_hash"] == research_rows_hash(rows)
    assert result.formal_oos_allowed is False
    assert result.production_action_allowed is False
    assert result.production_blend_alpha_bp == 0


@pytest.mark.parametrize("failure", ["legacy_profile", "formal_path", "changed_row", "wrong_order", "clock"])
def test_research_binding_does_not_relax_existing_or_prepared_input_guards(training_result, failure) -> None:
    service = _service(training_result)
    if failure != "legacy_profile":
        service._artifact = replace(service._artifact, training_profile=RESTATED_RESEARCH_PROFILE)
    rows, binding = _prepared()
    if failure == "changed_row":
        with post_freeze_shadow_decision_scope():
            changed = replace(rows[0].features[0], value_int=12345)
            rows = (replace(rows[0], features=(changed, *rows[0].features[1:])), *rows[1:])
    elif failure == "wrong_order":
        binding = replace(binding, ordered_features=tuple(reversed(binding.ordered_features)))
    elif failure == "clock":
        binding = replace(binding, captured_at="2027-01-04T19:00:00+08:00")
    with pytest.raises(ValueError):
        _infer(service, rows, binding, research=failure != "formal_path")


def test_binding_rejects_mutable_nested_contract() -> None:
    _rows, binding = _prepared()
    with pytest.raises(ValueError, match="immutable"):
        replace(binding, source_manifest_hashes=[list(pair) for pair in binding.source_manifest_hashes])


def test_direct_research_inference_enforces_official_market_compatibility(training_result):
    from ml_module.restated_research_input_contract import OFFICIAL_MARKET_CONTRACT_HASH

    service = _service(training_result)
    service._artifact = replace(
        service._artifact,
        training_profile=RESTATED_RESEARCH_PROFILE,
        source_manifest_hashes=tuple(sorted((
            *service._artifact.source_manifest_hashes,
            ("official.twse_market", "sha256:" + "1" * 64),
        ))),
    )
    rows, binding = _prepared()
    with pytest.raises(ValueError, match="official-market"):
        _infer(service, rows, binding)
    sources = tuple(sorted((
        *binding.source_manifest_hashes,
        ("official.twse_market", "sha256:" + "2" * 64),
        ("contract.official_twse_market", OFFICIAL_MARKET_CONTRACT_HASH),
    )))
    with post_freeze_shadow_decision_scope():
        rows = tuple(replace(row, source_manifest_hashes=sources) for row in rows)
    binding = replace(
        binding, source_manifest_hashes=sources, prepared_rows_hash=research_rows_hash(rows),
    )
    assert _infer(service, rows, binding).production_action_allowed is False


@pytest.mark.parametrize(
    ("training_sources", "current_sources", "must_reject"),
    [
        (
            (("source.other", "sha256:" + "1" * 64),),
            (("source.current", "sha256:" + "2" * 64),),
            False,
        ),
        (
            (("official.twse_market", "sha256:" + "1" * 64),),
            (
                ("official.twse_market", "sha256:" + "2" * 64),
                ("contract.official_twse_market", OFFICIAL_MARKET_CONTRACT_HASH),
            ),
            False,
        ),
        (
            (("official.twse_market", "sha256:" + "1" * 64),),
            (("official.twse_market", "sha256:" + "2" * 64),),
            True,
        ),
        (
            (("official.twse_market", "sha256:" + "1" * 64),),
            (
                ("official.twse_market", "sha256:" + "2" * 64),
                ("contract.official_twse_market", "sha256:" + "3" * 64),
            ),
            True,
        ),
    ],
)
def test_binding_compatibility_method_matches_legacy_helper(
    training_sources: tuple[tuple[str, str], ...],
    current_sources: tuple[tuple[str, str], ...],
    must_reject: bool,
) -> None:
    _rows, original_binding = _prepared()
    binding = replace(original_binding, source_manifest_hashes=current_sources)

    if must_reject:
        with pytest.raises(ValueError, match="official-market") as legacy_error:
            require_compatible_market_sources(training_sources, current_sources)
        with pytest.raises(ValueError, match="official-market") as binding_error:
            binding.require_compatible_training_sources(training_sources)
        assert str(binding_error.value) == str(legacy_error.value)
        return

    require_compatible_market_sources(training_sources, current_sources)
    binding.require_compatible_training_sources(training_sources)


def test_shared_owner_preserves_legacy_identity_metadata_and_row_hash_vector() -> None:
    from ml_module.restated_research_input_contract import _hash

    assert RestatedResearchInputBinding is SharedRestatedResearchInputBinding
    assert _hash is shared_hash
    assert require_compatible_market_sources is shared_require_compatible_market_sources
    assert RESTATED_RESEARCH_PROFILE == SHARED_RESTATED_RESEARCH_PROFILE
    assert OFFICIAL_MARKET_CONTRACT_HASH == SHARED_OFFICIAL_MARKET_CONTRACT_HASH
    assert RestatedResearchInputBinding.__module__ == (
        "ml_module.restated_research_input_contract"
    )
    assert RestatedResearchInputBinding.__qualname__ == "RestatedResearchInputBinding"
    assert str(inspect.signature(research_rows_hash)) == (
        "(rows: 'Sequence[PortfolioMLDatasetRow]') -> 'str'"
    )
    assert research_rows_hash.__module__ == "ml_module.restated_research_input_contract"
    assert research_rows_hash.__qualname__ == "research_rows_hash"
    assert get_type_hints(research_rows_hash) == {
        "rows": Sequence[PortfolioMLDatasetRow],
        "return": str,
    }

    expected_methods = {
        "__init__": "RestatedResearchInputBinding.__init__",
        "__repr__": "RestatedResearchInputBinding.__repr__",
        "__eq__": "RestatedResearchInputBinding.__eq__",
        "__hash__": "RestatedResearchInputBinding.__hash__",
        "__setattr__": "RestatedResearchInputBinding.__setattr__",
        "__delattr__": "RestatedResearchInputBinding.__delattr__",
        "__post_init__": "RestatedResearchInputBinding.__post_init__",
        "require_compatible_training_sources": (
            "RestatedResearchInputBinding.require_compatible_training_sources"
        ),
        "to_dict": "RestatedResearchInputBinding.to_dict",
    }
    for name, expected_qualname in expected_methods.items():
        method = getattr(RestatedResearchInputBinding, name)
        assert method.__module__ == "ml_module.restated_research_input_contract"
        assert method.__qualname__ == expected_qualname
    repr_function = RestatedResearchInputBinding.__repr__
    assert repr_function.__wrapped__.__module__ == (
        "ml_module.restated_research_input_contract"
    )
    assert repr_function.__wrapped__.__qualname__ == "__create_fn__.<locals>.__repr__"
    assert RestatedResearchInputBinding.binding_hash.fget.__module__ == (
        "ml_module.restated_research_input_contract"
    )
    assert RestatedResearchInputBinding.binding_hash.fget.__qualname__ == (
        "RestatedResearchInputBinding.binding_hash"
    )

    rows = _research_rows()
    expected_rows_hash = (
        "sha256:0d602ceef141814b3a4ef4830ce4c2a0c188bbecd83d996c3c52233d64c319c0"
    )
    assert research_rows_hash(rows) == expected_rows_hash
    assert research_rows_hash(tuple(reversed(rows))) == expected_rows_hash
    canonical_payloads = [
        asdict(row)
        for row in sorted(rows, key=lambda row: row.symbol)
    ]
    assert hash_canonical_research_row_payloads(canonical_payloads) == expected_rows_hash


def test_old_qualified_binding_pickle_and_joblib_bytes_load_in_fresh_processes(
    tmp_path: Path,
) -> None:
    # These bytes were captured before the owner move from a synthetic test
    # binding. They are not formal model or production artifacts.
    protocol4_base64 = (
        "gASV7AIAAAAAAACMKm1sX21vZHVsZS5yZXN0YXRlZF9yZXNlYXJjaF9pbnB1dF9jb250cmFjdJSMHFJlc3RhdGVkUmVzZWFyY2hJ"
        "bnB1dEJpbmRpbmeUk5QpgZR9lCiMCmRhdGFzZXRfaWSUjB1hYmktY3VzdG9keS1yZXN0YXRlZC1pbnB1dC12MZSMFWRhdGFzZXRf"
        "aWRlbnRpdHlfaGFzaJSMR3NoYTI1NjphYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFh"
        "YWFhYWFhYWFhYWFhlIwaZGF0YXNldF9tYW5pZmVzdF9maWxlX2hhc2iUjEdzaGEyNTY6YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJi"
        "YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYpSMFWZlYXR1cmVfcmVnaXN0cnlfaGFzaJSMR3NoYTI1Njph"
        "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhlIwWc291cmNlX21h"
        "bmlmZXN0X2hhc2hlc5SMDGRhaWx5X3ByaWNlc5SMR3NoYTI1NjpiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJi"
        "YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJilIaUhZSMEG9yZGVyZWRfZmVhdHVyZXOUjA1yZXR1cm5fMjBkX2JwlEsBhpSMDnZv"
        "bHVtZV9yYW5rX2JwlEsBhpSGlIwScHJlcGFyZWRfcm93c19oYXNolIxHc2hhMjU2OjBkNjAyY2VlZjE0MTgxNGIzYTRlZjQ4MzBj"
        "ZTRjMmEwYzE4OGJiZWNkODNkOTk2YzNjNTIyMzNkNjRjMzE5YzCUjAtjYXB0dXJlZF9hdJSMGTIwMjctMDEtMDRUMTg6MDA6MDAr"
        "MDg6MDCUdWIu"
    )
    protocol5_base64 = (
        "gAWV7AIAAAAAAACMKm1sX21vZHVsZS5yZXN0YXRlZF9yZXNlYXJjaF9pbnB1dF9jb250cmFjdJSMHFJlc3RhdGVkUmVzZWFyY2hJ"
        "bnB1dEJpbmRpbmeUk5QpgZR9lCiMCmRhdGFzZXRfaWSUjB1hYmktY3VzdG9keS1yZXN0YXRlZC1pbnB1dC12MZSMFWRhdGFzZXRf"
        "aWRlbnRpdHlfaGFzaJSMR3NoYTI1NjphYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFh"
        "YWFhYWFhYWFhYWFhlIwaZGF0YXNldF9tYW5pZmVzdF9maWxlX2hhc2iUjEdzaGEyNTY6YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJi"
        "YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYpSMFWZlYXR1cmVfcmVnaXN0cnlfaGFzaJSMR3NoYTI1Njph"
        "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhlIwWc291cmNlX21h"
        "bmlmZXN0X2hhc2hlc5SMDGRhaWx5X3ByaWNlc5SMR3NoYTI1NjpiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJi"
        "YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJilIaUhZSMEG9yZGVyZWRfZmVhdHVyZXOUjA1yZXR1cm5fMjBkX2JwlEsBhpSMDnZv"
        "bHVtZV9yYW5rX2JwlEsBhpSGlIwScHJlcGFyZWRfcm93c19oYXNolIxHc2hhMjU2OjBkNjAyY2VlZjE0MTgxNGIzYTRlZjQ4MzBj"
        "ZTRjMmEwYzE4OGJiZWNkODNkOTk2YzNjNTIyMzNkNjRjMzE5YzCUjAtjYXB0dXJlZF9hdJSMGTIwMjctMDEtMDRUMTg6MDA6MDAr"
        "MDg6MDCUdWIu"
    )
    protocol4 = base64.b64decode(protocol4_base64)
    protocol5 = base64.b64decode(protocol5_base64)
    assert hashlib.sha256(protocol4).hexdigest() == (
        "fd0fa50847cdf63dba118ea600e958073ae963bbe9d56e31e22a6825355a6309"
    )
    assert hashlib.sha256(protocol5).hexdigest() == (
        "1fd9c46bc4986810624ebaa9c684dabf0cb301ca7eaa065515a724b63ec0130d"
    )
    (tmp_path / "binding.protocol4.pickle").write_bytes(protocol4)
    (tmp_path / "binding.protocol5.pickle").write_bytes(protocol5)

    child = r"""
from __future__ import annotations

from io import BytesIO
import inspect
import joblib
import pickle
import sys
from pathlib import Path
from typing import Sequence, get_type_hints

from ml_module.allocation_contracts import PortfolioMLDatasetRow

if sys.argv[2] == "shared-first":
    from artifact_contracts.restated_research_contract import (
        OFFICIAL_MARKET_CONTRACT_HASH as SharedOfficial,
        RESTATED_RESEARCH_PROFILE as SharedProfile,
        RestatedResearchInputBinding as SharedBinding,
    )
    from ml_module.restated_research_input_contract import (
        OFFICIAL_MARKET_CONTRACT_HASH,
        RESTATED_RESEARCH_PROFILE,
        RestatedResearchInputBinding,
        research_rows_hash,
    )
else:
    from ml_module.restated_research_input_contract import (
        OFFICIAL_MARKET_CONTRACT_HASH,
        RESTATED_RESEARCH_PROFILE,
        RestatedResearchInputBinding,
        research_rows_hash,
    )
    from artifact_contracts.restated_research_contract import (
        OFFICIAL_MARKET_CONTRACT_HASH as SharedOfficial,
        RESTATED_RESEARCH_PROFILE as SharedProfile,
        RestatedResearchInputBinding as SharedBinding,
    )

assert RestatedResearchInputBinding is SharedBinding
assert OFFICIAL_MARKET_CONTRACT_HASH == SharedOfficial
assert RESTATED_RESEARCH_PROFILE == SharedProfile
assert RestatedResearchInputBinding.__module__ == (
    "ml_module.restated_research_input_contract"
)
assert research_rows_hash.__module__ == "ml_module.restated_research_input_contract"
assert str(inspect.signature(research_rows_hash)) == (
    "(rows: 'Sequence[PortfolioMLDatasetRow]') -> 'str'"
)
assert get_type_hints(research_rows_hash) == {
    "rows": Sequence[PortfolioMLDatasetRow],
    "return": str,
}

fixture_root = Path(sys.argv[1])
payload4 = (fixture_root / "binding.protocol4.pickle").read_bytes()
payload5 = (fixture_root / "binding.protocol5.pickle").read_bytes()
assert type(pickle.loads(payload4)) is RestatedResearchInputBinding
assert type(pickle.loads(payload5)) is RestatedResearchInputBinding
value = joblib.load(BytesIO(payload5))
assert type(value) is RestatedResearchInputBinding
assert value.binding_hash == (
    "sha256:bd23f0c7ef3a9837176264b6da85bbb25a63094c400e2cda00be58f04d705b4c"
)
assert len(value.to_dict()) == 14
assert pickle.dumps(value, protocol=4) == payload4
assert pickle.dumps(value, protocol=5) == payload5
stream = BytesIO()
joblib.dump(value, stream, compress=0, protocol=5)
assert stream.getvalue() == payload5
"""
    repo_root = Path(__file__).resolve().parents[1]
    for order in ("shared-first", "legacy-first"):
        result = subprocess.run(
            [sys.executable, "-c", child, str(tmp_path), order],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
