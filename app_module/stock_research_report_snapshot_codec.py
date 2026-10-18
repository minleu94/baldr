"""一般個股完整報告投影的有限、版本化 canonical codec。

本版明確拒絕輸入或解碼樹中任何 ``ResearchRankContextDTO`` 節點：該DTO建構子會解析
檔案系統路徑，codec不允許以解碼間接執行此行為。其餘已列入allowlist的報告欄位完整保存。
"""
from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType, UnionType
from typing import Any, Literal, Mapping, Union, get_args, get_origin, get_type_hints

from app_module.advice_dtos import (
    AdviceAction,
    AdviceClassification,
    PortfolioAdviceDTO,
    RecommendationAdviceDTO,
)
from app_module.portfolio_research_stock_projection import (
    PortfolioScenarioStockProjection,
    PortfolioScenarioStockReference,
    PortfolioScenarioStockTarget,
)
from app_module.research_session.session_dtos import (
    ResearchRankContextDTO,
    ResearchStockContextDTO,
)
from app_module.stock_research_report_dtos import (
    STOCK_RESEARCH_REPORT_SCHEMA_VERSION,
    ReportFreshness,
    ReportQuality,
    ReportSectionStatus,
    StockAdviceSnapshotDTO,
    StockEvidenceEventDTO,
    StockFlowObservationDTO,
    StockFundamentalComparisonDTO,
    StockFundamentalObservationDTO,
    StockMarketStatusEvidenceDTO,
    StockMarketStatusSnapshotDTO,
    StockMetricDTO,
    StockMLSnapshotDTO,
    StockOfficialAttentionDTO,
    StockOfficialAttentionRowDTO,
    StockOriginalRankingReportDTO,
    StockOutcomeDTO,
    StockPositionSnapshotDTO,
    StockPricePointDTO,
    StockReportSectionDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
    StockSavedSourceOptionDTO,
    StockTechnicalHistoryRowDTO,
    StockTechnicalSnapshotDTO,
    StockTradingRestrictionDTO,
)
from app_module.watchlist_analysis_service import WatchlistAnalysisDTO


STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1 = (
    "stock-research-report-projection-snapshot.v1"
)
_UNSUPPORTED_DATACLASS_IDS = frozenset(
    {f"{ResearchRankContextDTO.__module__}.{ResearchRankContextDTO.__qualname__}"}
)
_MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
_MAX_DEPTH = 64
_MAX_NODES = 100_000
_MAX_INTEGER_DIGITS = 256
_MAX_INTEGER_BITS = 850
_MAX_FLOAT_HEX_LENGTH = 32
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class StockResearchReportSnapshotCodecError(ValueError):
    """快照 payload、型別或身份不符合 codec 契約。"""


@dataclass(frozen=True, slots=True)
class StockResearchReportProjectionSnapshot:
    identity_sha256: str
    stock_code: str
    report: StockResearchReportDTO
    context: ResearchStockContextDTO | None
    canonical_json: str


_DATACLASS_TYPES: tuple[type[Any], ...] = (
    StockReportSourceDTO,
    StockReportSectionDTO,
    StockMetricDTO,
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
    StockFundamentalObservationDTO,
    StockFundamentalComparisonDTO,
    StockFlowObservationDTO,
    StockOutcomeDTO,
    StockEvidenceEventDTO,
    StockPositionSnapshotDTO,
    StockTechnicalHistoryRowDTO,
    StockTradingRestrictionDTO,
    StockMarketStatusEvidenceDTO,
    StockOfficialAttentionRowDTO,
    StockOfficialAttentionDTO,
    StockMarketStatusSnapshotDTO,
    StockMLSnapshotDTO,
    StockSavedSourceOptionDTO,
    StockOriginalRankingReportDTO,
    StockAdviceSnapshotDTO,
    StockResearchReportDTO,
    RecommendationAdviceDTO,
    PortfolioAdviceDTO,
    WatchlistAnalysisDTO,
    PortfolioScenarioStockReference,
    PortfolioScenarioStockTarget,
    PortfolioScenarioStockProjection,
    ResearchRankContextDTO,
    ResearchStockContextDTO,
)
_ENUM_TYPES: tuple[type[Enum], ...] = (
    ReportQuality,
    ReportFreshness,
    ReportSectionStatus,
    AdviceAction,
    AdviceClassification,
)
_DATACLASS_IDS = {
    f"{item.__module__}.{item.__qualname__}": item for item in _DATACLASS_TYPES
}
_DATACLASS_NAMES = {item: key for key, item in _DATACLASS_IDS.items()}
_ENUM_IDS = {f"{item.__module__}.{item.__qualname__}": item for item in _ENUM_TYPES}
_ENUM_NAMES = {item: key for key, item in _ENUM_IDS.items()}


