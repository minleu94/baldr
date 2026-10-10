"""同一次已驗 parent callback 的 MA／KDJ／波動三路暫存投影。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, ClassVar, Literal, NoReturn

from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1,
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
    DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1,
    DailyMarketTechnicalKDJProjectionCollectorV1,
    DailyMarketTechnicalUniverseKDJSourceRequestV1,
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
    DailyMarketTechnicalVerifiedProjectionGroupV1,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_STOCKS_V1,
    DailyMarketTechnicalUniverseVolatilitySourceRequestV1,
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
    DailyMarketTechnicalVolatilityProjectionCollectorV1,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_feature_snapshot_v4 import (
        DailyMarketTechnicalFeatureSnapshotV4,
    )
    from app_module.daily_market_technical_parent_v4_query import (
        DailyMarketTechnicalParentV4Row,
    )
    from app_module.daily_market_technical_universe_v4_query import (
        DailyMarketTechnicalUniverseV4ReadSessionBuilder,
    )
    from app_module.daily_market_technical_snapshot_v4_repository import (
        DailyMarketTechnicalBatchArtifactV4,
    )
    from app_module.rule_research_technical_parent_capture_v4 import (
        DailyMarketTechnicalParentCaptureV4VerifiedRead,
    )


DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_SCHEMA = (
    "daily-market-technical-universe-projection-group.v2"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_STOCKS_V1
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MEMBER_MAX_BYTES = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1
)
DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES = (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1
    + DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1
    + DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1
)


class DailyMarketTechnicalUniverseProjectionGroupV2Error(ValueError):
    """三路暫存投影協調器的穩定錯誤碼。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseProjectionGroupV2Error(code, message)


