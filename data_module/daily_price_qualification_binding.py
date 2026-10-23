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
from pathlib import Path, PurePosixPath
import re
from typing import Any, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.daily_source_snapshot import (
    DailySourceRecordAvailability,
)
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
) -> tuple[datetime, DailySourceRecordAvailability]:
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

    def register_publication(
        self,
        *,
        source_id: str,
        relative_path: str,
        expected_sha256: str | None = None,
    ) -> int:
        """讀取並驗證單份 publication 及其 projection manifest，加入不可變修訂鏈。"""

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
        if (
            payload.get("schema_version") != profile["publication_schema"]
            or payload.get("source_id") != source_id
            or payload.get("content_sha256") != _sha256_prefixed(_canonical_bytes(body))
            or payload.get("source_published_at") is not None
        ):
            raise DailyPriceQualificationError("publication_envelope_invalid")

        written_at_dt = _parse_aware_datetime(
            payload.get("written_at"), field_name="written_at"
        )
        written_at_iso = written_at_dt.astimezone(timezone.utc).isoformat()

        # Verify referenced projection manifests exist and match SHA-256
        proj_refs = payload.get("projection_manifests")
        if not isinstance(proj_refs, list) or not proj_refs:
            raise DailyPriceQualificationError("publication_projection_manifests_missing")
        for ref in proj_refs:
            if not isinstance(ref, Mapping):
                raise DailyPriceQualificationError("projection_manifest_ref_invalid")
            ref_rel = ref.get("relative_path")
            ref_sha = ref.get("sha256")
            if not isinstance(ref_rel, str) or not isinstance(ref_sha, str):
                raise DailyPriceQualificationError("projection_manifest_ref_invalid")
            ref_pure = PurePosixPath(ref_rel)
            if ref_pure.is_absolute() or any(p in {"", ".", ".."} for p in ref_pure.parts):
                raise DailyPriceQualificationError("projection_manifest_path_invalid")
            proj_path = self.output_root.joinpath(*ref_pure.parts)
            try:
                proj_raw = _read_bounded_regular_file_no_follow(
                    proj_path, maximum_bytes=MAX_PUBLICATION_ARTIFACT_BYTES
                )
            except Exception as exc:
                raise DailyPriceQualificationError("projection_manifest_missing") from exc
            if _sha256_prefixed(proj_raw) != ref_sha:
                raise DailyPriceQualificationError("projection_manifest_sha256_drift")
            proj_payload = _strict_json(proj_raw)
            if not isinstance(proj_payload, dict):
                raise DailyPriceQualificationError("projection_manifest_json_invalid")
            for sub_field in (
                "raw_response_relative_path",
                "custody_receipt_relative_path",
                "observation_receipt_relative_path",
            ):
                sub_rel = proj_payload.get(sub_field)
                if not isinstance(sub_rel, str) or not sub_rel:
                    raise DailyPriceQualificationError(f"missing_{sub_field}")
                sub_pure = PurePosixPath(sub_rel)
                sub_path = self.output_root.joinpath(*sub_pure.parts)
                if not sub_path.is_file():
                    raise DailyPriceQualificationError(f"missing_artifact:{sub_field}")

        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise DailyPriceQualificationError("publication_rows_missing")

        staged_entries: list[dict[str, Any]] = []
        observed_dates: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise DailyPriceQualificationError("publication_row_invalid")
            source_date_key, trading_date = _parse_date_key(row.get("source_date"))
            stock_code = str(row.get("stock_code") or "").strip()
            if not stock_code:
                raise DailyPriceQualificationError("publication_row_stock_code_missing")
            first_obs_dt = _parse_aware_datetime(
                row.get("first_observed_at"), field_name="first_observed_at"
            )
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
                    "projection_manifest_relative_path": str(
                        row.get("projection_manifest_relative_path") or ""
                    ),
                    "projection_manifest_sha256": str(
                        row.get("projection_manifest_sha256") or ""
                    ),
                    "raw_response_sha256": str(row.get("raw_response_sha256") or ""),
                    "custody_receipt_sha256": str(
                        row.get("custody_receipt_sha256") or ""
                    ),
                    "observation_receipt_sha256": str(
                        row.get("observation_receipt_sha256") or ""
                    ),
                    "csv_sha256": str(row.get("csv_sha256") or ""),
                    "projection_row_sha256": str(row.get("projection_row_sha256") or ""),
                    "sqlite_projection_row_sha256": str(
                        row.get("sqlite_projection_row_sha256") or ""
                    ),
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
            raw_nodes = [
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
        return len(staged_entries)

    def scan_scheduled_publications(self) -> int:
        """掃描 `output_root/scheduled/*_daily_price_sqlite_publication` 下所有不可變 publication。"""

        count = 0
        for source_id, profile in SUPPORTED_DAILY_PRICE_SOURCES.items():
            base = self.output_root / "scheduled" / profile["publication_dir"]
            if not base.is_dir():
                continue
            for json_file in sorted(base.rglob("*.json")):
                rel = json_file.relative_to(self.output_root).as_posix()
                expected_sha = "sha256:" + json_file.stem
                if _SHA256_PREFIX_RE.fullmatch(expected_sha):
                    self.register_publication(
                        source_id=source_id,
                        relative_path=rel,
                        expected_sha256=expected_sha,
                    )
                    count += 1
        return count

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
            not self.acceptance_decision_id or not self.acceptance_binding_sha256
        ):
            raise DailyPriceQualificationError(
                "accepted_source_use_requires_pinned_decision_and_binding_sha256"
            )


class PinnedDailyPriceQualificationResolver:
    """以受外部 SHA 固定的 qualification binding JSON 核發 `DailyPriceQualificationPolicy`。"""

    def __init__(self, binding_path: str | Path, expected_sha256: str) -> None:
        self._binding_path = Path(binding_path).expanduser().resolve(strict=True)
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
        errors = validate_source_acceptance_decision_revision(decision)
        if errors:
            raise DailyPriceQualificationError(
                f"binding_decision_validation_failed:{','.join(errors)}"
            )
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


def verify_qualified_binding_payload(binding: Mapping[str, Any]) -> bool:
    """供 `ForwardSourceObservationRecorder` 驗證非預設 qualification 綁定並非偽造。"""

    proof = binding.get("qualification_proof_sha256")
    if not isinstance(proof, str) or not _SHA256_PREFIX_RE.fullmatch(proof):
        return False
    body = {k: v for k, v in binding.items() if k != "qualification_proof_sha256"}
    if _sha256_prefixed(_canonical_bytes(body)) != proof:
        return False
    if binding.get("source_published_at") is not None:
        return False
    if binding.get("temporal_role") not in ("decision_baseline", "outcome_realization"):
        return False
    avail = binding.get("available_at")
    cutoff = binding.get("cutoff_at")
    if not isinstance(avail, str) or not isinstance(cutoff, str):
        return False
    try:
        avail_dt = _parse_aware_datetime(avail, field_name="available_at")
        cutoff_dt = _parse_aware_datetime(cutoff, field_name="cutoff_at")
    except DailyPriceQualificationError:
        return False
    if avail_dt > cutoff_dt:
        return False
    if binding.get("source_use_accepted") is True:
        if not binding.get("acceptance_decision_id") or not _SHA256_PREFIX_RE.fullmatch(
            str(binding.get("acceptance_binding_sha256") or "")
        ):
            return False
    else:
        if binding.get("pit_eligible") is not False or binding.get("training_eligible") is not False:
            return False
    return True


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
