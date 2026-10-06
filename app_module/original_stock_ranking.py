"""受控發布並唯讀讀回既有原始強弱排名。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import ast
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import MappingProxyType, SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast

from app_module.research_session.session_dtos import ResearchRankContextDTO

if TYPE_CHECKING:
    import pandas as pd
    from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot

OriginalPeriod = Literal["day", "week"]
OriginalDirection = Literal["strong", "weak"]
ORIGINAL_RANKING_MANIFEST_SCHEMA = "original-stock-ranking-manifest.v1"
ORIGINAL_RANKING_ARTIFACT_SCHEMA = "original-stock-ranking-artifact.v1"
ORIGINAL_RANKING_POINTER_SCHEMA = "original-stock-ranking-pointer.v1"
_MAX_PRICE_POINTS_PER_STOCK = 120
_MAX_STOCKS = 16
_MAX_RANKING_ARTIFACT_BYTES = 8 * 1024 * 1024
_MAX_RANKING_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_RANKING_POINTER_BYTES = 16 * 1024
_MAX_NEW_BYTES_PER_RUN = 8 * 1024 * 1024
_MAX_TEMPORARY_BYTES_PER_RUN = 8 * 1024 * 1024
_MAX_RETENTION_BYTES = 64 * 1024 * 1024
_MAX_RETENTION_ENTRIES = 4096
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RANK_ROW_KEYS = frozenset(
    {
        "stock_code",
        "rank",
        "score_label",
        "price_change_percent",
        "volume_change_percent",
        "comparison_date",
        "latest_date",
        "native_reasons",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "period",
        "direction",
        "decision_date",
        "readiness",
        "manifest_identity_sha256",
        "parent_manifest_sha256",
        "parent_manifest_identity_sha256",
        "cohort_id",
        "research_universe",
        "declared_stock_codes",
        "captured_stock_codes",
        "eligible_stock_codes",
        "missing_rank_stock_codes",
        "missing_rank_reasons",
        "eligible_universe_size",
        "artifact_sha256",
        "engine",
        "engine_parameters",
        "source",
        "qualification",
    }
)
_ARTIFACT_KEYS = frozenset(
    {"schema_version", "period", "direction", "decision_date", "parent_manifest_sha256", "rows"}
)
_POINTER_KEYS = frozenset(
    {"schema_version", "period", "direction", "manifest_sha256", "parent_manifest_sha256"}
)


class OriginalStockRankingError(ValueError):
    """原始排名資料契約或來源驗證失敗。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class VerifiedOriginalStockRanking:
    """獨立驗證後的研究用途原始排名。"""

    period: OriginalPeriod
    direction: OriginalDirection
    decision_date: str
    manifest_sha256: str
    manifest_identity_sha256: str
    readiness: Literal["research_only"]
    rows: tuple[Mapping[str, Any], ...]
    eligible_universe_size: int
    declared_stock_codes: tuple[str, ...]
    missing_rank_stock_codes: tuple[str, ...]
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _CapturedStock:
    code: str
    points: tuple[Any, ...]
    technical: Any
    scope_identity: str
    fingerprint: str
    latest_date: str | None


@dataclass(frozen=True, slots=True)
class _ParentContext:
    snapshot: Any
    db_path: Path
    declared_codes: tuple[str, ...]
    captured: Mapping[str, _CapturedStock]
    source_schema_sha256: str
    source_pin: tuple[Any, ...]
    universe_binding: Mapping[str, Any]


def _fail(code: str, message: str) -> NoReturn:
    raise OriginalStockRankingError(code, message)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OriginalStockRankingError("ranking_json_invalid", "排名資料不是嚴格 canonical JSON。") from exc


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity_sha256(manifest: Mapping[str, Any]) -> str:
    return _sha256(
        _canonical_bytes(
            {key: value for key, value in manifest.items() if key != "manifest_identity_sha256"}
        )
    )


def _date_text(value: Any, code: str = "ranking_date_invalid") -> str:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        try:
            if len(raw) == 8 and raw.isdigit():
                parsed = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
            else:
                parsed = date.fromisoformat(raw.replace("/", "-"))
        except ValueError as exc:
            raise OriginalStockRankingError(code, f"無效日期：{value!r}") from exc
    else:
        _fail(code, "日期必須是 date 或 ISO 日期字串。")
    return parsed.isoformat()


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        _fail("ranking_numeric_invalid", f"{field} 缺少有效數值。")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OriginalStockRankingError("ranking_numeric_invalid", f"{field} 不是有效十進位數值。") from exc
    if not result.is_finite():
        _fail("ranking_numeric_invalid", f"{field} 必須是有限十進位數值。")
    return result