@dataclass
class _Budget:
    nodes: int = 0
    quoted_text_bytes: int = 0

    def visit(self, depth: int) -> None:
        if depth > _MAX_DEPTH:
            raise StockResearchReportSnapshotCodecError("payload nesting exceeds limit")
        self.nodes += 1
        if self.nodes > _MAX_NODES:
            raise StockResearchReportSnapshotCodecError("payload node count exceeds limit")

    def text(self, value: str) -> None:
        try:
            raw = value.encode("utf-8", errors="strict")
            if len(raw) > _MAX_PAYLOAD_BYTES:
                raise StockResearchReportSnapshotCodecError("payload text exceeds size limit")
            quoted = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            size = len(quoted.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as exc:
            raise StockResearchReportSnapshotCodecError("payload contains invalid UTF-8 text") from exc
        self.quoted_text_bytes += size
        if self.quoted_text_bytes > _MAX_PAYLOAD_BYTES:
            raise StockResearchReportSnapshotCodecError("payload text exceeds size limit")


def _class_name(value: type[Any]) -> str:
    if value in _DATACLASS_NAMES:
        return _DATACLASS_NAMES[value]
    if value in _ENUM_NAMES:
        return _ENUM_NAMES[value]
    raise StockResearchReportSnapshotCodecError("class is outside the typed allowlist")


def _field_specs(cls: type[Any]) -> tuple[tuple[str, Any], ...]:
    if cls not in _DATACLASS_NAMES or not is_dataclass(cls):
        raise StockResearchReportSnapshotCodecError("dataclass is outside the typed allowlist")
    try:
        hints = get_type_hints(cls)
    except (NameError, TypeError) as exc:
        raise StockResearchReportSnapshotCodecError(
            f"cannot resolve trusted DTO annotations for {_class_name(cls)}"
        ) from exc
    declared = fields(cls)
    names = tuple(item.name for item in declared)
    if len(names) != len(set(names)) or any(name not in hints for name in names):
        raise StockResearchReportSnapshotCodecError(
            f"incomplete trusted DTO field annotations for {_class_name(cls)}"
        )
    return tuple((item.name, hints[item.name]) for item in declared)


def _is_supported_mapping(value: object) -> bool:
    return type(value) in (dict, MappingProxyType)


def _literal_matches(value: object, values: tuple[object, ...]) -> bool:
    return any(type(value) is type(candidate) and value == candidate for candidate in values)


def _runtime_matches(value: object, expected: Any) -> bool:
    if expected is Any:
        return True
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in (Union, UnionType):
        return any(_runtime_matches(value, item) for item in args)
    if origin is Literal:
        return _literal_matches(value, args)
    if origin is MappingABC:
        return _is_supported_mapping(value)
    if origin is tuple:
        return type(value) is tuple
    if origin is list:
        return type(value) is list
    if isinstance(expected, type) and issubclass(expected, Enum):
        return type(value) is expected
    if isinstance(expected, type) and expected in _DATACLASS_NAMES:
        return type(value) is expected
    if expected is Decimal or expected is float or expected is int or expected is bool or expected is str:
        return type(value) is expected
    if expected is type(None):
        return value is None
    return False


def _select_union_branch(value: object, expected: Any) -> Any:
    branches = tuple(item for item in get_args(expected) if item is not type(None))
    matches = tuple(item for item in branches if _runtime_matches(value, item))
    if len(matches) != 1:
        raise StockResearchReportSnapshotCodecError("ambiguous or invalid Union field value")
    return matches[0]


def _encode_value(value: object, expected: Any, budget: _Budget, depth: int) -> object:
    budget.visit(depth)
    origin = get_origin(expected)
    args = get_args(expected)

    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        return _encode_body(value, _select_union_branch(value, expected), budget, depth)
    return _encode_body(value, expected, budget, depth)


def _encode_body(value: object, expected: Any, budget: _Budget, depth: int) -> object:
    origin = get_origin(expected)
    args = get_args(expected)

    if expected is Any:
        return _encode_dynamic(value, budget, depth)
    if origin is Literal:
        if not _literal_matches(value, args):
            raise StockResearchReportSnapshotCodecError("Literal field value is not allowed")
        if type(value) is str:
            budget.text(value)
        return value
    if origin is MappingABC:
        if not _is_supported_mapping(value):
            raise StockResearchReportSnapshotCodecError("Mapping field has the wrong type")
        key_type, value_type = args if len(args) == 2 else (str, Any)
        if key_type not in (str, Any):
            raise StockResearchReportSnapshotCodecError("Mapping keys must be strings")
        return _encode_mapping(value, value_type, budget, depth)
    if origin is tuple or expected is tuple:
        if type(value) is not tuple:
            raise StockResearchReportSnapshotCodecError("tuple field has the wrong type")
        if not args:
            item_types = (Any,) * len(value)
        elif len(args) == 2 and args[1] is Ellipsis:
            item_types = (args[0],) * len(value)
        else:
            if len(args) != len(value):
                raise StockResearchReportSnapshotCodecError("tuple field length does not match its type")
            item_types = args
        return {
            "$type": "tuple",
            "items": [
                _encode_value(item, item_type, budget, depth + 1)
                for item, item_type in zip(value, item_types)
            ],
        }
    if origin is list or expected is list:
        if type(value) is not list:
            raise StockResearchReportSnapshotCodecError("list field has the wrong type")
        item_type = args[0] if args else Any
        return {
            "$type": "list",
            "items": [_encode_value(item, item_type, budget, depth + 1) for item in value],
        }
    if expected is type(None):
        if value is not None:
            raise StockResearchReportSnapshotCodecError("None field has the wrong type")
        return None
    if expected is Decimal:
        return _encode_decimal(value)
    if expected is float:
        return _encode_float(value)
    if expected is bool:
        if type(value) is not bool:
            raise StockResearchReportSnapshotCodecError("bool field has the wrong type")
        return value
    if expected is int:
        return _encode_integer(value)
    if expected is str:
        if type(value) is not str:
            raise StockResearchReportSnapshotCodecError("str field has the wrong type")
        budget.text(value)
        return value
    if isinstance(expected, type) and issubclass(expected, Enum):
        if expected not in _ENUM_NAMES or type(value) is not expected:
            raise StockResearchReportSnapshotCodecError("Enum field is outside its typed allowlist")
        member_value = value.value  # type: ignore[union-attr]
        if type(member_value) is str:
            budget.text(member_value)
        return {"$type": "enum", "class": _class_name(expected), "value": member_value}
    if isinstance(expected, type) and expected in _DATACLASS_NAMES:
        if expected is ResearchRankContextDTO:
            raise StockResearchReportSnapshotCodecError(
                "ResearchRankContextDTO is unsupported because its constructor resolves filesystem paths"
            )
        if type(value) is not expected:
            raise StockResearchReportSnapshotCodecError("dataclass field has the wrong type")
        return _encode_dataclass(value, budget, depth)
    raise StockResearchReportSnapshotCodecError("unsupported trusted DTO annotation")


def _encode_dynamic(value: object, budget: _Budget, depth: int) -> object:
    if value is None:
        return None
    if type(value) is bool:
        return value
    if type(value) is int:
        return _encode_integer(value)
    if type(value) is float:
        return _encode_float(value)
    if type(value) is str:
        budget.text(value)
        return value
    if type(value) is Decimal:
        return _encode_decimal(value)
    if isinstance(value, Enum):
        enum_type = type(value)
        if enum_type not in _ENUM_NAMES:
            raise StockResearchReportSnapshotCodecError("Enum is outside the typed allowlist")
        member_value = value.value
        if type(member_value) not in (str, int, bool):
            raise StockResearchReportSnapshotCodecError("Enum value has an unsupported type")
        if type(member_value) is str:
            budget.text(member_value)
        return {"$type": "enum", "class": _class_name(enum_type), "value": member_value}
    if type(value) is tuple:
        return {
            "$type": "tuple",
            "items": [_encode_value(item, Any, budget, depth + 1) for item in value],
        }
    if type(value) is list:
        return {
            "$type": "list",
            "items": [_encode_value(item, Any, budget, depth + 1) for item in value],
        }
    if _is_supported_mapping(value):
        return _encode_mapping(value, Any, budget, depth)
    if type(value) in _DATACLASS_NAMES:
        return _encode_dataclass(value, budget, depth)
    raise StockResearchReportSnapshotCodecError(
        f"unsupported Any value type: {type(value).__module__}.{type(value).__qualname__}"
    )


def _encode_mapping(
    value: MappingABC[object, object], item_type: Any, budget: _Budget, depth: int
) -> object:
    if not _is_supported_mapping(value):
        raise StockResearchReportSnapshotCodecError("custom Mapping implementations are unsupported")
    items: dict[str, object] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise StockResearchReportSnapshotCodecError("Mapping keys must be strings")
        if key in items:
            raise StockResearchReportSnapshotCodecError("duplicate Mapping key")
        budget.text(key)
        items[key] = _encode_value(item, item_type, budget, depth + 1)
    return {"$type": "mapping", "items": items}


def _encode_dataclass(value: object, budget: _Budget, depth: int) -> object:
    cls = type(value)
    if cls is ResearchRankContextDTO:
        raise StockResearchReportSnapshotCodecError(
            "ResearchRankContextDTO is unsupported because its constructor resolves filesystem paths"
        )
    specs = _field_specs(cls)
    encoded_fields: dict[str, object] = {}
    for field_name, annotation in specs:
        budget.text(field_name)
        encoded_fields[field_name] = _encode_value(
            getattr(value, field_name), annotation, budget, depth + 1
        )
    class_name = _class_name(cls)
    budget.text(class_name)
    return {"$type": "dataclass", "class": class_name, "fields": encoded_fields}


def _encode_integer(value: object) -> int:
    if type(value) is not int:
        raise StockResearchReportSnapshotCodecError("int field has the wrong type")
    if value.bit_length() > _MAX_INTEGER_BITS:
        raise StockResearchReportSnapshotCodecError("integer magnitude exceeds limit")
    return value


def _encode_decimal(value: object) -> object:
    if type(value) is not Decimal or not value.is_finite():
        raise StockResearchReportSnapshotCodecError("Decimal must be finite")
    return {"$type": "decimal", "value": str(value)}


def _encode_float(value: object) -> object:
    if type(value) is not float or not math.isfinite(value):
        raise StockResearchReportSnapshotCodecError("float must be finite")
    return {"$type": "float", "hex": value.hex()}


def _check_wire_tree(root: object) -> None:
    stack: list[tuple[object, int]] = [(root, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > _MAX_NODES:
            raise StockResearchReportSnapshotCodecError("payload node count exceeds limit")
        if depth > _MAX_DEPTH:
            raise StockResearchReportSnapshotCodecError("payload nesting exceeds limit")
        if type(node) is dict:
            stack.extend((item, depth + 1) for item in node.values())
        elif type(node) is list:
            stack.extend((item, depth + 1) for item in node)
        elif type(node) not in (str, int, bool, type(None)):
            raise StockResearchReportSnapshotCodecError("payload contains an unsupported JSON value")


def _canonical_json(root: object) -> str:
    try:
        value = json.dumps(
            root,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(value.encode("utf-8", errors="strict")) > _MAX_PAYLOAD_BYTES:
            raise StockResearchReportSnapshotCodecError("payload exceeds 4 MiB")
        return value
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        if isinstance(exc, StockResearchReportSnapshotCodecError):
            raise
        raise StockResearchReportSnapshotCodecError("payload cannot be canonicalized") from exc


def _validate_report_context(
    report: object, context: object | None
) -> tuple[StockResearchReportDTO, ResearchStockContextDTO | None]:
    if type(report) is not StockResearchReportDTO:
        raise StockResearchReportSnapshotCodecError("report must be StockResearchReportDTO")
    if report.read_only is not True:
        raise StockResearchReportSnapshotCodecError("report must remain read-only")
    if report.schema_version != STOCK_RESEARCH_REPORT_SCHEMA_VERSION:
        raise StockResearchReportSnapshotCodecError("unsupported report schema version")
    if context is not None:
        if type(context) is not ResearchStockContextDTO:
            raise StockResearchReportSnapshotCodecError(
                "context must be ResearchStockContextDTO or None"
            )
        assert isinstance(context, ResearchStockContextDTO)
        if context.stock_code != report.stock_code:
            raise StockResearchReportSnapshotCodecError(
                "report/context stock identity mismatch"
            )
        if context.rank_context is not None:
            raise StockResearchReportSnapshotCodecError(
                "ResearchRankContextDTO is unsupported because its constructor resolves filesystem paths"
            )
    return report, context


def _reject_unsupported_decode_nodes(root: object) -> None:
    """拒絕建構子會碰檔案系統的節點，避免 reader 間接執行檔案操作。"""
    stack = [root]
    while stack:
        node = stack.pop()
        if type(node) is dict:
            if (
                node.get("$type") == "dataclass"
                and type(node.get("class")) is str
                and node.get("class") in _UNSUPPORTED_DATACLASS_IDS
            ):
                raise StockResearchReportSnapshotCodecError(
                    "ResearchRankContextDTO is unsupported because its constructor resolves filesystem paths"
                )
            stack.extend(node.values())
        elif type(node) is list:
            stack.extend(node)


def _reject_non_read_only_report_node(node: object) -> None:
    """在呼叫DTO建構子前拒絕未標記唯讀的報告投影。"""
    if (
        type(node) is dict
        and node.get("$type") == "dataclass"
        and node.get("class") == _DATACLASS_NAMES[StockResearchReportDTO]
        and type(node.get("fields")) is dict
        and node["fields"].get("read_only") is not True
    ):
        raise StockResearchReportSnapshotCodecError("report must remain read-only")


def create_stock_research_report_projection_snapshot(
    report: StockResearchReportDTO,
    context: ResearchStockContextDTO | None = None,
) -> StockResearchReportProjectionSnapshot:
    """將完整 report/context 編碼為有界、內容定址的唯讀投影。"""

    report, context = _validate_report_context(report, context)
    budget = _Budget()
    budget.visit(0)
    wire: dict[str, object] = {
        "schema_version": STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
        "stock_code": _encode_value(report.stock_code, str, budget, 1),
        "report": _encode_value(report, StockResearchReportDTO, budget, 1),
        "context": _encode_value(
            context, ResearchStockContextDTO | None, budget, 1
        ),
    }
    _check_wire_tree(wire)
    canonical_json = _canonical_json(wire)
    identity_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    # 經同一 reader 重新建構，避免公開 DTO 共用 caller 的可變 Mapping/list。
    return read_stock_research_report_projection_snapshot(
        canonical_json, expected_identity_sha256=identity_sha256
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StockResearchReportSnapshotCodecError("duplicate JSON object key")
        result[key] = value
    return result


def _parse_integer(text: str) -> int:
    digits = text.lstrip("-")
    if not digits or len(digits) > _MAX_INTEGER_DIGITS:
        raise StockResearchReportSnapshotCodecError("JSON integer text exceeds limit")
    value = int(text)
    if value.bit_length() > _MAX_INTEGER_BITS:
        raise StockResearchReportSnapshotCodecError("integer magnitude exceeds limit")
    return value


def _reject_json_number(_text: str) -> object:
    raise StockResearchReportSnapshotCodecError("untagged JSON float is not allowed")


def _reject_json_constant(_text: str) -> object:
    raise StockResearchReportSnapshotCodecError("non-finite JSON number is not allowed")


def _check_raw_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_DEPTH:
                raise StockResearchReportSnapshotCodecError("payload nesting exceeds limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise StockResearchReportSnapshotCodecError("invalid JSON nesting")
    if in_string or depth != 0:
        raise StockResearchReportSnapshotCodecError("invalid JSON nesting")


def _node_matches(node: object, expected: Any) -> bool:
    if expected is Any:
        return True
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in (Union, UnionType):
        return any(_node_matches(node, item) for item in args)
    if origin is Literal:
        return _literal_matches(node, args)
    if origin is MappingABC:
        return _tag_is(node, "mapping")
    if origin is tuple or expected is tuple:
        return _tag_is(node, "tuple")
    if origin is list or expected is list:
        return _tag_is(node, "list")
    if isinstance(expected, type) and issubclass(expected, Enum):
        return _tag_class_is(node, "enum", expected)
    if isinstance(expected, type) and expected in _DATACLASS_NAMES:
        return _tag_class_is(node, "dataclass", expected)
    if expected is Decimal:
        return _tag_is(node, "decimal")
    if expected is float:
        return _tag_is(node, "float")
    if expected is bool:
        return type(node) is bool
    if expected is int:
        return type(node) is int
    if expected is str:
        return type(node) is str
    if expected is type(None):
        return node is None
    return False


def _tag_is(node: object, tag: str) -> bool:
    return type(node) is dict and node.get("$type") == tag


def _tag_class_is(node: object, tag: str, cls: type[Any]) -> bool:
    return _tag_is(node, tag) and node.get("class") == _class_name(cls)  # type: ignore[union-attr]


def _decode_value(node: object, expected: Any, budget: _Budget, depth: int) -> object:
    budget.visit(depth)
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in (Union, UnionType):
        if node is None and type(None) in args:
            return None
        branches = tuple(item for item in args if item is not type(None))
        matches = tuple(item for item in branches if _node_matches(node, item))
        if len(matches) != 1:
            raise StockResearchReportSnapshotCodecError("ambiguous or invalid Union payload")
        return _decode_body(node, matches[0], budget, depth)
    return _decode_body(node, expected, budget, depth)


def _decode_body(node: object, expected: Any, budget: _Budget, depth: int) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if expected is Any:
        return _decode_dynamic(node, budget, depth)
    if origin is Literal:
        if not _literal_matches(node, args):
            raise StockResearchReportSnapshotCodecError("Literal payload value is not allowed")
        return node
    if origin is MappingABC:
        key_type, value_type = args if len(args) == 2 else (str, Any)
        if key_type not in (str, Any):
            raise StockResearchReportSnapshotCodecError("Mapping keys must be strings")
        return _decode_mapping(node, value_type, budget, depth)
    if origin is tuple or expected is tuple:
        items = _tag_items(node, "tuple")
        if not args:
            item_types = (Any,) * len(items)
        elif len(args) == 2 and args[1] is Ellipsis:
            item_types = (args[0],) * len(items)
        else:
            if len(args) != len(items):
                raise StockResearchReportSnapshotCodecError("tuple payload length does not match its type")
            item_types = args
        return tuple(
            _decode_value(item, item_type, budget, depth + 1)
            for item, item_type in zip(items, item_types)
        )
    if origin is list or expected is list:
        items = _tag_items(node, "list")
        item_type = args[0] if args else Any
        return [
            _decode_value(item, item_type, budget, depth + 1) for item in items
        ]
    if expected is type(None):
        if node is not None:
            raise StockResearchReportSnapshotCodecError("None payload has the wrong type")
        return None
    if expected is Decimal:
        return _decode_decimal(node)
    if expected is float:
        return _decode_float(node)
    if expected is bool:
        if type(node) is not bool:
            raise StockResearchReportSnapshotCodecError("bool payload has the wrong type")
        return node
    if expected is int:
        if type(node) is not int or node.bit_length() > _MAX_INTEGER_BITS:
            raise StockResearchReportSnapshotCodecError("int payload has the wrong type or magnitude")
        return node
    if expected is str:
        if type(node) is not str:
            raise StockResearchReportSnapshotCodecError("str payload has the wrong type")
        return node
    if isinstance(expected, type) and issubclass(expected, Enum):
        return _decode_enum(node, expected)
    if isinstance(expected, type) and expected in _DATACLASS_NAMES:
        return _decode_dataclass(node, expected, budget, depth)
    raise StockResearchReportSnapshotCodecError("unsupported trusted DTO annotation")


def _decode_dynamic(node: object, budget: _Budget, depth: int) -> object:
    if node is None or type(node) in (str, int, bool):
        return node
    if type(node) is not dict or type(node.get("$type")) is not str:
        raise StockResearchReportSnapshotCodecError("Any payload must use an allowlisted typed node")
    tag = node["$type"]
    if tag == "decimal":
        return _decode_decimal(node)
    if tag == "float":
        return _decode_float(node)
    if tag == "tuple":
        items = _tag_items(node, "tuple")
        return tuple(_decode_value(item, Any, budget, depth + 1) for item in items)
    if tag == "list":
        items = _tag_items(node, "list")
        return [_decode_value(item, Any, budget, depth + 1) for item in items]
    if tag == "mapping":
        return _decode_mapping(node, Any, budget, depth)
    if tag == "enum":
        class_id = node.get("class")
        enum_type = _ENUM_IDS.get(class_id) if type(class_id) is str else None
        if enum_type is None:
            raise StockResearchReportSnapshotCodecError("Enum class is outside the typed allowlist")
        return _decode_enum(node, enum_type)
    if tag == "dataclass":
        class_id = node.get("class")
        if type(class_id) is str and class_id in _UNSUPPORTED_DATACLASS_IDS:
            raise StockResearchReportSnapshotCodecError(
                "ResearchRankContextDTO is unsupported because its constructor resolves filesystem paths"
            )
        dataclass_type = _DATACLASS_IDS.get(class_id) if type(class_id) is str else None
        if dataclass_type is None:
            raise StockResearchReportSnapshotCodecError("dataclass is outside the typed allowlist")
        return _decode_dataclass(node, dataclass_type, budget, depth)
    raise StockResearchReportSnapshotCodecError("unknown typed Any node")


def _require_tagged_object(node: object, tag: str, fields_expected: set[str]) -> dict[str, object]:
    if type(node) is not dict or node.get("$type") != tag or set(node) != fields_expected:
        raise StockResearchReportSnapshotCodecError(f"invalid {tag} node shape")
    return node


def _tag_items(node: object, tag: str) -> list[object]:
    tagged = _require_tagged_object(node, tag, {"$type", "items"})
    items = tagged["items"]
    if type(items) is not list:
        raise StockResearchReportSnapshotCodecError(f"invalid {tag} items")
    return items


def _decode_mapping(
    node: object, value_type: Any, budget: _Budget, depth: int
) -> dict[str, object]:
    tagged = _require_tagged_object(node, "mapping", {"$type", "items"})
    items = tagged["items"]
    if type(items) is not dict or any(type(key) is not str for key in items):
        raise StockResearchReportSnapshotCodecError("invalid Mapping items")
    return {
        key: _decode_value(value, value_type, budget, depth + 1)
        for key, value in items.items()
    }


def _decode_decimal(node: object) -> Decimal:
    tagged = _require_tagged_object(node, "decimal", {"$type", "value"})
    text = tagged["value"]
    if type(text) is not str or not text or len(text) > _MAX_PAYLOAD_BYTES:
        raise StockResearchReportSnapshotCodecError("invalid Decimal text")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise StockResearchReportSnapshotCodecError("invalid Decimal text") from exc
    if not value.is_finite() or str(value) != text:
        raise StockResearchReportSnapshotCodecError("Decimal must be finite and canonical")
    return value


def _decode_float(node: object) -> float:
    tagged = _require_tagged_object(node, "float", {"$type", "hex"})
    value = tagged["hex"]
    if type(value) is not str or not value or len(value) > _MAX_FLOAT_HEX_LENGTH:
        raise StockResearchReportSnapshotCodecError("invalid float hex value")
    try:
        decoded = float.fromhex(value)
    except (OverflowError, ValueError) as exc:
        raise StockResearchReportSnapshotCodecError("invalid float hex value") from exc
    if not math.isfinite(decoded) or decoded.hex() != value:
        raise StockResearchReportSnapshotCodecError("float must be finite and canonical")
    return decoded


def _decode_enum(node: object, enum_type: type[Enum]) -> Enum:
    if enum_type not in _ENUM_NAMES:
        raise StockResearchReportSnapshotCodecError("Enum class is outside the typed allowlist")
    tagged = _require_tagged_object(node, "enum", {"$type", "class", "value"})
    if tagged["class"] != _class_name(enum_type):
        raise StockResearchReportSnapshotCodecError("Enum class does not match field annotation")
    raw_value = tagged["value"]
    for member in enum_type:
        if type(member.value) is type(raw_value) and member.value == raw_value:
            return member
    raise StockResearchReportSnapshotCodecError("unknown Enum value")


def _decode_dataclass(
    node: object, cls: type[Any], budget: _Budget, depth: int
) -> object:
    if cls is ResearchRankContextDTO:
        raise StockResearchReportSnapshotCodecError(
            "ResearchRankContextDTO is unsupported because its constructor resolves filesystem paths"
        )
    class_name = _class_name(cls)
    tagged = _require_tagged_object(
        node, "dataclass", {"$type", "class", "fields"}
    )
    if tagged["class"] != class_name:
        raise StockResearchReportSnapshotCodecError("dataclass class does not match field annotation")
    field_nodes = tagged["fields"]
    specs = _field_specs(cls)
    expected_names = {name for name, _annotation in specs}
    if type(field_nodes) is not dict or set(field_nodes) != expected_names:
        raise StockResearchReportSnapshotCodecError(
            f"unknown or missing field in {class_name}"
        )
    values = {
        name: _decode_value(field_nodes[name], annotation, budget, depth + 1)
        for name, annotation in specs
    }
    try:
        return cls(**values)
    except Exception as exc:
        raise StockResearchReportSnapshotCodecError(
            f"invalid typed DTO {class_name}"
        ) from exc


def read_stock_research_report_projection_snapshot(
    payload: bytes | str,
    *,
    expected_identity_sha256: str,
) -> StockResearchReportProjectionSnapshot:
    """只從固定 bytes 解碼；不碰報告 producer 或其他來源。"""

    if type(expected_identity_sha256) is not str or _SHA256_RE.fullmatch(
        expected_identity_sha256
    ) is None:
        raise StockResearchReportSnapshotCodecError("expected identity must be lowercase SHA-256")
    if type(payload) is bytes:
        if len(payload) > _MAX_PAYLOAD_BYTES:
            raise StockResearchReportSnapshotCodecError("payload exceeds 4 MiB")
        raw = payload
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise StockResearchReportSnapshotCodecError("payload must be UTF-8") from exc
    elif type(payload) is str:
        if len(payload) > _MAX_PAYLOAD_BYTES:
            raise StockResearchReportSnapshotCodecError("payload exceeds 4 MiB")
        text = payload
        try:
            raw = text.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise StockResearchReportSnapshotCodecError("payload must be valid UTF-8") from exc
    else:
        raise StockResearchReportSnapshotCodecError("payload must be bytes or str")
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise StockResearchReportSnapshotCodecError("payload exceeds 4 MiB")
    _check_raw_depth(text)
    try:
        wire = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_integer,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_constant,
        )
    except StockResearchReportSnapshotCodecError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise StockResearchReportSnapshotCodecError("invalid JSON payload") from exc
    _check_wire_tree(wire)
    canonical_json = _canonical_json(wire)
    canonical_bytes = canonical_json.encode("utf-8")
    if canonical_bytes != raw:
        raise StockResearchReportSnapshotCodecError("payload is not canonical JSON")
    identity_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    if identity_sha256 != expected_identity_sha256:
        raise StockResearchReportSnapshotCodecError("snapshot SHA-256 mismatch")
    _reject_unsupported_decode_nodes(wire)
    if type(wire) is not dict or set(wire) != {
        "schema_version",
        "stock_code",
        "report",
        "context",
    }:
        raise StockResearchReportSnapshotCodecError("invalid snapshot envelope fields")
    if wire["schema_version"] != STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1:
        raise StockResearchReportSnapshotCodecError("unsupported snapshot schema version")
    if type(wire["stock_code"]) is not str:
        raise StockResearchReportSnapshotCodecError("snapshot stock_code must be text")
    _reject_non_read_only_report_node(wire["report"])
    budget = _Budget()
    budget.visit(0)
    report = _decode_value(wire["report"], StockResearchReportDTO, budget, 1)
    context = _decode_value(
        wire["context"], ResearchStockContextDTO | None, budget, 1
    )
    report, context = _validate_report_context(report, context)
    if wire["stock_code"] != report.stock_code:
        raise StockResearchReportSnapshotCodecError("envelope/report stock identity mismatch")
    # DTO 建構子可能正規化欄位；重編碼仍須逐位符合 canonical bytes。
    rebuilt_budget = _Budget()
    rebuilt_budget.visit(0)
    rebuilt_wire: dict[str, object] = {
        "schema_version": STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
        "stock_code": _encode_value(report.stock_code, str, rebuilt_budget, 1),
        "report": _encode_value(report, StockResearchReportDTO, rebuilt_budget, 1),
        "context": _encode_value(
            context, ResearchStockContextDTO | None, rebuilt_budget, 1
        ),
    }
    _check_wire_tree(rebuilt_wire)
    if _canonical_json(rebuilt_wire) != canonical_json:
        raise StockResearchReportSnapshotCodecError("typed DTO round-trip changed payload")
    return StockResearchReportProjectionSnapshot(
        identity_sha256=identity_sha256,
        stock_code=report.stock_code,
        report=report,
        context=context,
        canonical_json=canonical_json,
    )
