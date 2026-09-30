"""MOPS 成功回應的研究用 raw entity custody 與唯讀讀回。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Mapping, cast

from data_module.mops_ezsearch_statement_availability import (
    MOPS_EZSEARCH_QUERY_URL,
    MOPS_MARKETS,
    MOPS_RESPONSE_MAX_BYTES,
    MOPS_RESPONSE_MAX_DECODED_BYTES,
    MOPS_RESPONSE_PREFIX_BYTES,
    MOPS_STATEMENT_ITEMS,
    MOPSQueryAttempt,
    MOPSQueryResult,
    _decode_response_body,
    build_query_payload,
)
from data_module.wp5_official_daily_capture_validator import (
    CaptureValidationError,
    _assert_no_reparse_chain,
    _read_regular_single_link_file,
)

MOPS_SUCCESS_CUSTODY_SCHEMA = "mops-success-response-custody.v1"
MOPS_SUCCESS_CUSTODY_RECEIPT = "capture_receipt.json"
MOPS_SUCCESS_CUSTODY_READBACK = "source_readback.json"
MOPS_SUCCESS_CUSTODY_READBACK_SCHEMA = "mops-success-response-readback.v1"
MOPS_SUCCESS_CUSTODY_DIRECTORY = "raw_success_responses"
MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES = 128 * 1024 * 1024
MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES = 64 * 1024
MOPS_SUCCESS_CUSTODY_MAX_TOTAL_METADATA_BYTES = 4 * 1024 * 1024
MOPS_SUCCESS_CUSTODY_DISK_RESERVE_BYTES = 16 * 1024 * 1024
MOPS_SUCCESS_CUSTODY_MAX_COMPONENTS = 512
MOPS_SUCCESS_CUSTODY_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
class MOPSSuccessResponseCustodyError(ValueError):
    """成功回應 custody 來源或檔案契約無效。"""


@dataclass(frozen=True)
class _PendingSidecar:
    result: MOPSQueryResult
    attempt: MOPSQueryAttempt
    raw_path: str
    raw_sha256: str
    raw_bytes: int
    attempt_lineage: tuple[dict[str, object], ...]


class MOPSSuccessResponseCustodyWriter:
    """在已建立的隔離 run root 內 create-only 保存成功 raw entity。"""

    def __init__(self, *, run_root: Path, capture_root: Path) -> None:
        self.run_root = Path(os.path.abspath(str(run_root.expanduser())))
        self.capture_root = Path(os.path.abspath(str(capture_root.expanduser())))
        if self.capture_root != self.run_root / MOPS_SUCCESS_CUSTODY_DIRECTORY:
            raise MOPSSuccessResponseCustodyError(
                "成功回應 custody root 必須是 run root 的固定子目錄"
            )
        if not self.run_root.is_dir():
            raise MOPSSuccessResponseCustodyError("MOPS custody run root 必須先存在")
        try:
            _assert_no_reparse_chain(self.run_root)
        except CaptureValidationError as error:
            raise MOPSSuccessResponseCustodyError(
                "MOPS custody run root 含有 reparse 元件"
            ) from error
        if self.capture_root.exists() or self.capture_root.is_symlink():
            raise MOPSSuccessResponseCustodyError(
                "MOPS successful response custody root 已存在；請使用新的 run root"
            )
        self._require_free_space(
            MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES
            + MOPS_SUCCESS_CUSTODY_MAX_TOTAL_METADATA_BYTES
        )
        self.capture_root.mkdir(exist_ok=False)
        self.pending: list[_PendingSidecar] = []
        self.total_raw_bytes = 0
        self.total_success_entity_bytes = 0
        self.total_failure_prefix_bytes = 0
        self.failure_prefix_count = 0
        self.total_metadata_bytes = 0
        self.collection_started_at = datetime.now(timezone.utc)

    def reserve_for_output(self, incoming_bytes: int) -> None:
        """確保接續寫入 legacy artifact/mapping 後仍保留磁碟安全餘額。"""

        if type(incoming_bytes) is not int or incoming_bytes < 0:
            raise MOPSSuccessResponseCustodyError(
                "MOPS custody output reservation must be a non-negative integer"
            )
        self._require_free_space(incoming_bytes)

    def add_result(self, result: MOPSQueryResult) -> None:
        """保存一筆 live query 的完整成功 encoded entity。"""

        self._account_failure_prefixes(result)
        if result.source_status == "error":
            return
        if result.source_status not in {"success", "fail"}:
            raise MOPSSuccessResponseCustodyError(
                "MOPS response has an unsupported source status"
            )
        if (
            result.market not in MOPS_MARKETS
            or result.announcement_item not in MOPS_STATEMENT_ITEMS
            or result.query_start_date is None
            or result.query_end_date is None
            or result.query_end_date < result.query_start_date
            or (result.query_end_date - result.query_start_date).days >= 31
        ):
            raise MOPSSuccessResponseCustodyError("MOPS query identity/window is invalid")
        if len(self.pending) >= MOPS_SUCCESS_CUSTODY_MAX_COMPONENTS:
            raise MOPSSuccessResponseCustodyError("MOPS custody component-count limit exceeded")
        if not result.attempts:
            raise MOPSSuccessResponseCustodyError(
                "opt-in custody requires live HTTP attempt metadata"
            )
        attempt = result.attempts[-1]
        self._validate_success_attempt(result, attempt)
        raw_body = attempt.success_entity_bytes
        next_success_total = self.total_success_entity_bytes + len(raw_body)
        next_total = self.total_raw_bytes + len(raw_body)
        if next_total > MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES:
            raise MOPSSuccessResponseCustodyError(
                "MOPS success raw entity total exceeds 128 MiB"
            )
        slug = (
            f"mops_{result.market}_{result.announcement_item}_"
            f"{result.query_start_date.isoformat()}_{result.query_end_date.isoformat()}_"
            f"attempt_{attempt.attempt_number:02d}"
        )
        raw_relative = f"{slug}.entity"
        raw_path = self.capture_root / raw_relative
        self._require_free_space(len(raw_body))
        try:
            with raw_path.open("xb") as stream:
                stream.write(raw_body)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise MOPSSuccessResponseCustodyError(
                "duplicate MOPS query sidecar identity"
            ) from error
        self.total_raw_bytes = next_total
        self.total_success_entity_bytes = next_success_total
        self.pending.append(
            _PendingSidecar(
                result=result,
                attempt=attempt,
                raw_path=raw_relative,
                raw_sha256=sha256(raw_body).hexdigest(),
                raw_bytes=len(raw_body),
                attempt_lineage=tuple(
                    _attempt_lineage_item(item) for item in result.attempts
                ),
            )
        )

    def _account_failure_prefixes(self, result: MOPSQueryResult) -> None:
        for attempt in result.attempts:
            if attempt.source_status != "error" or not attempt.raw_body_prefix_path:
                continue
            relative = _required_relative_path(
                attempt.raw_body_prefix_path,
                "failed response prefix",
            )
            if not relative.startswith("raw_failed_attempts/"):
                raise MOPSSuccessResponseCustodyError(
                    "MOPS failed response prefix must be under raw_failed_attempts"
                )
            prefix = _read_bounded_file(
                self.run_root.joinpath(*relative.split("/")),
                label="MOPS failed response prefix",
                max_bytes=MOPS_RESPONSE_PREFIX_BYTES,
            )
            if (
                not attempt.raw_body_prefix
                or len(prefix) != len(attempt.raw_body_prefix)
                or prefix != attempt.raw_body_prefix
                or attempt.raw_body_prefix_sha256 != sha256(prefix).hexdigest()
            ):
                raise MOPSSuccessResponseCustodyError(
                    "MOPS failed response prefix differs from its attempt receipt"
                )
            next_total = self.total_raw_bytes + len(prefix)
            if next_total > MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES:
                raise MOPSSuccessResponseCustodyError(
                    "MOPS raw captures exceed the 128 MiB per-run limit"
                )
            self.total_raw_bytes = next_total
            self.total_failure_prefix_bytes += len(prefix)
            self.failure_prefix_count += 1

    def finalize(self, *, artifact_path: Path) -> dict[str, object]:
        """將成功 response metadata 綁到同 run 的實際 artifact bytes。"""

        artifact = Path(os.path.abspath(str(artifact_path.expanduser())))
        if artifact.parent != self.run_root:
            raise MOPSSuccessResponseCustodyError(
                "MOPS artifact must be a direct child of the isolated run root"
            )
        artifact_raw = _read_bounded_file(
            artifact,
            label="MOPS statement artifact",
            max_bytes=MOPS_SUCCESS_CUSTODY_MAX_ARTIFACT_BYTES,
        )
        artifact_body = _decode_json_object(artifact_raw, "MOPS statement artifact")
        selected_start = _parse_iso_date(
            artifact_body.get("query_start_date"), "artifact.query_start_date"
        )
        selected_end = _parse_iso_date(
            artifact_body.get("query_end_date"), "artifact.query_end_date"
        )
        if selected_end < selected_start:
            raise MOPSSuccessResponseCustodyError(
                "MOPS artifact selected date range is invalid"
            )
        artifact_captured_at = _parse_timestamp(
            artifact_body.get("captured_at"), "artifact.captured_at"
        ).astimezone(timezone.utc)
        collection_completed_at = datetime.now(timezone.utc)
        if not (
            self.collection_started_at <= artifact_captured_at <= collection_completed_at
        ):
            raise MOPSSuccessResponseCustodyError(
                "MOPS collection and artifact capture times are inconsistent"
            )
        query_manifest = artifact_body.get("query_manifest")
        if not isinstance(query_manifest, list):
            raise MOPSSuccessResponseCustodyError(
                "MOPS statement artifact query manifest is invalid"
            )
        artifact_sha256 = sha256(artifact_raw).hexdigest()
        components: list[dict[str, object]] = []
        for item in self.pending:
            result = item.result
            attempt = item.attempt
            assert result.query_start_date is not None
            assert result.query_end_date is not None
            metadata: dict[str, object] = {
                "schema_version": MOPS_SUCCESS_CUSTODY_SCHEMA,
                "source_url": MOPS_EZSEARCH_QUERY_URL,
                "market": result.market,
                "announcement_item": result.announcement_item,
                "query_start_date": result.query_start_date.isoformat(),
                "query_end_date": result.query_end_date.isoformat(),
                "query_payload": build_query_payload(
                    market=result.market,
                    announcement_item=result.announcement_item,
                    start_date=result.query_start_date,
                    end_date=result.query_end_date,
                ),
                "source_status": result.source_status,
                "row_count": len(result.rows),
                "raw_entity_path": item.raw_path,
                "raw_entity_sha256": f"sha256:{item.raw_sha256}",
                "raw_entity_bytes": item.raw_bytes,
                "legacy_canonical_json_sha256": f"sha256:{result.response_sha256}",
                "artifact_path": artifact.name,
                "artifact_sha256": f"sha256:{artifact_sha256}",
                "attempt_count": result.attempt_count,
                "retry_error_codes": list(result.retry_error_codes),
                "attempt_lineage": list(item.attempt_lineage),
                "http": {
                    "request_url": MOPS_EZSEARCH_QUERY_URL,
                    "final_url": attempt.response_url,
                    "status_code": attempt.http_status,
                    "reason": attempt.http_reason,
                    "content_type": attempt.content_type,
                    "content_length": attempt.content_length_header,
                    "content_encoding": attempt.content_encoding,
                    "transfer_encoding": attempt.transfer_encoding,
                    "started_at_utc": attempt.started_at_utc,
                    "completed_at_utc": attempt.completed_at_utc,
                },
                "research_only": True,
                "formal_oos_allowed": False,
                "formal_credit_authorized": False,
            }
            encoded_metadata = _canonical_json_bytes(metadata)
            if len(encoded_metadata) > MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES:
                raise MOPSSuccessResponseCustodyError(
                    "MOPS sidecar metadata exceeds 64 KiB"
                )
            next_metadata_total = self.total_metadata_bytes + len(encoded_metadata)
            if next_metadata_total > MOPS_SUCCESS_CUSTODY_MAX_TOTAL_METADATA_BYTES:
                raise MOPSSuccessResponseCustodyError(
                    "MOPS sidecar metadata total exceeds 4 MiB"
                )
            self._require_free_space(len(encoded_metadata))
            metadata_relative = item.raw_path.removesuffix(".entity") + ".metadata.json"
            metadata_path = self.capture_root / metadata_relative
            _write_create_only(metadata_path, encoded_metadata)
            metadata_sha256 = sha256(encoded_metadata).hexdigest()
            self.total_metadata_bytes = next_metadata_total
            components.append(
                {
                    "market": result.market,
                    "announcement_item": result.announcement_item,
                    "query_start_date": result.query_start_date.isoformat(),
                    "query_end_date": result.query_end_date.isoformat(),
                    "attempt": attempt.attempt_number,
                    "raw_entity_path": item.raw_path,
                    "raw_entity_sha256": f"sha256:{item.raw_sha256}",
                    "raw_entity_bytes": item.raw_bytes,
                    "metadata_path": metadata_relative,
                    "metadata_sha256": f"sha256:{metadata_sha256}",
                }
            )
        receipt: dict[str, object] = {
            "schema_version": MOPS_SUCCESS_CUSTODY_SCHEMA,
            "status": "captured" if components else "empty",
            "run_id": self.run_root.name,
            "selected_start_date": selected_start.isoformat(),
            "selected_end_date": selected_end.isoformat(),
            "query_count": len(query_manifest),
            "collection_started_at_utc": self.collection_started_at.isoformat(),
            "artifact_captured_at_utc": artifact_captured_at.isoformat(),
            "collection_completed_at_utc": collection_completed_at.isoformat(),
            "artifact_path": artifact.name,
            "artifact_sha256": f"sha256:{artifact_sha256}",
            "component_count": len(components),
            "aggregate_raw_bytes": self.total_raw_bytes,
            "aggregate_success_entity_bytes": self.total_success_entity_bytes,
            "aggregate_failure_prefix_bytes": self.total_failure_prefix_bytes,
            "failure_prefix_count": self.failure_prefix_count,
            "aggregate_metadata_bytes": self.total_metadata_bytes,
            "max_raw_bytes": MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES,
            "max_metadata_bytes": MOPS_SUCCESS_CUSTODY_MAX_TOTAL_METADATA_BYTES,
            "disk_reserve_bytes": MOPS_SUCCESS_CUSTODY_DISK_RESERVE_BYTES,
            "components": components,
            "research_only": True,
            "formal_oos_allowed": False,
            "formal_credit_authorized": False,
        }
        receipt_bytes = _canonical_json_bytes(receipt)
        if len(receipt_bytes) > MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES:
            raise MOPSSuccessResponseCustodyError(
                "MOPS custody receipt exceeds 64 KiB"
            )
        self._require_free_space(len(receipt_bytes))
        _write_create_only(self.capture_root / MOPS_SUCCESS_CUSTODY_RECEIPT, receipt_bytes)
        return receipt

    def _require_free_space(self, incoming_bytes: int) -> None:
        try:
            free_bytes = shutil.disk_usage(self.run_root).free
        except OSError as error:
            raise MOPSSuccessResponseCustodyError(
                "MOPS custody cannot inspect free disk space"
            ) from error
        if free_bytes - incoming_bytes < MOPS_SUCCESS_CUSTODY_DISK_RESERVE_BYTES:
            raise MOPSSuccessResponseCustodyError(
                "MOPS custody write would breach the 16 MiB disk reserve"
            )

    @staticmethod
    def _validate_success_attempt(
        result: MOPSQueryResult,
        attempt: MOPSQueryAttempt,
    ) -> None:
        if (
            attempt.source_status != result.source_status
            or attempt.http_status != 200
            or attempt.response_url != MOPS_EZSEARCH_QUERY_URL
            or attempt.raw_body_hash_scope != "full_body"
            or not attempt.success_entity_bytes
            or attempt.raw_body_bytes_read != len(attempt.success_entity_bytes)
            or attempt.raw_body_sha256 != sha256(attempt.success_entity_bytes).hexdigest()
        ):
            raise MOPSSuccessResponseCustodyError(
                "MOPS successful attempt lacks a complete matching official entity"
            )
        started_at = _parse_utc_timestamp(attempt.started_at_utc, "started_at_utc")
        completed_at = _parse_utc_timestamp(attempt.completed_at_utc, "completed_at_utc")
        if completed_at < started_at:
            raise MOPSSuccessResponseCustodyError(
                "MOPS response completion precedes request start"
            )
        if attempt.content_length_header:
            try:
                content_length = int(attempt.content_length_header)
            except ValueError as error:
                raise MOPSSuccessResponseCustodyError(
                    "MOPS Content-Length is invalid"
                ) from error
            if content_length != len(attempt.success_entity_bytes):
                raise MOPSSuccessResponseCustodyError(
                    "MOPS Content-Length differs from preserved entity bytes"
                )


def read_mops_success_response_custody(
    *,
    capture_root: Path,
    artifact_path: Path,
) -> dict[str, object]:
    """以 bounded regular-file 讀回驗證 receipt、raw entity 與 legacy artifact。"""

    root = Path(os.path.abspath(str(capture_root.expanduser())))
    artifact = Path(os.path.abspath(str(artifact_path.expanduser())))
    if root.name != MOPS_SUCCESS_CUSTODY_DIRECTORY or root.parent != artifact.parent:
        raise MOPSSuccessResponseCustodyError(
            "MOPS capture root and artifact do not share the expected run root"
        )
    try:
        _assert_no_reparse_chain(root)
        receipt_raw = _read_bounded_file(
            root / MOPS_SUCCESS_CUSTODY_RECEIPT,
            label="MOPS custody receipt",
            max_bytes=MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES,
        )
        artifact_raw = _read_bounded_file(
            artifact,
            label="MOPS statement artifact",
            max_bytes=MOPS_SUCCESS_CUSTODY_MAX_ARTIFACT_BYTES,
        )
    except CaptureValidationError as error:
        raise MOPSSuccessResponseCustodyError(
            "MOPS receipt or artifact file custody check failed"
        ) from error
    receipt = _decode_json_object(receipt_raw, "MOPS custody receipt")
    artifact_body = _decode_json_object(artifact_raw, "MOPS statement artifact")
    artifact_sha256 = sha256(artifact_raw).hexdigest()
    if (
        receipt.get("schema_version") != MOPS_SUCCESS_CUSTODY_SCHEMA
        or receipt.get("status") not in {"captured", "empty"}
        or receipt.get("artifact_path") != artifact.name
        or receipt.get("artifact_sha256") != f"sha256:{artifact_sha256}"
        or receipt.get("research_only") is not True
        or receipt.get("formal_oos_allowed") is not False
        or receipt.get("formal_credit_authorized") is not False
    ):
        raise MOPSSuccessResponseCustodyError("MOPS custody receipt contract is invalid")
    expected_receipt_fields = {
        "schema_version",
        "status",
        "run_id",
        "selected_start_date",
        "selected_end_date",
        "query_count",
        "collection_started_at_utc",
        "artifact_captured_at_utc",
        "collection_completed_at_utc",
        "artifact_path",
        "artifact_sha256",
        "component_count",
        "aggregate_raw_bytes",
        "aggregate_success_entity_bytes",
        "aggregate_failure_prefix_bytes",
        "failure_prefix_count",
        "aggregate_metadata_bytes",
        "max_raw_bytes",
        "max_metadata_bytes",
        "disk_reserve_bytes",
        "components",
        "research_only",
        "formal_oos_allowed",
        "formal_credit_authorized",
    }
    if set(receipt) != expected_receipt_fields:
        raise MOPSSuccessResponseCustodyError("MOPS custody receipt schema is invalid")
    if (
        receipt.get("max_raw_bytes") != MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES
        or receipt.get("max_metadata_bytes")
        != MOPS_SUCCESS_CUSTODY_MAX_TOTAL_METADATA_BYTES
        or receipt.get("disk_reserve_bytes") != MOPS_SUCCESS_CUSTODY_DISK_RESERVE_BYTES
    ):
        raise MOPSSuccessResponseCustodyError("MOPS custody receipt bounds differ")
    collection_started = _parse_utc_timestamp(
        receipt.get("collection_started_at_utc"), "receipt.collection_started_at_utc"
    )
    artifact_captured = _parse_utc_timestamp(
        receipt.get("artifact_captured_at_utc"), "receipt.artifact_captured_at_utc"
    )
    collection_completed = _parse_utc_timestamp(
        receipt.get("collection_completed_at_utc"), "receipt.collection_completed_at_utc"
    )
    artifact_captured_body = _parse_timestamp(
        artifact_body.get("captured_at"), "artifact.captured_at"
    ).astimezone(timezone.utc)
    artifact_start = _parse_iso_date(
        artifact_body.get("query_start_date"), "artifact.query_start_date"
    )
    artifact_end = _parse_iso_date(
        artifact_body.get("query_end_date"), "artifact.query_end_date"
    )
    query_manifest = artifact_body.get("query_manifest")
    if not isinstance(query_manifest, list):
        raise MOPSSuccessResponseCustodyError(
            "MOPS legacy artifact query manifest is invalid"
        )
    if (
        receipt.get("run_id") != root.parent.name
        or receipt.get("selected_start_date") != artifact_start.isoformat()
        or receipt.get("selected_end_date") != artifact_end.isoformat()
        or artifact_end < artifact_start
        or type(receipt.get("query_count")) is not int
        or receipt.get("query_count") != len(query_manifest)
        or artifact_captured != artifact_captured_body
        or not collection_started <= artifact_captured <= collection_completed
    ):
        raise MOPSSuccessResponseCustodyError(
            "MOPS custody receipt collection identity/time bounds differ"
        )
    _validate_legacy_artifact_flags(artifact_body)
    components = receipt.get("components")
    if not isinstance(components, list) or len(components) > MOPS_SUCCESS_CUSTODY_MAX_COMPONENTS:
        raise MOPSSuccessResponseCustodyError("MOPS custody component list is invalid")
    if receipt.get("component_count") != len(components):
        raise MOPSSuccessResponseCustodyError("MOPS custody component count differs")
    if receipt.get("status") == "empty" and components:
        raise MOPSSuccessResponseCustodyError("empty MOPS receipt contains components")
    failure_prefix_bytes, failure_prefix_count = _verified_failure_prefixes(
        query_manifest,
        run_root=root.parent,
    )
    total_success_entity = 0
    total_metadata = 0
    verified: list[dict[str, object]] = []
    seen_component_keys: set[tuple[str, str, str, str]] = set()
    for component in components:
        if not isinstance(component, Mapping):
            raise MOPSSuccessResponseCustodyError("MOPS custody component is invalid")
        expected_component_fields = {
            "market",
            "announcement_item",
            "query_start_date",
            "query_end_date",
            "attempt",
            "raw_entity_path",
            "raw_entity_sha256",
            "raw_entity_bytes",
            "metadata_path",
            "metadata_sha256",
        }
        if set(component) != expected_component_fields:
            raise MOPSSuccessResponseCustodyError("MOPS custody component schema is invalid")
        component_key = (
            str(component.get("market", "")),
            str(component.get("announcement_item", "")),
            str(component.get("query_start_date", "")),
            str(component.get("query_end_date", "")),
        )
        if component_key in seen_component_keys:
            raise MOPSSuccessResponseCustodyError("MOPS custody contains duplicate query identity")
        seen_component_keys.add(component_key)
        raw_relative = _required_relative_path(component.get("raw_entity_path"), "raw entity")
        metadata_relative = _required_relative_path(component.get("metadata_path"), "metadata")
        if not metadata_relative.endswith(".metadata.json") or not raw_relative.endswith(".entity"):
            raise MOPSSuccessResponseCustodyError("MOPS custody component suffix is invalid")
        if metadata_relative != raw_relative.removesuffix(".entity") + ".metadata.json":
            raise MOPSSuccessResponseCustodyError("MOPS metadata path does not match raw path")
        raw = _read_bounded_file(
            root.joinpath(*raw_relative.split("/")),
            label="MOPS successful raw entity",
            max_bytes=MOPS_RESPONSE_MAX_BYTES,
        )
        metadata_raw = _read_bounded_file(
            root.joinpath(*metadata_relative.split("/")),
            label="MOPS successful response metadata",
            max_bytes=MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES,
        )
        if (
            not _is_sha256_value(component.get("raw_entity_sha256"))
            or f"sha256:{sha256(raw).hexdigest()}" != component.get("raw_entity_sha256")
        ):
            raise MOPSSuccessResponseCustodyError("MOPS raw entity hash differs from receipt")
        if type(component.get("raw_entity_bytes")) is not int or len(raw) != component.get("raw_entity_bytes"):
            raise MOPSSuccessResponseCustodyError("MOPS raw entity size differs from receipt")
        if (
            not _is_sha256_value(component.get("metadata_sha256"))
            or f"sha256:{sha256(metadata_raw).hexdigest()}" != component.get("metadata_sha256")
        ):
            raise MOPSSuccessResponseCustodyError("MOPS metadata hash differs from receipt")
        metadata = _decode_json_object(metadata_raw, "MOPS successful response metadata")
        _verify_sidecar_metadata(
            metadata,
            raw=raw,
            artifact_body=artifact_body,
            artifact_name=artifact.name,
            raw_relative=raw_relative,
            component=component,
            artifact_sha256=artifact_sha256,
            collection_started_at=collection_started,
            artifact_captured_at=artifact_captured,
        )
        total_success_entity += len(raw)
        total_metadata += len(metadata_raw)
        verified.append(
            {
                "market": metadata.get("market"),
                "announcement_item": metadata.get("announcement_item"),
                "query_start_date": metadata.get("query_start_date"),
                "query_end_date": metadata.get("query_end_date"),
                "raw_entity_sha256": component.get("raw_entity_sha256"),
                "legacy_canonical_json_sha256": metadata.get("legacy_canonical_json_sha256"),
            }
        )
    if (
        total_success_entity + failure_prefix_bytes != receipt.get("aggregate_raw_bytes")
        or total_success_entity != receipt.get("aggregate_success_entity_bytes")
        or failure_prefix_bytes != receipt.get("aggregate_failure_prefix_bytes")
        or failure_prefix_count != receipt.get("failure_prefix_count")
        or total_metadata != receipt.get("aggregate_metadata_bytes")
        or total_success_entity + failure_prefix_bytes
        > MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES
        or total_metadata > MOPS_SUCCESS_CUSTODY_MAX_TOTAL_METADATA_BYTES
    ):
        raise MOPSSuccessResponseCustodyError("MOPS custody aggregate byte totals differ")
    readback_path = root / MOPS_SUCCESS_CUSTODY_READBACK
    readback_verified = False
    if readback_path.exists() or readback_path.is_symlink():
        readback_raw = _read_bounded_file(
            readback_path,
            label="MOPS source readback receipt",
            max_bytes=MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES,
        )
        readback = _decode_json_object(readback_raw, "MOPS source readback receipt")
        expected_readback_fields = {
            "schema_version",
            "status",
            "run_id",
            "capture_receipt_sha256",
            "artifact_sha256",
            "verified_at_utc",
            "component_count",
            "components",
            "research_only",
            "formal_oos_allowed",
            "formal_credit_authorized",
        }
        verified_at = _parse_utc_timestamp(
            readback.get("verified_at_utc"), "readback.verified_at_utc"
        )
        if (
            set(readback) != expected_readback_fields
            or readback.get("schema_version") != MOPS_SUCCESS_CUSTODY_READBACK_SCHEMA
            or readback.get("status") != "verified"
            or readback.get("run_id") != root.parent.name
            or readback.get("capture_receipt_sha256")
            != f"sha256:{sha256(receipt_raw).hexdigest()}"
            or readback.get("artifact_sha256") != f"sha256:{artifact_sha256}"
            or type(readback.get("component_count")) is not int
            or readback.get("component_count") != len(verified)
            or readback.get("components") != verified
            or readback.get("research_only") is not True
            or readback.get("formal_oos_allowed") is not False
            or readback.get("formal_credit_authorized") is not False
            or verified_at < collection_completed
        ):
            raise MOPSSuccessResponseCustodyError(
                "MOPS source readback receipt differs from verified bytes"
            )
        readback_verified = True
    return {
        "status": str(receipt["status"]),
        "artifact_sha256": f"sha256:{artifact_sha256}",
        "component_count": len(verified),
        "aggregate_raw_bytes": total_success_entity + failure_prefix_bytes,
        "aggregate_success_entity_bytes": total_success_entity,
        "aggregate_failure_prefix_bytes": failure_prefix_bytes,
        "failure_prefix_count": failure_prefix_count,
        "aggregate_metadata_bytes": total_metadata,
        "components": verified,
        "source_readback_status": "verified" if readback_verified else "not_written",
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
    }


def write_mops_success_response_readback(
    *,
    capture_root: Path,
    artifact_path: Path,
) -> dict[str, object]:
    """先重驗已封存 bytes，再 create-only 寫入來源讀回收據。"""

    root = Path(os.path.abspath(str(capture_root.expanduser())))
    artifact = Path(os.path.abspath(str(artifact_path.expanduser())))
    verified = read_mops_success_response_custody(
        capture_root=root,
        artifact_path=artifact,
    )
    capture_receipt_raw = _read_bounded_file(
        root / MOPS_SUCCESS_CUSTODY_RECEIPT,
        label="MOPS custody receipt",
        max_bytes=MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES,
    )
    payload: dict[str, object] = {
        "schema_version": MOPS_SUCCESS_CUSTODY_READBACK_SCHEMA,
        "status": "verified",
        "run_id": root.parent.name,
        "capture_receipt_sha256": f"sha256:{sha256(capture_receipt_raw).hexdigest()}",
        "artifact_sha256": verified["artifact_sha256"],
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "component_count": verified["component_count"],
        "components": verified["components"],
        "research_only": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
    }
    encoded = _canonical_json_bytes(payload)
    if len(encoded) > MOPS_SUCCESS_CUSTODY_MAX_METADATA_FILE_BYTES:
        raise MOPSSuccessResponseCustodyError(
            "MOPS source readback receipt exceeds 64 KiB"
        )
    try:
        free_bytes = shutil.disk_usage(root.parent).free
    except OSError as error:
        raise MOPSSuccessResponseCustodyError(
            "MOPS custody cannot inspect free disk space for source readback"
        ) from error
    if free_bytes - len(encoded) < MOPS_SUCCESS_CUSTODY_DISK_RESERVE_BYTES:
        raise MOPSSuccessResponseCustodyError(
            "MOPS source readback write would breach the 16 MiB disk reserve"
        )
    _write_create_only(root / MOPS_SUCCESS_CUSTODY_READBACK, encoded)
    return payload


def _verify_sidecar_metadata(
    metadata: Mapping[str, object],
    *,
    raw: bytes,
    artifact_body: Mapping[str, object],
    artifact_name: str,
    raw_relative: str,
    component: Mapping[str, object],
    artifact_sha256: str,
    collection_started_at: datetime,
    artifact_captured_at: datetime,
) -> None:
    expected_fields = {
        "schema_version",
        "source_url",
        "market",
        "announcement_item",
        "query_start_date",
        "query_end_date",
        "query_payload",
        "source_status",
        "row_count",
        "raw_entity_path",
        "raw_entity_sha256",
        "raw_entity_bytes",
        "legacy_canonical_json_sha256",
        "artifact_path",
        "artifact_sha256",
        "attempt_count",
        "retry_error_codes",
        "attempt_lineage",
        "http",
        "research_only",
        "formal_oos_allowed",
        "formal_credit_authorized",
    }
    if set(metadata) != expected_fields or metadata.get("schema_version") != MOPS_SUCCESS_CUSTODY_SCHEMA:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar metadata schema is invalid")
    if metadata.get("source_url") != MOPS_EZSEARCH_QUERY_URL:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar source URL is unsupported")
    market = metadata.get("market")
    item = metadata.get("announcement_item")
    if not isinstance(market, str) or not isinstance(item, str) or market not in MOPS_MARKETS or item not in MOPS_STATEMENT_ITEMS:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar market/item is invalid")
    start = _parse_iso_date(metadata.get("query_start_date"), "query_start_date")
    end = _parse_iso_date(metadata.get("query_end_date"), "query_end_date")
    if end < start or (end - start).days >= 31:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar query window is invalid")
    expected_payload = build_query_payload(
        market=str(market),
        announcement_item=str(item),
        start_date=start,
        end_date=end,
    )
    if metadata.get("query_payload") != expected_payload:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar query payload differs")
    if (
        metadata.get("artifact_path") != artifact_name
        or metadata.get("artifact_sha256") != f"sha256:{artifact_sha256}"
    ):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar artifact binding differs")
    if (
        metadata.get("raw_entity_path") != raw_relative
        or component.get("raw_entity_path") != raw_relative
        or component.get("metadata_path")
        != raw_relative.removesuffix(".entity") + ".metadata.json"
        or component.get("market") != market
        or component.get("announcement_item") != item
        or component.get("query_start_date") != start.isoformat()
        or component.get("query_end_date") != end.isoformat()
        or component.get("raw_entity_sha256") != metadata.get("raw_entity_sha256")
        or component.get("raw_entity_bytes") != metadata.get("raw_entity_bytes")
    ):
        raise MOPSSuccessResponseCustodyError("MOPS receipt component identity differs")
    if (
        type(metadata.get("raw_entity_bytes")) is not int
        or type(metadata.get("row_count")) is not int
        or type(metadata.get("attempt_count")) is not int
        or component.get("attempt") != metadata.get("attempt_count")
    ):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar count fields are invalid")
    http = metadata.get("http")
    if not isinstance(http, Mapping):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar HTTP metadata is invalid")
    if (
        http.get("request_url") != MOPS_EZSEARCH_QUERY_URL
        or http.get("final_url") != MOPS_EZSEARCH_QUERY_URL
        or http.get("status_code") != 200
        or not isinstance(http.get("content_type"), str)
        or not isinstance(http.get("content_encoding"), str)
    ):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar HTTP source identity is invalid")
    started = _parse_utc_timestamp(http.get("started_at_utc"), "started_at_utc")
    completed = _parse_utc_timestamp(http.get("completed_at_utc"), "completed_at_utc")
    if (
        completed < started
        or completed > artifact_captured_at
        or started < collection_started_at
    ):
        raise MOPSSuccessResponseCustodyError("MOPS response completion time is invalid")
    if metadata.get("source_status") not in {"success", "fail"}:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar status is invalid")
    if metadata.get("research_only") is not True or metadata.get("formal_oos_allowed") is not False:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar research boundary is invalid")
    if metadata.get("formal_credit_authorized") is not False:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar must not grant formal credit")
    if len(raw) > MOPS_RESPONSE_MAX_BYTES or metadata.get("raw_entity_bytes") != len(raw):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar entity size is invalid")
    raw_hash = sha256(raw).hexdigest()
    if metadata.get("raw_entity_sha256") != f"sha256:{raw_hash}":
        raise MOPSSuccessResponseCustodyError("MOPS sidecar entity hash is invalid")
    if http.get("content_length"):
        try:
            if int(str(http["content_length"])) != len(raw):
                raise MOPSSuccessResponseCustodyError("MOPS sidecar Content-Length differs")
        except ValueError as error:
            raise MOPSSuccessResponseCustodyError("MOPS sidecar Content-Length is invalid") from error
    decoded, decode_error, decoded_limit = _decode_response_body(
        raw,
        content_encoding=str(http.get("content_encoding") or ""),
    )
    if decode_error is not None or decoded is None or decoded_limit:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar entity cannot be decoded within bounds")
    try:
        body = json.loads(decoded.decode("utf-8-sig", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar entity is not valid JSON") from error
    if not isinstance(body, Mapping):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar entity JSON must be an object")
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    canonical_hash = sha256(canonical.encode("utf-8")).hexdigest()
    if metadata.get("legacy_canonical_json_sha256") != f"sha256:{canonical_hash}":
        raise MOPSSuccessResponseCustodyError("MOPS canonical JSON hash differs")
    rows = body.get("data")
    if rows is None:
        rows = []
    status = str(body.get("status", "")).strip()
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar data rows are invalid")
    if status != metadata.get("source_status") or len(rows) != metadata.get("row_count"):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar response status/row count differs")
    if status == "fail" and rows:
        raise MOPSSuccessResponseCustodyError("MOPS no-data response contains rows")
    query_manifest = artifact_body.get("query_manifest")
    if not isinstance(query_manifest, list):
        raise MOPSSuccessResponseCustodyError("MOPS legacy artifact query manifest is invalid")
    matches = [
        query
        for query in query_manifest
        if isinstance(query, Mapping)
        and query.get("market") == market
        and query.get("announcement_item") == item
        and query.get("query_start_date") == start.isoformat()
        and query.get("query_end_date") == end.isoformat()
        and query.get("response_sha256") == canonical_hash
        and query.get("source_status") == status
        and query.get("row_count") == len(rows)
    ]
    if len(matches) != 1:
        raise MOPSSuccessResponseCustodyError(
            "MOPS sidecar does not bind exactly one legacy query manifest entry"
        )
    lineage = metadata.get("attempt_lineage")
    if not isinstance(lineage, list) or not 1 <= len(lineage) <= 2:
        raise MOPSSuccessResponseCustodyError("MOPS sidecar attempt lineage is invalid")
    if metadata.get("attempt_count") != len(lineage):
        raise MOPSSuccessResponseCustodyError("MOPS sidecar attempt count differs")
    retry_errors: list[str] = []
    previous: datetime | None = None
    for index, item_value in enumerate(lineage, start=1):
        if not isinstance(item_value, Mapping) or item_value.get("attempt") != index:
            raise MOPSSuccessResponseCustodyError("MOPS sidecar attempt order is invalid")
        attempt_start = _parse_utc_timestamp(item_value.get("started_at_utc"), "attempt.started_at")
        attempt_end = _parse_utc_timestamp(item_value.get("completed_at_utc"), "attempt.completed_at")
        if (
            attempt_end < attempt_start
            or attempt_start < collection_started_at
            or attempt_end > artifact_captured_at
            or (previous is not None and attempt_start < previous)
        ):
            raise MOPSSuccessResponseCustodyError("MOPS sidecar attempt timestamps are invalid")
        if index < len(lineage):
            if item_value.get("source_status") != "error" or item_value.get("retryable") is not True:
                raise MOPSSuccessResponseCustodyError(
                    "MOPS retry lineage contains a non-retryable attempt"
                )
            error_code = item_value.get("error_code")
            if not isinstance(error_code, str) or not error_code:
                raise MOPSSuccessResponseCustodyError("MOPS retry error code is missing")
            retry_errors.append(error_code)
        previous = attempt_end
    terminal = lineage[-1]
    if (
        terminal.get("attempt") != metadata.get("attempt_count")
        or terminal.get("source_status") != status
        or terminal.get("http_status") != 200
        or terminal.get("raw_body_sha256") != raw_hash
        or terminal.get("raw_body_bytes_read") != len(raw)
        or terminal.get("raw_body_hash_scope") != "full_body"
        or terminal.get("response_url") != MOPS_EZSEARCH_QUERY_URL
        or terminal.get("completed_at_utc") != http.get("completed_at_utc")
    ):
        raise MOPSSuccessResponseCustodyError("MOPS terminal attempt does not match raw response")
    if metadata.get("retry_error_codes") != retry_errors:
        raise MOPSSuccessResponseCustodyError("MOPS retry error codes differ from attempt lineage")
    query_manifest_entry = cast(Mapping[str, object], matches[0])
    artifact_attempts = query_manifest_entry.get("attempts")
    if len(lineage) > 1:
        expected_attempts = [
            {key: value for key, value in item_value.items() if key not in {"response_url", "transfer_encoding"}}
            for item_value in lineage
        ]
        if artifact_attempts != expected_attempts:
            raise MOPSSuccessResponseCustodyError("MOPS artifact retry lineage differs")
    elif query_manifest_entry.get("attempt_count", 1) != 1:
        raise MOPSSuccessResponseCustodyError("MOPS artifact query attempt count differs")


def _attempt_lineage_item(attempt: MOPSQueryAttempt) -> dict[str, object]:
    return {
        **attempt.to_manifest_item(),
        "response_url": attempt.response_url,
        "transfer_encoding": attempt.transfer_encoding,
    }


def _verified_failure_prefixes(
    query_manifest: list[object],
    *,
    run_root: Path,
) -> tuple[int, int]:
    total_bytes = 0
    prefix_count = 0
    for query in query_manifest:
        if not isinstance(query, Mapping):
            raise MOPSSuccessResponseCustodyError("MOPS query manifest entry is invalid")
        attempts = query.get("attempts", [])
        if not isinstance(attempts, list):
            raise MOPSSuccessResponseCustodyError("MOPS query attempt list is invalid")
        for attempt in attempts:
            if not isinstance(attempt, Mapping):
                raise MOPSSuccessResponseCustodyError("MOPS query attempt entry is invalid")
            prefix_path = attempt.get("raw_body_prefix_path")
            prefix_bytes = attempt.get("raw_body_prefix_bytes")
            prefix_sha = attempt.get("raw_body_prefix_sha256")
            if prefix_path is None:
                if (
                    attempt.get("source_status") == "error"
                    and (prefix_bytes != 0 or prefix_sha)
                ):
                    raise MOPSSuccessResponseCustodyError(
                        "MOPS attempt omits its declared failed response prefix"
                    )
                continue
            if attempt.get("source_status") != "error":
                raise MOPSSuccessResponseCustodyError(
                    "MOPS successful attempt cannot reference a failure prefix"
                )
            relative = _required_relative_path(prefix_path, "failed response prefix")
            if not relative.startswith("raw_failed_attempts/"):
                raise MOPSSuccessResponseCustodyError(
                    "MOPS failed response prefix is outside raw_failed_attempts"
                )
            raw = _read_bounded_file(
                run_root.joinpath(*relative.split("/")),
                label="MOPS failed response prefix",
                max_bytes=MOPS_RESPONSE_PREFIX_BYTES,
            )
            if (
                type(prefix_bytes) is not int
                or prefix_bytes != len(raw)
                or not isinstance(prefix_sha, str)
                or prefix_sha != sha256(raw).hexdigest()
            ):
                raise MOPSSuccessResponseCustodyError(
                    "MOPS failed response prefix receipt differs from bytes"
                )
            total_bytes += len(raw)
            prefix_count += 1
            if total_bytes > MOPS_SUCCESS_CUSTODY_MAX_TOTAL_RAW_BYTES:
                raise MOPSSuccessResponseCustodyError(
                    "MOPS failed response prefixes exceed the per-run raw limit"
                )
    return total_bytes, prefix_count


def _write_create_only(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise MOPSSuccessResponseCustodyError(
            "MOPS sidecar path already exists"
        ) from error


def _read_bounded_file(path: Path, *, label: str, max_bytes: int) -> bytes:
    try:
        return _read_regular_single_link_file(path, label=label, max_bytes=max_bytes)
    except (CaptureValidationError, OSError) as error:
        raise MOPSSuccessResponseCustodyError(f"{label} bounded custody read failed") from error


def _decode_json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MOPSSuccessResponseCustodyError(f"{label} JSON is invalid") from error
    if not isinstance(value, Mapping):
        raise MOPSSuccessResponseCustodyError(f"{label} JSON must be an object")
    return {str(key): item for key, item in value.items()}


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _is_sha256_value(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _required_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value:
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} path is invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} path is not normalized")
    return value


def _parse_iso_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} is invalid")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} is invalid") from error
    if result.isoformat() != value:
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} is not canonical")
    return result


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} is invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} is invalid") from error
    if result.tzinfo is None:
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} must include a timezone")
    return result


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    result = _parse_timestamp(value, label)
    if result.utcoffset() != timezone.utc.utcoffset(result):
        raise MOPSSuccessResponseCustodyError(f"MOPS {label} must be UTC")
    return result.astimezone(timezone.utc)


def _validate_legacy_artifact_flags(value: Mapping[str, object]) -> None:
    if (
        value.get("schema_version") != "mops-ezsearch-statement-availability.v1"
        or value.get("research_only") is not True
        or value.get("formal_oos_allowed") is not False
        or value.get("formal_credit_authorized") is not False
        or value.get("production_blend_alpha_bp") != 0
    ):
        raise MOPSSuccessResponseCustodyError("MOPS legacy artifact safety flags are invalid")
