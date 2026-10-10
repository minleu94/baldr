"""純合成 SQLite 測試：不讀取正式帳本、D 資料或排程。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from app_module.paper_portfolio_snapshot_repository import (
    PAPER_SNAPSHOT_RECEIPT_MAX_BYTES,
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotReceipt,
    PaperPortfolioSnapshotRepository,
)
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.personal_store_routes import (
    PersonalStoreDomain,
    PersonalStoreMode,
    StoreIdentity,
    select_personal_store_route,
)


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _binding(seed: str) -> tuple[str, str]:
    binding_sha256 = _digest(seed.encode("ascii"))
    namespace = "acct-" + binding_sha256.removeprefix("sha256:")
    return namespace, binding_sha256


def _snapshot(
    *,
    snapshot_id: str = "acct-seed-20261001",
    portfolio_id: str | None = None,
    decision_date: str = "2026-10-01",
    source_result_id: str = "strategy-run-1",
) -> PaperPortfolioSnapshot:
    return PaperPortfolioSnapshot(
        snapshot_id=snapshot_id,
        portfolio_id=portfolio_id or _binding("account-a")[0],
        decision_date=decision_date,
        source_result_id=source_result_id,
        cash=Decimal("200000.00"),
        total_value=Decimal("500000.00"),
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=300,
                mark_price=Decimal("1000.00"),
                market_value=Decimal("300000.00"),
                weight_bp=6000,
            ),
        ),
    )


def _seed_receipt(
    snapshot: PaperPortfolioSnapshot,
) -> PaperPortfolioSnapshotReceipt:
    namespace, binding_sha256 = _binding("account-a")
    return PaperPortfolioSnapshotReceipt.seed_reference_for(
        snapshot,
        account_namespace=namespace,
        binding_sha256=binding_sha256,
        seed_source_id="synthetic:seed-v1",
        seed_source_sha256=_digest(b"synthetic seed bytes"),
    )


def _snapshot_with_position(
    position: PaperPortfolioPositionSnapshot,
    *,
    cash: Decimal | None = None,
) -> PaperPortfolioSnapshot:
    base = _snapshot()
    return PaperPortfolioSnapshot(
        snapshot_id=base.snapshot_id,
        portfolio_id=base.portfolio_id,
        decision_date=base.decision_date,
        source_result_id=base.source_result_id,
        cash=cash if cash is not None else base.total_value - position.market_value,
        total_value=base.total_value,
        positions=(position,),
    )


def _account_repository(
    tmp_path: Path, namespace: str
) -> tuple[PaperPortfolioSnapshotRepository, PersonalPaperStorePaths]:
    market_root = tmp_path / "market"
    personal_paths = PersonalDataPaths(
        market_root=market_root,
        legacy_output_root=tmp_path / "legacy-output",
        personal_root=market_root / "personal",
    )
    route = select_personal_store_route(
        domain=PersonalStoreDomain.PAPER,
        mode=PersonalStoreMode.PERSONAL,
        identity=StoreIdentity(namespace),
        personal_paths=personal_paths,
        paper_account_namespace=namespace,
    )
    paths = PersonalPaperStorePaths.from_route(route, portfolio_id=namespace)
    repository = PaperPortfolioSnapshotRepository(
        paths.state_db,
        route=route,
        portfolio_id=namespace,
        personal_paths=personal_paths,
    )
    return repository, paths


def test_unknown_and_seed_reference_roundtrip_are_immutable() -> None:
    snapshot = _snapshot()
    namespace, binding_sha256 = _binding("account-a")
    unknown = PaperPortfolioSnapshotReceipt.unknown_for(
        snapshot,
        reason="historical_seed_basis_unverified",
        account_namespace=namespace,
        binding_sha256=binding_sha256,
    )
    seed = _seed_receipt(snapshot)

    assert PaperPortfolioSnapshotReceipt.from_json(unknown.to_json()) == unknown
    assert PaperPortfolioSnapshotReceipt.from_json(seed.to_json()) == seed
    assert seed.receipt_kind == "seed_reference"
    assert not hasattr(seed, "net_qualified")
    with pytest.raises(FrozenInstanceError):
        seed.receipt_kind = "unknown"  # type: ignore[misc]


def test_seed_reference_rejects_wrong_account_namespace_and_binding_hash() -> None:
    snapshot = _snapshot()
    wrong_namespace, wrong_binding_hash = _binding("account-b")

    with pytest.raises(ValueError, match="account binding mismatch"):
        PaperPortfolioSnapshotReceipt.seed_reference_for(
            snapshot,
            account_namespace=wrong_namespace,
            binding_sha256=wrong_binding_hash,
            seed_source_id="synthetic:seed-v1",
            seed_source_sha256=_digest(b"synthetic seed bytes"),
        )

    correct_namespace, correct_binding_hash = _binding("account-a")
    with pytest.raises(ValueError, match="limited to synthetic source IDs"):
        PaperPortfolioSnapshotReceipt.seed_reference_for(
            snapshot,
            account_namespace=correct_namespace,
            binding_sha256=correct_binding_hash,
            seed_source_id="baseline.json",
            seed_source_sha256=_digest(b"unverified source"),
        )

    correct_namespace, _correct_binding_hash = _binding("account-a")
    with pytest.raises(ValueError, match="account binding mismatch"):
        PaperPortfolioSnapshotReceipt.seed_reference_for(
            snapshot,
            account_namespace=correct_namespace,
            binding_sha256=wrong_binding_hash,
            seed_source_id="synthetic:seed-v1",
            seed_source_sha256=_digest(b"synthetic seed bytes"),
        )


def test_seed_reference_rejects_wrong_snapshot_identity_or_positions() -> None:
    snapshot = _snapshot()
    receipt = _seed_receipt(snapshot)
    other_snapshot = _snapshot(snapshot_id="acct-seed-20261002", decision_date="2026-10-02")

    with pytest.raises(ValueError, match="does not match snapshot identity"):
        receipt.validate_for_snapshot(other_snapshot)

    altered_positions = PaperPortfolioSnapshot(
        snapshot_id=snapshot.snapshot_id,
        portfolio_id=snapshot.portfolio_id,
        decision_date=snapshot.decision_date,
        source_result_id=snapshot.source_result_id,
        cash=Decimal("201000.00"),
        total_value=snapshot.total_value,
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=299,
                mark_price=Decimal("1000.00"),
                market_value=Decimal("299000.00"),
                weight_bp=5980,
            ),
        ),
    )
    with pytest.raises(ValueError, match="positions hash mismatch"):
        receipt.validate_for_snapshot(altered_positions)


def test_seed_reference_rejects_market_value_not_supported_by_quantity_and_price() -> None:
    inconsistent = PaperPortfolioPositionSnapshot(
        stock_code="2330",
        quantity=300,
        mark_price=Decimal("1000.00"),
        market_value=Decimal("299999.00"),
        weight_bp=5999,
    )
    snapshot = _snapshot_with_position(inconsistent)

    with pytest.raises(ValueError, match="market value does not match quantity and mark price"):
        _seed_receipt(snapshot)


def test_seed_reference_rejects_weight_bp_inconsistent_with_market_value() -> None:
    inconsistent = PaperPortfolioPositionSnapshot(
        stock_code="2330",
        quantity=300,
        mark_price=Decimal("1000.00"),
        market_value=Decimal("300000.00"),
        weight_bp=6001,
    )
    snapshot = _snapshot_with_position(inconsistent)

    with pytest.raises(ValueError, match="weight_bp does not match market value"):
        _seed_receipt(snapshot)


def test_seed_reference_preserves_daily_runner_cent_quantization() -> None:
    position = PaperPortfolioPositionSnapshot(
        stock_code="2330",
        quantity=1,
        mark_price=Decimal("1000.005"),
        market_value=Decimal("1000.00"),
        weight_bp=20,
    )
    snapshot = _snapshot_with_position(position, cash=Decimal("499000.00"))

    assert _seed_receipt(snapshot).receipt_kind == "seed_reference"


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("mark_price", Decimal("NaN")),
        ("mark_price", Decimal("Infinity")),
        ("mark_price", Decimal("-0.01")),
        ("market_value", Decimal("NaN")),
        ("market_value", Decimal("Infinity")),
        ("market_value", Decimal("-0.01")),
    ),
)
def test_position_rejects_non_finite_or_negative_decimal_values(
    field_name: str,
    value: Decimal,
) -> None:
    payload: dict[str, object] = {
        "stock_code": "2330",
        "quantity": 300,
        "mark_price": Decimal("1000.00"),
        "market_value": Decimal("300000.00"),
        "weight_bp": 6000,
    }
    payload[field_name] = value

    with pytest.raises(ValueError, match="finite non-negative Decimal"):
        PaperPortfolioPositionSnapshot(**payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("cash", Decimal("NaN")),
        ("cash", Decimal("Infinity")),
        ("cash", Decimal("-0.01")),
        ("total_value", Decimal("NaN")),
        ("total_value", Decimal("Infinity")),
        ("total_value", Decimal("-0.01")),
    ),
)
def test_snapshot_rejects_non_finite_or_negative_decimal_values(
    field_name: str,
    value: Decimal,
) -> None:
    base = _snapshot()
    payload: dict[str, object] = {
        "snapshot_id": base.snapshot_id,
        "portfolio_id": base.portfolio_id,
        "decision_date": base.decision_date,
        "source_result_id": base.source_result_id,
        "cash": base.cash,
        "total_value": base.total_value,
        "positions": base.positions,
    }
    payload[field_name] = value

    with pytest.raises(ValueError, match="finite non-negative Decimal"):
        PaperPortfolioSnapshot(**payload)  # type: ignore[arg-type]


def test_tampered_json_and_oversized_claims_are_rejected() -> None:
    receipt = _seed_receipt(_snapshot())
    payload = json.loads(receipt.to_json())
    payload["seed_source_id"] = "synthetic:tampered-source"

    with pytest.raises(ValueError, match="hash mismatch"):
        PaperPortfolioSnapshotReceipt.from_json(json.dumps(payload))

    unsupported = json.loads(receipt.to_json())
    unsupported["receipt_kind"] = "net_after_fill_cost"
    unsupported.pop("receipt_sha256")
    canonical = json.dumps(
        unsupported,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    unsupported["receipt_sha256"] = _digest(canonical.encode("utf-8"))
    with pytest.raises(ValueError, match="contract is unsupported"):
        PaperPortfolioSnapshotReceipt.from_json(json.dumps(unsupported))

    unsupported["receipt_kind"] = "seed_reference"
    unsupported["performance_eligible"] = True
    unsupported.pop("receipt_sha256")
    canonical = json.dumps(
        {key: value for key, value in unsupported.items() if key != "performance_eligible"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    unsupported["receipt_sha256"] = _digest(canonical.encode("utf-8"))
    with pytest.raises(ValueError, match="fields are incomplete or unknown"):
        PaperPortfolioSnapshotReceipt.from_json(json.dumps(unsupported))

    with pytest.raises(ValueError, match="unknown_reason is too long"):
        PaperPortfolioSnapshotReceipt.unknown_for(
            _snapshot(portfolio_id="paper-main"), reason="x" * 513
        )


def test_receipt_parser_rejects_duplicate_json_keys_and_over_16kib() -> None:
    receipt = _seed_receipt(_snapshot())
    duplicate_key_json = receipt.to_json().replace(
        '"schema_version":', '"schema_version":"duplicate","schema_version":', 1
    )

    with pytest.raises(ValueError, match="duplicate keys"):
        PaperPortfolioSnapshotReceipt.from_json(duplicate_key_json)
    with pytest.raises(ValueError, match="size limit"):
        PaperPortfolioSnapshotReceipt.from_json(
            " " * (PAPER_SNAPSHOT_RECEIPT_MAX_BYTES + 1)
        )


def test_repository_roundtrips_receipt_and_duplicate_does_not_overwrite(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    repository = PaperPortfolioSnapshotRepository(tmp_path / "paper.sqlite")
    first = _seed_receipt(snapshot)
    namespace, binding_sha256 = _binding("account-a")
    second = PaperPortfolioSnapshotReceipt.unknown_for(
        snapshot,
        reason="different_candidate_receipt",
        account_namespace=namespace,
        binding_sha256=binding_sha256,
    )

    repository.append(snapshot, first)
    assert repository.get_receipt(snapshot.snapshot_id) == first
    with pytest.raises(ValueError, match="already exists"):
        repository.append(snapshot, second)
    assert repository.get(snapshot.snapshot_id) == snapshot
    assert repository.get_receipt(snapshot.snapshot_id) == first


def test_legacy_append_without_receipt_remains_unknown(tmp_path: Path) -> None:
    snapshot = _snapshot(portfolio_id="paper-main")
    repository = PaperPortfolioSnapshotRepository(tmp_path / "legacy-append.sqlite")

    repository.append(snapshot)

    assert repository.get(snapshot.snapshot_id) == snapshot
    assert repository.get_receipt(snapshot.snapshot_id) is None


def test_reader_rejects_tampered_stored_receipt(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite"
    snapshot = _snapshot()
    repository = PaperPortfolioSnapshotRepository(path)
    repository.append(snapshot, _seed_receipt(snapshot))
    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            "SELECT receipt_json FROM paper_portfolio_snapshot_receipts WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()[0]
        payload = json.loads(raw)
        payload["seed_source_id"] = "synthetic:tampered-source"
        connection.execute(
            "UPDATE paper_portfolio_snapshot_receipts SET receipt_json = ? WHERE snapshot_id = ?",
            (json.dumps(payload), snapshot.snapshot_id),
        )

    with pytest.raises(ValueError, match="receipt hash mismatch"):
        repository.get_receipt(snapshot.snapshot_id)


@pytest.mark.parametrize(
    ("column", "replacement"),
    (
        ("account_namespace", "acct-" + "f" * 64),
        ("binding_sha256", "sha256:" + "0" * 64),
        ("receipt_sha256", "sha256:" + "0" * 64),
    ),
)
def test_reader_rejects_row_metadata_tampering_with_valid_receipt_json_hash(
    tmp_path: Path,
    column: str,
    replacement: str,
) -> None:
    path = tmp_path / "metadata-tamper.sqlite"
    snapshot = _snapshot()
    receipt = _seed_receipt(snapshot)
    repository = PaperPortfolioSnapshotRepository(path)
    repository.append(snapshot, receipt)
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE paper_portfolio_snapshot_receipts SET {column} = ? WHERE snapshot_id = ?",
            (replacement, snapshot.snapshot_id),
        )
        raw_json = connection.execute(
            "SELECT receipt_json FROM paper_portfolio_snapshot_receipts WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()[0]

    assert PaperPortfolioSnapshotReceipt.from_json(str(raw_json)) == receipt
    with pytest.raises(ValueError, match="row metadata mismatch"):
        repository.get_receipt(snapshot.snapshot_id)


def test_receipt_insert_failure_rolls_back_snapshot_and_positions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.sqlite"
    repository = PaperPortfolioSnapshotRepository(path)
    snapshot = _snapshot()
    receipt = _seed_receipt(snapshot)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TRIGGER synthetic_receipt_failure
            BEFORE INSERT ON paper_portfolio_snapshot_receipts
            BEGIN
                SELECT RAISE(ABORT, 'synthetic receipt failure');
            END
            """
        )

    with pytest.raises(ValueError, match="snapshot append failed"):
        repository.append(snapshot, receipt)

    assert repository.get(snapshot.snapshot_id) is None
    assert repository.get_receipt(snapshot.snapshot_id) is None
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM paper_portfolio_positions WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()[0] == 0


