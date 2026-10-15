"""每日雙市場 cohort 時間依據的 fundamental snapshot V2 codec。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal

from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortPin
from data_module.fundamental_read_snapshot import (
    MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES,
    MAX_SNAPSHOT_REFERENCE_JSON_BYTES,
    FundamentalFilePin,
    FundamentalReadSnapshotBinding,
    FundamentalSnapshotSourceClock,
    _canonical_json_bytes,
    _canonical_sha256,
    _parse_reference_cutoff,
    _parse_snapshot_binding,
    _parse_snapshot_pin_tuple,
    _reject_json_constant,
    _unique_json_object,
    _validate_json_depth,
)


FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_V2_SCHEMA: Literal[
    "selection-fundamental-source-clock.snapshot.v2"
] = "selection-fundamental-source-clock.snapshot.v2"
FUNDAMENTAL_READ_SNAPSHOT_V2_SCHEMA: Literal[
    "selection-fundamental-read-snapshot.v2"
] = "selection-fundamental-read-snapshot.v2"
FUNDAMENTAL_SNAPSHOT_FINISHED_COHORT_V2_SCHEMA: Literal[
    "selection-fundamental-snapshot-finished-cohort.v2"
] = "selection-fundamental-snapshot-finished-cohort.v2"
FUNDAMENTAL_READ_SNAPSHOT_REFERENCE_V2_SCHEMA: Literal[
    "fundamental-read-snapshot-reference.v2"
] = "fundamental-read-snapshot-reference.v2"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_STOCK_CODE_RE = re.compile(r"^[0-9]{4,6}$")
_MAX_CLOCK_JSON_BYTES = MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES
_MAX_CLOCK_JSON_DEPTH = 48
_MAX_REFERENCE_JSON_DEPTH = 16


@dataclass(frozen=True, slots=True)
class FundamentalSnapshotSourceClockV2:
    """把 immutable daily cohort 與既有隔離 SQLite snapshot 綁在一起。"""

    database_path: str
    decision_cutoff: datetime
    declared_stock_codes: tuple[str, ...]
    schema_identity_sha256: str
    schema_descriptor: tuple[tuple[int, str, str, int, str | None, int], ...]
    database_file_pins_start: tuple[FundamentalFilePin, ...]
    database_file_pins_finish: tuple[FundamentalFilePin, ...]
    capture_file_pins_start: tuple[FundamentalFilePin, ...]
    capture_file_pins_finish: tuple[FundamentalFilePin, ...]
    snapshot_binding: FundamentalReadSnapshotBinding
    cohort_pin: DailyMonthlyRevenueCohortPin
    verified_markets: tuple[str, ...]
    cohort_validation_status: Literal["pass"] = "pass"
    schema_version: Literal["selection-fundamental-source-clock.snapshot.v2"] = (
        FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_V2_SCHEMA
    )
    source_id: Literal["sqlite.fundamental_current_observations"] = (
        "sqlite.fundamental_current_observations"
    )
    source_scope: Literal["current_observed_only"] = "current_observed_only"
    availability_status: Literal["cohort_hour_bound"] = "cohort_hour_bound"
    historical_pit_eligible: Literal[False] = False
    formal_pit_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        if type(self.database_path) is not str or not Path(self.database_path).is_absolute():
            raise ValueError("V2 database_path 必須是原始來源 canonical 絕對路徑")
        if type(self.decision_cutoff) is not datetime:
            raise TypeError("V2 decision_cutoff 必須是 datetime")
        if self.decision_cutoff.tzinfo is None or self.decision_cutoff.utcoffset() is None:
            raise ValueError("V2 decision_cutoff 必須帶時區")
        if (
            type(self.declared_stock_codes) is not tuple
            or not self.declared_stock_codes
            or len(self.declared_stock_codes) > 100_000
            or self.declared_stock_codes
            != tuple(sorted(set(self.declared_stock_codes)))
            or any(
                type(code) is not str or not _STOCK_CODE_RE.fullmatch(code)
                for code in self.declared_stock_codes
            )
        ):
            raise ValueError("V2 declared_stock_codes 必須是排序唯一的 bounded 清冊")
        if type(self.schema_identity_sha256) is not str or not _SHA256_RE.fullmatch(
            self.schema_identity_sha256
        ):
            raise ValueError("V2 schema_identity_sha256 格式錯誤")
        if type(self.schema_descriptor) is not tuple or not self.schema_descriptor:
            raise ValueError("V2 schema_descriptor 不可為空且必須是 tuple")
        for row in self.schema_descriptor:
            if (
                type(row) is not tuple
                or len(row) != 6
                or type(row[0]) is not int
                or type(row[1]) is not str
                or type(row[2]) is not str
                or type(row[3]) is not int
                or (row[4] is not None and type(row[4]) is not str)
                or type(row[5]) is not int
            ):
                raise ValueError("V2 schema_descriptor 列型別錯誤")
        for name in (
            "database_file_pins_start",
            "database_file_pins_finish",
            "capture_file_pins_start",
            "capture_file_pins_finish",
        ):
            pins = getattr(self, name)
            if type(pins) is not tuple or (name.startswith("database_") and not pins):
                raise ValueError(f"V2 {name} 必須是 tuple，database pins 不可為空")
            if any(type(pin) is not FundamentalFilePin for pin in pins):
                raise TypeError(f"V2 {name} pin 型別錯誤")
        if type(self.snapshot_binding) is not FundamentalReadSnapshotBinding:
            raise TypeError("V2 snapshot_binding 型別錯誤")
        if type(self.cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise TypeError("V2 cohort_pin 型別錯誤")
        if type(self.verified_markets) is not tuple or any(
            type(market) is not str for market in self.verified_markets
        ):
            raise ValueError("V2 verified_markets 必須是字串 tuple")
        if self.verified_markets != self.cohort_pin.required_markets:
            raise ValueError("V2 verified_markets 必須完整符合每日 cohort 所需市場")
        base_clock = FundamentalSnapshotSourceClock(
            database_path=self.database_path,
            decision_cutoff=self.decision_cutoff,
            declared_stock_codes=self.declared_stock_codes,
            schema_identity_sha256=self.schema_identity_sha256,
            schema_descriptor=self.schema_descriptor,
            database_file_pins_start=self.database_file_pins_start,
            database_file_pins_finish=self.database_file_pins_finish,
            capture_file_pins_start=self.capture_file_pins_start,
            capture_file_pins_finish=self.capture_file_pins_finish,
            snapshot_binding=self.snapshot_binding,
        )
        if type(base_clock) is not FundamentalSnapshotSourceClock:
            raise TypeError("V2 基礎 snapshot clock 型別錯誤")
        if self.cohort_pin.available_hour > self.decision_cutoff:
            raise ValueError("fundamental_snapshot_v2_cohort_after_decision_cutoff")
        if self.snapshot_binding.source_database_path != self.database_path:
            raise ValueError("V2 snapshot binding 必須指向 clock database")
        if (
            type(self.schema_version) is not str
            or self.schema_version != FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_V2_SCHEMA
        ):
            raise ValueError("V2 source clock schema 不支援")
        if (
            type(self.source_id) is not str
            or self.source_id != "sqlite.fundamental_current_observations"
        ):
            raise ValueError("V2 source id 不支援")
        if type(self.source_scope) is not str or self.source_scope != "current_observed_only":
            raise ValueError("V2 source scope 必須保持 current-only")
        if (
            type(self.availability_status) is not str
            or self.availability_status != "cohort_hour_bound"
        ):
            raise ValueError("V2 availability status 必須表達已固定 cohort 小時依據")
        if (
            type(self.cohort_validation_status) is not str
            or self.cohort_validation_status != "pass"
        ):
            raise ValueError("V2 cohort 必須通過完整市場重驗")
        if self.historical_pit_eligible is not False or self.formal_pit_eligible is not False:
            raise ValueError("V2 current-only cohort 不可標記為 PIT eligible")

    @classmethod
    def from_base_clock(
        cls,
        base: FundamentalSnapshotSourceClock,
        *,
        cohort_pin: DailyMonthlyRevenueCohortPin,
        verified_markets: tuple[str, ...],
    ) -> FundamentalSnapshotSourceClockV2:
        """沿用 V1 SQLite copy clock，另加已驗證的完整每日 cohort。"""

        if type(base) is not FundamentalSnapshotSourceClock:
            raise TypeError("V2 base clock 必須是 FundamentalSnapshotSourceClock")
        if type(cohort_pin) is not DailyMonthlyRevenueCohortPin:
            raise TypeError("V2 cohort_pin 型別錯誤")
        return cls(
            database_path=base.database_path,
            decision_cutoff=base.decision_cutoff,
            declared_stock_codes=base.declared_stock_codes,
            schema_identity_sha256=base.schema_identity_sha256,
            schema_descriptor=base.schema_descriptor,
            database_file_pins_start=base.database_file_pins_start,
            database_file_pins_finish=base.database_file_pins_finish,
            capture_file_pins_start=base.capture_file_pins_start,
            capture_file_pins_finish=base.capture_file_pins_finish,
            snapshot_binding=base.snapshot_binding,
            cohort_pin=cohort_pin,
            verified_markets=tuple(verified_markets),
        )

    @property
    def declared_stock_codes_sha256(self) -> str:
        return _canonical_sha256(list(self.declared_stock_codes))

    @property
    def cohort_sha256(self) -> str:
        return self.cohort_pin.cohort_sha256

    @property
    def source_content_identity_sha256(self) -> str:
        """來源內容身分包含完整 cohort pin，但不含單次 copy binding。"""

        return _canonical_sha256(self._content_payload())

    @property
    def source_pin_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    @property
    def identity_sha256(self) -> str:
        return self.source_pin_sha256

    def _content_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_scope": self.source_scope,
            "availability_status": self.availability_status,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "database_path": self.database_path,
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "schema_descriptor": [list(item) for item in self.schema_descriptor],
            "database_file_pins_start": [
                pin.to_dict() for pin in self.database_file_pins_start
            ],
            "database_file_pins_finish": [
                pin.to_dict() for pin in self.database_file_pins_finish
            ],
            "capture_file_pins_start": [
                pin.to_dict() for pin in self.capture_file_pins_start
            ],
            "capture_file_pins_finish": [
                pin.to_dict() for pin in self.capture_file_pins_finish
            ],
            "cohort_pin": self.cohort_pin.to_dict(),
            "cohort_sha256": self.cohort_sha256,
            "cohort_available_hour": self.cohort_pin.available_hour.isoformat(),
            "cohort_validation_status": self.cohort_validation_status,
            "verified_markets": list(self.verified_markets),
        }

    def _identity_payload(self) -> dict[str, object]:
        return {
            **self._content_payload(),
            "snapshot_binding": self.snapshot_binding.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["source_content_identity_sha256"] = self.source_content_identity_sha256
        payload["source_pin_sha256"] = self.source_pin_sha256
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def to_json(self) -> str:
        """輸出有界、canonical 的 V2 clock JSON。"""

        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > _MAX_CLOCK_JSON_BYTES:
            raise ValueError("fundamental_snapshot_source_clock_v2_exceeds_size_limit")
        return raw.decode("utf-8")

    @classmethod
    def from_json(cls, raw: str | bytes) -> FundamentalSnapshotSourceClockV2:
        """嚴格讀取 canonical V2 clock JSON，不接受重複或額外欄位。"""

        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            try:
                encoded = raw.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("fundamental_snapshot_source_clock_v2_not_utf8") from exc
        else:
            raise TypeError("fundamental_snapshot_source_clock_v2_json_type_invalid")
        if len(encoded) > _MAX_CLOCK_JSON_BYTES:
            raise ValueError("fundamental_snapshot_source_clock_v2_exceeds_size_limit")
        _validate_json_depth(encoded, max_depth=_MAX_CLOCK_JSON_DEPTH)
        try:
            payload = json.loads(
                encoded.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError("fundamental_snapshot_source_clock_v2_json_invalid") from exc
        if type(payload) is not dict:
            raise ValueError("fundamental_snapshot_source_clock_v2_json_object_required")
        clock = parse_snapshot_source_clock_v2(payload)
        if encoded != clock.to_json().encode("utf-8"):
            raise ValueError("fundamental_snapshot_source_clock_v2_not_canonical")
        return clock


_SOURCE_CLOCK_V2_KEYS = {
    "schema_version",
    "source_id",
    "source_scope",
    "availability_status",
    "historical_pit_eligible",
    "formal_pit_eligible",
    "database_path",
    "decision_cutoff",
    "declared_stock_codes",
    "declared_stock_codes_sha256",
    "schema_identity_sha256",
    "schema_descriptor",
    "database_file_pins_start",
    "database_file_pins_finish",
    "capture_file_pins_start",
    "capture_file_pins_finish",
    "cohort_pin",
    "cohort_sha256",
    "cohort_available_hour",
    "cohort_validation_status",
    "verified_markets",
    "snapshot_binding",
    "source_content_identity_sha256",
    "source_pin_sha256",
    "identity_sha256",
}


def parse_snapshot_source_clock_v2(value: object) -> FundamentalSnapshotSourceClockV2:
    """嚴格解析 V2 clock；V1 clock 及缺欄位/多欄位一律拒絕。"""

    if type(value) is not dict or set(value) != _SOURCE_CLOCK_V2_KEYS:
        raise ValueError("fundamental_snapshot_source_clock_v2_fields_invalid")
    string_keys = (
        "schema_version",
        "source_id",
        "source_scope",
        "availability_status",
        "database_path",
        "decision_cutoff",
        "declared_stock_codes_sha256",
        "schema_identity_sha256",
        "cohort_sha256",
        "cohort_available_hour",
        "cohort_validation_status",
        "source_content_identity_sha256",
        "source_pin_sha256",
        "identity_sha256",
    )
    if any(type(value[key]) is not str for key in string_keys):
        raise ValueError("fundamental_snapshot_source_clock_v2_string_type_invalid")
    if value["historical_pit_eligible"] is not False or value["formal_pit_eligible"] is not False:
        raise ValueError("fundamental_snapshot_source_clock_v2_pit_flags_invalid")
    raw_codes = value["declared_stock_codes"]
    raw_descriptor = value["schema_descriptor"]
    raw_markets = value["verified_markets"]
    if type(raw_codes) is not list or any(type(code) is not str for code in raw_codes):
        raise ValueError("fundamental_snapshot_source_clock_v2_codes_invalid")
    if type(raw_descriptor) is not list:
        raise ValueError("fundamental_snapshot_source_clock_v2_schema_descriptor_invalid")
    descriptor: list[tuple[int, str, str, int, str | None, int]] = []
    for row in raw_descriptor:
        if (
            type(row) is not list
            or len(row) != 6
            or type(row[0]) is not int
            or type(row[1]) is not str
            or type(row[2]) is not str
            or type(row[3]) is not int
            or (row[4] is not None and type(row[4]) is not str)
            or type(row[5]) is not int
        ):
            raise ValueError("fundamental_snapshot_source_clock_v2_schema_column_invalid")
        descriptor.append((row[0], row[1], row[2], row[3], row[4], row[5]))
    if type(raw_markets) is not list or any(type(item) is not str for item in raw_markets):
        raise ValueError("fundamental_snapshot_source_clock_v2_markets_invalid")
    if type(value["cohort_pin"]) is not dict:
        raise ValueError("fundamental_snapshot_source_clock_v2_cohort_pin_invalid")
    try:
        cohort_pin = DailyMonthlyRevenueCohortPin.from_dict(value["cohort_pin"])
        clock = FundamentalSnapshotSourceClockV2(
            database_path=value["database_path"],
            decision_cutoff=_parse_reference_cutoff(value["decision_cutoff"]),
            declared_stock_codes=tuple(raw_codes),
            schema_identity_sha256=value["schema_identity_sha256"],
            schema_descriptor=tuple(descriptor),
            database_file_pins_start=_parse_snapshot_pin_tuple(
                value["database_file_pins_start"]
            ),
            database_file_pins_finish=_parse_snapshot_pin_tuple(
                value["database_file_pins_finish"]
            ),
            capture_file_pins_start=_parse_snapshot_pin_tuple(
                value["capture_file_pins_start"]
            ),
            capture_file_pins_finish=_parse_snapshot_pin_tuple(
                value["capture_file_pins_finish"]
            ),
            snapshot_binding=_parse_snapshot_binding(value["snapshot_binding"]),
            cohort_pin=cohort_pin,
            verified_markets=tuple(raw_markets),
            cohort_validation_status=value["cohort_validation_status"],
            schema_version=value["schema_version"],
            source_id=value["source_id"],
            source_scope=value["source_scope"],
            availability_status=value["availability_status"],
            historical_pit_eligible=False,
            formal_pit_eligible=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("fundamental_snapshot_source_clock_v2_contract_invalid") from exc
    if (
        value["cohort_sha256"] != clock.cohort_sha256
        or value["cohort_available_hour"] != clock.cohort_pin.available_hour.isoformat()
        or value["declared_stock_codes_sha256"] != clock.declared_stock_codes_sha256
        or value["source_content_identity_sha256"]
        != clock.source_content_identity_sha256
        or value["source_pin_sha256"] != clock.source_pin_sha256
        or value["identity_sha256"] != clock.identity_sha256
        or clock.to_dict() != value
    ):
        raise ValueError("fundamental_snapshot_source_clock_v2_digest_mismatch")
    return clock


def _validate_finished_ledger_v2(
    *,
    session_id: str,
    reader_session_id: str,
    source_clock: FundamentalSnapshotSourceClockV2,
    processed_stock_codes: tuple[str, ...],
    result_identity_by_stock: tuple[tuple[str, str], ...],
    result_status_counts: tuple[tuple[str, int], ...],
) -> None:
    if type(session_id) is not str or not _SHA256_RE.fullmatch(session_id):
        raise ValueError("fundamental_snapshot_finished_v2_session_id_invalid")
    if type(reader_session_id) is not str or not _SHA256_RE.fullmatch(reader_session_id):
        raise ValueError("fundamental_snapshot_finished_v2_reader_session_id_invalid")
    if type(source_clock) is not FundamentalSnapshotSourceClockV2:
        raise TypeError("fundamental_snapshot_finished_v2_clock_type_invalid")
    if type(processed_stock_codes) is not tuple or (
        processed_stock_codes != source_clock.declared_stock_codes
    ):
        raise ValueError("fundamental_snapshot_finished_v2_codes_incomplete")
    if type(result_identity_by_stock) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        or not _SHA256_RE.fullmatch(item[1])
        for item in result_identity_by_stock
    ):
        raise ValueError("fundamental_snapshot_finished_v2_result_identity_invalid")
    if tuple(code for code, _identity in result_identity_by_stock) != processed_stock_codes:
        raise ValueError("fundamental_snapshot_finished_v2_result_order_invalid")
    if type(result_status_counts) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or not item[0]
        or type(item[1]) is not int
        or item[1] < 0
        for item in result_status_counts
    ):
        raise ValueError("fundamental_snapshot_finished_v2_status_counts_invalid")
    if (
        tuple(status for status, _count in result_status_counts)
        != tuple(sorted({status for status, _count in result_status_counts}))
        or sum(count for _status, count in result_status_counts) != len(processed_stock_codes)
    ):
        raise ValueError("fundamental_snapshot_finished_v2_status_counts_inconsistent")


def compute_finished_snapshot_cohort_identity_v2(
    *,
    session_id: str,
    reader_session_id: str,
    source_clock: FundamentalSnapshotSourceClockV2,
    processed_stock_codes: tuple[str, ...],
    result_identity_by_stock: tuple[tuple[str, str], ...],
    result_status_counts: tuple[tuple[str, int], ...],
) -> str:
    """計算不含 manifest bytes 的完成 identity，避免雜湊自我參照。"""

    _validate_finished_ledger_v2(
        session_id=session_id,
        reader_session_id=reader_session_id,
        source_clock=source_clock,
        processed_stock_codes=processed_stock_codes,
        result_identity_by_stock=result_identity_by_stock,
        result_status_counts=result_status_counts,
    )
    return _canonical_sha256(
        {
            "schema_version": FUNDAMENTAL_SNAPSHOT_FINISHED_COHORT_V2_SCHEMA,
            "session_id": session_id,
            "reader_session_id": reader_session_id,
            "source_clock_identity_sha256": source_clock.identity_sha256,
            "daily_cohort_sha256": source_clock.cohort_sha256,
            "processed_stock_codes": list(processed_stock_codes),
            "result_identity_by_stock": [list(item) for item in result_identity_by_stock],
            "result_status_counts": [list(item) for item in result_status_counts],
            "complete": True,
        }
    )


@dataclass(frozen=True, slots=True)
class FinishedFundamentalSnapshotReadCohortV2:
    """完成隔離 copy、每日 cohort 起訖重驗及全清冊讀取的 V2 token。"""

    session_id: str
    reader_session_id: str
    source_clock: FundamentalSnapshotSourceClockV2
    processed_stock_codes: tuple[str, ...]
    result_identity_by_stock: tuple[tuple[str, str], ...]
    result_status_counts: tuple[tuple[str, int], ...]
    finished_manifest_sha256: str
    complete: Literal[True] = True

    def __post_init__(self) -> None:
        _validate_finished_ledger_v2(
            session_id=self.session_id,
            reader_session_id=self.reader_session_id,
            source_clock=self.source_clock,
            processed_stock_codes=self.processed_stock_codes,
            result_identity_by_stock=self.result_identity_by_stock,
            result_status_counts=self.result_status_counts,
        )
        if type(self.finished_manifest_sha256) is not str or not _SHA256_RE.fullmatch(
            self.finished_manifest_sha256
        ):
            raise ValueError("fundamental_snapshot_finished_v2_manifest_sha_invalid")
        if self.complete is not True:
            raise ValueError("FinishedFundamentalSnapshotReadCohortV2 必須 complete")

    @property
    def identity_sha256(self) -> str:
        return compute_finished_snapshot_cohort_identity_v2(
            session_id=self.session_id,
            reader_session_id=self.reader_session_id,
            source_clock=self.source_clock,
            processed_stock_codes=self.processed_stock_codes,
            result_identity_by_stock=self.result_identity_by_stock,
            result_status_counts=self.result_status_counts,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": FUNDAMENTAL_SNAPSHOT_FINISHED_COHORT_V2_SCHEMA,
            "session_id": self.session_id,
            "reader_session_id": self.reader_session_id,
            "source_clock": self.source_clock.to_dict(),
            "source_clock_identity_sha256": self.source_clock.identity_sha256,
            "daily_cohort_sha256": self.source_clock.cohort_sha256,
            "processed_stock_codes": list(self.processed_stock_codes),
            "result_identity_by_stock": [
                list(item) for item in self.result_identity_by_stock
            ],
            "result_status_counts": [list(item) for item in self.result_status_counts],
            "availability_status": self.source_clock.availability_status,
            "source_scope": self.source_clock.source_scope,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "finished_manifest_sha256": self.finished_manifest_sha256,
            "complete": True,
            "identity_sha256": self.identity_sha256,
        }


def make_finished_snapshot_manifest_v2(
    *,
    session_id: str,
    reader_session_id: str,
    source_clock: FundamentalSnapshotSourceClockV2,
    processed_stock_codes: tuple[str, ...],
    result_identity_by_stock: tuple[tuple[str, str], ...],
    result_status_counts: tuple[tuple[str, int], ...],
    manifest_state: Literal["candidate_pending_publication", "complete"],
) -> dict[str, object]:
    """建立含內層與外層 identity 的 V2 manifest，不寫檔也不授予完成資格。"""

    if type(manifest_state) is not str or manifest_state not in {
        "candidate_pending_publication",
        "complete",
    }:
        raise ValueError("fundamental_snapshot_manifest_v2_state_invalid")
    cohort_identity = compute_finished_snapshot_cohort_identity_v2(
        session_id=session_id,
        reader_session_id=reader_session_id,
        source_clock=source_clock,
        processed_stock_codes=processed_stock_codes,
        result_identity_by_stock=result_identity_by_stock,
        result_status_counts=result_status_counts,
    )
    manifest: dict[str, object] = {
        "schema_version": FUNDAMENTAL_READ_SNAPSHOT_V2_SCHEMA,
        "manifest_state": manifest_state,
        "snapshot_binding": source_clock.snapshot_binding.to_dict(),
        "source_clock": source_clock.to_dict(),
        "cohort_identity_sha256": cohort_identity,
        "cohort_pin_sha256": source_clock.cohort_sha256,
        "finished_cohort": {
            "session_id": session_id,
            "reader_session_id": reader_session_id,
            "processed_stock_codes": list(processed_stock_codes),
            "result_identity_by_stock": [list(item) for item in result_identity_by_stock],
            "result_status_counts": [list(item) for item in result_status_counts],
            "source_clock_identity_sha256": source_clock.identity_sha256,
            "daily_cohort_sha256": source_clock.cohort_sha256,
            "complete": True,
            "identity_sha256": cohort_identity,
        },
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    if len(_canonical_json_bytes(manifest)) > MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES:
        raise ValueError("fundamental_snapshot_manifest_v2_exceeds_size_limit")
    return manifest


_FINISHED_MANIFEST_V2_KEYS = {
    "schema_version",
    "manifest_state",
    "snapshot_binding",
    "source_clock",
    "cohort_identity_sha256",
    "cohort_pin_sha256",
    "finished_cohort",
    "manifest_sha256",
}
_FINISHED_LEDGER_V2_KEYS = {
    "session_id",
    "reader_session_id",
    "processed_stock_codes",
    "result_identity_by_stock",
    "result_status_counts",
    "source_clock_identity_sha256",
    "daily_cohort_sha256",
    "complete",
    "identity_sha256",
}


def parse_finished_snapshot_cohort_v2(
    complete_manifest: object,
    source_clock: FundamentalSnapshotSourceClockV2,
) -> FinishedFundamentalSnapshotReadCohortV2:
    """解析完整 manifest，並以 canonical bytes 摘要發布 finished token。"""

    if type(source_clock) is not FundamentalSnapshotSourceClockV2:
        raise TypeError("fundamental_snapshot_finished_v2_clock_type_invalid")
    if type(complete_manifest) is not dict or set(complete_manifest) != _FINISHED_MANIFEST_V2_KEYS:
        raise ValueError("fundamental_snapshot_finished_manifest_v2_fields_invalid")
    if (
        complete_manifest.get("schema_version") != FUNDAMENTAL_READ_SNAPSHOT_V2_SCHEMA
        or complete_manifest.get("manifest_state") != "complete"
    ):
        raise ValueError("fundamental_snapshot_finished_manifest_v2_not_complete")
    manifest_digest = complete_manifest.get("manifest_sha256")
    if type(manifest_digest) is not str or not _SHA256_RE.fullmatch(manifest_digest):
        raise ValueError("fundamental_snapshot_finished_manifest_v2_sha_invalid")
    body = {
        key: value for key, value in complete_manifest.items() if key != "manifest_sha256"
    }
    if manifest_digest != _canonical_sha256(body):
        raise ValueError("fundamental_snapshot_finished_manifest_v2_digest_mismatch")
    if (
        complete_manifest.get("cohort_pin_sha256") != source_clock.cohort_sha256
        or complete_manifest.get("snapshot_binding") != source_clock.snapshot_binding.to_dict()
    ):
        raise ValueError("fundamental_snapshot_finished_manifest_v2_binding_mismatch")
    parsed_clock = parse_snapshot_source_clock_v2(complete_manifest.get("source_clock"))
    if parsed_clock.to_dict() != source_clock.to_dict():
        raise ValueError("fundamental_snapshot_finished_manifest_v2_clock_mismatch")
    ledger = complete_manifest.get("finished_cohort")
    if type(ledger) is not dict or set(ledger) != _FINISHED_LEDGER_V2_KEYS:
        raise ValueError("fundamental_snapshot_finished_ledger_v2_fields_invalid")
    for key in (
        "session_id",
        "reader_session_id",
        "source_clock_identity_sha256",
        "daily_cohort_sha256",
        "identity_sha256",
    ):
        if type(ledger[key]) is not str:
            raise ValueError("fundamental_snapshot_finished_ledger_v2_string_type_invalid")
    if ledger["complete"] is not True:
        raise ValueError("fundamental_snapshot_finished_ledger_v2_incomplete")
    codes_raw = ledger["processed_stock_codes"]
    identities_raw = ledger["result_identity_by_stock"]
    counts_raw = ledger["result_status_counts"]
    if type(codes_raw) is not list or any(type(code) is not str for code in codes_raw):
        raise ValueError("fundamental_snapshot_finished_ledger_v2_codes_invalid")
    if type(identities_raw) is not list or any(
        type(item) is not list
        or len(item) != 2
        or any(type(part) is not str for part in item)
        for item in identities_raw
    ):
        raise ValueError("fundamental_snapshot_finished_ledger_v2_result_invalid")
    if type(counts_raw) is not list or any(
        type(item) is not list
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not int
        for item in counts_raw
    ):
        raise ValueError("fundamental_snapshot_finished_ledger_v2_counts_invalid")
    processed = tuple(codes_raw)
    identities = tuple((item[0], item[1]) for item in identities_raw)
    counts = tuple((item[0], item[1]) for item in counts_raw)
    expected_identity = compute_finished_snapshot_cohort_identity_v2(
        session_id=ledger["session_id"],
        reader_session_id=ledger["reader_session_id"],
        source_clock=source_clock,
        processed_stock_codes=processed,
        result_identity_by_stock=identities,
        result_status_counts=counts,
    )
    if (
        ledger["source_clock_identity_sha256"] != source_clock.identity_sha256
        or ledger["daily_cohort_sha256"] != source_clock.cohort_sha256
        or ledger["identity_sha256"] != expected_identity
        or complete_manifest.get("cohort_identity_sha256") != expected_identity
    ):
        raise ValueError("fundamental_snapshot_finished_ledger_v2_identity_mismatch")
    # 寫入端使用 canonical JSON；core 在把這個 token 發布前仍須比對原始檔 bytes。
    manifest_raw = _canonical_json_bytes(complete_manifest)
    if len(manifest_raw) > MAX_FINISHED_SNAPSHOT_MANIFEST_BYTES:
        raise ValueError("fundamental_snapshot_finished_manifest_v2_exceeds_size_limit")
    return FinishedFundamentalSnapshotReadCohortV2(
        session_id=ledger["session_id"],
        reader_session_id=ledger["reader_session_id"],
        source_clock=source_clock,
        processed_stock_codes=processed,
        result_identity_by_stock=identities,
        result_status_counts=counts,
        finished_manifest_sha256=sha256(manifest_raw).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class FundamentalReadSnapshotReferenceV2:
    """V2 完成 snapshot 的傳輸參照；接受資格須由外部 digest 提供。"""

    snapshot_root: str
    snapshot_id: str
    finished_manifest_sha256: str
    source_clock_identity_sha256: str
    source_content_identity_sha256: str
    cohort_identity_sha256: str
    daily_cohort_sha256: str
    decision_cutoff: str
    declared_stock_codes: tuple[str, ...]
    declared_stock_codes_sha256: str
    schema_version: Literal["fundamental-read-snapshot-reference.v2"] = (
        FUNDAMENTAL_READ_SNAPSHOT_REFERENCE_V2_SCHEMA
    )

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != FUNDAMENTAL_READ_SNAPSHOT_REFERENCE_V2_SCHEMA
        ):
            raise ValueError("fundamental_snapshot_reference_v2_schema_unsupported")
        if type(self.snapshot_root) is not str or not Path(self.snapshot_root).is_absolute():
            raise ValueError("fundamental_snapshot_reference_v2_root_invalid")
        if type(self.snapshot_id) is not str or not _SNAPSHOT_ID_RE.fullmatch(self.snapshot_id):
            raise ValueError("fundamental_snapshot_reference_v2_id_invalid")
        for value in (
            self.finished_manifest_sha256,
            self.source_clock_identity_sha256,
            self.source_content_identity_sha256,
            self.cohort_identity_sha256,
            self.daily_cohort_sha256,
            self.declared_stock_codes_sha256,
        ):
            if type(value) is not str or not _SHA256_RE.fullmatch(value):
                raise ValueError("fundamental_snapshot_reference_v2_sha_invalid")
        cutoff = _parse_reference_cutoff(self.decision_cutoff)
        if cutoff.isoformat() != self.decision_cutoff:
            raise ValueError("fundamental_snapshot_reference_v2_cutoff_not_canonical")
        if (
            type(self.declared_stock_codes) is not tuple
            or not self.declared_stock_codes
            or len(self.declared_stock_codes) > 100_000
            or self.declared_stock_codes
            != tuple(sorted(set(self.declared_stock_codes)))
            or any(
                type(code) is not str or not _STOCK_CODE_RE.fullmatch(code)
                for code in self.declared_stock_codes
            )
            or self.declared_stock_codes_sha256
            != _canonical_sha256(list(self.declared_stock_codes))
        ):
            raise ValueError("fundamental_snapshot_reference_v2_codes_invalid")

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self._identity_payload())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_root": self.snapshot_root,
            "snapshot_id": self.snapshot_id,
            "finished_manifest_sha256": self.finished_manifest_sha256,
            "source_clock_identity_sha256": self.source_clock_identity_sha256,
            "source_content_identity_sha256": self.source_content_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "daily_cohort_sha256": self.daily_cohort_sha256,
            "decision_cutoff": self.decision_cutoff,
            "declared_stock_codes": list(self.declared_stock_codes),
            "declared_stock_codes_sha256": self.declared_stock_codes_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._identity_payload()
        payload["identity_sha256"] = self.identity_sha256
        return payload

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > MAX_SNAPSHOT_REFERENCE_JSON_BYTES:
            raise ValueError("fundamental_snapshot_reference_v2_exceeds_size_limit")
        return raw.decode("utf-8")

    @classmethod
    def from_dict(
        cls,
        value: object,
        *,
        expected_reference_sha256: str,
    ) -> FundamentalReadSnapshotReferenceV2:
        if type(expected_reference_sha256) is not str or not _SHA256_RE.fullmatch(
            expected_reference_sha256
        ):
            raise ValueError("fundamental_snapshot_reference_v2_external_sha_invalid")
        if type(value) is not dict:
            raise ValueError("fundamental_snapshot_reference_v2_json_object_required")
        expected_keys = {
            "schema_version",
            "snapshot_root",
            "snapshot_id",
            "finished_manifest_sha256",
            "source_clock_identity_sha256",
            "source_content_identity_sha256",
            "cohort_identity_sha256",
            "daily_cohort_sha256",
            "decision_cutoff",
            "declared_stock_codes",
            "declared_stock_codes_sha256",
            "identity_sha256",
        }
        if set(value) != expected_keys:
            raise ValueError("fundamental_snapshot_reference_v2_fields_invalid")
        string_keys = expected_keys - {"declared_stock_codes"}
        if any(type(value[key]) is not str for key in string_keys):
            raise ValueError("fundamental_snapshot_reference_v2_string_type_invalid")
        codes = value["declared_stock_codes"]
        if (
            type(codes) is not list
            or len(codes) > 100_000
            or any(type(code) is not str or len(code) > 6 for code in codes)
        ):
            raise ValueError("fundamental_snapshot_reference_v2_codes_invalid")
        if len(value["snapshot_root"]) > 32_768 or len(value["decision_cutoff"]) > 64:
            raise ValueError("fundamental_snapshot_reference_v2_field_exceeds_limit")
        if any(
            len(value[key]) != 64
            for key in (
                "finished_manifest_sha256",
                "source_clock_identity_sha256",
                "source_content_identity_sha256",
                "cohort_identity_sha256",
                "daily_cohort_sha256",
                "declared_stock_codes_sha256",
                "identity_sha256",
            )
        ):
            raise ValueError("fundamental_snapshot_reference_v2_sha_invalid")
        raw = _canonical_json_bytes(value)
        if len(raw) > MAX_SNAPSHOT_REFERENCE_JSON_BYTES:
            raise ValueError("fundamental_snapshot_reference_v2_exceeds_size_limit")
        if sha256(raw).hexdigest() != expected_reference_sha256:
            raise ValueError("fundamental_snapshot_reference_v2_external_sha_mismatch")
        reference = cls(
            snapshot_root=value["snapshot_root"],
            snapshot_id=value["snapshot_id"],
            finished_manifest_sha256=value["finished_manifest_sha256"],
            source_clock_identity_sha256=value["source_clock_identity_sha256"],
            source_content_identity_sha256=value["source_content_identity_sha256"],
            cohort_identity_sha256=value["cohort_identity_sha256"],
            daily_cohort_sha256=value["daily_cohort_sha256"],
            decision_cutoff=value["decision_cutoff"],
            declared_stock_codes=tuple(codes),
            declared_stock_codes_sha256=value["declared_stock_codes_sha256"],
            schema_version=value["schema_version"],
        )
        if value["identity_sha256"] != reference.identity_sha256:
            raise ValueError("fundamental_snapshot_reference_v2_identity_mismatch")
        if raw != reference.to_json().encode("utf-8"):
            raise ValueError("fundamental_snapshot_reference_v2_not_canonical")
        return reference

    @classmethod
    def from_json(
        cls,
        raw: str | bytes,
        *,
        expected_reference_sha256: str,
    ) -> FundamentalReadSnapshotReferenceV2:
        if type(raw) is bytes:
            encoded = raw
        elif type(raw) is str:
            try:
                encoded = raw.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise ValueError("fundamental_snapshot_reference_v2_not_utf8") from exc
        else:
            raise TypeError("fundamental_snapshot_reference_v2_json_type_invalid")
        if len(encoded) > MAX_SNAPSHOT_REFERENCE_JSON_BYTES:
            raise ValueError("fundamental_snapshot_reference_v2_exceeds_size_limit")
        if type(expected_reference_sha256) is not str or not _SHA256_RE.fullmatch(
            expected_reference_sha256
        ):
            raise ValueError("fundamental_snapshot_reference_v2_external_sha_invalid")
        if sha256(encoded).hexdigest() != expected_reference_sha256:
            raise ValueError("fundamental_snapshot_reference_v2_external_sha_mismatch")
        _validate_json_depth(encoded, max_depth=_MAX_REFERENCE_JSON_DEPTH)
        try:
            payload = json.loads(
                encoded.decode("utf-8", errors="strict"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError("fundamental_snapshot_reference_v2_json_invalid") from exc
        if type(payload) is not dict:
            raise ValueError("fundamental_snapshot_reference_v2_json_object_required")
        reference = cls.from_dict(
            payload,
            expected_reference_sha256=expected_reference_sha256,
        )
        if encoded != reference.to_json().encode("utf-8"):
            raise ValueError("fundamental_snapshot_reference_v2_not_canonical")
        return reference


def make_snapshot_reference_v2(
    finished: FinishedFundamentalSnapshotReadCohortV2,
    *,
    snapshot_root: str | Path,
    snapshot_id: str,
) -> FundamentalReadSnapshotReferenceV2:
    """由真正完成 token 的來源時鐘與已保存 manifest SHA 發行參照。"""

    if type(finished) is not FinishedFundamentalSnapshotReadCohortV2:
        raise TypeError("fundamental_snapshot_reference_v2_finished_type_invalid")
    source_clock = finished.source_clock
    selected_root = str(snapshot_root)
    if (
        selected_root != source_clock.snapshot_binding.snapshot_root
        or snapshot_id != source_clock.snapshot_binding.snapshot_id
    ):
        raise ValueError("fundamental_snapshot_reference_v2_binding_path_mismatch")
    return FundamentalReadSnapshotReferenceV2(
        snapshot_root=selected_root,
        snapshot_id=snapshot_id,
        finished_manifest_sha256=finished.finished_manifest_sha256,
        source_clock_identity_sha256=source_clock.identity_sha256,
        source_content_identity_sha256=source_clock.source_content_identity_sha256,
        cohort_identity_sha256=finished.identity_sha256,
        daily_cohort_sha256=source_clock.cohort_sha256,
        decision_cutoff=source_clock.decision_cutoff.isoformat(),
        declared_stock_codes=source_clock.declared_stock_codes,
        declared_stock_codes_sha256=source_clock.declared_stock_codes_sha256,
    )


def encode_snapshot_reference_v2(reference: FundamentalReadSnapshotReferenceV2) -> bytes:
    """輸出 bounded canonical JSON bytes；呼叫端另保存外部 SHA 信任錨點。"""

    if type(reference) is not FundamentalReadSnapshotReferenceV2:
        raise TypeError("fundamental_snapshot_reference_v2_type_invalid")
    raw = reference.to_json().encode("utf-8")
    if len(raw) > MAX_SNAPSHOT_REFERENCE_JSON_BYTES:
        raise ValueError("fundamental_snapshot_reference_v2_exceeds_size_limit")
    return raw


def decode_snapshot_reference_v2(
    raw: str | bytes,
    *,
    expected_reference_sha256: str,
) -> FundamentalReadSnapshotReferenceV2:
    """需要 caller 提供的獨立 SHA 錨點才可解碼參照。"""

    return FundamentalReadSnapshotReferenceV2.from_json(
        raw,
        expected_reference_sha256=expected_reference_sha256,
    )


__all__ = [
    "FUNDAMENTAL_READ_SNAPSHOT_REFERENCE_V2_SCHEMA",
    "FUNDAMENTAL_READ_SNAPSHOT_V2_SCHEMA",
    "FUNDAMENTAL_SNAPSHOT_FINISHED_COHORT_V2_SCHEMA",
    "FUNDAMENTAL_SNAPSHOT_SOURCE_CLOCK_V2_SCHEMA",
    "FinishedFundamentalSnapshotReadCohortV2",
    "FundamentalReadSnapshotReferenceV2",
    "FundamentalSnapshotSourceClockV2",
    "compute_finished_snapshot_cohort_identity_v2",
    "decode_snapshot_reference_v2",
    "encode_snapshot_reference_v2",
    "make_finished_snapshot_manifest_v2",
    "make_snapshot_reference_v2",
    "parse_finished_snapshot_cohort_v2",
    "parse_snapshot_source_clock_v2",
]