def _strict_cancel_check(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    try:
        cancelled = callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseProjectionGroupV2Error(
            "technical_projection_group_v2_cancel_check_failed", str(exc)
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_projection_group_v2_cancel_callback_invalid")
    if cancelled:
        _fail("technical_projection_group_v2_cancelled")


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalUniverseProjectionGroupV2Error(
            "technical_projection_group_v2_entry_encoding_invalid", str(exc)
        ) from exc


@dataclass(frozen=True, slots=True)
class _CallbackRowProvenanceV2:
    """原 callback 的 compact 參照及 exact pin；不保留 raw snapshot。"""

    ma_entry: DailyMarketTechnicalMaAlignmentCompactEntryV1
    kdj_entry: DailyMarketTechnicalUniverseKDJCompactEntryV1
    volatility_entry: DailyMarketTechnicalUniverseVolatilityCompactEntryV1
    snapshot_identity_sha256: str
    source_pin_sha256: str
    raw_source_window_fingerprint_sha256: str
    source_clock_sha256: str


class DailyMarketTechnicalUniverseProjectionGroupV2:
    """綁定同一 MA request 的 MA、KDJ、波動 collector，僅供同次 observer 使用。

    本類沒有 entry/index/finalize/publication API。完成只表示三路 callback 暫存
    均消費完畢，並不表示 reader-issued 或來源資格。任何例外或取消都永久毒化
    整組並清空所有 member 的部分資料。
    """

    qualification_status: Literal["projection_group_unqualified"] = (
        "projection_group_unqualified"
    )
    _source_request: DailyMarketTechnicalMaAlignmentSourceRequestV1
    _cancel_callback: Callable[[], object] | None
    _ma_collector: DailyMarketTechnicalMaAlignmentVerifiedCollectorV1
    _kdj_collector: DailyMarketTechnicalKDJProjectionCollectorV1
    _volatility_collector: DailyMarketTechnicalVolatilityProjectionCollectorV1
    _kdj_membership_group: DailyMarketTechnicalVerifiedProjectionGroupV1
    _bound_builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder | None
    _bind_attempted: bool
    _failed: bool
    _next_segment_index: int
    _active_parent: DailyMarketTechnicalParentCaptureV4VerifiedRead | None
    _active_segment_index: int | None
    _expected_snapshots: tuple[DailyMarketTechnicalFeatureSnapshotV4, ...]
    _consumed_in_parent: int
    _seen_parent_identities: set[tuple[str, str]]
    _processed_snapshot_count: int
    _completed_parent_count: int
    _member_bytes: list[int]
    _row_provenance: list[_CallbackRowProvenanceV2]
    _max_stocks: int
    _max_total_bytes: int
    __slots__ = (
        "_source_request",
        "_cancel_callback",
        "_ma_collector",
        "_kdj_collector",
        "_volatility_collector",
        "_kdj_membership_group",
        "_bound_builder",
        "_bind_attempted",
        "_failed",
        "_next_segment_index",
        "_active_parent",
        "_active_segment_index",
        "_expected_snapshots",
        "_consumed_in_parent",
        "_seen_parent_identities",
        "_processed_snapshot_count",
        "_completed_parent_count",
        "_member_bytes",
        "_row_provenance",
        "_max_stocks",
        "_max_total_bytes",
    )

    _MEMBER_FIELDS: ClassVar[frozenset[str]] = frozenset({
        "_source_request",
        "_ma_collector",
        "_kdj_collector",
        "_volatility_collector",
        "_kdj_membership_group",
        "_row_provenance",
    })

    def __init__(
        self,
        source_request: DailyMarketTechnicalMaAlignmentSourceRequestV1,
        *,
        cancel_callback: Callable[[], object] | None = None,
        max_stocks: int = DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS,
        max_total_bytes: int = DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
    ) -> None:
        _strict_cancel_check(cancel_callback)
        if type(source_request) is not DailyMarketTechnicalMaAlignmentSourceRequestV1:
            _fail("technical_projection_group_v2_source_request_invalid")
        source_request.to_dict()
        if (
            type(max_stocks) is not int
            or not 1 <= max_stocks <= DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS
            or source_request.included_count > max_stocks
            or type(max_total_bytes) is not int
            or not 1 <= max_total_bytes <= DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES
        ):
            _fail("technical_projection_group_v2_budget_invalid")

        kdj_request = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(
            source_request
        )
        volatility_request = DailyMarketTechnicalUniverseVolatilitySourceRequestV1.from_ma_source_request(
            source_request
        )
        ma_collector = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1(
            source_request,
            cancel_callback=cancel_callback,
        )
        kdj_collector = DailyMarketTechnicalKDJProjectionCollectorV1(
            kdj_request,
            cancel_callback=cancel_callback,
            max_stocks=max_stocks,
            max_index_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1,
        )
        volatility_collector = DailyMarketTechnicalVolatilityProjectionCollectorV1(
            volatility_request,
            cancel_callback=cancel_callback,
            max_stocks=max_stocks,
            max_index_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1,
        )
        membership_group = DailyMarketTechnicalVerifiedProjectionGroupV1(
            ma_collector,
            kdj_collector,
            cancel_callback=cancel_callback,
        )

        object.__setattr__(self, "_source_request", source_request)
        object.__setattr__(self, "_cancel_callback", cancel_callback)
        object.__setattr__(self, "_ma_collector", ma_collector)
        object.__setattr__(self, "_kdj_collector", kdj_collector)
        object.__setattr__(self, "_volatility_collector", volatility_collector)
        object.__setattr__(self, "_kdj_membership_group", membership_group)
        object.__setattr__(self, "_bound_builder", None)
        object.__setattr__(self, "_bind_attempted", False)
        object.__setattr__(self, "_failed", False)
        object.__setattr__(self, "_next_segment_index", 0)
        object.__setattr__(self, "_active_parent", None)
        object.__setattr__(self, "_active_segment_index", None)
        object.__setattr__(self, "_expected_snapshots", ())
        object.__setattr__(self, "_consumed_in_parent", 0)
        object.__setattr__(self, "_seen_parent_identities", set())
        object.__setattr__(self, "_processed_snapshot_count", 0)
        object.__setattr__(self, "_completed_parent_count", 0)
        object.__setattr__(self, "_member_bytes", [0, 0, 0])
        object.__setattr__(self, "_row_provenance", [])
        object.__setattr__(self, "_max_stocks", max_stocks)
        object.__setattr__(self, "_max_total_bytes", max_total_bytes)
        _strict_cancel_check(cancel_callback)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self._MEMBER_FIELDS and hasattr(self, name):
            _fail("technical_projection_group_v2_members_immutable")
        object.__setattr__(self, name, value)

    @property
    def status(self) -> Literal["unbound", "collecting", "between_parents", "failed"]:
        if self._failed:
            return "failed"
        if self._bound_builder is None:
            return "unbound"
        if self._active_parent is not None:
            return "collecting"
        if self._completed_parent_count > 0:
            # 單一 parent 結束不證明 bundle 全母體已完成；下一片 publication seam
            # 必須再以完整 store counts 與 reader 終態決定資格。
            return "between_parents"
        return "collecting"

    @property
    def processed_snapshot_count(self) -> int:
        return 0 if self._failed else self._processed_snapshot_count

    @property
    def completed_parent_count(self) -> int:
        return 0 if self._failed else self._completed_parent_count

    def bind_to_builder(self, builder: object) -> None:
        try:
            self._bind_to_builder(builder)
        except BaseException:
            self._poison()
            raise

    def _bind_to_builder(self, builder: object) -> None:
        from app_module.daily_market_technical_universe_v4_query import (
            DailyMarketTechnicalUniverseV4ReadSessionBuilder,
        )

        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._bind_attempted
            or self._bound_builder is not None
            or type(builder) is not DailyMarketTechnicalUniverseV4ReadSessionBuilder
        ):
            _fail("technical_projection_group_v2_bind_invalid")
        self._bind_attempted = True
        try:
            self._ma_collector.bind_to_builder(builder)
            _strict_cancel_check(self._cancel_callback)
            self._kdj_collector.bind_to_builder(builder)
            _strict_cancel_check(self._cancel_callback)
            builder.bind_verified_projection(self)
            self._bound_builder = builder
            _strict_cancel_check(self._cancel_callback)
        except BaseException:
            self._poison()
            raise

    def begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        try:
            self._begin_verified_parent(segment_index, parent_read)
        except BaseException:
            self._poison()
            raise

    def _begin_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        from app_module.daily_market_technical_feature_snapshot_v4 import (
            DailyMarketTechnicalFeatureSnapshotV4,
        )
        from app_module.daily_market_technical_snapshot_v4_repository import (
            DailyMarketTechnicalBatchArtifactV4,
        )
        from app_module.rule_research_technical_parent_capture_v4 import (
            DailyMarketTechnicalParentCaptureV4VerifiedRead,
        )

        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._bound_builder is None
            or self._active_parent is not None
            or type(segment_index) is not int
            or not 0 <= segment_index < DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1
            or segment_index != self._next_segment_index
            or type(parent_read) is not DailyMarketTechnicalParentCaptureV4VerifiedRead
            or self._completed_parent_count >= DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_SEGMENT_INDEX_V1
        ):
            _fail("technical_projection_group_v2_parent_order_invalid")

        package = parent_read.package
        if not isinstance(package, Mapping):
            _fail("technical_projection_group_v2_parent_package_invalid")
        plan = package.get("plan")
        receipt = package.get("receipt")
        if not isinstance(plan, Mapping) or not isinstance(receipt, Mapping):
            _fail("technical_projection_group_v2_parent_package_invalid")
        parent_plan_identity = plan.get("parent_plan_identity_sha256")
        parent_receipt_identity = receipt.get("receipt_identity_sha256")
        if (
            type(parent_plan_identity) is not str
            or len(parent_plan_identity) != 64
            or type(parent_receipt_identity) is not str
            or len(parent_receipt_identity) != 64
            or any(ch not in "0123456789abcdef" for ch in parent_plan_identity + parent_receipt_identity)
        ):
            _fail("technical_projection_group_v2_parent_identity_invalid")
        parent_identity = (parent_plan_identity, parent_receipt_identity)
        if parent_identity in self._seen_parent_identities:
            _fail("technical_projection_group_v2_parent_replayed")

        batches = parent_read.verified_batches
        if type(batches) is not tuple or not batches:
            _fail("technical_projection_group_v2_parent_batches_invalid")
        total_count = 0
        for batch in batches:
            _strict_cancel_check(self._cancel_callback)
            if type(batch) is not DailyMarketTechnicalBatchArtifactV4:
                _fail("technical_projection_group_v2_parent_batch_type_invalid")
            batch_snapshots = batch.snapshots
            if type(batch_snapshots) is not tuple or len(batch_snapshots) > 16:
                _fail("technical_projection_group_v2_parent_batch_bound_invalid")
            total_count += len(batch_snapshots)
            if (
                total_count > self._max_stocks
                or total_count > self._source_request.included_count
                or total_count > DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS
            ):
                _fail("technical_projection_group_v2_parent_stock_limit")
            if any(type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4 for snapshot in batch_snapshots):
                _fail("technical_projection_group_v2_parent_snapshot_type_invalid")
        if total_count <= 0:
            _fail("technical_projection_group_v2_parent_population_empty")

        # 先驗過所有 batch 數量與型別，才建立有界的 snapshot 引用 tuple。
        snapshots = tuple(
            snapshot
            for batch in batches
            for snapshot in batch.snapshots
        )
        codes = tuple(snapshot.stock_code for snapshot in snapshots)
        if (
            len(snapshots) != total_count
            or codes != tuple(sorted(set(codes)))
            or any(type(code) is not str or not code for code in codes)
        ):
            _fail("technical_projection_group_v2_parent_snapshot_order_invalid")

        self._active_parent = parent_read
        self._active_segment_index = segment_index
        self._expected_snapshots = snapshots
        self._consumed_in_parent = 0
        try:
            self._ma_collector.begin_verified_parent(segment_index, parent_read)
            _strict_cancel_check(self._cancel_callback)
            self._kdj_collector.begin_verified_parent(segment_index, parent_read)
            _strict_cancel_check(self._cancel_callback)
            self._volatility_collector.begin_unqualified_segment(segment_index, snapshots)
            _strict_cancel_check(self._cancel_callback)
            self._seen_parent_identities.add(parent_identity)
        except BaseException:
            self._poison()
            raise

    def consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        try:
            self._consume_verified_snapshot(segment_index, snapshot, parent_row)
        except BaseException:
            self._poison()
            raise

    def _consume_verified_snapshot(
        self,
        segment_index: int,
        snapshot: DailyMarketTechnicalFeatureSnapshotV4,
        parent_row: DailyMarketTechnicalParentV4Row,
    ) -> None:
        from app_module.daily_market_technical_feature_snapshot_v4 import (
            DailyMarketTechnicalFeatureSnapshotV4,
        )
        from app_module.daily_market_technical_parent_v4_query import (
            DailyMarketTechnicalParentV4Row,
        )

        _strict_cancel_check(self._cancel_callback)
        position = self._consumed_in_parent
        if (
            self._failed
            or self._bound_builder is None
            or self._active_parent is None
            or type(segment_index) is not int
            or segment_index != self._active_segment_index
            or type(snapshot) is not DailyMarketTechnicalFeatureSnapshotV4
            or type(parent_row) is not DailyMarketTechnicalParentV4Row
            or position < 0
            or position >= len(self._expected_snapshots)
            or self._expected_snapshots[position] is not snapshot
        ):
            _fail("technical_projection_group_v2_snapshot_order_invalid")

        before = (
            len(self._ma_collector._entries),
            len(self._kdj_collector._entries),
            len(self._volatility_collector._entries),
        )
        self._ma_collector.consume_verified_snapshot(segment_index, snapshot, parent_row)
        _strict_cancel_check(self._cancel_callback)
        self._kdj_collector.consume_verified_snapshot(segment_index, snapshot, parent_row)
        _strict_cancel_check(self._cancel_callback)
        self._volatility_collector.consume_unqualified_snapshot(segment_index, snapshot, parent_row)
        _strict_cancel_check(self._cancel_callback)

        entries = (
            self._ma_collector._entries,
            self._kdj_collector._entries,
            self._volatility_collector._entries,
        )
        if (
            len(entries[0]) != before[0] + 1
            or len(entries[1]) != before[1] + 1
            or len(entries[2]) != before[2] + 1
        ):
            _fail("technical_projection_group_v2_member_count_mismatch")
        new_sizes: list[int] = []
        for items in entries:
            entry = items[-1]
            payload = entry.to_dict()
            new_sizes.append(len(_canonical_bytes(payload)) + 1)
        if new_sizes[1] - 1 > DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1:
            _fail("technical_projection_group_v2_kdj_entry_limit")
        if new_sizes[2] - 1 > DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1:
            _fail("technical_projection_group_v2_volatility_entry_limit")

        # 此處僅限制記憶體中的三份 compact entry buffer；不含最終 index
        # identity、source request 或外層 envelope。發行層必須重新核完整序列化大小。
        next_member_bytes = [
            self._member_bytes[index] + new_sizes[index]
            for index in range(3)
        ]
        if (
            any(value > DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MEMBER_MAX_BYTES for value in next_member_bytes)
            or sum(next_member_bytes) > self._max_total_bytes
            or self._processed_snapshot_count >= self._max_stocks
            or self._processed_snapshot_count >= self._source_request.included_count
            or entries[0][-1].stock_code != snapshot.stock_code
            or entries[1][-1].stock_code != snapshot.stock_code
            or entries[2][-1].stock_code != snapshot.stock_code
        ):
            _fail("technical_projection_group_v2_index_budget_exceeded")
        if (
            self._kdj_collector._index_byte_count != next_member_bytes[1]
            or self._volatility_collector._index_bytes != next_member_bytes[2]
        ):
            _fail("technical_projection_group_v2_member_byte_accounting_mismatch")
        _strict_cancel_check(self._cancel_callback)
        self._row_provenance.append(_CallbackRowProvenanceV2(
            ma_entry=entries[0][-1],
            kdj_entry=entries[1][-1],
            volatility_entry=entries[2][-1],
            snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
            source_pin_sha256=snapshot.source_pin_sha256,
            raw_source_window_fingerprint_sha256=snapshot.raw_source_window_fingerprint_sha256,
            source_clock_sha256=snapshot.source_clock_sha256,
        ))
        self._member_bytes[:] = next_member_bytes
        self._consumed_in_parent += 1
        self._processed_snapshot_count += 1
        _strict_cancel_check(self._cancel_callback)

    def end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        try:
            self._end_verified_parent(segment_index, parent_read)
        except BaseException:
            self._poison()
            raise

    def _end_verified_parent(
        self,
        segment_index: int,
        parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead,
    ) -> None:
        _strict_cancel_check(self._cancel_callback)
        if (
            self._failed
            or self._active_parent is not parent_read
            or type(segment_index) is not int
            or self._active_segment_index != segment_index
            or self._consumed_in_parent != len(self._expected_snapshots)
        ):
            _fail("technical_projection_group_v2_parent_end_invalid")
        self._ma_collector.end_verified_parent(segment_index, parent_read)
        _strict_cancel_check(self._cancel_callback)
        self._kdj_collector.end_verified_parent(segment_index, parent_read)
        _strict_cancel_check(self._cancel_callback)
        self._volatility_collector.end_unqualified_segment(segment_index)
        _strict_cancel_check(self._cancel_callback)
        self._active_parent = None
        self._active_segment_index = None
        self._expected_snapshots = ()
        self._consumed_in_parent = 0
        self._next_segment_index += 1
        self._completed_parent_count += 1

    def _poison(self) -> None:
        if self._failed:
            return
        self._failed = True
        self._active_parent = None
        self._active_segment_index = None
        self._expected_snapshots = ()
        self._consumed_in_parent = 0
        self._seen_parent_identities.clear()
        self._processed_snapshot_count = 0
        self._completed_parent_count = 0
        self._member_bytes[:] = [0, 0, 0]
        self._row_provenance.clear()

        # MA 的公開 finalizer 只能接受尚未完成的 collector；毒化後即使外部
        # 先前保留了 collector 參考，也不能從部分 observations 發行 session。
        self._ma_collector._finished = True
        self._ma_collector._issued_session = None
        self._ma_collector._active_parent = None
        self._ma_collector._observations.clear()
        self._ma_collector._entries.clear()
        self._ma_collector._seen_codes.clear()

        self._kdj_membership_group._poison()
        self._kdj_collector._failed = True
        self._kdj_collector._active_parent = None
        self._kdj_collector._entries.clear()
        self._kdj_collector._seen_codes.clear()
        self._kdj_collector._index_byte_count = 0

        self._volatility_collector._poison()
        self._volatility_collector._entries.clear()
        self._volatility_collector._seen_codes.clear()
        self._volatility_collector._index_bytes = 0


__all__ = [
    "DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS",
    "DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES",
    "DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MEMBER_MAX_BYTES",
    "DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_SCHEMA",
    "DailyMarketTechnicalUniverseProjectionGroupV2",
    "DailyMarketTechnicalUniverseProjectionGroupV2Error",
]