def test_old_snapshot_without_receipt_remains_unknown(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    snapshot = _snapshot(portfolio_id="paper-main")
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_portfolio_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                cash TEXT NOT NULL,
                total_value TEXT NOT NULL
            );
            CREATE TABLE paper_portfolio_positions (
                snapshot_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                mark_price TEXT NOT NULL,
                market_value TEXT NOT NULL,
                weight_bp INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, stock_code)
            );
            """
        )
        connection.execute(
            "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                snapshot.portfolio_id,
                snapshot.decision_date,
                snapshot.source_result_id,
                str(snapshot.cash),
                str(snapshot.total_value),
            ),
        )
        connection.execute(
            "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                "2330",
                300,
                "1000.00",
                "300000.00",
                6000,
            ),
        )

    repository = PaperPortfolioSnapshotRepository(path)
    assert repository.get(snapshot.snapshot_id) == snapshot
    assert repository.get_receipt(snapshot.snapshot_id) is None


def test_readonly_legacy_route_missing_receipt_table_is_non_mutating(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(portfolio_id="paper-main")
    personal_paths = PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "legacy",
        personal_root=tmp_path / "market" / "personal",
    )
    route = select_personal_store_route(
        domain=PersonalStoreDomain.PAPER,
        mode=PersonalStoreMode.LEGACY_READ_ONLY,
        identity=StoreIdentity("paper-main"),
        personal_paths=personal_paths,
    )
    store_paths = PersonalPaperStorePaths.from_route(
        route,
        portfolio_id=snapshot.portfolio_id,
    )
    store_paths.state_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store_paths.state_db) as connection:
        connection.executescript(
            """
            CREATE TABLE paper_portfolio_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                source_result_id TEXT NOT NULL,
                cash TEXT NOT NULL,
                total_value TEXT NOT NULL
            );
            CREATE TABLE paper_portfolio_positions (
                snapshot_id TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                mark_price TEXT NOT NULL,
                market_value TEXT NOT NULL,
                weight_bp INTEGER NOT NULL,
                PRIMARY KEY (snapshot_id, stock_code)
            );
            """
        )
        connection.execute(
            "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                snapshot.portfolio_id,
                snapshot.decision_date,
                snapshot.source_result_id,
                str(snapshot.cash),
                str(snapshot.total_value),
            ),
        )
        connection.execute(
            "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                "2330",
                300,
                "1000.00",
                "300000.00",
                6000,
            ),
        )

    def table_names() -> tuple[str, ...]:
        with sqlite3.connect(store_paths.state_db) as connection:
            return tuple(
                sorted(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                )
            )

    before_bytes = store_paths.state_db.read_bytes()
    before_schema = table_names()
    repository = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=route,
        portfolio_id=snapshot.portfolio_id,
        personal_paths=personal_paths,
    )

    assert repository.read_only is True
    assert repository.get_receipt(snapshot.snapshot_id) is None
    assert store_paths.state_db.read_bytes() == before_bytes
    assert table_names() == before_schema
    assert "paper_portfolio_snapshot_receipts" not in before_schema


def test_account_route_rejects_wrong_portfolio_and_receipt_namespace(
    tmp_path: Path,
) -> None:
    namespace_a, binding_a = _binding("account-a")
    namespace_b, binding_b = _binding("account-b")
    repository, _paths = _account_repository(tmp_path, namespace_a)

    wrong_portfolio = _snapshot(portfolio_id=namespace_b)
    wrong_account_receipt = PaperPortfolioSnapshotReceipt.seed_reference_for(
        wrong_portfolio,
        account_namespace=namespace_b,
        binding_sha256=binding_b,
        seed_source_id="synthetic:seed-v1",
        seed_source_sha256=_digest(b"synthetic seed bytes"),
    )
    with pytest.raises(ValueError, match="paper identity mismatch"):
        repository.append(wrong_portfolio, wrong_account_receipt)

    snapshot = _snapshot(portfolio_id=namespace_a)
    with pytest.raises(ValueError, match="namespace binding is missing"):
        PaperPortfolioSnapshotReceipt.unknown_for(
            snapshot,
            reason="receipt_binding_not_attested",
        )

    receipt = PaperPortfolioSnapshotReceipt.seed_reference_for(
        snapshot,
        account_namespace=namespace_a,
        binding_sha256=binding_a,
        seed_source_id="synthetic:seed-v1",
        seed_source_sha256=_digest(b"synthetic seed bytes"),
    )
    repository.append(snapshot, receipt)
    assert repository.get_receipt(snapshot.snapshot_id) == receipt
