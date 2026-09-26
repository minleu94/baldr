"""為同次準備中的 ML 呼叫提供不可變、無檔案系統操作的來源合約證據。

呼叫端只讀取一次已設定的合約，並將原始 bytes 傳入。此純型別模組驗證那些 bytes
與已正規化的 consumed rows；不解析路徑、不開啟檔案，也不查詢來源資料。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
from typing import Any, Final, cast


_EVIDENCE_DOMAIN: Final[str] = "r026.prepared-source-contract-evidence.v1"
_BINDING_SCHEMA: Final[str] = "recommendation-calibration-capture-source-binding.v1"
_EVIDENCE_FACTORY_TOKEN: Final[object] = object()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash_payload(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _require_hash(value: object, field_name: str) -> str:
    if type(value) is not str or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} 必須使用 sha256 格式")
    digest = value[len("sha256:") :]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{field_name} 必須是小寫 sha256")
    return value


def _date_text(value: object, field_name: str) -> str:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} is not ISO date") from exc


def _freeze_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) not in (tuple, list):
        raise TypeError(f"{field_name} 必須是 tuple 或 list")
    frozen = tuple(cast(tuple[object, ...] | list[object], value))
    if any(type(item) is not str for item in frozen):
        raise TypeError(f"{field_name} 項目必須是字串")
    return cast(tuple[str, ...], frozen)


def _freeze_feature_values(value: object) -> tuple[int | None, ...]:
    if type(value) not in (tuple, list):
        raise TypeError("feature_values 必須是 tuple 或 list")
    frozen = tuple(cast(tuple[object, ...] | list[object], value))
    if any(item is not None and (type(item) is not int) for item in frozen):
        raise TypeError("feature_values 只能包含 int 或 None")
    return cast(tuple[int | None, ...], frozen)


@dataclass(frozen=True, slots=True)
class SourceContractFeatureRowV1:
    """一筆由目前 invocation 消費並已正規化的 feature row。"""

    symbol: str
    decision_date: str
    feature_as_of_date: str
    feature_available_date: str
    feature_ids: tuple[str, ...]
    feature_values: tuple[int | None, ...]
    snapshot_hash: str

    def __post_init__(self) -> None:
        for name in (
            "symbol",
            "decision_date",
            "feature_as_of_date",
            "feature_available_date",
            "snapshot_hash",
        ):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        feature_ids = _freeze_text_tuple(self.feature_ids, "feature_ids")
        feature_values = _freeze_feature_values(self.feature_values)
        if len(feature_ids) != len(feature_values):
            raise ValueError("feature_ids 與 feature_values 長度必須相同")
        object.__setattr__(self, "feature_ids", feature_ids)
        object.__setattr__(self, "feature_values", feature_values)


def _row_payload(row: SourceContractFeatureRowV1) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "decision_date": row.decision_date,
        "feature_as_of_date": row.feature_as_of_date,
        "feature_available_date": row.feature_available_date,
        "feature_ids": list(row.feature_ids),
        "feature_values": list(row.feature_values),
        # 沿用既有 normalization：空字串與不透明字串都必須原樣保留。
        "snapshot_hash": row.snapshot_hash,
    }


def _freeze_rows(value: object) -> tuple[SourceContractFeatureRowV1, ...]:
    if type(value) not in (tuple, list):
        raise TypeError("consumed_feature_rows 必須是 tuple 或 list")
    rows = tuple(cast(tuple[object, ...] | list[object], value))
    if any(type(row) is not SourceContractFeatureRowV1 for row in rows):
        raise TypeError("consumed_feature_rows 含有不支援的 row 型別")
    return cast(tuple[SourceContractFeatureRowV1, ...], rows)


def _parse_json_object(payload: bytes, field_name: str) -> dict[str, Any]:
    if type(payload) is not bytes:
        raise TypeError(f"{field_name} 必須是不可變 bytes")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} is not UTF-8 JSON") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError(f"{field_name} 必須編碼為 JSON object")
    return dict(decoded)


def _decode_canonical_binding(payload: bytes) -> dict[str, Any]:
    binding = _parse_json_object(payload, "binding_payload_json")
    if _canonical_json_bytes(binding) != payload:
        raise ValueError("binding_payload_json 必須使用 canonical JSON bytes")
    return binding


def _source_contract_rows_hash(
    *,
    source_db: str,
    decision_date: str,
    history_start_date: str,
    feature_registry_hash: str,
    feature_schema_hash: str,
    symbols: list[str],
    rows: tuple[SourceContractFeatureRowV1, ...],
) -> str:
    ordered_rows = [
        _row_payload(row)
        for row in sorted(rows, key=lambda item: str(item.symbol or ""))
    ]
    return _hash_payload(
        {
            "component": "prospective_recommendation_features",
            "source_db": source_db,
            "decision_date": decision_date,
            "history_start_date": history_start_date,
            "feature_registry_hash": feature_registry_hash,
            "feature_schema_hash": feature_schema_hash,
            "symbols": symbols,
            "rows": ordered_rows,
        }
    )


def _validate_source_contract(
    *,
    binding_payload_json: bytes,
    contract_file_bytes: bytes,
    contract_path: str,
    contract_file_sha256: str,
    contract_content_sha256: str,
    decision_date: str,
    symbols: tuple[str, ...],
    source_database: str | None,
    source_database_original: str | None,
    history_start_date: str | None,
    feature_registry_hash: str,
    feature_schema_hash: str,
    feature_builder_schema_hash: str | None,
    feature_snapshot_content_sha256: str,
    feature_snapshot_rows_sha256: str,
    consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...],
) -> None:
    """不讀檔案，只比對既有驗證器要求的內容斷言。"""

    if type(binding_payload_json) is not bytes:
        raise TypeError("binding_payload_json 必須是不可變 bytes")
    if type(contract_file_bytes) is not bytes:
        raise TypeError("contract_file_bytes 必須是不可變 bytes")
    binding = _decode_canonical_binding(binding_payload_json)
    if binding.get("schema_version") != _BINDING_SCHEMA:
        raise ValueError("source contract binding schema 不支援")
    if binding.get("historical_pit_eligible") is not False:
        raise ValueError("source contract binding 不可宣稱 historical PIT")
    if binding.get("price_up_prospective_status") != "ready":
        raise ValueError("source contract prospective lane 尚未 ready")
    if type(contract_path) is not str:
        raise TypeError("contract_path 必須是 str")
    if source_database is not None and type(source_database) is not str:
        raise TypeError("source_database 必須是 str 或 None")
    if source_database_original is not None and type(source_database_original) is not str:
        raise TypeError("source_database_original 必須是 str 或 None")
    if (source_database is None) != (source_database_original is None):
        raise ValueError("來源資料庫原始與解析路徑必須同時存在或同時缺省")

    file_hash = _require_hash(contract_file_sha256, "source contract file hash")
    content_hash = _require_hash(
        contract_content_sha256, "source contract content hash"
    )
    if _sha256_bytes(contract_file_bytes) != file_hash:
        raise ValueError("source contract file hash 不一致")
    if binding.get("contract_file_sha256") != file_hash:
        raise ValueError("source contract binding file hash 不一致")
    if binding.get("contract_content_sha256") != content_hash:
        raise ValueError("source contract binding content hash 不一致")

    try:
        contract = json.loads(contract_file_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("source contract receipt 無法讀取") from exc
    if not isinstance(contract, Mapping):
        raise ValueError("source contract payload 無效")
    contract = dict(contract)
    contract_body = {
        key: value
        for key, value in contract.items()
        if key not in {"contract_sha256", "checked_at"}
    }
    contract_self_hash = contract.get("contract_sha256")
    if contract_self_hash != _hash_payload(contract_body):
        raise ValueError("source contract content self-hash 不一致")
    if contract_self_hash != content_hash:
        raise ValueError("source contract content hash 不一致")

    day = _date_text(decision_date, "decision_date")
    if _date_text(contract.get("decision_date"), "source contract decision_date") != day:
        raise ValueError("source contract decision date 不一致")

    expected_symbols = sorted({str(row.symbol or "") for row in consumed_feature_rows})
    contract_symbols = sorted(
        {
            str(item)
            for item in contract.get("symbols", ())
            if str(item).strip()
        }
    )
    binding_symbols = sorted(
        {str(item) for item in binding.get("symbols", ()) if str(item).strip()}
    )
    if (
        not expected_symbols
        or expected_symbols != contract_symbols
        or expected_symbols != binding_symbols
        or expected_symbols != sorted(set(symbols))
    ):
        raise ValueError("source contract symbol coverage 不一致")

    technical = contract.get("technical")
    technical = technical if isinstance(technical, Mapping) else {}
    snapshot = technical.get("prospective_feature_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("source contract feature snapshot 缺失")
    snapshot_content_hash = str(snapshot.get("content_sha256") or "")
    _require_hash(snapshot_content_hash, "source contract feature snapshot content hash")
    if snapshot_content_hash != feature_snapshot_content_sha256:
        raise ValueError("source contract feature snapshot identity 不一致")
    if snapshot_content_hash != binding.get("feature_snapshot_content_sha256"):
        raise ValueError("source contract binding feature snapshot identity 不一致")
    snapshot_body = {
        key: value for key, value in snapshot.items() if key != "content_sha256"
    }
    if snapshot_content_hash != _hash_payload(snapshot_body):
        raise ValueError("source contract feature snapshot self-hash 不一致")

    if snapshot.get("feature_registry_hash") != feature_registry_hash:
        raise ValueError("source contract feature registry identity 不一致")
    expected_source_schema_hash = feature_builder_schema_hash or feature_schema_hash
    if snapshot.get("feature_schema_hash") != expected_source_schema_hash:
        raise ValueError("source contract feature schema identity 不一致")

    # preparation owner 同次保存原始與已解析路徑；此 leaf 不碰觸檔案系統。
    if source_database is not None:
        if str(snapshot.get("source_db") or "") != source_database:
            raise ValueError("source contract source database identity 不一致")
    if history_start_date is not None:
        if type(history_start_date) is not str:
            raise TypeError("history_start_date 必須是 str 或 None")
        if _date_text(snapshot.get("history_start_date"), "source contract history_start_date") != _date_text(
            history_start_date, "history_start_date"
        ):
            raise ValueError("source contract history start identity 不一致")

    expected_rows = snapshot.get("rows")
    if not isinstance(expected_rows, list):
        raise ValueError("source contract feature snapshot rows 缺失")
    expected_rows_hash = _source_contract_rows_hash(
        source_db=str(snapshot.get("source_db") or ""),
        decision_date=day,
        history_start_date=str(snapshot.get("history_start_date") or ""),
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=expected_source_schema_hash,
        symbols=expected_symbols,
        rows=consumed_feature_rows,
    )
    if snapshot.get("rows_sha256") != expected_rows_hash:
        raise ValueError("source contract feature rows hash 不一致")
    if feature_snapshot_rows_sha256 != expected_rows_hash:
        raise ValueError("source contract feature rows binding 不一致")
    if binding.get("feature_snapshot_rows_sha256") != expected_rows_hash:
        raise ValueError("source contract feature rows hash 不一致")

    expected_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in expected_rows
        if isinstance(row, Mapping) and str(row.get("symbol") or "")
    }
    actual_by_symbol = {str(row.symbol or ""): row for row in consumed_feature_rows}
    if set(expected_by_symbol) != set(actual_by_symbol):
        raise ValueError("source contract feature row coverage 不一致")
    for symbol, actual in actual_by_symbol.items():
        expected = expected_by_symbol[symbol]
        for key in ("decision_date", "feature_as_of_date", "feature_available_date"):
            if str(getattr(actual, key) or "")[:10] != str(expected.get(key) or "")[:10]:
                raise ValueError("source contract feature timing 不一致")
        if list(actual.feature_values or ()) != list(expected.get("feature_values") or ()):
            raise ValueError("source contract feature values 不一致")


def _evidence_payload_values(
    *,
    binding_payload_json: bytes,
    contract_file_bytes: bytes,
    contract_path: str,
    contract_file_sha256: str,
    contract_content_sha256: str,
    decision_date: str,
    symbols: tuple[str, ...],
    source_database: str | None,
    source_database_original: str | None,
    history_start_date: str | None,
    feature_registry_hash: str,
    feature_schema_hash: str,
    feature_builder_schema_hash: str | None,
    feature_snapshot_content_sha256: str,
    feature_snapshot_rows_sha256: str,
    consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...],
) -> dict[str, Any]:
    return {
        "domain": _EVIDENCE_DOMAIN,
        "binding_payload_sha256": _sha256_bytes(binding_payload_json),
        "contract_file_bytes_sha256": _sha256_bytes(contract_file_bytes),
        "contract_path": contract_path,
        "contract_file_sha256": contract_file_sha256,
        "contract_content_sha256": contract_content_sha256,
        "decision_date": decision_date,
        "symbols": list(symbols),
        "source_database": source_database,
        "source_database_original": source_database_original,
        "history_start_date": history_start_date,
        "feature_registry_hash": feature_registry_hash,
        "feature_schema_hash": feature_schema_hash,
        "feature_builder_schema_hash": feature_builder_schema_hash,
        "feature_snapshot_content_sha256": feature_snapshot_content_sha256,
        "feature_snapshot_rows_sha256": feature_snapshot_rows_sha256,
        "consumed_feature_rows": [
            _row_payload(row) for row in consumed_feature_rows
        ],
    }


@dataclass(frozen=True, slots=True, init=False)
class VerifiedSourceContractEvidenceV1:
    """只有在驗證同次 source bytes 與 rows 後才能建立的證據。"""

    binding_payload_json: bytes
    contract_file_bytes: bytes
    contract_path: str
    contract_file_sha256: str
    contract_content_sha256: str
    decision_date: str
    symbols: tuple[str, ...]
    source_database: str | None
    source_database_original: str | None
    history_start_date: str | None
    feature_registry_hash: str
    feature_schema_hash: str
    feature_builder_schema_hash: str | None
    feature_snapshot_content_sha256: str
    feature_snapshot_rows_sha256: str
    consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...]
    evidence_sha256: str = field(repr=True)

    def __init__(
        self,
        *,
        _factory_token: object,
        binding_payload_json: bytes,
        contract_file_bytes: bytes,
        contract_path: str,
        contract_file_sha256: str,
        contract_content_sha256: str,
        decision_date: str,
        symbols: tuple[str, ...],
        source_database: str | None,
        source_database_original: str | None,
        history_start_date: str | None,
        feature_registry_hash: str,
        feature_schema_hash: str,
        feature_builder_schema_hash: str | None,
        feature_snapshot_content_sha256: str,
        feature_snapshot_rows_sha256: str,
        consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...],
        evidence_sha256: str,
    ) -> None:
        if _factory_token is not _EVIDENCE_FACTORY_TOKEN:
            raise TypeError("verified source-contract evidence 必須透過 factory 建立")
        object.__setattr__(self, "binding_payload_json", binding_payload_json)
        object.__setattr__(self, "contract_file_bytes", contract_file_bytes)
        object.__setattr__(self, "contract_path", contract_path)
        object.__setattr__(self, "contract_file_sha256", contract_file_sha256)
        object.__setattr__(self, "contract_content_sha256", contract_content_sha256)
        object.__setattr__(self, "decision_date", decision_date)
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "source_database", source_database)
        object.__setattr__(self, "source_database_original", source_database_original)
        object.__setattr__(self, "history_start_date", history_start_date)
        object.__setattr__(self, "feature_registry_hash", feature_registry_hash)
        object.__setattr__(self, "feature_schema_hash", feature_schema_hash)
        object.__setattr__(self, "feature_builder_schema_hash", feature_builder_schema_hash)
        object.__setattr__(self, "feature_snapshot_content_sha256", feature_snapshot_content_sha256)
        object.__setattr__(self, "feature_snapshot_rows_sha256", feature_snapshot_rows_sha256)
        object.__setattr__(self, "consumed_feature_rows", consumed_feature_rows)
        object.__setattr__(self, "evidence_sha256", evidence_sha256)
        self.__post_init__()

    def __post_init__(self) -> None:
        if type(self.binding_payload_json) is not bytes:
            raise TypeError("binding_payload_json 必須是不可變 bytes")
        if type(self.contract_file_bytes) is not bytes:
            raise TypeError("contract_file_bytes 必須是不可變 bytes")
        if type(self.contract_path) is not str:
            raise TypeError("contract_path 必須是 str")
        if type(self.decision_date) is not str:
            raise TypeError("decision_date 必須是 str")
        if self.source_database is not None and type(self.source_database) is not str:
            raise TypeError("source_database 必須是 str 或 None")
        if self.source_database_original is not None and type(self.source_database_original) is not str:
            raise TypeError("source_database_original 必須是 str 或 None")
        if (self.source_database is None) != (self.source_database_original is None):
            raise ValueError("來源資料庫原始與解析路徑必須同時存在或同時缺省")
        if self.history_start_date is not None and type(self.history_start_date) is not str:
            raise TypeError("history_start_date 必須是 str 或 None")
        if type(self.feature_registry_hash) is not str:
            raise TypeError("feature_registry_hash 必須是 str")
        if type(self.feature_schema_hash) is not str:
            raise TypeError("feature_schema_hash 必須是 str")
        if (
            self.feature_builder_schema_hash is not None
            and type(self.feature_builder_schema_hash) is not str
        ):
            raise TypeError("feature_builder_schema_hash 必須是 str 或 None")
        symbols = _freeze_text_tuple(self.symbols, "symbols")
        rows = _freeze_rows(self.consumed_feature_rows)
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "consumed_feature_rows", rows)
        _validate_source_contract(
            binding_payload_json=self.binding_payload_json,
            contract_file_bytes=self.contract_file_bytes,
            contract_path=self.contract_path,
            contract_file_sha256=self.contract_file_sha256,
            contract_content_sha256=self.contract_content_sha256,
            decision_date=self.decision_date,
            symbols=symbols,
            source_database=self.source_database,
            source_database_original=self.source_database_original,
            history_start_date=self.history_start_date,
            feature_registry_hash=self.feature_registry_hash,
            feature_schema_hash=self.feature_schema_hash,
            feature_builder_schema_hash=self.feature_builder_schema_hash,
            feature_snapshot_content_sha256=self.feature_snapshot_content_sha256,
            feature_snapshot_rows_sha256=self.feature_snapshot_rows_sha256,
            consumed_feature_rows=rows,
        )
        expected = _hash_payload(
            _evidence_payload_values(
                binding_payload_json=self.binding_payload_json,
                contract_file_bytes=self.contract_file_bytes,
                contract_path=self.contract_path,
                contract_file_sha256=self.contract_file_sha256,
                contract_content_sha256=self.contract_content_sha256,
                decision_date=self.decision_date,
                symbols=symbols,
                source_database=self.source_database,
                source_database_original=self.source_database_original,
                history_start_date=self.history_start_date,
                feature_registry_hash=self.feature_registry_hash,
                feature_schema_hash=self.feature_schema_hash,
                feature_builder_schema_hash=self.feature_builder_schema_hash,
                feature_snapshot_content_sha256=self.feature_snapshot_content_sha256,
                feature_snapshot_rows_sha256=self.feature_snapshot_rows_sha256,
                consumed_feature_rows=rows,
            )
        )
        if self.evidence_sha256 != expected:
            raise ValueError("source contract evidence self-hash 不一致")


def build_verified_source_contract_evidence_v1(
    *,
    binding_payload_json: bytes,
    contract_file_bytes: bytes,
    contract_path: str,
    decision_date: str,
    symbols: tuple[str, ...],
    source_database: str | None,
    source_database_original: str | None,
    history_start_date: str | None,
    feature_registry_hash: str,
    feature_schema_hash: str,
    feature_builder_schema_hash: str | None,
    consumed_feature_rows: tuple[SourceContractFeatureRowV1, ...],
) -> VerifiedSourceContractEvidenceV1:
    """由同次綁定 bytes 與已正規化的 feature rows 建立證據。

    呼叫端需在同次 preparation 檢查檔案存在與 symlink 狀態，並讀取
    ``contract_file_bytes``。此函式不執行任何 I/O。
    """

    frozen_symbols = _freeze_text_tuple(symbols, "symbols")
    frozen_rows = _freeze_rows(consumed_feature_rows)
    # 建立唯一公開 evidence 前先驗證內容；post-init 會重做斷言並檢查 digest。
    binding = _decode_canonical_binding(binding_payload_json)
    contract_file_sha256 = binding.get("contract_file_sha256")
    contract_content_sha256 = binding.get("contract_content_sha256")
    feature_snapshot_content_sha256 = binding.get(
        "feature_snapshot_content_sha256"
    )
    feature_snapshot_rows_sha256 = binding.get("feature_snapshot_rows_sha256")
    if type(contract_file_sha256) is not str:
        raise ValueError("source contract file hash 缺失")
    if type(contract_content_sha256) is not str:
        raise ValueError("source contract content hash 缺失")
    if type(feature_snapshot_content_sha256) is not str:
        raise ValueError("source contract feature snapshot hash 缺失")
    if type(feature_snapshot_rows_sha256) is not str:
        raise ValueError("source contract feature rows hash 缺失")

    _validate_source_contract(
        binding_payload_json=binding_payload_json,
        contract_file_bytes=contract_file_bytes,
        contract_path=contract_path,
        contract_file_sha256=contract_file_sha256,
        contract_content_sha256=contract_content_sha256,
        decision_date=decision_date,
        symbols=frozen_symbols,
        source_database=source_database,
        source_database_original=source_database_original,
        history_start_date=history_start_date,
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=feature_schema_hash,
        feature_builder_schema_hash=feature_builder_schema_hash,
        feature_snapshot_content_sha256=feature_snapshot_content_sha256,
        feature_snapshot_rows_sha256=feature_snapshot_rows_sha256,
        consumed_feature_rows=frozen_rows,
    )
    payload = _evidence_payload_values(
        binding_payload_json=binding_payload_json,
        contract_file_bytes=contract_file_bytes,
        contract_path=contract_path,
        contract_file_sha256=contract_file_sha256,
        contract_content_sha256=contract_content_sha256,
        decision_date=decision_date,
        symbols=frozen_symbols,
        source_database=source_database,
        source_database_original=source_database_original,
        history_start_date=history_start_date,
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=feature_schema_hash,
        feature_builder_schema_hash=feature_builder_schema_hash,
        feature_snapshot_content_sha256=feature_snapshot_content_sha256,
        feature_snapshot_rows_sha256=feature_snapshot_rows_sha256,
        consumed_feature_rows=frozen_rows,
    )
    digest = _hash_payload(payload)
    return VerifiedSourceContractEvidenceV1(
        _factory_token=_EVIDENCE_FACTORY_TOKEN,
        binding_payload_json=binding_payload_json,
        contract_file_bytes=contract_file_bytes,
        contract_path=contract_path,
        contract_file_sha256=contract_file_sha256,
        contract_content_sha256=contract_content_sha256,
        decision_date=decision_date,
        symbols=frozen_symbols,
        source_database=source_database,
        source_database_original=source_database_original,
        history_start_date=history_start_date,
        feature_registry_hash=feature_registry_hash,
        feature_schema_hash=feature_schema_hash,
        feature_builder_schema_hash=feature_builder_schema_hash,
        feature_snapshot_content_sha256=feature_snapshot_content_sha256,
        feature_snapshot_rows_sha256=feature_snapshot_rows_sha256,
        consumed_feature_rows=frozen_rows,
        evidence_sha256=digest,
    )
