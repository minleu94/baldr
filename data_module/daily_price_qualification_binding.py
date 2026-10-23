"""Forward 日頻行情來源之可用時間（Availability）、不可變修訂鏈（Revision Lineage）、用途資格與 Consumer Readback 驗證器。

本模組嚴格遵守以下原則：
1. Identity bound 不等於金融合格：未經已驗證資格綁定（Qualification Binding）與 cutoff 檢查，
   `source_use_accepted`、`pit_eligible`、`training_eligible` 一律維持 `False`。
2. 區分事件決策當時可用資料（`temporal_role="decision_baseline"`）與事後 realized outcome
   可用資料（`temporal_role="outcome_realization"`），嚴禁混用。
3. 不把現在捕獲時間回填成歷史可得時間；TWSE `MI_INDEX` 與 TPEx `daily_close_quotes` 原始回應無官方簽章發布時刻，
   故 `source_published_at` 誠實保留為 `None`，本機可得時間 `available_at` 僅能由已驗證收據之
   `first_observed_at` / `written_at` 依 `daily-hour.v1`（Asia/Taipei 整點進位）推導且不得早於當日收盤（13:30+08:00）。
4. 驗證六大失敗模式並 fail closed：
   - 缺件（missing publication / projection manifest / raw response / custody receipt / CSV）
   - 漂移（publication hash / SQLite row drift）
   - 同鍵修訂（same-key revision / post-cutoff value restatement）
   - 雙來源歧義（same `(source_date, stock_code)` present in both TWSE and TPEx）
   - 提前可得時間（`first_observed_at` 或 `available_at` 早於收盤，或晚於對應 `cutoff_at`）
   - OOS 分界（跨或晚於 `oos_purge_cutoff_date` 時 `training_eligible=False`）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.ml_research_output_boundary import (
    _read_bounded_regular_file_no_follow,
    _reject_json_constant,
    _unique_json_object,
)
from data_module.source_acceptance_decision_registry import (
    SourceAcceptanceDecisionRevision,
    parse_source_acceptance_decision_revision,
    validate_source_acceptance_decision_revision,
)


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
MARKET_CLOSE_TIME = time(13, 30, 0)

DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1 = "daily-price-qualification-binding.v1"
DAILY_PRICE_REVISION_ENTRY_SCHEMA_V1 = "daily-price-revision-entry.v1"
MAX_QUALIFICATION_BINDING_BYTES = 2 * 1024 * 1024
MAX_PUBLICATION_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_REVISION_PUBLICATIONS = 4096
MAX_REVISION_ROWS = 500_000
MAX_REVISION_SCAN_ENTRIES = 16_384
MAX_REVISION_SCAN_DIRECTORIES = 8_192
MAX_REVISION_CLOSURE_READ_BYTES = 4 * 1024 * 1024 * 1024
_SHA256_PREFIX_RE = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_DATE_KEY_RE = re.compile(r"\A\d{8}\Z")

TemporalRole = Literal["decision_baseline", "outcome_realization"]

SUPPORTED_DAILY_PRICE_SOURCES: dict[str, dict[str, str]] = {
    "twse.mi_index.daily_price": {
        "publication_schema": "twse-daily-price-sqlite-publication.v1",
        "projection_schema": "twse-daily-price-download-projection.v1",
        "publication_dir": "twse_daily_price_sqlite_publication",
    },
    "tpex.daily_close_quotes": {
        "publication_schema": "tpex-daily-price-sqlite-publication.v1",
        "projection_schema": "tpex-daily-price-download-projection.v1",
        "publication_dir": "tpex_daily_price_sqlite_publication",
    },
}


class DailyPriceQualificationError(ValueError):
    """日頻行情來源資格、可用時間或修訂鏈驗證失敗。"""


DailyPriceQualificationBindingError = DailyPriceQualificationError


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_prefixed(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_json(raw: bytes) -> object:
    trimmed = raw[:-1] if raw.endswith(b"\n") else raw
    return json.loads(
        trimmed.decode("utf-8", errors="strict"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def _parse_aware_datetime(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise DailyPriceQualificationError(f"{field_name}_invalid_iso") from exc
    else:
        raise DailyPriceQualificationError(f"{field_name}_missing_or_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DailyPriceQualificationError(f"{field_name}_timezone_missing")
    return parsed


def _parse_date_key(value: object) -> tuple[str, date]:
    text = str(value or "").strip().replace("-", "").replace("/", "")
    if not _DATE_KEY_RE.fullmatch(text):
        raise DailyPriceQualificationError("source_date_invalid")
    try:
        parsed = datetime.strptime(text, "%Y%m%d").date()
    except ValueError as exc:
        raise DailyPriceQualificationError("source_date_invalid") from exc
    return text, parsed


def compute_daily_price_available_at(
    *,
    source_date: str | date | None = None,
    trading_date: str | date | None = None,
    first_observed_at: str | datetime | None = None,
    fetched_at: str | datetime | None = None,
    written_at: str | datetime,
) -> tuple[datetime, DailyPriceAvailabilityInfo]:
    """依 verified `first_observed_at` 與 `written_at` 計算 `daily-hour.v1` 本機可得時間。

    若 `first_observed_at` 或 `written_at` 早於該交易日台股收盤時間（13:30 Asia/Taipei），
    視為提前可得時間（premature availability）並 fail closed。
    """

    effective_date = source_date if source_date is not None else trading_date
    if effective_date is None:
        raise DailyPriceQualificationError("missing_source_date")
    effective_first = first_observed_at if first_observed_at is not None else fetched_at
    if effective_first is None:
        raise DailyPriceQualificationError("missing_first_observed_at")

    if isinstance(effective_date, date) and not isinstance(effective_date, datetime):
        t_date = effective_date
        date_key = t_date.strftime("%Y%m%d")
    else:
        date_key, t_date = _parse_date_key(effective_date)

    first_dt = _parse_aware_datetime(effective_first, field_name="first_observed_at")
    written_dt = _parse_aware_datetime(written_at, field_name="written_at")
    if written_dt < first_dt:
        raise DailyPriceQualificationError("publication_written_before_first_observed")

    market_close_dt = datetime.combine(t_date, MARKET_CLOSE_TIME, tzinfo=TAIPEI_TZ)
    if first_dt.astimezone(TAIPEI_TZ) < market_close_dt:
        raise DailyPriceQualificationError("premature_availability_before_market_close")
    if written_dt.astimezone(TAIPEI_TZ) < market_close_dt:
        raise DailyPriceQualificationError("premature_availability_before_market_close")

    written_taipei = written_dt.astimezone(TAIPEI_TZ)
    if (written_taipei.minute, written_taipei.second, written_taipei.microsecond) == (0, 0, 0):
        avail_hour = written_taipei
    else:
        avail_hour = (written_taipei + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    if avail_hour < market_close_dt:
        raise DailyPriceQualificationError("premature_availability_before_market_close")

    avail_utc = avail_hour.astimezone(timezone.utc)
    basis_str = "daily-hour.v1"
    info = DailyPriceAvailabilityInfo(
        available_at=avail_utc.isoformat(),
        availability_basis=basis_str,
        available_hour=avail_hour,
    )
    return avail_utc, info


@dataclass(frozen=True, slots=True)
class DailyPriceAvailabilityInfo:
    available_at: str
    availability_basis: str
    available_hour: datetime


@dataclass(frozen=True, slots=True)
class DailyPriceRowRevision:
    """單一 `(source_date, stock_code)` 在不可變 publication 中的版本與修訂節點。"""

    source_id: str
    source_date: str
    trading_date: date
    stock_code: str
    revision_number: int
    revision_id: str
    parent_revision_id: str | None = None
    publication_relative_path: str = ""
    publication_sha256: str = ""
    parent_publication_sha256: str | None = None
    projection_manifest_relative_path: str = ""
    projection_manifest_sha256: str = ""
    raw_response_sha256: str = ""
    custody_receipt_sha256: str = ""
    observation_receipt_sha256: str = ""
    csv_sha256: str = ""
    projection_row_sha256: str = ""
    sqlite_projection_row_sha256: str = ""
    first_observed_at: str = ""
    written_at: str = ""
    available_at: str = ""
    availability_basis: str = ""
    source_published_at: None = None
    is_value_restatement: bool = False


class DailyPriceRevisionLedger:
    """多日期不可變日頻行情 publication 的版本、parent/revision 與雙來源歧義驗證帳本。"""

    def __init__(self, *, output_root: str | Path, data_root: str | Path) -> None:
        self.output_root = Path(output_root).expanduser().resolve(strict=True)
        self.data_root = Path(data_root).expanduser().resolve(strict=True)
        self._revisions_by_source_key: dict[
            tuple[str, str, str], tuple[DailyPriceRowRevision, ...]
        ] = {}
        self._sources_by_natural_key: dict[tuple[str, str], set[str]] = {}
        self._publication_descriptors_by_date: dict[
            tuple[str, str], list[dict[str, object]]
        ] = {}
        self._revision_closure_verified = False
        self._last_registration_read_bytes = 0

    @property
    def revision_closure_verified(self) -> bool:
        """只有完整掃描並驗證兩個來源目錄後才表示修訂閉包完整。"""
        return self._revision_closure_verified

    def register_publication(
        self,
        *,
        source_id: str,
        relative_path: str,
        expected_sha256: str | None = None,
    ) -> int:
        """讀取並驗證單份 publication 及其 projection manifest，加入不可變修訂鏈。"""

        self._revision_closure_verified = False
        self._last_registration_read_bytes = 0

        if source_id not in SUPPORTED_DAILY_PRICE_SOURCES:
            raise DailyPriceQualificationError("unsupported_daily_price_source_id")
        profile = SUPPORTED_DAILY_PRICE_SOURCES[source_id]
        pure = PurePosixPath(relative_path)
        if (
            not relative_path
            or "\\" in relative_path
            or ":" in relative_path
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise DailyPriceQualificationError("publication_relative_path_invalid")
        pub_path = self.output_root.joinpath(*pure.parts)
        try:
            raw = _read_bounded_regular_file_no_follow(
                pub_path, maximum_bytes=MAX_PUBLICATION_ARTIFACT_BYTES
            )
        except Exception as exc:
            raise DailyPriceQualificationError("publication_artifact_missing_or_invalid") from exc
        actual_sha = _sha256_prefixed(raw)
        if expected_sha256 is not None and actual_sha != expected_sha256:
            raise DailyPriceQualificationError("publication_sha256_drift")
        payload = _strict_json(raw)
        if not isinstance(payload, dict) or _canonical_bytes(payload) + b"\n" != raw:
            raise DailyPriceQualificationError("publication_json_not_canonical")
        body = {k: v for k, v in payload.items() if k != "content_sha256"}
        expected_publication_fields = {
            "schema_version", "source_id", "source_published_at", "written_at",
            "database_relative_path", "projection_manifests", "rows", "content_sha256",
        }
        if source_id == "twse.mi_index.daily_price":
            expected_publication_fields.add("coverage_basis")
        else:
            expected_publication_fields |= {
                "formal_source_contract_eligible", "pit_eligible", "training_eligible"
            }
        if (
            set(payload) != expected_publication_fields
            or payload.get("schema_version") != profile["publication_schema"]
            or payload.get("source_id") != source_id
            or payload.get("content_sha256") != _sha256_prefixed(_canonical_bytes(body))
            or payload.get("source_published_at") is not None
            or (
                source_id == "twse.mi_index.daily_price"
                and payload.get("coverage_basis")
                != "keys_observed_in_this_twse_response_only"
            )
            or any(
                payload.get(field) is not False
                for field in (
                    {"formal_source_contract_eligible", "pit_eligible", "training_eligible"}
                    if source_id == "tpex.daily_close_quotes" else set()
                )
            )
        ):
            raise DailyPriceQualificationError("publication_envelope_invalid")

        written_at_dt = _parse_aware_datetime(
            payload.get("written_at"), field_name="written_at"
        )
        written_at_iso = written_at_dt.astimezone(timezone.utc).isoformat()

        proj_refs = payload.get("projection_manifests")
        if not isinstance(proj_refs, list) or not proj_refs:
            raise DailyPriceQualificationError("publication_projection_manifests_missing")
        if len(proj_refs) > 128:
            raise DailyPriceQualificationError("publication_projection_manifest_limit")
        read_budget = [len(raw)]
        verified_manifests: dict[
            str, tuple[Mapping[str, Any], list[Mapping[str, Any]]]
        ] = {}
        if len({
            ref.get("relative_path") for ref in proj_refs if isinstance(ref, Mapping)
        }) != len(proj_refs):
            raise DailyPriceQualificationError("publication_projection_manifest_duplicate")
        for ref in proj_refs:
            if not isinstance(ref, Mapping):
                raise DailyPriceQualificationError("projection_manifest_ref_invalid")
            ref_rel = ref.get("relative_path")
            ref_sha = ref.get("sha256")
            if not isinstance(ref_rel, str) or not isinstance(ref_sha, str):
                raise DailyPriceQualificationError("projection_manifest_ref_invalid")
            ref_pure = PurePosixPath(ref_rel)
            if (
                ref_pure.is_absolute()
                or "\\" in ref_rel
                or ":" in ref_rel
                or any(p in {"", ".", ".."} for p in ref_pure.parts)
                or not _SHA256_PREFIX_RE.fullmatch(ref_sha)
            ):
                raise DailyPriceQualificationError("projection_manifest_path_invalid")
            try:
                if source_id == "twse.mi_index.daily_price":
                    from data_module.twse_daily_price_publication import (
                        _load_projection_manifest,
                    )

                    manifest = _load_projection_manifest(
                        output_root=self.output_root,
                        data_root=self.data_root,
                        descriptor={
                            "status": "captured",
                            "schema_version": profile["projection_schema"],
                            "relative_path": ref_rel,
                            "sha256": ref_sha,
                        },
                        read_budget=read_budget,
                    )
                    projected_rows = manifest.get("observed_response_rows")
                else:
                    from data_module.tpex_daily_price_publication import (
                        _verify_download_manifest,
                    )

                    manifest, _csv_rows = _verify_download_manifest(
                        output_root=self.output_root,
                        data_root=self.data_root,
                        descriptor={
                            "status": "captured",
                            "schema_version": profile["projection_schema"],
                            "relative_path": ref_rel,
                            "sha256": ref_sha,
                        },
                        read_budget=read_budget,
                    )
                    projected_rows = manifest.get("rows")
            except Exception as exc:
                raise DailyPriceQualificationError(
                    "projection_source_chain_invalid"
                ) from exc
            if not isinstance(projected_rows, list) or not all(
                isinstance(item, Mapping) for item in projected_rows
            ):
                raise DailyPriceQualificationError("projection_rows_invalid")
            verified_manifests[ref_rel] = (manifest, projected_rows)
            manifest_observed = _parse_aware_datetime(
                manifest.get("observed_at"), field_name="observed_at"
            )
            if written_at_dt < manifest_observed:
                raise DailyPriceQualificationError("publication_written_before_observation")

        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise DailyPriceQualificationError("publication_rows_missing")
        if len(rows) > MAX_REVISION_ROWS:
            raise DailyPriceQualificationError("publication_row_limit")

        staged_entries: list[dict[str, Any]] = []
        observed_dates: set[str] = set()
        seen_row_keys: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise DailyPriceQualificationError("publication_row_invalid")
            source_date_key, trading_date = _parse_date_key(row.get("source_date"))
            stock_code = str(row.get("stock_code") or "").strip()
            if not stock_code:
                raise DailyPriceQualificationError("publication_row_stock_code_missing")
            row_key = (source_date_key, stock_code)
            if row_key in seen_row_keys:
                raise DailyPriceQualificationError("publication_duplicate_natural_key")
            seen_row_keys.add(row_key)
            if source_id == "twse.mi_index.daily_price":
                projection_rel = row.get("projection_manifest_relative_path")
                projection_sha = row.get("projection_manifest_sha256")
                if (
                    not isinstance(projection_rel, str)
                    or not isinstance(projection_sha, str)
                    or projection_rel not in verified_manifests
                    or not _SHA256_PREFIX_RE.fullmatch(projection_sha)
                    or not any(
                        isinstance(ref, Mapping)
                        and ref.get("relative_path") == projection_rel
                        and ref.get("sha256") == projection_sha
                        for ref in proj_refs
                    )
                ):
                    raise DailyPriceQualificationError(
                        "publication_row_projection_reference_invalid"
                    )
                selected_manifest, projected_rows = verified_manifests[projection_rel]
                projected = [
                    item for item in projected_rows
                    if item.get("source_date") == source_date_key
                    and item.get("stock_code") == stock_code
                ]
            else:
                projected_candidates: list[
                    tuple[str, Mapping[str, Any], Mapping[str, Any]]
                ] = []
                for ref in proj_refs:
                    if not isinstance(ref, Mapping):
                        continue
                    ref_rel = str(ref.get("relative_path") or "")
                    candidate_manifest, candidate_rows = verified_manifests[ref_rel]
                    for candidate_row in candidate_rows:
                        if (
                            candidate_row.get("source_date") == source_date_key
                            and candidate_row.get("stock_code") == stock_code
                            and candidate_row.get("source_row_ordinal") == row.get("source_row_ordinal")
                            and candidate_row.get("source_row_sha256") == row.get("source_row_sha256")
                            and candidate_row.get("projection_row_sha256") == row.get("projection_row_sha256")
                        ):
                            projected_candidates.append(
                                (ref_rel, candidate_manifest, candidate_row)
                            )
                if len(projected_candidates) != 1:
                    raise DailyPriceQualificationError(
                        "publication_row_projection_missing_or_ambiguous"
                    )
                projection_rel, selected_manifest, projected_row = projected_candidates[0]
                projection_sha = next(
                    str(ref.get("sha256")) for ref in proj_refs
                    if isinstance(ref, Mapping)
                    and ref.get("relative_path") == projection_rel
                )
                projected = [projected_row]
            if len(projected) != 1:
                raise DailyPriceQualificationError(
                    "publication_row_source_projection_missing_or_ambiguous"
                )
            projected_row = projected[0]
            if row.get("projection_row_sha256") != projected_row.get("projection_row_sha256"):
                raise DailyPriceQualificationError("publication_row_projection_hash_drift")
            if (
                row.get("source_id", source_id) != source_id
                or row.get("parser_id") != selected_manifest.get("parser_id")
                or _parse_aware_datetime(
                    row.get("written_at", written_at_dt), field_name="written_at"
                ) != written_at_dt
            ):
                raise DailyPriceQualificationError("publication_row_identity_or_time_drift")
            source_fields = {
                "raw_response_sha256": selected_manifest.get("raw_response_sha256"),
                "custody_receipt_sha256": selected_manifest.get("custody_receipt_sha256"),
                "observation_receipt_sha256": selected_manifest.get("observation_receipt_sha256"),
                "csv_sha256": selected_manifest.get("csv_sha256"),
            }
            if source_id == "tpex.daily_close_quotes" and (
                row.get("observed_at") != selected_manifest.get("observed_at")
                or row.get("parser_id") != selected_manifest.get("parser_id")
            ):
                raise DailyPriceQualificationError("publication_row_observation_drift")
            for field_name, expected_value in source_fields.items():
                if (
                    field_name in row and row.get(field_name) != expected_value
                ) or (
                    source_id == "twse.mi_index.daily_price"
                    and field_name not in row
                ):
                    raise DailyPriceQualificationError(
                        f"publication_row_{field_name}_drift"
                    )
            if source_id == "tpex.daily_close_quotes":
                first_observed = selected_manifest.get("observed_at")
            else:
                first_observed = selected_manifest.get("first_observed_at")
            first_obs_dt = _parse_aware_datetime(
                first_observed, field_name="first_observed_at"
            )
            row_first = row.get("first_observed_at")
            if row_first is not None and _parse_aware_datetime(
                row_first, field_name="first_observed_at"
            ) != first_obs_dt:
                raise DailyPriceQualificationError("publication_row_first_observed_at_drift")
            projection_row_hash = row.get("projection_row_sha256")
            sqlite_row_hash = row.get("sqlite_projection_row_sha256")
            if (
                not isinstance(projection_row_hash, str)
                or not _SHA256_PREFIX_RE.fullmatch(projection_row_hash)
                or not isinstance(sqlite_row_hash, str)
                or not _SHA256_PREFIX_RE.fullmatch(sqlite_row_hash)
            ):
                raise DailyPriceQualificationError("publication_sqlite_row_hash_invalid")
            first_obs_iso = first_obs_dt.astimezone(timezone.utc).isoformat()
            available_dt, availability = compute_daily_price_available_at(
                source_date=trading_date,
                first_observed_at=first_obs_dt,
                written_at=written_at_dt,
            )
            observed_dates.add(source_date_key)
            staged_entries.append(
                {
                    "source_id": source_id,
                    "source_date": source_date_key,
                    "trading_date": trading_date,
                    "stock_code": stock_code,
                    "publication_relative_path": pure.as_posix(),
                    "publication_sha256": actual_sha,
                    "projection_manifest_relative_path": projection_rel,
                    "projection_manifest_sha256": projection_sha,
                    **source_fields,
                    "projection_row_sha256": projection_row_hash,
                    "sqlite_projection_row_sha256": sqlite_row_hash,
                    "first_observed_at": first_obs_iso,
                    "written_at": written_at_iso,
                    "available_at": available_dt.isoformat(),
                    "availability_basis": availability.availability_basis,
                }
            )

        for date_key in observed_dates:
            desc_list = self._publication_descriptors_by_date.setdefault(
                (source_id, date_key), []
            )
            descriptor = {
                "status": "captured",
                "schema_version": profile["publication_schema"],
                "relative_path": pure.as_posix(),
                "sha256": actual_sha,
                "row_count": len(rows),
            }
            if descriptor not in desc_list:
                desc_list.append(descriptor)

        for item in staged_entries:
            s_key = (item["source_id"], item["source_date"], item["stock_code"])
            n_key = (item["source_date"], item["stock_code"])
            self._sources_by_natural_key.setdefault(n_key, set()).add(source_id)
            existing = list(self._revisions_by_source_key.get(s_key, ()))
            if any(
                rev.publication_sha256 == item["publication_sha256"]
                for rev in existing
            ):
                continue
            raw_nodes: list[dict[str, Any]] = [
                {
                    "source_id": rev.source_id,
                    "source_date": rev.source_date,
                    "trading_date": rev.trading_date,
                    "stock_code": rev.stock_code,
                    "publication_relative_path": rev.publication_relative_path,
                    "publication_sha256": rev.publication_sha256,
                    "projection_manifest_relative_path": rev.projection_manifest_relative_path,
                    "projection_manifest_sha256": rev.projection_manifest_sha256,
                    "raw_response_sha256": rev.raw_response_sha256,
                    "custody_receipt_sha256": rev.custody_receipt_sha256,
                    "observation_receipt_sha256": rev.observation_receipt_sha256,
                    "csv_sha256": rev.csv_sha256,
                    "projection_row_sha256": rev.projection_row_sha256,
                    "sqlite_projection_row_sha256": rev.sqlite_projection_row_sha256,
                    "first_observed_at": rev.first_observed_at,
                    "written_at": rev.written_at,
                    "available_at": rev.available_at,
                    "availability_basis": rev.availability_basis,
                }
                for rev in existing
            ]
            raw_nodes.append(item)
            raw_nodes.sort(
                key=lambda n: (
                    n["first_observed_at"],
                    n["written_at"],
                    n["publication_sha256"],
                )
            )
            rebuilt: list[DailyPriceRowRevision] = []
            for idx, node in enumerate(raw_nodes, start=1):
                parent = rebuilt[-1] if rebuilt else None
                proj_hash = node["projection_row_sha256"].removeprefix("sha256:")
                rev_id = (
                    f"{node['source_id']}:{node['source_date']}:"
                    f"{node['stock_code']}:r{idx}:{proj_hash[:16]}"
                )
                is_restatement = bool(
                    parent is not None
                    and (
                        parent.projection_row_sha256 != node["projection_row_sha256"]
                        or parent.sqlite_projection_row_sha256
                        != node["sqlite_projection_row_sha256"]
                    )
                )
                rebuilt.append(
                    DailyPriceRowRevision(
                        source_id=node["source_id"],
                        source_date=node["source_date"],
                        trading_date=node["trading_date"],
                        stock_code=node["stock_code"],
                        revision_number=idx,
                        revision_id=rev_id,
                        parent_revision_id=parent.revision_id if parent else None,
                        publication_relative_path=node["publication_relative_path"],
                        publication_sha256=node["publication_sha256"],
                        parent_publication_sha256=(
                            parent.publication_sha256 if parent else None
                        ),
                        projection_manifest_relative_path=node[
                            "projection_manifest_relative_path"
                        ],
                        projection_manifest_sha256=node["projection_manifest_sha256"],
                        raw_response_sha256=node["raw_response_sha256"],
                        custody_receipt_sha256=node["custody_receipt_sha256"],
                        observation_receipt_sha256=node["observation_receipt_sha256"],
                        csv_sha256=node["csv_sha256"],
                        projection_row_sha256=node["projection_row_sha256"],
                        sqlite_projection_row_sha256=node[
                            "sqlite_projection_row_sha256"
                        ],
                        first_observed_at=node["first_observed_at"],
                        written_at=node["written_at"],
                        available_at=node["available_at"],
                        availability_basis=node["availability_basis"],
                        source_published_at=None,
                        is_value_restatement=is_restatement,
                    )
                )
            self._revisions_by_source_key[s_key] = tuple(rebuilt)
        self._last_registration_read_bytes = read_budget[0]
        return len(staged_entries)

    def scan_scheduled_publications(self) -> int:
        """封閉本機已保存的兩來源 publication inventory。

        這只證明目前核准輸出根內的 publication inventory 已完整掃描，
        不證明官方來源的歷史資料完整或所有曾發布版本均已取得。
        任一來源目錄缺失、連結、超界或含壞檔時都不建立本機閉包。
        """

        self._revision_closure_verified = False
        discovered: list[tuple[str, str, str]] = []
        scanned_entries = 0
        try:
            for source_id, profile in SUPPORTED_DAILY_PRICE_SOURCES.items():
                base = self.output_root / "scheduled" / profile["publication_dir"]
                base_info = base.lstat()
                if (
                    not stat.S_ISDIR(base_info.st_mode)
                    or getattr(base_info, "st_file_attributes", 0) & 0x400
                    or base.is_symlink()
                ):
                    raise DailyPriceQualificationError("revision_closure_source_directory_invalid")
                pending = [base]
                while pending:
                    directory = pending.pop()
                    with os.scandir(directory) as iterator:
                        for entry in iterator:
                            scanned_entries += 1
                            if scanned_entries > MAX_REVISION_SCAN_ENTRIES:
                                raise DailyPriceQualificationError(
                                    "revision_closure_entry_limit"
                                )
                            info = entry.stat(follow_symlinks=False)
                            if (
                                entry.is_symlink()
                                or getattr(info, "st_file_attributes", 0) & 0x400
                            ):
                                raise DailyPriceQualificationError(
                                    "revision_closure_reparse_entry"
                                )
                            if stat.S_ISDIR(info.st_mode):
                                pending.append(Path(entry.path))
                                if len(pending) > MAX_REVISION_SCAN_DIRECTORIES:
                                    raise DailyPriceQualificationError(
                                        "revision_closure_directory_limit"
                                    )
                                continue
                            if not stat.S_ISREG(info.st_mode) or not entry.name.endswith(".json"):
                                raise DailyPriceQualificationError(
                                    "revision_closure_unexpected_entry"
                                )
                            stem = entry.name[:-5]
                            if not re.fullmatch(r"[0-9a-f]{64}", stem):
                                raise DailyPriceQualificationError(
                                    "revision_closure_filename_invalid"
                                )
                            relative = Path(entry.path).relative_to(self.output_root).as_posix()
                            discovered.append((source_id, relative, "sha256:" + stem))
                            if len(discovered) > MAX_REVISION_PUBLICATIONS:
                                raise DailyPriceQualificationError(
                                    "revision_closure_publication_limit"
                                )
            staged = DailyPriceRevisionLedger(
                output_root=self.output_root, data_root=self.data_root
            )
            total_rows = 0
            total_read_bytes = 0
            for source_id, relative, expected_sha in discovered:
                total_rows += staged.register_publication(
                    source_id=source_id,
                    relative_path=relative,
                    expected_sha256=expected_sha,
                )
                total_read_bytes += staged._last_registration_read_bytes
                if total_rows > MAX_REVISION_ROWS:
                    raise DailyPriceQualificationError("revision_closure_row_limit")
                if total_read_bytes > MAX_REVISION_CLOSURE_READ_BYTES:
                    raise DailyPriceQualificationError(
                        "revision_closure_read_budget_exceeded"
                    )
        except Exception as exc:
            if isinstance(exc, DailyPriceQualificationError):
                raise
            raise DailyPriceQualificationError("revision_closure_scan_failed") from exc
        self._revisions_by_source_key = staged._revisions_by_source_key
        self._sources_by_natural_key = staged._sources_by_natural_key
        self._publication_descriptors_by_date = staged._publication_descriptors_by_date
        self._revision_closure_verified = True
        return len(discovered)

    def resolve_row_revision(
        self,
        *,
        source_id: str,
        source_date: str,
        stock_code: str,
        publication_sha256: str,
        sqlite_projection_row_sha256: str,
        cutoff_at: datetime,
    ) -> DailyPriceRowRevision:
        """驗證單一列在 `cutoff_at` 當下的不可變版本、無雙來源歧義與無同鍵數值覆寫。"""

        if not self._revision_closure_verified:
            raise DailyPriceQualificationError("revision_closure_unverified")

        date_key, _ = _parse_date_key(source_date)
        n_key = (date_key, stock_code)
        sources = self._sources_by_natural_key.get(n_key, set())
        if len(sources) > 1:
            raise DailyPriceQualificationError("dual_source_ambiguity")
        s_key = (source_id, date_key, stock_code)
        revisions = self._revisions_by_source_key.get(s_key, ())
        if not revisions:
            raise DailyPriceQualificationError("revision_lineage_missing")
        if any(rev.is_value_restatement for rev in revisions):
            raise DailyPriceQualificationError("same_key_revision_conflict")
        matching = next(
            (
                rev
                for rev in revisions
                if rev.publication_sha256 == publication_sha256
            ),
            None,
        )
        if matching is None:
            raise DailyPriceQualificationError("publication_revision_not_registered")
        if matching.sqlite_projection_row_sha256 != sqlite_projection_row_sha256:
            raise DailyPriceQualificationError("sqlite_row_drift")
        cutoff_utc = _parse_aware_datetime(cutoff_at, field_name="cutoff_at").astimezone(
            timezone.utc
        )
        avail_utc = _parse_aware_datetime(
            matching.available_at, field_name="available_at"
        ).astimezone(timezone.utc)
        if avail_utc > cutoff_utc:
            raise DailyPriceQualificationError("available_after_cutoff")
        return matching


@dataclass(frozen=True, slots=True)
class DailyPriceQualificationPolicy:
    """Forward 日頻行情單次綁定與資格判定政策。

    區分：
    - `temporal_role="decision_baseline"`：事件決策當時基期價格（必須 `available_at <= decision_cutoff_at`）
    - `temporal_role="outcome_realization"`：事後 realized outcome 觀察價格（必須 `available_at <= outcome_cutoff_at`，且 `decision_time_usable=False`）
    """

    temporal_role: TemporalRole
    cutoff_at: datetime
    decision_cutoff_at: datetime | None = None
    event_price_date: date | None = None
    outcome_price_date: date | None = None
    oos_purge_cutoff_date: date | None = None
    source_use_accepted: bool = False
    accepted_uses: tuple[str, ...] = ()
    source_id: str | None = None
    acceptance_decision_id: str | None = None
    acceptance_binding_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.temporal_role not in ("decision_baseline", "outcome_realization"):
            raise DailyPriceQualificationError("temporal_role_invalid")
        _parse_aware_datetime(self.cutoff_at, field_name="cutoff_at")
        if self.decision_cutoff_at is not None:
            _parse_aware_datetime(
                self.decision_cutoff_at, field_name="decision_cutoff_at"
            )
        if self.source_use_accepted and (
            not self.source_id
            or self.source_id not in SUPPORTED_DAILY_PRICE_SOURCES
            or not self.acceptance_decision_id
            or not self.acceptance_binding_sha256
        ):
            raise DailyPriceQualificationError(
                "accepted_source_use_requires_pinned_decision_and_binding_sha256"
            )


class PinnedDailyPriceQualificationResolver:
    """以受外部 SHA 固定的 qualification binding JSON 核發 `DailyPriceQualificationPolicy`。"""

    def __init__(self, binding_path: str | Path, expected_sha256: str) -> None:
        self._binding_path = Path(binding_path).expanduser().absolute()
        if not isinstance(expected_sha256, str) or not _SHA256_PREFIX_RE.fullmatch(
            expected_sha256
        ):
            raise DailyPriceQualificationError("binding_expected_sha256_invalid")
        self._expected_sha256 = expected_sha256

    def load_verified_binding(self) -> tuple[Mapping[str, Any], SourceAcceptanceDecisionRevision]:
        raw = _read_bounded_regular_file_no_follow(
            self._binding_path, maximum_bytes=MAX_QUALIFICATION_BINDING_BYTES
        )
        actual_sha = _sha256_prefixed(raw)
        if actual_sha != self._expected_sha256:
            raise DailyPriceQualificationError("binding_external_sha256_mismatch")
        payload = _strict_json(raw)
        if not isinstance(payload, dict) or _canonical_bytes(payload) + b"\n" != raw:
            raise DailyPriceQualificationError("binding_json_not_canonical")
        if payload.get("schema_version") != DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1:
            raise DailyPriceQualificationError("binding_schema_version_unsupported")
        decision_raw = payload.get("decision")
        if not isinstance(decision_raw, Mapping):
            raise DailyPriceQualificationError("binding_decision_invalid")
        decision = parse_source_acceptance_decision_revision(decision_raw)
        try:
            validate_source_acceptance_decision_revision(decision)
        except (TypeError, ValueError) as exc:
            raise DailyPriceQualificationError(
                f"binding_decision_validation_failed:{type(exc).__name__}"
            ) from exc
        return payload, decision

    def build_policy(
        self,
        *,
        temporal_role: TemporalRole,
        cutoff_at: datetime,
        decision_cutoff_at: datetime | None = None,
        event_price_date: date | None = None,
        outcome_price_date: date | None = None,
        oos_purge_cutoff_date: date | None = None,
    ) -> DailyPriceQualificationPolicy:
        payload, decision = self.load_verified_binding()
        cutoff_utc = _parse_aware_datetime(cutoff_at, field_name="cutoff_at").astimezone(
            timezone.utc
        )
        decided_utc = _parse_aware_datetime(
            decision.decided_at, field_name="decided_at"
        ).astimezone(timezone.utc)
        decision_status = getattr(decision, "status", getattr(decision, "acceptance_status", None))
        decision_uses = getattr(decision, "allowed_use_cases", getattr(decision, "accepted_uses", ()))
        decision_id = getattr(decision, "decision_revision_id", getattr(decision, "decision_id", "decision"))
        accepted = (
            decision_status == "accepted"
            and decided_utc <= cutoff_utc
            and bool(decision_uses)
            and decision.source_id in SUPPORTED_DAILY_PRICE_SOURCES
        )
        return DailyPriceQualificationPolicy(
            temporal_role=temporal_role,
            cutoff_at=cutoff_at,
            decision_cutoff_at=decision_cutoff_at,
            event_price_date=event_price_date,
            outcome_price_date=outcome_price_date,
            oos_purge_cutoff_date=oos_purge_cutoff_date,
            source_use_accepted=accepted,
            accepted_uses=tuple(decision_uses) if accepted else (),
            source_id=decision.source_id if accepted else None,
            acceptance_decision_id=decision_id if accepted else None,
            acceptance_binding_sha256=self._expected_sha256 if accepted else None,
        )


def evaluate_bound_daily_price_row_qualification(
    *,
    bound_row: Mapping[str, Any],
    revision_ledger: DailyPriceRevisionLedger,
    policy: DailyPriceQualificationPolicy,
) -> dict[str, Any]:
    """對已通過 `source_identity_bound` 的資料列進行版本、可用時間、用途與 OOS 資格核驗。"""

    if bound_row.get("status") != "source_identity_bound":
        return {
            **dict(bound_row),
            "status": "unknown",
            "reason_code": str(bound_row.get("reason_code") or "source_row_not_bound"),
            "source_use_accepted": False,
            "source_published_at": None,
            "available_at": None,
            "pit_eligible": False,
            "training_eligible": False,
        }

    source_id = str(bound_row.get("source_id") or "")
    source_date = str(bound_row.get("source_date") or "")
    stock_code = str(bound_row.get("stock_code") or "")
    publication_sha256 = str(bound_row.get("publication_sha256") or "")
    sqlite_row_sha256 = str(bound_row.get("sqlite_projection_row_sha256") or "")

    if policy.source_use_accepted and policy.source_id != source_id:
        return {
            **dict(bound_row),
            "status": "unknown",
            "reason_code": "acceptance_source_id_mismatch",
            "temporal_role": policy.temporal_role,
            "source_use_accepted": False,
            "source_published_at": None,
            "available_at": None,
            "pit_eligible": False,
            "training_eligible": False,
        }

    effective_cutoff = (
        policy.decision_cutoff_at
        if policy.temporal_role == "decision_baseline"
        and policy.decision_cutoff_at is not None
        else policy.cutoff_at
    )
    effective_cutoff_utc = _parse_aware_datetime(
        effective_cutoff, field_name="effective_cutoff"
    ).astimezone(timezone.utc)

    try:
        if getattr(revision_ledger, "revision_closure_verified", False) is not True:
            raise DailyPriceQualificationError("revision_closure_unverified")
        revision = revision_ledger.resolve_row_revision(
            source_id=source_id,
            source_date=source_date,
            stock_code=stock_code,
            publication_sha256=publication_sha256,
            sqlite_projection_row_sha256=sqlite_row_sha256,
            cutoff_at=effective_cutoff_utc,
        )
        if policy.temporal_role == "decision_baseline":
            if (
                policy.event_price_date is not None
                and revision.trading_date > policy.event_price_date
            ):
                raise DailyPriceQualificationError(
                    "decision_baseline_row_after_event_price_date"
                )
        else:
            if (
                policy.event_price_date is not None
                and revision.trading_date < policy.event_price_date
            ):
                raise DailyPriceQualificationError(
                    "outcome_realization_row_before_event_price_date"
                )
            if (
                policy.outcome_price_date is not None
                and revision.trading_date > policy.outcome_price_date
            ):
                raise DailyPriceQualificationError(
                    "outcome_realization_row_after_outcome_price_date"
                )
    except DailyPriceQualificationError as exc:
        reason = str(exc)
        if reason == "available_after_cutoff":
            reason = (
                "available_after_decision_cutoff"
                if policy.temporal_role == "decision_baseline"
                else "available_after_outcome_cutoff"
            )
        return {
            **dict(bound_row),
            "status": "unknown",
            "reason_code": reason,
            "temporal_role": policy.temporal_role,
            "source_use_accepted": False,
            "source_published_at": None,
            "available_at": None,
            "pit_eligible": False,
            "training_eligible": False,
        }

    required_use = (
        "forward_decision_baseline"
        if policy.temporal_role == "decision_baseline"
        else "forward_outcome_evaluation"
    )
    use_accepted = bool(
        policy.source_use_accepted
        and (
            required_use in policy.accepted_uses
            or "forward_evaluation" in policy.accepted_uses
        )
    )
    pit_eligible = use_accepted

    # OOS / Training eligibility check
    oos_cutoff = policy.oos_purge_cutoff_date
    horizon_end_date = policy.outcome_price_date or revision.trading_date
    if not use_accepted or "ml_training" not in policy.accepted_uses:
        training_eligible = False
        oos_boundary_status = "not_accepted_for_ml_training"
    elif oos_cutoff is None:
        training_eligible = False
        oos_boundary_status = "oos_purge_cutoff_missing"
    elif revision.trading_date >= oos_cutoff or horizon_end_date >= oos_cutoff:
        training_eligible = False
        oos_boundary_status = "crosses_or_after_oos_purge_cutoff"
    else:
        training_eligible = True
        oos_boundary_status = " strictly_before_oos_purge_cutoff".strip()

    qualified_payload = {
        **dict(bound_row),
        "status": (
            "source_qualified"
            if use_accepted
            else "source_identity_and_availability_bound"
        ),
        "reason_code": "ok",
        "temporal_role": policy.temporal_role,
        "decision_time_usable": policy.temporal_role == "decision_baseline" and pit_eligible,
        "outcome_time_usable": True,
        "cutoff_at": effective_cutoff_utc.isoformat(),
        "first_observed_at": revision.first_observed_at,
        "written_at": revision.written_at,
        "available_at": revision.available_at,
        "availability_basis": revision.availability_basis,
        "source_published_at": None,
        "revision_number": revision.revision_number,
        "revision_id": revision.revision_id,
        "parent_revision_id": revision.parent_revision_id,
        "parent_publication_sha256": revision.parent_publication_sha256,
        "is_value_restatement": revision.is_value_restatement,
        "source_use_accepted": use_accepted,
        "acceptance_decision_id": policy.acceptance_decision_id if use_accepted else None,
        "acceptance_source_id": policy.source_id if use_accepted else None,
        "acceptance_binding_sha256": (
            policy.acceptance_binding_sha256 if use_accepted else None
        ),
        "pit_eligible": pit_eligible,
        "training_eligible": training_eligible,
        "oos_boundary_status": oos_boundary_status,
    }
    proof_body = {
        k: v for k, v in qualified_payload.items() if k != "qualification_proof_sha256"
    }
    qualified_payload["qualification_proof_sha256"] = _sha256_prefixed(
        _canonical_bytes(proof_body)
    )
    return qualified_payload


def verify_qualified_binding_payload(
    binding: Mapping[str, Any],
    *,
    resolver: PinnedDailyPriceQualificationResolver | None = None,
    policy: DailyPriceQualificationPolicy | None = None,
    revision_ledger: DailyPriceRevisionLedger | None = None,
) -> bool:
    """用外部 SHA、當前用途政策及完整修訂帳本重算資格；自算 proof 不作信任根。"""

    if (
        not isinstance(binding, Mapping)
        or resolver is None
        or policy is None
        or revision_ledger is None
        or getattr(revision_ledger, "revision_closure_verified", False) is not True
        or binding.get("source_use_accepted") is not True
        or binding.get("pit_eligible") is not True
        or binding.get("status") != "source_qualified"
    ):
        return False
    try:
        _payload, decision = resolver.load_verified_binding()
        decision_id = getattr(
            decision, "decision_revision_id", getattr(decision, "decision_id", None)
        )
        decision_uses = tuple(
            getattr(decision, "allowed_use_cases", getattr(decision, "accepted_uses", ()))
        )
        decision_status = getattr(
            decision, "status", getattr(decision, "acceptance_status", None)
        )
        decision_cutoff = _parse_aware_datetime(
            policy.cutoff_at, field_name="policy_cutoff_at"
        ).astimezone(timezone.utc)
        decided_at = _parse_aware_datetime(
            decision.decided_at, field_name="decision_decided_at"
        ).astimezone(timezone.utc)
        required_use = (
            "forward_decision_baseline"
            if policy.temporal_role == "decision_baseline"
            else "forward_outcome_evaluation"
        )
        if (
            decision_status != "accepted"
            or decided_at > decision_cutoff
            or policy.source_use_accepted is not True
            or policy.acceptance_binding_sha256 != resolver._expected_sha256
            or binding.get("acceptance_binding_sha256") != resolver._expected_sha256
            or policy.source_id != decision.source_id
            or binding.get("acceptance_source_id") != decision.source_id
            or binding.get("source_id") != decision.source_id
            or policy.acceptance_decision_id != decision_id
            or binding.get("acceptance_decision_id") != decision_id
            or tuple(policy.accepted_uses) != decision_uses
            or not (
                required_use in decision_uses
                or "forward_evaluation" in decision_uses
            )
        ):
            return False
        proof = binding.get("qualification_proof_sha256")
        if not isinstance(proof, str) or not _SHA256_PREFIX_RE.fullmatch(proof):
            return False
        derived_fields = {
            "status", "reason_code", "temporal_role", "decision_time_usable",
            "outcome_time_usable", "cutoff_at", "first_observed_at", "written_at",
            "available_at", "availability_basis", "source_published_at",
            "revision_number", "revision_id", "parent_revision_id",
            "parent_publication_sha256", "is_value_restatement", "source_use_accepted",
            "acceptance_decision_id", "acceptance_source_id",
            "acceptance_binding_sha256", "pit_eligible", "training_eligible",
            "oos_boundary_status", "qualification_proof_sha256",
        }
        source_row = {
            key: value for key, value in binding.items() if key not in derived_fields
        }
        source_row["status"] = "source_identity_bound"
        recomputed = evaluate_bound_daily_price_row_qualification(
            bound_row=source_row,
            revision_ledger=revision_ledger,
            policy=policy,
        )
        return (
            recomputed.get("status") == "source_qualified"
            and _canonical_bytes(recomputed) == _canonical_bytes(dict(binding))
        )
    except (DailyPriceQualificationError, OSError, TypeError, ValueError, KeyError):
        return False


__all__ = (
    "DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1",
    "DAILY_PRICE_REVISION_ENTRY_SCHEMA_V1",
    "DailyPriceQualificationError",
    "DailyPriceQualificationPolicy",
    "DailyPriceRevisionLedger",
    "DailyPriceRowRevision",
    "PinnedDailyPriceQualificationResolver",
    "SUPPORTED_DAILY_PRICE_SOURCES",
    "TemporalRole",
    "compute_daily_price_available_at",
    "evaluate_bound_daily_price_row_qualification",
    "verify_qualified_binding_payload",
)