def _decimal_text(value: Any, *, field: str) -> str:
    return format(_decimal(value, field=field), "f")


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _read_json(path: Path, *, maximum: int, missing_code: str, invalid_code: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink():
        _fail(invalid_code, "排名儲存不接受 symbolic link。")
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except FileNotFoundError as exc:
        raise OriginalStockRankingError(missing_code, "找不到指定排名檔案。") from exc
    except OSError as exc:
        raise OriginalStockRankingError(invalid_code, f"排名檔案無法讀取：{type(exc).__name__}。") from exc
    if len(raw) > maximum:
        _fail(invalid_code, "排名檔案超過固定 byte 上限。")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_rejecting_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise OriginalStockRankingError(invalid_code, "排名檔案不是有效 UTF-8 JSON。") from exc
    if not isinstance(parsed, dict) or _canonical_bytes(parsed) != raw:
        _fail(invalid_code, "排名檔案不是符合契約的 canonical JSON。")
    return raw, parsed


def _current_pointer_bytes_or_missing(path: Path) -> bytes | None:
    """讀取 canonical pointer；保留檔案缺席狀態供 compare-and-swap 比對。"""
    try:
        raw, _pointer = _read_json(
            path,
            maximum=_MAX_RANKING_POINTER_BYTES,
            missing_code="ranking_pointer_missing",
            invalid_code="ranking_pointer_invalid",
        )
    except OriginalStockRankingError as exc:
        if exc.code == "ranking_pointer_missing":
            return None
        raise
    return raw


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _parse_period_direction(period: str, direction: str) -> tuple[OriginalPeriod, OriginalDirection]:
    if period not in {"day", "week"}:
        _fail("ranking_period_invalid", "period 僅接受 day 或 week。")
    if direction not in {"strong", "weak"}:
        _fail("ranking_direction_invalid", "direction 僅接受 strong 或 weak。")
    return period, direction  # type: ignore[return-value]


def _pointer_name(period: str, direction: str) -> str:
    return f"latest-{period}-{direction}.json"


def _object_relpath(digest: str) -> Path:
    return Path("objects") / digest[:2] / f"{digest}.json"


def _manifest_relpath(digest: str) -> Path:
    return Path("manifests") / digest[:2] / f"{digest}.json"


def _resolved_path_key(path: Path | str) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    return os.path.normcase(os.path.normpath(str(resolved)))


def _validate_codes(raw: Any, *, name: str, maximum: int = _MAX_STOCKS) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or len(raw) > maximum:
        _fail("ranking_universe_invalid", f"{name} 不符合非空且最多 {maximum} 檔限制。")
    if any(not isinstance(code, str) or not code.strip() for code in raw):
        _fail("ranking_universe_invalid", f"{name} 只接受非空股票代碼。")
    codes = tuple(raw)
    if codes != tuple(sorted(set(codes))):
        _fail("ranking_universe_invalid", f"{name} 必須排序且不可重複。")
    return codes


def _stock_records(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    records = manifest.get("stocks")
    if not isinstance(records, list):
        _fail("ranking_parent_manifest_invalid", "來源快照缺少逐股 artifact 清單。")
    output: dict[str, Mapping[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping) or not isinstance(item.get("stock_code"), str):
            _fail("ranking_parent_manifest_invalid", "來源快照逐股 artifact 記錄無效。")
        code = item["stock_code"]
        if code in output:
            _fail("ranking_parent_manifest_invalid", "來源快照逐股 artifact 重複。")
        output[code] = item
    return output


def _engine_contract() -> tuple[Path, dict[str, Any]]:
    try:
        source_path = Path(__file__).resolve().parents[1] / "decision_module" / "stock_screener.py"
        source_bytes = source_path.read_bytes()
        tree = ast.parse(source_bytes.decode("utf-8"), filename=str(source_path))
        screener_node = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "StockScreener"
        )
        method_node = next(
            node
            for node in screener_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_build_stock_screen_from_frame"
        )
        method_parameters = tuple(item.arg for item in method_node.args.args)
        if method_parameters != ("self", "df", "period", "top_n", "min_volume", "direction"):
            _fail("ranking_engine_signature_mismatch", "原生排名方法簽章已變更。")
        source_sha = _sha256(source_bytes)
    except OriginalStockRankingError:
        raise
    except Exception as exc:
        raise OriginalStockRankingError("ranking_engine_unavailable", "無法確認既有原生排名引擎。") from exc
    return source_path, {
        "file_sha256": source_sha,
        "method": "StockScreener._build_stock_screen_from_frame",
        "version": "stock-screener-frame.v1",
    }


def _engine_parameters(period: str, direction: str, top_n: int) -> dict[str, Any]:
    return {
        "period": period,
        "direction": direction,
        "top_n": top_n,
        "min_volume": None,
        "min_price": "5.0",
        "volume_lookback": 20,
        "min_liquidity": None,
        "frame_boundary": "isolated_legacy_pandas_analytical_boundary",
    }


def _ensure_latest_and_core(
    captured: Mapping[str, _CapturedStock], declared_codes: Sequence[str], decision_date: str, period: str
) -> None:
    not_captured = sorted(set(declared_codes) - set(captured))
    if not_captured:
        _fail("ranking_source_capture_incomplete", "來源快照未捕獲全部設定母體成員。")
    minimum_points = 2 if period == "day" else 3
    for code in declared_codes:
        item = captured[code]
        if len(item.points) > _MAX_PRICE_POINTS_PER_STOCK:
            _fail("ranking_source_window_exceeded", f"{code} 的來源視窗超過 120 筆。")
        if len(item.points) < minimum_points:
            _fail("ranking_source_window_incomplete", f"{code} 的 {period} 排名來源列數不足。")
        if item.latest_date != decision_date:
            _fail("ranking_source_date_not_current", f"{code} 最新行情日不等於決策日。")
        seen_dates: set[str] = set()
        for point in item.points:
            point_date = _date_text(point.data_date)
            if point_date in seen_dates:
                _fail("ranking_source_duplicate_date", f"{code} 行情日期重複，無法固定原生比較列。")
            seen_dates.add(point_date)
            close = _decimal(point.close_price, field=f"{code}.close_price")
            volume = point.volume
            if close <= 0 or isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
                _fail("ranking_source_core_value_missing", f"{code} 的收盤價或成交股數不符合來源核心欄位。")


def _comparison_index(point_count: int, period: str) -> tuple[int, str]:
    if period == "day":
        return -2, "native_previous_source_row"
    if point_count >= 6:
        return -6, "native_week_sixth_row"
    return -3, "native_week_third_row_fallback"


def _to_engine_float(value: Any) -> float | None:
    """只在既有 Pandas 引擎邊界將 Decimal 轉成其要求的浮點輸入。"""
    if value is None:
        return None
    return float(_decimal(value, field="legacy_engine_input"))


def _captured_frame(captured: Mapping[str, _CapturedStock]) -> pd.DataFrame:
    import pandas as pd

    records: list[dict[str, Any]] = []
    for code in sorted(captured):
        for point in sorted(captured[code].points, key=lambda item: _date_text(item.data_date)):
            records.append(
                {
                    "日期": _date_text(point.data_date),
                    "證券代號": code,
                    "證券名稱": code,
                    "開盤價": _to_engine_float(point.open_price),
                    "最高價": _to_engine_float(point.high_price),
                    "最低價": _to_engine_float(point.low_price),
                    "收盤價": _to_engine_float(point.close_price),
                    "成交股數": point.volume,
                    "成交金額": _to_engine_float(point.turnover),
                }
            )
    return pd.DataFrame.from_records(records)


def _assert_parent_context_current(parent: _ParentContext, *, expected_engine: Mapping[str, Any]) -> None:
    """在讀回出口及 pointer 原子切換前，以輕量檢查重驗來源 pin 與契約。"""
    from app_module.daily_market_snapshot_repository import validate_research_universe_binding

    try:
        from app_module.daily_market_snapshot_source import _source_pin

        if _source_pin(parent.db_path) != parent.source_pin:
            _fail("ranking_source_changed", "讀取或發布期間來源 SQLite/WAL 身份已變更。")
    except OriginalStockRankingError:
        raise
    except Exception as exc:
        raise OriginalStockRankingError("ranking_source_unavailable", "無法重驗來源 SQLite/WAL 身份。") from exc
    try:
        current_binding = validate_research_universe_binding(
            parent.snapshot.manifest.get("research_universe"),
            decision_date=parent.snapshot.decision_date,
            cohort_id=parent.snapshot.cohort_id,
            declared_stock_codes=parent.declared_codes,
        )
    except Exception as exc:
        raise OriginalStockRankingError("ranking_research_universe_changed", "research_universe 設定在讀取或發布期間已變更。") from exc
    if _canonical_bytes(current_binding) != _canonical_bytes(dict(parent.universe_binding)):
        _fail("ranking_research_universe_changed", "research_universe 設定在讀取或發布期間已變更。")
    _path, current_engine = _engine_contract()
    if _canonical_bytes(current_engine) != _canonical_bytes(dict(expected_engine)):
        _fail("ranking_engine_changed", "原生排名引擎檔案在讀取或發布期間已變更。")


def _immutable_write(root: Path, relpath: Path, payload: bytes, *, maximum: int) -> None:
    if len(payload) > maximum:
        _fail("ranking_file_too_large", "排名 artifact 或 manifest 超過固定 byte 上限。")
    target = root / relpath
    _make_safe_dirs(root, target.parent)
    if target.exists():
        if target.is_symlink():
            _fail("ranking_storage_invalid", "排名 immutable 檔案不接受 symbolic link。")
        raw, _ = _read_json(target, maximum=maximum, missing_code="ranking_file_missing", invalid_code="ranking_file_invalid")
        if raw != payload:
            _fail("ranking_immutable_collision", "content-addressed 排名檔案已存在但內容不同。")
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{target.name}.{os.getpid()}.", suffix=".tmp", dir=target.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                _fail("ranking_immutable_collision", "content-addressed 排名檔案競爭寫入內容不符。")
        except OSError as exc:
            raise OriginalStockRankingError("ranking_immutable_write_failed", "無法原子建立 immutable 排名檔案。") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _make_safe_dirs(root: Path, destination: Path) -> None:
    if root.is_symlink():
        _fail("ranking_storage_invalid", "排名儲存根目錄不接受 symbolic link。")
    try:
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir() or root.is_symlink():
            _fail("ranking_storage_invalid", "排名儲存根目錄必須是一般目錄。")
        relative = destination.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.exists() and (current.is_symlink() or not current.is_dir()):
                _fail("ranking_storage_invalid", "排名儲存路徑含 symbolic link 或非目錄項目。")
            current.mkdir(exist_ok=True)
    except OriginalStockRankingError:
        raise
    except (OSError, ValueError) as exc:
        raise OriginalStockRankingError("ranking_storage_invalid", "無法建立安全的排名儲存目錄。") from exc


def _retention_state(root: Path, *, additional_entries: int = 0) -> tuple[int, int]:
    if not root.exists():
        return 0, 0
    if root.is_symlink() or not root.is_dir():
        _fail("ranking_storage_invalid", "排名儲存根目錄必須是一般目錄。")
    total = 0
    entries = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    entries += 1
                    if entries + additional_entries > _MAX_RETENTION_ENTRIES:
                        _fail("ranking_retention_entry_limit", "排名保留項目數超過固定 4096 上限。")
                    if entry.is_symlink():
                        _fail("ranking_storage_invalid", "排名保留區不接受 symbolic link。")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        if total > _MAX_RETENTION_BYTES:
                            _fail("ranking_retention_byte_limit", "排名保留容量超過固定 64 MiB 上限。")
        except OriginalStockRankingError:
            raise
        except OSError as exc:
            raise OriginalStockRankingError("ranking_storage_invalid", "無法唯讀盤點排名保留區。") from exc
    if entries + additional_entries > _MAX_RETENTION_ENTRIES:
        _fail("ranking_retention_entry_limit", "排名保留項目數超過固定 4096 上限。")
    if total > _MAX_RETENTION_BYTES:
        _fail("ranking_retention_byte_limit", "排名保留容量超過固定 64 MiB 上限。")
    return total, entries


def _capacity_preflight(root: Path, *, persistent_new: int, temporary_peak: int, additional_entries: int) -> dict[str, Any]:
    from data_module.ml_storage_capacity import MLStorageCapacityBudget, evaluate_capacity, filesystem_usage

    retained, _ = _retention_state(root, additional_entries=additional_entries)
    probe_path = root
    while not probe_path.exists():
        if probe_path.parent == probe_path:
            _fail("ranking_capacity_probe_failed", "找不到排名儲存所在磁碟。")
        probe_path = probe_path.parent
    usage = filesystem_usage(probe_path)
    budget = MLStorageCapacityBudget(
        persistent_new_bytes_budget=_MAX_NEW_BYTES_PER_RUN,
        temporary_peak_bytes_budget=_MAX_TEMPORARY_BYTES_PER_RUN,
        safety_reserve_bytes=200 * 1024**3,
    )
    preflight = evaluate_capacity(
        budget=budget,
        usage=usage,
        stage="original_stock_ranking_preflight",
        persistent_existing_bytes=retained,
        persistent_new_bytes_estimate=persistent_new,
        temporary_peak_bytes_observed=temporary_peak,
    ).as_dict()
    preflight["retained_bytes"] = retained
    preflight["retained_entries"] = _retention_state(root)[1]
    preflight["maximum_retention_bytes"] = _MAX_RETENTION_BYTES
    preflight["maximum_retention_entries"] = _MAX_RETENTION_ENTRIES
    if not preflight.get("within_budget"):
        _fail("ranking_capacity_blocked", "排名儲存磁碟未保留 200 GiB reserve 與本次寫入額度。")
    return preflight


class OriginalStockRankingRepository:
    """驗證排名 pointer、immutable 產物、母體與目前唯讀來源。"""

    def __init__(self, snapshot_root: str | Path, ranking_root: str | Path | None = None) -> None:
        self.snapshot_root = Path(snapshot_root).expanduser().resolve()
        self.ranking_root = Path(ranking_root or (self.snapshot_root / "original_rankings")).expanduser().resolve()

    def read(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        *,
        db_path: str | Path,
        period: OriginalPeriod,
        direction: OriginalDirection,
    ) -> VerifiedOriginalStockRanking:
        """依既有 latest pointer 讀取目前發佈的不可變排名。"""

        return self._read(
            snapshot,
            db_path=db_path,
            period=period,
            direction=direction,
            pinned_manifest_sha256=None,
            pinned_manifest_identity_sha256=None,
        )

    def read_pinned(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        *,
        db_path: str | Path,
        period: OriginalPeriod,
        direction: OriginalDirection,
        manifest_sha256: str,
        manifest_identity_sha256: str,
    ) -> VerifiedOriginalStockRanking:
        """依明示 manifest hash 讀回 immutable 排名，不解析 latest pointer。"""

        if not _is_sha(manifest_sha256):
            _fail("ranking_manifest_hash_invalid", "pinned manifest_sha256 無效。")
        if not _is_sha(manifest_identity_sha256):
            _fail("ranking_manifest_identity_invalid", "pinned manifest identity 無效。")
        return self._read(
            snapshot,
            db_path=db_path,
            period=period,
            direction=direction,
            pinned_manifest_sha256=manifest_sha256,
            pinned_manifest_identity_sha256=manifest_identity_sha256,
        )

    def _read(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        *,
        db_path: str | Path,
        period: OriginalPeriod,
        direction: OriginalDirection,
        pinned_manifest_sha256: str | None,
        pinned_manifest_identity_sha256: str | None,
    ) -> VerifiedOriginalStockRanking:
        selected_period, selected_direction = _parse_period_direction(period, direction)
        parent = _load_parent_context(self.snapshot_root, snapshot, db_path)
        _ensure_latest_and_core(parent.captured, parent.declared_codes, parent.snapshot.decision_date.isoformat(), selected_period)
        _engine_path, engine = _engine_contract()
        pointer_path = self.ranking_root / _pointer_name(selected_period, selected_direction)
        pointer: dict[str, Any] | None = None
        if pinned_manifest_sha256 is None:
            pointer_raw, pointer = _read_json(
                pointer_path,
                maximum=_MAX_RANKING_POINTER_BYTES,
                missing_code="ranking_pointer_missing",
                invalid_code="ranking_pointer_invalid",
            )
            del pointer_raw
            if set(pointer) != _POINTER_KEYS or pointer.get("schema_version") != ORIGINAL_RANKING_POINTER_SCHEMA:
                _fail("ranking_pointer_schema_mismatch", "原始排名 pointer schema 不相容。")
            if pointer.get("period") != selected_period or pointer.get("direction") != selected_direction:
                _fail("ranking_pointer_scope_mismatch", "原始排名 pointer period/direction 不符。")
            if pointer.get("parent_manifest_sha256") != parent.snapshot.manifest_sha256:
                _fail("ranking_parent_manifest_mismatch", "原始排名綁定的來源 manifest 已不同。")
            digest = pointer.get("manifest_sha256")
            if not isinstance(digest, str) or not _is_sha(digest):
                _fail("ranking_pointer_invalid", "原始排名 pointer manifest hash 無效。")
        else:
            digest = pinned_manifest_sha256
        manifest_raw, manifest = _read_json(
            self.ranking_root / _manifest_relpath(digest),
            maximum=_MAX_RANKING_MANIFEST_BYTES,
            missing_code="ranking_manifest_missing",
            invalid_code="ranking_manifest_invalid",
        )
        if _sha256(manifest_raw) != digest:
            _fail("ranking_manifest_hash_mismatch", "原始排名 manifest hash 不符。")
        if set(manifest) != _MANIFEST_KEYS or manifest.get("schema_version") != ORIGINAL_RANKING_MANIFEST_SCHEMA:
            _fail("ranking_manifest_schema_mismatch", "原始排名 manifest schema 不相容。")
        if manifest.get("manifest_identity_sha256") != _identity_sha256(manifest):
            _fail("ranking_manifest_identity_mismatch", "原始排名穩定 identity 不符。")
        if (
            pinned_manifest_identity_sha256 is not None
            and manifest.get("manifest_identity_sha256") != pinned_manifest_identity_sha256
        ):
            _fail("ranking_manifest_identity_mismatch", "pinned manifest identity 與內容不符。")
        _validate_manifest_binding(manifest, parent, selected_period, selected_direction, engine)
        artifact_digest = manifest.get("artifact_sha256")
        if not isinstance(artifact_digest, str) or not _is_sha(artifact_digest):
            _fail("ranking_artifact_hash_invalid", "原始排名 artifact hash 無效。")
        artifact_raw, artifact = _read_json(
            self.ranking_root / _object_relpath(artifact_digest),
            maximum=_MAX_RANKING_ARTIFACT_BYTES,
            missing_code="ranking_artifact_missing",
            invalid_code="ranking_artifact_invalid",
        )
        if _sha256(artifact_raw) != artifact_digest:
            _fail("ranking_artifact_hash_mismatch", "原始排名 artifact hash 不符。")
        if set(artifact) != _ARTIFACT_KEYS or artifact.get("schema_version") != ORIGINAL_RANKING_ARTIFACT_SCHEMA:
            _fail("ranking_artifact_schema_mismatch", "原始排名 artifact schema 不相容。")
        if (
            artifact.get("period") != selected_period
            or artifact.get("direction") != selected_direction
            or artifact.get("decision_date") != parent.snapshot.decision_date.isoformat()
            or artifact.get("parent_manifest_sha256") != parent.snapshot.manifest_sha256
        ):
            _fail("ranking_artifact_binding_mismatch", "原始排名 artifact 與母體契約不符。")
        rows = _validate_rows(artifact.get("rows"), parent, selected_period, selected_direction)
        eligible_codes = tuple(row["stock_code"] for row in rows)
        missing_codes = tuple(code for code in parent.declared_codes if code not in set(eligible_codes))
        if manifest.get("eligible_stock_codes") != list(eligible_codes):
            _fail("ranking_eligible_scope_mismatch", "manifest eligible 股票順序與 artifact 不符。")
        if manifest.get("missing_rank_stock_codes") != list(missing_codes):
            _fail("ranking_missing_rank_scope_mismatch", "manifest missing-rank 清單與 artifact 不符。")
        reasons = manifest.get("missing_rank_reasons")
        if not isinstance(reasons, dict) or set(reasons) != set(missing_codes):
            _fail("ranking_missing_rank_reason_mismatch", "missing-rank 理由集合與股票分母不符。")
        if any(value != "native_engine_rejection_reason_unavailable" for value in reasons.values()):
            _fail("ranking_missing_rank_reason_mismatch", "原生引擎缺少個股淘汰原因時，理由必須明示 unknown。")
        eligible_count = manifest.get("eligible_universe_size")
        if type(eligible_count) is not int or not 0 <= eligible_count <= len(parent.declared_codes) or eligible_count != len(rows):
            _fail("ranking_eligible_count_mismatch", "eligible universe size 與排名列數不符。")
        if pointer is not None:
            if pointer.get("manifest_sha256") != digest or pointer.get("parent_manifest_sha256") != parent.snapshot.manifest_sha256:
                _fail("ranking_pointer_manifest_mismatch", "原始排名 pointer 與 manifest 不符。")
            current_manifest_raw, current_pointer = _read_json(
                pointer_path,
                maximum=_MAX_RANKING_POINTER_BYTES,
                missing_code="ranking_pointer_missing",
                invalid_code="ranking_pointer_invalid",
            )
            if current_manifest_raw != _canonical_bytes(pointer) or current_pointer != pointer:
                _fail("ranking_pointer_changed_during_read", "讀取期間原始排名 pointer 已變更。")
        _assert_parent_context_current(parent, expected_engine=engine)
        comparison_windows: dict[str, dict[str, Any]] = {}
        for code, captured_stock in parent.captured.items():
            comparison_index, comparison_rule = _comparison_index(
                len(captured_stock.points), selected_period
            )
            comparison_windows[code] = {
                "dates": tuple(
                    _date_text(point.data_date)
                    for point in captured_stock.points[comparison_index:]
                ),
                "rule": comparison_rule,
            }
        metadata = {
            "run_id": str(manifest["manifest_identity_sha256"]),
            "publisher_run_identity_sha256": manifest["manifest_identity_sha256"],
            "run_id_source": "publisher_manifest_identity_not_native_engine_run_id",
            "source_db_path": parent.db_path.as_posix(),
            "source_schema_sha256": parent.source_schema_sha256,
            "engine_file_sha256": engine["file_sha256"],
            "engine_method": engine["method"],
            "engine_version": engine["version"],
            "engine_parameters": manifest["engine_parameters"],
            "engine": manifest["engine"],
            "source": manifest["source"],
            "input_fingerprints": manifest["source"]["input_fingerprints"],
            "captured_stock_codes": tuple(manifest["captured_stock_codes"]),
            "eligible_stock_codes": tuple(eligible_codes),
            "missing_rank_stock_codes": tuple(missing_codes),
            "missing_rank_reason": manifest["missing_rank_reasons"],
            "volume_window_size": 20,
            "volume_history": manifest["source"]["volume_history"],
            "comparison_rules": manifest["source"]["comparison_rules"],
            "parent_manifest_sha256": parent.snapshot.manifest_sha256,
            "parent_manifest_identity_sha256": parent.snapshot.manifest_identity_sha256,
            "parent_cohort_id": parent.snapshot.cohort_id,
            "decision_date": parent.snapshot.decision_date.isoformat(),
            "snapshot_root": self.snapshot_root.as_posix(),
            "ranking_root": self.ranking_root.as_posix(),
            "manifest_sha256": digest,
            "artifact_sha256": artifact_digest,
            "research_universe": manifest["research_universe"],
            "research_universe_id": manifest["research_universe"].get("universe_id"),
            "research_universe_version": manifest["research_universe"].get("version"),
            "research_universe_source_sha256": manifest["research_universe"].get("source_sha256"),
            "research_universe_identity": manifest["research_universe"],
            "qualification": manifest["qualification"],
            "native_score_semantics": manifest["qualification"]["native_score_semantics"],
            "numeric_score_status": manifest["qualification"]["numeric_score_status"],
            "comparison_windows": comparison_windows,
        }
        return VerifiedOriginalStockRanking(
            period=selected_period,
            direction=selected_direction,
            decision_date=parent.snapshot.decision_date.isoformat(),
            manifest_sha256=digest,
            manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
            readiness="research_only",
            rows=tuple(_freeze(row) for row in rows),
            eligible_universe_size=len(rows),
            declared_stock_codes=parent.declared_codes,
            missing_rank_stock_codes=missing_codes,
            metadata=_freeze(metadata),
        )


def _thaw(value: Any) -> Any:
    """將只讀 metadata 轉成 canonical JSON 可用的獨立複本。"""

    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _canonical_text(value: Any) -> str:
    return _canonical_bytes(_thaw(value)).decode("utf-8")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(_thaw(value))).hexdigest()


def research_rank_context_for_original_stock_ranking(
    ranking: VerifiedOriginalStockRanking,
    stock_code: str,
    *,
    filter_state: str = "all",
    sort_key: str = "rank",
    descending: bool = False,
) -> ResearchRankContextDTO:
    """由已驗證 publisher 結果與原始排序列建立完整 immutable rank context。"""

    if not isinstance(ranking, VerifiedOriginalStockRanking):
        _fail("ranking_context_source_unverified", "rank context 需要 repository 驗證過的排名結果。")
    code = str(stock_code or "").strip()
    rows = tuple(ranking.rows)
    matching = [row for row in rows if row.get("stock_code") == code]
    if len(matching) != 1:
        _fail("ranking_context_stock_mismatch", "選取股票不在唯一的 verified 原始排名列中。")
    if filter_state not in {"all", "match", "no_match", "unknown"}:
        _fail("ranking_context_filter_invalid", "rank filter_state 不支援。")
    if not isinstance(sort_key, str) or not sort_key.strip() or not isinstance(descending, bool):
        _fail("ranking_context_sort_invalid", "rank sort key/direction 無效。")
    metadata = ranking.metadata
    try:
        universe = _thaw(metadata["research_universe_identity"])
        parameters = _thaw(metadata["engine_parameters"])
        windows = metadata["comparison_windows"]
        window = windows[code]
        volume = metadata["volume_history"][code]
        fingerprints = metadata["input_fingerprints"]
        method_contract = {
            "method_name": str(metadata["engine_method"]),
            "method_version": str(metadata["engine_version"]),
            "engine_file_sha256": str(metadata["engine_file_sha256"]),
        }
        selected_row = matching[0]
        window_dates = tuple(str(value) for value in window["dates"])
        method_parameters_sha = _canonical_hash(parameters)
        universe_sha = _canonical_hash(universe)
    except (KeyError, TypeError, ValueError) as exc:
        raise OriginalStockRankingError(
            "ranking_context_source_incomplete", "已驗證排名缺少建立 rank context 所需的 manifest 脈絡。"
        ) from exc
    expected_rank = int(selected_row["rank"])
    if (
        type(selected_row.get("rank")) is not int
        or expected_rank < 1
        or rows[expected_rank - 1].get("stock_code") != code
        or not window_dates
        or window_dates[0] != selected_row.get("comparison_date")
        or window_dates[-1] != selected_row.get("latest_date")
    ):
        _fail("ranking_context_row_mismatch", "選取列 rank/date window 與 immutable source 不一致。")
    return ResearchRankContextDTO(
        rank_kind="original_stock_ranking",
        period=ranking.period,
        direction=ranking.direction,
        rank_snapshot_id=ranking.manifest_identity_sha256,
        source_hash=ranking.manifest_sha256,
        ranking_root=str(metadata["ranking_root"]),
        snapshot_root=str(metadata["snapshot_root"]),
        decision_date=ranking.decision_date,
        parent_snapshot_id=str(metadata["parent_manifest_identity_sha256"]),
        parent_snapshot_hash=str(metadata["parent_manifest_sha256"]),
        parent_cohort_id=str(metadata["parent_cohort_id"]),
        selected_stock_code=code,
        selected_rank=expected_rank,
        comparison_date=str(selected_row["comparison_date"]),
        latest_date=str(selected_row["latest_date"]),
        comparison_window_dates=window_dates,
        comparison_window_rule=str(window["rule"]),
        volume_reference_point_count=int(volume["actual_reference_point_count"]),
        declared_stock_codes=tuple(ranking.declared_stock_codes),
        eligible_stock_codes=tuple(str(row["stock_code"]) for row in rows),
        missing_rank_stock_codes=tuple(ranking.missing_rank_stock_codes),
        research_universe_json=_canonical_text(universe),
        research_universe_sha256=universe_sha,
        method_name=method_contract["method_name"],
        method_version=method_contract["method_version"],
        method_contract_sha256=_canonical_hash(method_contract),
        engine_file_sha256=method_contract["engine_file_sha256"],
        engine_parameters_json=_canonical_text(parameters),
        engine_parameters_sha256=method_parameters_sha,
        source_schema_sha256=str(metadata["source_schema_sha256"]),
        selected_input_fingerprint_sha256=str(fingerprints[code]),
        filter_state=cast(Literal["all", "match", "no_match", "unknown"], filter_state),
        sort_key=sort_key.strip(),
        descending=descending,
    )


def research_context_for_original_stock_ranking(
    snapshot: VerifiedDailyMarketSnapshot,
    ranking: VerifiedOriginalStockRanking,
    *,
    ranking_root: str | Path,
    stock_code: str,
    stock_name: str = "",
    source_workspace: str = "recommendation",
    source_label: str = "原始強弱排名",
    inherited_context: Any = None,
    filter_state: str = "all",
    sort_key: str = "rank",
    descending: bool = False,
) -> Any:
    """由 verified rank row 建立單股研究 context，沿用當下外層研究查詢。"""

    from app_module.research_session.session_dtos import ResearchStockContextDTO

    rank_context = research_rank_context_for_original_stock_ranking(
        ranking,
        stock_code,
        filter_state=filter_state,
        sort_key=sort_key,
        descending=descending,
    )
    expected_root = Path(ranking_root).expanduser().resolve()
    if (
        str(expected_root) != rank_context.ranking_root
        or snapshot.manifest_sha256 != rank_context.parent_snapshot_hash
        or snapshot.manifest_identity_sha256 != rank_context.parent_snapshot_id
        or snapshot.cohort_id != rank_context.parent_cohort_id
        or snapshot.decision_date.isoformat() != rank_context.decision_date
    ):
        _fail("ranking_context_parent_mismatch", "rank context 與 verified parent snapshot/root 不一致。")
    inherited = inherited_context if isinstance(inherited_context, ResearchStockContextDTO) else None
    if inherited is not None and (
        inherited.stock_code != rank_context.selected_stock_code
        or (inherited.decision_date and inherited.decision_date != rank_context.decision_date)
    ):
        _fail("ranking_context_parent_mismatch", "繼承的研究 context 股票或日期與 rank row 不一致。")
    return ResearchStockContextDTO(
        stock_code=rank_context.selected_stock_code,
        stock_name=str(stock_name or (inherited.stock_name if inherited else "") or stock_code),
        decision_date=rank_context.decision_date,
        data_date=rank_context.latest_date,
        result_id="",
        source_snapshot_id=rank_context.parent_snapshot_id,
        source_snapshot_hash=rank_context.parent_snapshot_hash,
        source_kind="original_stock_ranking",
        source_label=source_label,
        source_workspace=source_workspace or (inherited.source_workspace if inherited else "recommendation"),
        source_id=rank_context.rank_snapshot_id,
        daily_snapshot_root=rank_context.snapshot_root,
        daily_snapshot_cohort_id=rank_context.parent_cohort_id,
        daily_snapshot_condition_keys=(
            inherited.daily_snapshot_condition_keys if inherited else ""
        ),
        daily_snapshot_combine_mode=(
            inherited.daily_snapshot_combine_mode if inherited else ""
        ),
        rank_context=rank_context,
    )


def load_original_stock_ranking_from_context(
    rank_context: ResearchRankContextDTO | Mapping[str, Any],
    *,
    db_path: str | Path,
) -> tuple[VerifiedDailyMarketSnapshot, VerifiedOriginalStockRanking]:
    """重驗 DTO 所指向的 parent/manifest/source，回傳 pinned verified bundle。"""

    from datetime import date
    from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository

    if isinstance(rank_context, Mapping):
        try:
            rank_context = ResearchRankContextDTO.from_mapping(rank_context)
        except (TypeError, ValueError) as exc:
            raise OriginalStockRankingError("ranking_context_invalid", "rank context mapping 不符合固定 DTO schema。") from exc
    if not isinstance(rank_context, ResearchRankContextDTO):
        _fail("ranking_context_invalid", "rank context 必須是已驗證的 ResearchRankContextDTO。")
    try:
        snapshot = DailyMarketSnapshotRepository(rank_context.snapshot_root).load_manifest(
            rank_context.parent_snapshot_hash,
            rank_context.parent_cohort_id,
            date.fromisoformat(rank_context.decision_date),
        )
    except Exception as exc:
        raise OriginalStockRankingError(
            "ranking_context_parent_refused", "無法以 rank context 的 pinned identity 讀回 parent snapshot。"
        ) from exc
    if (
        snapshot.manifest_sha256 != rank_context.parent_snapshot_hash
        or snapshot.manifest_identity_sha256 != rank_context.parent_snapshot_id
        or snapshot.cohort_id != rank_context.parent_cohort_id
        or snapshot.decision_date.isoformat() != rank_context.decision_date
    ):
        _fail("ranking_context_parent_mismatch", "pinned parent snapshot hash/date/cohort 不一致。")
    repository = OriginalStockRankingRepository(rank_context.snapshot_root, rank_context.ranking_root)
    ranking = repository.read_pinned(
        snapshot,
        db_path=db_path,
        period=rank_context.period,
        direction=rank_context.direction,
        manifest_sha256=rank_context.source_hash,
        manifest_identity_sha256=rank_context.rank_snapshot_id,
    )
    expected = research_rank_context_for_original_stock_ranking(
        ranking,
        rank_context.selected_stock_code,
        filter_state=rank_context.filter_state,
        sort_key=rank_context.sort_key,
        descending=rank_context.descending,
    )
    if expected.to_dict() != rank_context.to_dict():
        _fail("ranking_context_identity_mismatch", "rank context mode/window/universe/method/hash/order 與 pinned manifest 不一致。")
    return snapshot, ranking


def read_original_stock_ranking_row_from_context(
    rank_context: ResearchRankContextDTO | Mapping[str, Any],
    *,
    db_path: str | Path,
) -> Mapping[str, Any]:
    """重驗 DTO 並回傳 immutable artifact 中的原始 selected row。"""

    _snapshot, ranking = load_original_stock_ranking_from_context(
        rank_context,
        db_path=db_path,
    )
    selected = rank_context
    if isinstance(selected, Mapping):
        selected = ResearchRankContextDTO.from_mapping(selected)
    if not isinstance(selected, ResearchRankContextDTO):
        _fail("ranking_context_invalid", "rank context 型別無效。")
    return ranking.rows[selected.selected_rank - 1]


class OriginalStockRankingPublisher:
    """只對驗證過的 configured research universe 發布原始排名。"""

    def __init__(self, snapshot_root: str | Path, ranking_root: str | Path | None = None) -> None:
        self.snapshot_root = Path(snapshot_root).expanduser().resolve()
        self.ranking_root = Path(ranking_root or (self.snapshot_root / "original_rankings")).expanduser().resolve()
        self.repository = OriginalStockRankingRepository(self.snapshot_root, self.ranking_root)

    def publish(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        *,
        db_path: str | Path,
        period: OriginalPeriod,
        direction: OriginalDirection,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        from app_module.sqlite_read_only import ReadOperationCancelled

        selected_period, selected_direction = _parse_period_direction(period, direction)
        capacity: dict[str, Any] = {"status": "not_checked"}
        pointer_path = self.ranking_root / _pointer_name(selected_period, selected_direction)
        lock_context: Any = None
        old_pointer: bytes | None = None
        parent_context: _ParentContext | None = None
        try:
            _check_cancel(cancel_callback)
            parent = _load_parent_context(self.snapshot_root, snapshot, db_path, cancel_callback=cancel_callback)
            parent_context = parent
            decision_day = parent.snapshot.decision_date.isoformat()
            _ensure_latest_and_core(parent.captured, parent.declared_codes, decision_day, selected_period)
            _engine_path, engine = _engine_contract()
            parameters = _engine_parameters(selected_period, selected_direction, len(parent.declared_codes))
            self.ranking_root.mkdir(parents=True, exist_ok=True)
            if self.ranking_root.is_symlink() or not self.ranking_root.is_dir():
                _fail("ranking_storage_invalid", "排名儲存根目錄必須是一般目錄。")
            if pointer_path.exists():
                # 舊版本、不完整或 hash 錯誤的 pointer 不會被自動修補覆寫。
                old_pointer, existing_pointer = _read_json(
                    pointer_path,
                    maximum=_MAX_RANKING_POINTER_BYTES,
                    missing_code="ranking_pointer_missing",
                    invalid_code="ranking_pointer_invalid",
                )
                if set(existing_pointer) != _POINTER_KEYS or existing_pointer.get("schema_version") != ORIGINAL_RANKING_POINTER_SCHEMA:
                    _fail("ranking_pointer_schema_mismatch", "既有原始排名 pointer schema 不相容。")
                if existing_pointer.get("period") != selected_period or existing_pointer.get("direction") != selected_direction:
                    _fail("ranking_pointer_scope_mismatch", "既有原始排名 pointer 範圍不符。")
                if existing_pointer.get("parent_manifest_sha256") == parent.snapshot.manifest_sha256:
                    try:
                        verified = self.repository.read(
                            snapshot,
                            db_path=parent.db_path,
                            period=selected_period,
                            direction=selected_direction,
                        )
                    except OriginalStockRankingError as exc:
                        if exc.code in {"ranking_manifest_hash_mismatch", "ranking_artifact_hash_mismatch", "ranking_pointer_invalid", "ranking_manifest_invalid", "ranking_artifact_invalid"}:
                            raise
                    else:
                        _check_cancel(cancel_callback)
                        _assert_parent_context_current(parent, expected_engine=engine)
                        return {
                            "status": "unchanged",
                            "code": "original_stock_ranking_unchanged",
                            "period": selected_period,
                            "direction": selected_direction,
                            "decision_date": verified.decision_date,
                            "parent_manifest_sha256": parent.snapshot.manifest_sha256,
                            "manifest_sha256": verified.manifest_sha256,
                            "manifest_identity_sha256": verified.manifest_identity_sha256,
                            "run_id": str(verified.metadata["run_id"]),
                            "capacity": {"status": "not_needed", "reason": "verified_input_unchanged"},
                        }
            # Writer-only lazy import共用現有OS鎖；程序中止時由作業系統釋放鎖。
            _make_safe_dirs(self.ranking_root, self.ranking_root)
            from app_module.daily_market_snapshot_producer import _producer_lock

            lock_context = _producer_lock(self.ranking_root)
            if not lock_context.__enter__():
                _fail("ranking_publish_busy", "另一個排名發布程序持有 exclusive lock。")
            if _current_pointer_bytes_or_missing(pointer_path) != old_pointer:
                _fail("ranking_pointer_changed_during_publish", "取得發布鎖前 pointer 已被其他程序修改。")

            # verified unchanged 早退後才檢查本次寫入容量；沒有自動刪除或清理。
            try:
                capacity = _capacity_preflight(
                    self.ranking_root,
                    persistent_new=_MAX_NEW_BYTES_PER_RUN,
                    temporary_peak=_MAX_TEMPORARY_BYTES_PER_RUN,
                    additional_entries=8,
                )
            except OriginalStockRankingError as exc:
                if exc.code.startswith("ranking_capacity") or exc.code.startswith("ranking_retention"):
                    return self._unavailable(exc.code, selected_period, selected_direction, parent, capacity)
                raise

            _check_cancel(cancel_callback)
            frame = _captured_frame(parent.captured)
            from decision_module.stock_screener import StockScreener

            current_engine_class = StockScreener
            screener = current_engine_class(
                None,
                industry_mapper=None,
                volume_lookback=20,
                min_price=5.0,
                min_liquidity=None,
            )
            try:
                engine_output, eligible_total = screener._build_stock_screen_from_frame(
                    frame,
                    selected_period,
                    len(parent.declared_codes),
                    None,
                    selected_direction,
                )
            except Exception as exc:
                raise OriginalStockRankingError("ranking_engine_failed", "既有原生排名引擎執行失敗。") from exc
            rows = _rows_from_engine(engine_output, eligible_total, parent, selected_period, selected_direction)
            captured_codes = tuple(sorted(parent.captured))
            eligible_codes = tuple(row["stock_code"] for row in rows)
            missing_codes = tuple(code for code in parent.declared_codes if code not in set(eligible_codes))
            missing_reasons = {
                code: "native_engine_rejection_reason_unavailable" for code in missing_codes
            }
            comparison_rules = {
                code: {
                    "comparison_index_from_latest": _comparison_index(len(parent.captured[code].points), selected_period)[0],
                    "rule": _comparison_index(len(parent.captured[code].points), selected_period)[1],
                }
                for code in parent.declared_codes
            }
            volume_history = {
                code: {
                    "source_point_count": len(parent.captured[code].points),
                    "lookback_configuration": 20,
                    "actual_reference_point_count": min(20, len(parent.captured[code].points) - 1)
                    if len(parent.captured[code].points) >= 21
                    else (min(5, len(parent.captured[code].points) - 1) if len(parent.captured[code].points) >= 6 else len(parent.captured[code].points) - 1),
                }
                for code in parent.declared_codes
            }
            source_payload = {
                "source_db_path": parent.db_path.as_posix(),
                "schema_identity_sha256": parent.source_schema_sha256,
                "price_table": "daily_prices",
                "technical_table": "technical_indicators",
                "source_window_limit_per_stock": _MAX_PRICE_POINTS_PER_STOCK,
                "captured_stock_codes": list(captured_codes),
                "captured_point_counts": {code: len(parent.captured[code].points) for code in captured_codes},
                "latest_dates": {code: parent.captured[code].latest_date for code in captured_codes},
                "input_fingerprints": {code: parent.captured[code].fingerprint for code in captured_codes},
                "volume_history": volume_history,
                "comparison_rules": comparison_rules,
            }
            qualification = {
                "usage": "current_observed_research_only",
                "readiness": "research_only",
                "research_only": True,
                "historical_pit_eligible": False,
                "current_observed_only": True,
                "full_market_coverage": False,
                "formal_recommendation_eligible": False,
                "native_score_semantics": "legacy_percentile_label_preserved",
                "numeric_score_status": "not_exposed_by_legacy_engine",
            }
            artifact = {
                "schema_version": ORIGINAL_RANKING_ARTIFACT_SCHEMA,
                "period": selected_period,
                "direction": selected_direction,
                "decision_date": decision_day,
                "parent_manifest_sha256": parent.snapshot.manifest_sha256,
                "rows": rows,
            }
            artifact_bytes = _canonical_bytes(artifact)
            artifact_sha = _sha256(artifact_bytes)
            manifest: dict[str, Any] = {
                "schema_version": ORIGINAL_RANKING_MANIFEST_SCHEMA,
                "period": selected_period,
                "direction": selected_direction,
                "decision_date": decision_day,
                "readiness": "research_only",
                "manifest_identity_sha256": "",
                "parent_manifest_sha256": parent.snapshot.manifest_sha256,
                "parent_manifest_identity_sha256": parent.snapshot.manifest_identity_sha256,
                "cohort_id": parent.snapshot.cohort_id,
                "research_universe": dict(parent.universe_binding),
                "declared_stock_codes": list(parent.declared_codes),
                "captured_stock_codes": list(captured_codes),
                "eligible_stock_codes": list(eligible_codes),
                "missing_rank_stock_codes": list(missing_codes),
                "missing_rank_reasons": missing_reasons,
                "eligible_universe_size": len(rows),
                "artifact_sha256": artifact_sha,
                "engine": engine,
                "engine_parameters": parameters,
                "source": source_payload,
                "qualification": qualification,
            }
            manifest["manifest_identity_sha256"] = _identity_sha256(manifest)
            manifest_bytes = _canonical_bytes(manifest)
            manifest_sha = _sha256(manifest_bytes)
            pointer = {
                "schema_version": ORIGINAL_RANKING_POINTER_SCHEMA,
                "period": selected_period,
                "direction": selected_direction,
                "manifest_sha256": manifest_sha,
                "parent_manifest_sha256": parent.snapshot.manifest_sha256,
            }
            pointer_bytes = _canonical_bytes(pointer)
            if len(pointer_bytes) > _MAX_RANKING_POINTER_BYTES:
                _fail("ranking_pointer_too_large", "原始排名 pointer 超過固定 byte 上限。")

            # 引擎與來源在 pointer 發布前重新固定；任何修訂都保留既有 pointer。
            _check_cancel(cancel_callback)
            final_parent = _load_parent_context(self.snapshot_root, snapshot, db_path, cancel_callback=cancel_callback)
            if final_parent.source_pin != parent.source_pin:
                _fail("ranking_source_changed", "排名計算期間來源 DB/WAL 身份已變更。")
            if {code: item.fingerprint for code, item in final_parent.captured.items()} != source_payload["input_fingerprints"]:
                _fail("ranking_source_changed", "排名計算期間來源 input fingerprint 已變更。")
            _, final_engine = _engine_contract()
            if final_engine != engine:
                _fail("ranking_engine_changed", "排名計算期間原生引擎檔案已變更。")
            _ensure_latest_and_core(final_parent.captured, final_parent.declared_codes, decision_day, selected_period)
            _check_cancel(cancel_callback)

            _immutable_write(
                self.ranking_root,
                _object_relpath(artifact_sha),
                artifact_bytes,
                maximum=_MAX_RANKING_ARTIFACT_BYTES,
            )
            _immutable_write(
                self.ranking_root,
                _manifest_relpath(manifest_sha),
                manifest_bytes,
                maximum=_MAX_RANKING_MANIFEST_BYTES,
            )
            # 發布前再檢查完整 retention 與 reserve。失敗時只留下未引用的 immutable 物件，舊 pointer 不變。
            try:
                capacity = _capacity_preflight(
                    self.ranking_root,
                    persistent_new=0,
                    temporary_peak=len(pointer_bytes),
                    additional_entries=2,
                )
            except OriginalStockRankingError as exc:
                if exc.code.startswith("ranking_capacity") or exc.code.startswith("ranking_retention"):
                    return self._unavailable(exc.code, selected_period, selected_direction, parent, capacity)
                raise
            # 候選內容先經同一嚴格驗證器驗證，pointer 更新使用同目錄 replace 原子切換。
            _validate_candidate_bundle(self.ranking_root, pointer, manifest, artifact)
            _check_cancel(cancel_callback)
            _assert_parent_context_current(parent, expected_engine=engine)
            temp_pointer: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=f".{pointer_path.name}.{os.getpid()}.", suffix=".tmp", dir=self.ranking_root, delete=False
                ) as stream:
                    temp_pointer = Path(stream.name)
                    stream.write(pointer_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                _check_cancel(cancel_callback)
                _assert_parent_context_current(parent, expected_engine=engine)
                if _current_pointer_bytes_or_missing(pointer_path) != old_pointer:
                    _fail("ranking_pointer_changed_during_publish", "發布前原始排名 pointer 已被其他程序修改。")
                os.replace(temp_pointer, pointer_path)
                temp_pointer = None
            finally:
                if temp_pointer is not None:
                    try:
                        temp_pointer.unlink(missing_ok=True)
                    except OSError:
                        pass
            return {
                "status": "published",
                "code": "original_stock_ranking_published",
                "period": selected_period,
                "direction": selected_direction,
                "decision_date": decision_day,
                "parent_manifest_sha256": parent.snapshot.manifest_sha256,
                "manifest_sha256": manifest_sha,
                "manifest_identity_sha256": manifest["manifest_identity_sha256"],
                "artifact_sha256": artifact_sha,
                "run_id": manifest["manifest_identity_sha256"],
                "declared_stock_codes": list(parent.declared_codes),
                "captured_stock_codes": list(captured_codes),
                "eligible_stock_codes": list(eligible_codes),
                "missing_rank_stock_codes": list(missing_codes),
                "capacity": capacity,
            }
        except (ReadOperationCancelled, _Cancelled):
            return self._result_cancelled(selected_period, selected_direction, snapshot, capacity)
        except OriginalStockRankingError as exc:
            return self._unavailable(exc.code, selected_period, selected_direction, parent_context, capacity)
        except Exception as exc:
            return self._unavailable(
                f"ranking_publish_failed:{type(exc).__name__}", selected_period, selected_direction, parent_context, capacity
            )
        finally:
            if lock_context is not None:
                try:
                    lock_context.__exit__(None, None, None)
                except Exception:
                    pass

    @staticmethod
    def _unavailable(
        code: str,
        period: str,
        direction: str,
        parent: _ParentContext | None,
        capacity: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "code": code,
            "period": period,
            "direction": direction,
            "decision_date": parent.snapshot.decision_date.isoformat() if parent is not None else None,
            "parent_manifest_sha256": parent.snapshot.manifest_sha256 if parent is not None else None,
            "manifest_sha256": None,
            "manifest_identity_sha256": None,
            "capacity": dict(capacity),
        }

    @staticmethod
    def _result_cancelled(
        period: str,
        direction: str,
        snapshot: VerifiedDailyMarketSnapshot,
        capacity: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "cancelled",
            "code": "ranking_publish_cancelled",
            "period": period,
            "direction": direction,
            "decision_date": getattr(getattr(snapshot, "decision_date", None), "isoformat", lambda: None)(),
            "parent_manifest_sha256": getattr(snapshot, "manifest_sha256", None),
            "manifest_sha256": None,
            "manifest_identity_sha256": None,
            "capacity": dict(capacity),
        }


class _Cancelled(Exception):
    pass


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise _Cancelled()


def _load_parent_context(
    snapshot_root: Path,
    snapshot: VerifiedDailyMarketSnapshot,
    db_path: str | Path,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> _ParentContext:
    from app_module.daily_market_feature_snapshot import daily_market_feature_input_fingerprint
    from app_module.daily_market_snapshot_repository import (
        DailyMarketSnapshotRepository,
        VerifiedDailyMarketSnapshot,
        validate_research_universe_binding,
    )
    from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
    from app_module.sqlite_read_only import ReadOperationCancelled

    if not isinstance(snapshot, VerifiedDailyMarketSnapshot):
        _fail("ranking_parent_snapshot_invalid", "只接受 VerifiedDailyMarketSnapshot。")
    database = Path(db_path).expanduser().resolve()
    if not database.is_file():
        _fail("ranking_source_unavailable", "明示 SQLite 來源不存在。")
    try:
        parent = DailyMarketSnapshotRepository(snapshot_root).load_manifest(
            snapshot.manifest_sha256,
            snapshot.cohort_id,
            snapshot.decision_date,
        )
    except Exception as exc:
        raise OriginalStockRankingError("ranking_parent_snapshot_invalid", "無法重新驗證來源日快照。") from exc
    if (
        parent.manifest_sha256 != snapshot.manifest_sha256
        or parent.manifest_identity_sha256 != snapshot.manifest_identity_sha256
        or parent.cohort_id != snapshot.cohort_id
        or parent.decision_date != snapshot.decision_date
    ):
        _fail("ranking_parent_snapshot_mismatch", "呼叫端 Verified snapshot 身份與儲存內容不符。")
    declared_codes = _validate_codes(parent.manifest.get("declared_stock_codes"), name="declared_stock_codes")
    if parent.manifest.get("research_only") is False:
        _fail("ranking_parent_policy_invalid", "來源日快照未聲明研究用途。")
    universe_binding = parent.manifest.get("research_universe")
    if not isinstance(universe_binding, Mapping):
        _fail("ranking_research_universe_required", "原始排名只接受明示 research_universe 快照。")
    try:
        validated_binding = validate_research_universe_binding(
            universe_binding,
            decision_date=parent.decision_date,
            cohort_id=parent.cohort_id,
            declared_stock_codes=declared_codes,
        )
    except Exception as exc:
        raise OriginalStockRankingError("ranking_research_universe_invalid", "目前 research_universe 設定與來源快照不符。") from exc
    if not isinstance(validated_binding, Mapping):
        _fail("ranking_research_universe_invalid", "來源快照缺少已驗證 research_universe binding。")
    if tuple(validated_binding.get("included_stock_codes", ())) != declared_codes:
        _fail("ranking_research_universe_scope_mismatch", "設定母體 included members 與 declared 股票分母不同。")
    if validated_binding.get("research_only") is not True:
        _fail("ranking_research_universe_invalid", "research_universe 必須聲明 research_only。")

    records = _stock_records(parent.manifest)
    if set(records) != set(parent.stock_snapshots):
        _fail("ranking_parent_snapshot_invalid", "來源快照 artifact 集合與 manifest 記錄不符。")
    db_key = _resolved_path_key(database)
    for code, record in records.items():
        refs = record.get("source_refs")
        if not isinstance(refs, Mapping) or _resolved_path_key(str(refs.get("database") or "")) != db_key:
            _fail("ranking_source_db_mismatch", f"{code} 的 snapshot source DB 與明示 db_path 不同。")

    captured: dict[str, _CapturedStock] = {}
    source_pin: tuple[Any, ...] = ()
    schema_hash = ""
    try:
        with SQLiteDailyMarketSnapshotSource(database, parent.decision_date, cancel_callback=cancel_callback) as source:
            source_pin = tuple(source._pin)
            schema_hash = source.schema_identity
            for code in sorted(records):
                _check_cancel(cancel_callback)
                points, technical, scope_identity, refs = source.load(code)
                if len(points) > _MAX_PRICE_POINTS_PER_STOCK:
                    _fail("ranking_source_window_exceeded", f"{code} 來源視窗超過 120 筆。")
                expected_refs = records[code].get("source_refs")
                if not isinstance(expected_refs, Mapping):
                    _fail("ranking_parent_manifest_invalid", f"{code} source_refs 無效。")
                if refs.get("schema_identity_sha256") != expected_refs.get("schema_identity_sha256"):
                    _fail("ranking_source_schema_changed", f"{code} 來源 schema 與母快照不同。")
                if scope_identity != parent.stock_snapshots[code].get("scope_identity"):
                    _fail("ranking_source_scope_changed", f"{code} 來源 scope identity 與母快照不同。")
                fingerprint = daily_market_feature_input_fingerprint(
                    stock_code=code,
                    decision_date=parent.decision_date,
                    scope_identity=scope_identity,
                    price_points=points,
                    technical=technical,
                )
                parent_fingerprint = parent.stock_snapshots[code].get("input_fingerprint_sha256")
                if fingerprint != parent_fingerprint:
                    _fail("ranking_source_input_hash_mismatch", f"{code} 目前來源 fingerprint 與母快照不同。")
                dates = tuple(_date_text(point.data_date) for point in points)
                latest = max(dates) if dates else None
                captured[code] = _CapturedStock(
                    code=code,
                    points=tuple(sorted(points, key=lambda item: _date_text(item.data_date))),
                    technical=technical,
                    scope_identity=scope_identity,
                    fingerprint=fingerprint,
                    latest_date=latest,
                )
            source.validate_source_stable()
            if tuple(source._pin) != source_pin:
                _fail("ranking_source_changed", "來源 SQLite 身份於交易期間已變更。")
    except OriginalStockRankingError:
        raise
    except ReadOperationCancelled:
        raise
    except _Cancelled:
        raise
    except Exception as exc:
        raise OriginalStockRankingError("ranking_source_unavailable", "無法以 SQLite 唯讀交易驗證排名來源。") from exc
    return _ParentContext(
        snapshot=parent,
        db_path=database,
        declared_codes=declared_codes,
        captured=MappingProxyType(captured),
        source_schema_sha256=schema_hash,
        source_pin=source_pin,
        universe_binding=MappingProxyType(dict(validated_binding)),
    )


def _validate_manifest_binding(
    manifest: Mapping[str, Any],
    parent: _ParentContext,
    period: str,
    direction: str,
    engine: Mapping[str, Any],
) -> None:
    decision_day = parent.snapshot.decision_date.isoformat()
    checks = {
        "period": period,
        "direction": direction,
        "decision_date": decision_day,
        "readiness": "research_only",
        "parent_manifest_sha256": parent.snapshot.manifest_sha256,
        "parent_manifest_identity_sha256": parent.snapshot.manifest_identity_sha256,
        "cohort_id": parent.snapshot.cohort_id,
        "research_universe": dict(parent.universe_binding),
        "declared_stock_codes": list(parent.declared_codes),
        "captured_stock_codes": list(sorted(parent.captured)),
        "engine": dict(engine),
        "engine_parameters": _engine_parameters(period, direction, len(parent.declared_codes)),
        "source": {
            "source_db_path": parent.db_path.as_posix(),
            "schema_identity_sha256": parent.source_schema_sha256,
            "price_table": "daily_prices",
            "technical_table": "technical_indicators",
            "source_window_limit_per_stock": _MAX_PRICE_POINTS_PER_STOCK,
            "captured_stock_codes": list(sorted(parent.captured)),
            "captured_point_counts": {code: len(parent.captured[code].points) for code in sorted(parent.captured)},
            "latest_dates": {code: parent.captured[code].latest_date for code in sorted(parent.captured)},
            "input_fingerprints": {code: parent.captured[code].fingerprint for code in sorted(parent.captured)},
            "volume_history": {
                code: {
                    "source_point_count": len(parent.captured[code].points),
                    "lookback_configuration": 20,
                    "actual_reference_point_count": min(20, len(parent.captured[code].points) - 1)
                    if len(parent.captured[code].points) >= 21
                    else (min(5, len(parent.captured[code].points) - 1) if len(parent.captured[code].points) >= 6 else len(parent.captured[code].points) - 1),
                }
                for code in sorted(parent.captured)
            },
            "comparison_rules": {
                code: {
                    "comparison_index_from_latest": _comparison_index(len(parent.captured[code].points), period)[0],
                    "rule": _comparison_index(len(parent.captured[code].points), period)[1],
                }
                for code in sorted(parent.captured)
            },
        },
        "qualification": {
            "usage": "current_observed_research_only",
            "readiness": "research_only",
            "research_only": True,
            "historical_pit_eligible": False,
            "current_observed_only": True,
            "full_market_coverage": False,
            "formal_recommendation_eligible": False,
            "native_score_semantics": "legacy_percentile_label_preserved",
            "numeric_score_status": "not_exposed_by_legacy_engine",
        },
    }
    for key, expected in checks.items():
        try:
            equal = _canonical_bytes(manifest.get(key)) == _canonical_bytes(expected)
        except OriginalStockRankingError:
            equal = False
        if not equal:
            _fail("ranking_manifest_binding_mismatch", f"原始排名 manifest 欄位 {key} 與目前來源不符。")
    eligible_size = manifest.get("eligible_universe_size")
    eligible_codes = manifest.get("eligible_stock_codes")
    if (
        type(eligible_size) is not int
        or not isinstance(eligible_codes, list)
        or not 0 <= eligible_size <= len(parent.declared_codes)
        or eligible_size != len(eligible_codes)
    ):
        _fail("ranking_eligible_count_mismatch", "eligible_universe_size 與 eligible 清單數量不符。")


def _validate_rows(raw: Any, parent: _ParentContext, period: str, direction: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > len(parent.declared_codes):
        _fail("ranking_rows_invalid", "原始排名 rows 超過 declared universe。")
    output: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    seen_ranks: set[int] = set()
    for row in raw:
        if not isinstance(row, dict) or set(row) != _RANK_ROW_KEYS:
            _fail("ranking_row_schema_mismatch", "原始排名列 schema 不相容。")
        code = row.get("stock_code")
        rank = row.get("rank")
        if not isinstance(code, str) or code not in parent.captured or code in seen_codes:
            _fail("ranking_row_scope_invalid", "原始排名股票超出來源或重複。")
        if type(rank) is not int or rank <= 0 or rank in seen_ranks:
            _fail("ranking_rank_invalid", "原始排名 rank 必須是唯一正整數。")
        if not isinstance(row.get("score_label"), str) or not row["score_label"].strip():
            _fail("ranking_score_label_invalid", "原生評分必須保留為非空 label。")
        expected_prefix = "Top " if direction == "strong" else "Bottom "
        if not row["score_label"].startswith(expected_prefix):
            _fail("ranking_score_label_invalid", "原生評分 label 與 strong/weak 方向不符。")
        if not isinstance(row.get("native_reasons"), str):
            _fail("ranking_native_reasons_invalid", "原始推薦理由必須保留為文字。")
        _decimal(row.get("price_change_percent"), field="price_change_percent")
        _decimal(row.get("volume_change_percent"), field="volume_change_percent")
        latest = _date_text(row.get("latest_date"))
        comparison = _date_text(row.get("comparison_date"))
        expected_latest = parent.captured[code].latest_date
        index, _rule = _comparison_index(len(parent.captured[code].points), period)
        expected_comparison = _date_text(parent.captured[code].points[index].data_date)
        if latest != expected_latest or comparison != expected_comparison:
            _fail("ranking_row_date_mismatch", f"{code} 原生比較日期與來源窗口不同。")
        seen_codes.add(code)
        seen_ranks.add(rank)
        output.append({
            "stock_code": code,
            "rank": rank,
            "score_label": row["score_label"],
            "price_change_percent": _decimal_text(row["price_change_percent"], field="price_change_percent"),
            "volume_change_percent": _decimal_text(row["volume_change_percent"], field="volume_change_percent"),
            "comparison_date": comparison,
            "latest_date": latest,
            "native_reasons": row["native_reasons"],
        })
    if tuple(row["rank"] for row in output) != tuple(range(1, len(output) + 1)):
        _fail("ranking_rank_not_contiguous", "原始排名 rank 必須從 1 開始連續遞增。")
    if len(output) > len(parent.declared_codes):
        _fail("ranking_top_n_mismatch", "原始排名輸出超出整個 included universe 的 top_n。")
    return output


def _rows_from_engine(
    engine_output: Any,
    eligible_total: Any,
    parent: _ParentContext,
    period: str,
    direction: str,
) -> list[dict[str, Any]]:
    import pandas as pd

    if not isinstance(engine_output, pd.DataFrame):
        _fail("ranking_engine_output_invalid", "原生排名引擎未回傳 DataFrame。")
    if type(eligible_total) is not int or eligible_total < 0:
        _fail("ranking_engine_count_invalid", "原生 eligible 計數必須是非負整數。")
    if eligible_total != len(engine_output):
        _fail("ranking_top_n_mismatch", "top_n 設為完整 included universe，原生 eligible 計數與輸出列數不符。")
    required = {"排名", "證券代號", "評分", "漲幅%", "成交量變化率%", "推薦理由"}
    if len(engine_output) and not required.issubset(engine_output.columns):
        _fail("ranking_engine_output_invalid", "原生排名引擎輸出欄位不完整。")
    raw: list[dict[str, Any]] = []
    for item in engine_output.to_dict(orient="records"):
        code = str(item.get("證券代號", "")).strip()
        try:
            rank = int(item.get("排名"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise OriginalStockRankingError("ranking_rank_invalid", "原生引擎 rank 不是整數。") from exc
        if isinstance(item.get("排名"), bool) or Decimal(str(item.get("排名"))) != Decimal(rank):
            _fail("ranking_rank_invalid", "原生引擎 rank 不是整數。")
        if code not in parent.captured:
            _fail("ranking_row_scope_invalid", "原生排名引擎輸出未捕獲股票。")
        points = parent.captured[code].points
        index, _rule = _comparison_index(len(points), period)
        raw.append(
            {
                "stock_code": code,
                "rank": rank,
                "score_label": str(item.get("評分") or ""),
                "price_change_percent": _decimal_text(item.get("漲幅%"), field="price_change_percent"),
                "volume_change_percent": _decimal_text(item.get("成交量變化率%"), field="volume_change_percent"),
                "comparison_date": _date_text(points[index].data_date),
                "latest_date": parent.captured[code].latest_date,
                "native_reasons": str(item.get("推薦理由") or ""),
            }
        )
    return _validate_rows(raw, parent, period, direction)


def _validate_candidate_bundle(root: Path, pointer: Mapping[str, Any], manifest: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
    manifest_raw, persisted_manifest = _read_json(
        root / _manifest_relpath(str(pointer["manifest_sha256"])),
        maximum=_MAX_RANKING_MANIFEST_BYTES,
        missing_code="ranking_manifest_missing",
        invalid_code="ranking_manifest_invalid",
    )
    artifact_raw, persisted_artifact = _read_json(
        root / _object_relpath(str(manifest["artifact_sha256"])),
        maximum=_MAX_RANKING_ARTIFACT_BYTES,
        missing_code="ranking_artifact_missing",
        invalid_code="ranking_artifact_invalid",
    )
    if _sha256(manifest_raw) != pointer["manifest_sha256"] or persisted_manifest != manifest:
        _fail("ranking_candidate_manifest_invalid", "待發布排名 manifest 回讀驗證失敗。")
    if _sha256(artifact_raw) != manifest["artifact_sha256"] or persisted_artifact != artifact:
        _fail("ranking_candidate_artifact_invalid", "待發布排名 artifact 回讀驗證失敗。")
    if set(pointer) != _POINTER_KEYS or pointer.get("schema_version") != ORIGINAL_RANKING_POINTER_SCHEMA:
        _fail("ranking_candidate_pointer_invalid", "待發布排名 pointer schema 不相容。")
