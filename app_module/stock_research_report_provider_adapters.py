"""個股研究報告使用的唯讀、run-pinned ML／Exit adapters。

ML registry只記錄 current-restated research receipt 的不可變 run 身分；它
不訓練模型、不重新推論，也不把研究輸出升格成正式 Advice。Exit adapter
只投影既有 current Portfolio condition/health 結果，不新增交易規則。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from data_module.ml_research_output_boundary import (
    get_ml_research_root,
    resolve_ml_research_output_path,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_RELATIVE_ROOT = Path("current_stock_research_registry")
_REGISTRY_SCHEMA = "current-restated-stock-research-registry.v1"
_INDEX_SCHEMA = "current-restated-stock-research-registry-index.v1"
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_INDEX_BYTES = 32 * 1024 * 1024
_MAX_INDEX_ROWS = 100_000
_SHA256_RE = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_CONTEXT_IDENTITY_FIELDS = (
    "result_id",
    "source_id",
    "source_snapshot_id",
    "source_snapshot_hash",
    "decision_date",
    "data_date",
    "profile_id",
    "profile_version",
    "source_version",
    "source_kind",
    "source_workspace",
    "mapping_source_id",
    "mapping_version",
    "mapping_observed_date",
)
_CURRENT_PRICE_ROW_FINGERPRINT_SCHEMA = "stock-price-row-fingerprint.v1"
_TARGET_METRIC = "benchmark_excess_after_standard_80bp_cost"


class CurrentRestatedMLRegistryError(ValueError):
    """研究 run registry 格式、來源或時鐘違反 fail-closed 契約。"""


@dataclass(frozen=True, slots=True)
class PublishedCurrentRestatedMLRun:
    run_id: str
    cycle_id: str
    record_path: Path
    record_sha256: str
    index_path: Path
    indexed: bool


def _sha256_text(value: object, *, field_name: str) -> str:
    match = _SHA256_RE.fullmatch(str(value or "").strip())
    if not match:
        raise CurrentRestatedMLRegistryError(f"{field_name} must be a SHA-256 digest")
    return match.group(1).lower()


def _aware_datetime(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise CurrentRestatedMLRegistryError(f"{field_name} is not an ISO datetime") from exc
    else:
        raise CurrentRestatedMLRegistryError(f"{field_name} is required")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurrentRestatedMLRegistryError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso_date(value: object, *, field_name: str) -> date:
    if isinstance(value, datetime):
        raise CurrentRestatedMLRegistryError(f"{field_name} must be a date, not datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise CurrentRestatedMLRegistryError(f"{field_name} is required")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise CurrentRestatedMLRegistryError(f"{field_name} must be YYYY-MM-DD") from exc


def _plain_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CurrentRestatedMLRegistryError("registry payload is not canonical JSON") from exc


def _assert_regular_file(path: Path, *, role: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CurrentRestatedMLRegistryError(f"{role} is unavailable") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    is_junction = getattr(path, "is_junction", None)
    if (
        stat.S_ISLNK(info.st_mode)
        or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)
        or (callable(is_junction) and is_junction())
        or not stat.S_ISREG(info.st_mode)
    ):
        raise CurrentRestatedMLRegistryError(f"{role} must be a regular file without reparse aliases")


def _read_stable_bytes(path: Path, *, role: str, max_bytes: int) -> bytes:
    _assert_regular_file(path, role=role)
    try:
        before = path.stat()
        if before.st_size < 0 or before.st_size > max_bytes:
            raise CurrentRestatedMLRegistryError(f"{role} exceeds its byte limit")
        with path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
        after = path.stat()
    except OSError as exc:
        raise CurrentRestatedMLRegistryError(f"{role} could not be read") from exc
    if (
        len(payload) != before.st_size
        or len(payload) > max_bytes
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise CurrentRestatedMLRegistryError(f"{role} changed during read")
    return payload


def _read_json_object(path: Path, *, role: str, max_bytes: int = _MAX_JSON_BYTES) -> tuple[dict[str, Any], bytes]:
    payload = _read_stable_bytes(path, role=role, max_bytes=max_bytes)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentRestatedMLRegistryError(f"{role} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CurrentRestatedMLRegistryError(f"{role} root must be an object")
    return value, payload


def _context_map(context: object | None) -> dict[str, str]:
    if context is None:
        return {}
    names = (
        "stock_code", "ml_scope_mode", "current_event_date",
        "current_price_row_fingerprint_sha256", *_CONTEXT_IDENTITY_FIELDS,
    )
    result: dict[str, str] = {}
    for name in names:
        raw = context.get(name, "") if isinstance(context, Mapping) else getattr(context, name, "")
        value = str(raw or "").strip()
        if value:
            result[name] = value
    return result


def _fingerprint_decimal(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise CurrentRestatedMLRegistryError(f"{field_name} must be an exact Decimal or integer")
    if isinstance(value, Decimal):
        parsed = value
    elif type(value) is int or isinstance(value, str):
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise CurrentRestatedMLRegistryError(f"{field_name} is not a decimal value") from exc
    else:
        raise CurrentRestatedMLRegistryError(f"{field_name} has an unsupported numeric type")
    if not parsed.is_finite():
        raise CurrentRestatedMLRegistryError(f"{field_name} must be finite")
    if parsed == 0:
        return "0"
    return format(parsed.normalize(), "f")


def stock_price_row_fingerprint_sha256(
    *,
    stock_code: object,
    data_date: object,
    open_price: object,
    high_price: object,
    low_price: object,
    close_price: object,
    volume: object,
    turnover: object,
) -> str:
    """Hash one exact OHLCV/turnover row using a cross-process canonical contract."""

    code = str(stock_code or "").strip()
    if not re.fullmatch(r"\d{4,6}", code):
        raise CurrentRestatedMLRegistryError("price-row fingerprint stock_code is invalid")
    if isinstance(data_date, datetime):
        raise CurrentRestatedMLRegistryError("price-row fingerprint data_date must not be datetime")
    if isinstance(data_date, date):
        normalized_date = data_date.isoformat()
    else:
        normalized_date = _iso_date(data_date, field_name="price-row fingerprint data_date").isoformat()
    exact_prices = {
        "open_price": _fingerprint_decimal(open_price, field_name="open_price"),
        "high_price": _fingerprint_decimal(high_price, field_name="high_price"),
        "low_price": _fingerprint_decimal(low_price, field_name="low_price"),
        "close_price": _fingerprint_decimal(close_price, field_name="close_price"),
    }
    if any(value is None for value in exact_prices.values()):
        raise CurrentRestatedMLRegistryError("price-row fingerprint requires complete OHLC")
    if isinstance(volume, bool) or (volume is not None and type(volume) is not int):
        raise CurrentRestatedMLRegistryError("price-row fingerprint volume must be an integer or null")
    if volume is not None and volume < 0:
        raise CurrentRestatedMLRegistryError("price-row fingerprint volume cannot be negative")
    payload = {
        "schema_version": _CURRENT_PRICE_ROW_FINGERPRINT_SCHEMA,
        "stock_code": code,
        "data_date": normalized_date,
        **exact_prices,
        "volume": volume,
        "turnover": _fingerprint_decimal(turnover, field_name="turnover"),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _validate_prediction_payload(
    *,
    receipt: Mapping[str, Any],
    symbol: str,
    event_date: str,
    model_manifest_sha256: str,
    model_keys: Sequence[str],
    generated_at: datetime,
) -> tuple[dict[str, int], dict[str, Any]]:
    predictions = receipt.get("predictions")
    if not isinstance(predictions, list):
        raise CurrentRestatedMLRegistryError("sidecar predictions are missing")
    matches = [
        item
        for item in predictions
        if isinstance(item, Mapping)
        and str(item.get("symbol", "")) == symbol
        and str(item.get("event_date", "")) == event_date
    ]
    if len(matches) != 1:
        raise CurrentRestatedMLRegistryError("sidecar must contain one exact symbol/date prediction")
    row = matches[0]
    prediction = row.get("model_prediction")
    if not isinstance(prediction, Mapping):
        raise CurrentRestatedMLRegistryError("sidecar model prediction is missing")
    if (
        prediction.get("schema_version") != "ml-current-restated-outcome-prediction.v1"
        or prediction.get("status") != "research_prediction_only"
        or prediction.get("symbol") != symbol
        or prediction.get("event_date") != event_date
        or _sha256_text(prediction.get("model_manifest_sha256"), field_name="prediction model manifest SHA")
        != model_manifest_sha256
        or prediction.get("historical_pit") is not False
        or prediction.get("decision_time_eligible") is not False
        or prediction.get("production_action_allowed") is not False
    ):
        raise CurrentRestatedMLRegistryError("sidecar prediction identity or capability flags are invalid")
    if prediction.get("target_metric") != _TARGET_METRIC:
        raise CurrentRestatedMLRegistryError("sidecar prediction target metric differs from the reviewed outcome contract")
    raw_bp = prediction.get("predicted_benchmark_excess_return_bp")
    if not isinstance(raw_bp, Mapping) or not raw_bp:
        raise CurrentRestatedMLRegistryError("sidecar lacks benchmark-excess bp output")
    expected_keys = set(model_keys)
    if not expected_keys or set(raw_bp) != expected_keys:
        raise CurrentRestatedMLRegistryError("prediction output keys differ from the exact model manifest")
    bp: dict[str, int] = {}
    for key, value in raw_bp.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise CurrentRestatedMLRegistryError("benchmark-excess outputs must be integer bp")
        bp[str(key)] = value
    quality = prediction.get("input_quality_summary")
    if not isinstance(quality, Mapping) or not quality:
        raise CurrentRestatedMLRegistryError("sidecar prediction lacks input quality summary")
    for name in ("usable_feature_count", "registry_feature_count"):
        value = quality.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise CurrentRestatedMLRegistryError(f"sidecar input quality {name} is invalid")
    vector_sha = _sha256_text(row.get("core19_numeric_vector_sha256"), field_name="current vector SHA")
    vector_map = receipt.get("core19_numeric_vector_sha256_by_symbol")
    if not isinstance(vector_map, Mapping) or _sha256_text(
        vector_map.get(symbol), field_name="current vector map SHA"
    ) != vector_sha:
        raise CurrentRestatedMLRegistryError("sidecar current vector hash differs from prediction row")
    raw_h5 = row.get("gross_outcome_and_cost")
    if not isinstance(raw_h5, Mapping):
        raise CurrentRestatedMLRegistryError("sidecar H5 maturity status is missing")
    h5_status = str(raw_h5.get("status", ""))
    if h5_status not in {"not_mature", "mature_gross_label"}:
        raise CurrentRestatedMLRegistryError("sidecar H5 maturity status is unsupported")
    h5 = dict(raw_h5)
    h5["status"] = h5_status
    if h5_status == "mature_gross_label":
        horizon = h5.get("horizon")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon != 5:
            raise CurrentRestatedMLRegistryError("mature H5 label must declare horizon 5")
        next_entry = _iso_date(h5.get("next_entry_date"), field_name="H5 next_entry_date")
        horizon_end = _iso_date(h5.get("horizon_end_date"), field_name="H5 horizon_end_date")
        event_day = _iso_date(event_date, field_name="H5 event date")
        if next_entry <= event_day or horizon_end < next_entry:
            raise CurrentRestatedMLRegistryError("mature H5 dates are inconsistent with next-entry ordering")
        if horizon_end > generated_at.astimezone(_TAIPEI).date():
            raise CurrentRestatedMLRegistryError("mature H5 horizon is later than the sidecar receipt date")
        for name in (
            "gross_stock_return_bp",
            "gross_benchmark_return_bp",
            "benchmark_excess_after_standard_80bp_cost",
        ):
            value = h5.get(name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise CurrentRestatedMLRegistryError(f"mature H5 label lacks integer {name}")
        if h5["benchmark_excess_after_standard_80bp_cost"] != (
            h5["gross_stock_return_bp"] - h5["gross_benchmark_return_bp"] - 80
        ):
            raise CurrentRestatedMLRegistryError("mature H5 label violates the standard 80 bp target arithmetic")
        after_lane_cost = h5.get("after_lane_cost_stock_return_bp")
        if after_lane_cost is not None and (isinstance(after_lane_cost, bool) or not isinstance(after_lane_cost, int)):
            raise CurrentRestatedMLRegistryError("mature H5 after-lane-cost result must be integer bp or null")
    else:
        horizon = h5.get("horizon")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon != 5:
            raise CurrentRestatedMLRegistryError("immature H5 label must declare horizon 5")
        for name in (
            "gross_stock_return_bp",
            "gross_benchmark_return_bp",
            "benchmark_excess_after_standard_80bp_cost",
            "after_lane_cost_stock_return_bp",
            "next_entry_date",
            "horizon_end_date",
            "round_trip_cost",
            "price_inputs",
        ):
            if h5.get(name) is not None:
                raise CurrentRestatedMLRegistryError("immature H5 label must not contain a fabricated outcome")
    return bp, h5


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:  # pragma: no cover - Linux CI path
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - Linux CI path
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
    finally:
        handle.close()


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise CurrentRestatedMLRegistryError(f"immutable registry artifact already exists: {path.name}") from exc
    except OSError as exc:
        raise CurrentRestatedMLRegistryError(f"immutable registry artifact could not be written: {path.name}") from exc


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":  # pragma: no cover - Windows does not expose directory fsync
        return
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)


class CurrentRestatedMLRunRegistry:
    """發布不可變 sidecar run；唯讀查詢不需要 loader，發布必須明示注入。"""

    def __init__(
        self,
        *,
        repository_root: Path | None = None,
        research_output_root: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
        model_loader: Callable[..., object] | None = None,
    ) -> None:
        root = Path(repository_root or _REPO_ROOT).expanduser()
        if not root.is_absolute():
            raise CurrentRestatedMLRegistryError("repository_root must be absolute")
        self.repository_root = root.resolve()
        active_root = get_ml_research_root(repository_root=self.repository_root)
        requested_root = (
            active_root
            if research_output_root is None
            else Path(research_output_root).expanduser()
        )
        self.research_root = resolve_ml_research_output_path(
            requested_root,
            repository_root=self.repository_root,
            access="write",
        )
        if self.research_root != active_root:
            raise CurrentRestatedMLRegistryError(
                "registry write root differs from the configured active research root"
            )
        self.registry_root = resolve_ml_research_output_path(
            self.research_root / _REGISTRY_RELATIVE_ROOT,
            repository_root=self.repository_root,
            access="write",
        )
        self.index_path = self.registry_root / "run_index.jsonl"
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._model_loader = model_loader

    def _assert_active_write_root(self) -> None:
        active_root = get_ml_research_root(repository_root=self.repository_root)
        if active_root != self.research_root:
            raise CurrentRestatedMLRegistryError(
                "active ML research storage root changed during registry publication"
            )
        resolve_ml_research_output_path(
            self.registry_root,
            repository_root=self.repository_root,
            access="write",
        )

    def _registry_roots_for_read(self) -> tuple[Path, ...]:
        active_root = get_ml_research_root(repository_root=self.repository_root)
        legacy_root = self.repository_root / "output" / "ml_research"
        roots: list[Path] = []
        for research_root in (active_root, legacy_root):
            registry_root = resolve_ml_research_output_path(
                research_root / _REGISTRY_RELATIVE_ROOT,
                repository_root=self.repository_root,
                access="read",
            )
            if registry_root not in roots:
                roots.append(registry_root)
        return tuple(roots)

    def publish_sidecar(
        self,
        *,
        sidecar_receipt_path: Path | str,
        expected_sidecar_receipt_sha256: str,
        model_manifest_path: Path | str,
        expected_model_manifest_sha256: str,
        expected_model_bundle_sha256: str,
        context_identity: Mapping[str, object] | None = None,
        scope_mode: str = "current_stock_research",
        cycle_id: str = "",
        current_price_row_fingerprint_sha256_by_symbol: Mapping[str, object] | None = None,
        current_price_rows_source_path: Path | str | None = None,
        expected_current_price_rows_source_sha256: str | None = None,
    ) -> PublishedCurrentRestatedMLRun:
        """驗證已完成 current-restated sidecar 後，create-only 發布精確 run。"""

        model_loader = self._model_loader
        if not callable(model_loader):
            raise CurrentRestatedMLRegistryError("model_loader is required for registry publication")

        now = _aware_datetime(self._now_provider(), field_name="actual clock")
        sidecar_path = resolve_ml_research_output_path(
            Path(sidecar_receipt_path), repository_root=self.repository_root
        )
        manifest_path = resolve_ml_research_output_path(
            Path(model_manifest_path), repository_root=self.repository_root
        )
        if sidecar_path.is_symlink() or not sidecar_path.is_file() or sidecar_path.name != "receipt.json":
            raise CurrentRestatedMLRegistryError("sidecar receipt must be a regular receipt.json in ML research output")
        if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.name != "manifest.json":
            raise CurrentRestatedMLRegistryError("model manifest must be a regular manifest.json in ML research output")
        expected_sidecar_sha = _sha256_text(
            expected_sidecar_receipt_sha256, field_name="expected sidecar receipt SHA"
        )
        expected_manifest_sha = _sha256_text(
            expected_model_manifest_sha256, field_name="expected model manifest SHA"
        )
        expected_bundle_sha = _sha256_text(
            expected_model_bundle_sha256, field_name="expected model bundle SHA"
        )
        receipt, receipt_bytes = _read_json_object(sidecar_path, role="current-restated sidecar receipt")
        receipt_sha = sha256(receipt_bytes).hexdigest()
        if receipt_sha != expected_sidecar_sha:
            raise CurrentRestatedMLRegistryError("sidecar receipt actual-byte SHA mismatch")
        if (
            receipt.get("schema_version") != "current-restated-source-row-learning-terminal.v1"
            or receipt.get("status") != "verified_research_sidecar"
            or receipt.get("terminal") is not True
            or receipt.get("mode") != "source_row_outcome_research"
            or receipt.get("historical_pit_eligible") is not False
            or receipt.get("formal_calibration_performed") is not False
            or receipt.get("formal_order_allowed") is not False
            or receipt.get("production_action_allowed") is not False
            or receipt.get("model_training_performed") is not False
            or receipt.get("verified_model_reused") is not True
        ):
            raise CurrentRestatedMLRegistryError("sidecar is not a completed research-only terminal")
        generated_at = _aware_datetime(receipt.get("generated_at"), field_name="sidecar generated_at")
        inference_at = _aware_datetime(receipt.get("inference_at"), field_name="sidecar inference_at")
        if generated_at > now or inference_at > now or inference_at > generated_at:
            raise CurrentRestatedMLRegistryError("sidecar clocks must satisfy inference <= generated <= actual clock")
        input_binding = receipt.get("input_binding")
        source_pins = receipt.get("source_pins")
        if not isinstance(input_binding, Mapping) or not isinstance(source_pins, Mapping):
            raise CurrentRestatedMLRegistryError("sidecar source binding/pins are missing")
        event_date = _iso_date(input_binding.get("current_event_date"), field_name="current event date")
        if event_date > inference_at.astimezone(_TAIPEI).date():
            raise CurrentRestatedMLRegistryError("sidecar event date is later than the inference clock")
        lane = str(receipt.get("lane", ""))
        if lane not in {"legacy", "banktaiwan"}:
            raise CurrentRestatedMLRegistryError("sidecar research lane is unsupported")
        if scope_mode not in {"current_stock_research", "selected_saved_decision"}:
            raise CurrentRestatedMLRegistryError("registry scope_mode is unsupported")
        cycle = str(cycle_id or "").strip()
        if scope_mode == "current_stock_research" and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", cycle
        ):
            raise CurrentRestatedMLRegistryError("current-stock registry requires a valid cycle_id")
        symbols_raw = input_binding.get("current_symbols")
        if (
            not isinstance(symbols_raw, list)
            or not 2 <= len(symbols_raw) <= 16
            or any(not isinstance(item, str) or not item or item != item.strip() for item in symbols_raw)
            or len(set(symbols_raw)) != len(symbols_raw)
        ):
            raise CurrentRestatedMLRegistryError("sidecar must bind an explicit 2..16 symbol cohort")
        symbols = tuple(symbols_raw)
        price_fingerprints: dict[str, str] = {}
        price_rows_path = ""
        price_rows_sha = ""
        if scope_mode == "current_stock_research":
            if not isinstance(current_price_row_fingerprint_sha256_by_symbol, Mapping):
                raise CurrentRestatedMLRegistryError("current-stock registry requires price-row fingerprints")
            if set(current_price_row_fingerprint_sha256_by_symbol) != set(symbols):
                raise CurrentRestatedMLRegistryError("price-row fingerprint symbols differ from model scope")
            price_fingerprints = {
                symbol: _sha256_text(
                    current_price_row_fingerprint_sha256_by_symbol[symbol],
                    field_name=f"{symbol} price-row fingerprint SHA",
                )
                for symbol in symbols
            }
            if current_price_rows_source_path is None or not expected_current_price_rows_source_sha256:
                raise CurrentRestatedMLRegistryError("current-stock price-row fingerprints require an exact source pin")
            price_rows_path_obj = resolve_ml_research_output_path(
                Path(current_price_rows_source_path), repository_root=self.repository_root
            )
            price_rows_bytes = _read_stable_bytes(
                price_rows_path_obj,
                role="current price-row projection observations",
                max_bytes=64 * 1024 * 1024,
            )
            price_rows_sha = _sha256_text(
                expected_current_price_rows_source_sha256,
                field_name="current price-row projection observations SHA",
            )
            if sha256(price_rows_bytes).hexdigest() != price_rows_sha:
                raise CurrentRestatedMLRegistryError("current price-row projection actual-byte SHA mismatch")
            price_rows_path = str(price_rows_path_obj.resolve(strict=True))
        elif current_price_row_fingerprint_sha256_by_symbol or current_price_rows_source_path or expected_current_price_rows_source_sha256:
            raise CurrentRestatedMLRegistryError("saved-decision registry cannot accept unbound current price rows")
        context_sha = _sha256_text(
            input_binding.get("source_context_sha256"), field_name="sidecar source context SHA"
        )
        if _sha256_text(
            source_pins.get("source_context_sha256"), field_name="source pin context SHA"
        ) != context_sha:
            raise CurrentRestatedMLRegistryError("sidecar context source pins disagree")
        if scope_mode == "current_stock_research":
            supplied_identity = {
                str(key): str(value or "").strip()
                for key, value in dict(context_identity or {}).items()
                if str(value or "").strip()
            }
            if any(supplied_identity.get(key) for key in ("result_id", "source_id", "source_snapshot_id")):
                raise CurrentRestatedMLRegistryError(
                    "current-stock research registry must not bind a saved decision identity"
                )
            context = {
                "scope_mode": scope_mode,
                "source_snapshot_hash": context_sha,
                "source_snapshot_id": context_sha,
                "decision_date": event_date.isoformat(),
                "data_date": event_date.isoformat(),
            }
        else:
            context = {
                str(key): str(value or "").strip()
                for key, value in dict(context_identity or {}).items()
                if str(value or "").strip()
            }
            if not context or not context.get("source_snapshot_hash"):
                raise CurrentRestatedMLRegistryError("saved-decision registry requires exact source snapshot identity")
            context_stock = context.get("stock_code", "")
            if not context_stock or context_stock not in symbols:
                raise CurrentRestatedMLRegistryError("selected context stock is outside the pinned symbol cohort")
            if not any(context.get(field) for field in ("result_id", "source_id", "source_snapshot_id")):
                raise CurrentRestatedMLRegistryError("selected context lacks result/source run identity")
            source_hash = _sha256_text(
                context["source_snapshot_hash"], field_name="selected source snapshot hash"
            )
            if context_sha != source_hash:
                raise CurrentRestatedMLRegistryError(
                    "selected context snapshot hash differs from the sidecar source context"
                )
            for field_name in ("decision_date", "data_date"):
                if context.get(field_name):
                    if _iso_date(context[field_name], field_name=field_name) > event_date:
                        raise CurrentRestatedMLRegistryError(
                            f"selected context {field_name} is later than the pinned event date"
                        )
        if _iso_date(input_binding.get("current_event_date"), field_name="input event date") != event_date:
            raise CurrentRestatedMLRegistryError("sidecar event date binding differs")
        if _sha256_text(
            input_binding.get("model_manifest_sha256"), field_name="input model manifest SHA"
        ) != expected_manifest_sha:
            raise CurrentRestatedMLRegistryError("sidecar binds a different model manifest")
        if _sha256_text(
            input_binding.get("model_bundle_sha256"), field_name="input model bundle SHA"
        ) != expected_bundle_sha:
            raise CurrentRestatedMLRegistryError("sidecar binds a different model bundle")
        manifest_bytes = _read_stable_bytes(
            manifest_path, role="current-restated model manifest", max_bytes=_MAX_JSON_BYTES
        )
        if sha256(manifest_bytes).hexdigest() != expected_manifest_sha:
            raise CurrentRestatedMLRegistryError("model manifest actual-byte SHA mismatch")
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CurrentRestatedMLRegistryError("model manifest is invalid UTF-8 JSON") from exc
        if not isinstance(manifest, Mapping) or (
            manifest.get("schema_version") != "ml-current-restated-base-outcome-model.v1"
            or manifest.get("historical_pit_eligible") is not False
            or manifest.get("formal_training_eligible") is not False
            or manifest.get("production_action_allowed") is not False
        ):
            raise CurrentRestatedMLRegistryError("model manifest is not a bounded non-PIT research model")
        target_contract = manifest.get("target_contract")
        if not isinstance(target_contract, Mapping) or target_contract.get("target_metric") != _TARGET_METRIC:
            raise CurrentRestatedMLRegistryError("model manifest target metric differs from the reviewed research target")
        model_available_at = _aware_datetime(
            manifest.get("model_available_at"), field_name="model_available_at"
        )
        if model_available_at > inference_at:
            raise CurrentRestatedMLRegistryError("model is not available at the sidecar inference clock")
        model_bundle = manifest.get("model_bundle")
        if not isinstance(model_bundle, Mapping) or (
            _sha256_text(model_bundle.get("sha256"), field_name="manifest model bundle SHA") != expected_bundle_sha
        ):
            raise CurrentRestatedMLRegistryError("model manifest bundle SHA differs from pinned bundle")
        model_keys = model_bundle.get("model_keys")
        if (
            not isinstance(model_keys, list)
            or not model_keys
            or any(not isinstance(key, str) or not key for key in model_keys)
            or len(set(model_keys)) != len(model_keys)
        ):
            raise CurrentRestatedMLRegistryError("model manifest has no exact unique prediction key set")
        bundle_name = str(model_bundle.get("filename", "")).strip()
        if not bundle_name or Path(bundle_name).name != bundle_name:
            raise CurrentRestatedMLRegistryError("model bundle filename is unsafe")
        bundle_path = manifest_path.parent / bundle_name
        bundle_bytes = _read_stable_bytes(
            bundle_path, role="current-restated model bundle", max_bytes=512 * 1024 * 1024
        )
        if sha256(bundle_bytes).hexdigest() != expected_bundle_sha:
            raise CurrentRestatedMLRegistryError("model bundle actual-byte SHA mismatch")
        # 載入器會在反序列化前重新驗證 model manifest、runtime/code pins 與 bundle SHA。
        model_loader(
            manifest_path,
            expected_manifest_sha256=expected_manifest_sha,
            expected_model_bundle_sha256=expected_bundle_sha,
        )
        if _sha256_text(
            source_pins.get("model_manifest_sha256"), field_name="sidecar source model SHA"
        ) != expected_manifest_sha or _sha256_text(
            source_pins.get("model_bundle_sha256"), field_name="sidecar source bundle SHA"
        ) != expected_bundle_sha:
            raise CurrentRestatedMLRegistryError("sidecar source pins differ from verified model bytes")

        vector_hashes = receipt.get("core19_numeric_vector_sha256_by_symbol")
        if not isinstance(vector_hashes, Mapping) or set(vector_hashes) != set(symbols):
            raise CurrentRestatedMLRegistryError("sidecar current vector hashes differ from its symbol scope")
        rows: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            bp, h5 = _validate_prediction_payload(
                receipt=receipt,
                symbol=symbol,
                event_date=event_date.isoformat(),
                model_manifest_sha256=expected_manifest_sha,
                model_keys=model_keys,
                generated_at=generated_at,
            )
            raw_row = next(
                item for item in receipt["predictions"]
                if isinstance(item, Mapping)
                and item.get("symbol") == symbol
                and item.get("event_date") == event_date.isoformat()
            )
            raw_prediction = raw_row.get("model_prediction")
            if not isinstance(raw_prediction, Mapping):
                raise CurrentRestatedMLRegistryError("sidecar model prediction is missing")
            if (
                _aware_datetime(raw_prediction.get("inference_at"), field_name="prediction inference_at")
                != inference_at
                or _aware_datetime(raw_prediction.get("model_available_at"), field_name="prediction model_available_at")
                != model_available_at
            ):
                raise CurrentRestatedMLRegistryError("prediction clocks differ from verified sidecar/model clocks")
            rows[symbol] = {
                "core19_numeric_vector_sha256": _sha256_text(
                    vector_hashes[symbol], field_name=f"{symbol} vector SHA"
                ),
                "predicted_benchmark_excess_return_bp": bp,
                "h5": h5,
                "input_quality_summary": dict(raw_row["model_prediction"]["input_quality_summary"]),
                "target_metric": str(raw_row["model_prediction"].get("target_metric", "")),
            }

        record_payload: dict[str, Any] = {
            "schema_version": _REGISTRY_SCHEMA,
            "status": "verified_research_sidecar",
            "run_id": "",
            "cycle_id": cycle,
            "lane": lane,
            "scope_mode": scope_mode,
            "symbols": list(symbols),
            "event_date": event_date.isoformat(),
            "generated_at": generated_at.isoformat(),
            "inference_at": inference_at.isoformat(),
            "available_at": generated_at.isoformat(),
            "model_available_at": model_available_at.isoformat(),
            "source_context_sha256": context_sha,
            "current_price_row_fingerprint_sha256_by_symbol": price_fingerprints,
            "current_price_rows_source_path": price_rows_path,
            "current_price_rows_source_sha256": price_rows_sha,
            "context_identity": context,
            "input_binding": dict(input_binding),
            "source_pins": dict(source_pins),
            "model_manifest_path": str(manifest_path),
            "model_manifest_sha256": expected_manifest_sha,
            "model_bundle_sha256": expected_bundle_sha,
            "sidecar_receipt_path": str(sidecar_path),
            "sidecar_receipt_sha256": receipt_sha,
            "sample_cohort_sha256": _sha256_text(
                receipt.get("sample_cohort_sha256"), field_name="sample cohort SHA"
            ),
            "scope_count": len(symbols),
            "scope_limit": 16,
            "rows_by_symbol": rows,
            "historical_pit_eligible": False,
            "formal_calibration_performed": False,
            "formal_qualified": False,
            "production_action_allowed": False,
        }
        payload_hash = sha256(_plain_json_bytes(record_payload)).hexdigest()
        run_id = f"{event_date.strftime('%Y%m%d')}-{payload_hash[:24]}"
        record_payload["run_id"] = run_id
        record_bytes = _plain_json_bytes(record_payload)
        record_sha = sha256(record_bytes).hexdigest()
        run_dir = self.registry_root / "runs" / run_id
        record_path = run_dir / "record.json"
        index_path = self.index_path
        index_entry = {
            "schema_version": _INDEX_SCHEMA,
            "run_id": run_id,
            "record_path": str(Path("runs") / run_id / "record.json").replace("\\", "/"),
            "record_sha256": record_sha,
        }
        index_line = _plain_json_bytes(index_entry) + b"\n"
        self._assert_active_write_root()
        self.registry_root.mkdir(parents=True, exist_ok=True)
        self._assert_active_write_root()
        run_dir.mkdir(parents=True, exist_ok=False)
        try:
            _write_create_only(record_path, record_bytes)
            _fsync_directory(run_dir)
            with _exclusive_lock(self.registry_root / ".registry-index.lock"):
                self._assert_active_write_root()
                prior = self._find_index_entry(run_id)
                if prior is not None:
                    if prior.get("record_sha256") != record_sha:
                        raise CurrentRestatedMLRegistryError("registry run id collides with another immutable record")
                    return PublishedCurrentRestatedMLRun(
                        run_id=run_id,
                        cycle_id=cycle,
                        record_path=record_path,
                        record_sha256=record_sha,
                        index_path=index_path,
                        indexed=False,
                    )
                with index_path.open("ab") as handle:
                    handle.write(index_line)
                    handle.flush()
                    os.fsync(handle.fileno())
                _fsync_directory(self.registry_root)
        except Exception:
            # 不刪除可能已建立的研究記錄；失敗輸出保留，供追查且不覆寫。
            raise
        return PublishedCurrentRestatedMLRun(
            run_id=run_id,
            cycle_id=cycle,
            record_path=record_path,
            record_sha256=record_sha,
            index_path=index_path,
            indexed=True,
        )

    def __call__(
        self,
        stock_code: str,
        as_of_date: date,
        context: object | None = None,
    ) -> Mapping[str, Any] | None:
        """回傳一筆符合目前報告日期與所選來源身分的 research prediction。"""

        code = str(stock_code or "").strip()
        if not code:
            return None
        cutoff = _iso_date(as_of_date, field_name="as_of_date")
        now = _aware_datetime(self._now_provider(), field_name="actual clock")
        now_local_date = now.astimezone(_TAIPEI).date()
        if cutoff != now_local_date:
            return None
        selected = _context_map(context)
        selected_code = selected.get("stock_code", "")
        if selected_code != code:
            return None
        requested_mode = selected.get("ml_scope_mode", "")
        has_linked_saved_decision = bool(selected.get("result_id")) or bool(
            selected.get("source_snapshot_id") and selected.get("source_snapshot_hash")
        )
        if not requested_mode:
            requested_mode = (
                "selected_saved_decision" if has_linked_saved_decision else "current_stock_research"
            )
        if requested_mode not in {"current_stock_research", "selected_saved_decision"}:
            return None
        if requested_mode == "current_stock_research":
            if cutoff != now_local_date or not selected.get("current_event_date"):
                return None
            requested_fingerprint = selected.get("current_price_row_fingerprint_sha256", "")
            if not _SHA256_RE.fullmatch(requested_fingerprint):
                return None
            try:
                current_event_date = _iso_date(
                    selected["current_event_date"], field_name="current report market date"
                )
            except CurrentRestatedMLRegistryError:
                return None
        else:
            if (
                cutoff != now_local_date
                or not selected.get("source_snapshot_hash")
                or not any(selected.get(field) for field in ("result_id", "source_id", "source_snapshot_id"))
            ):
                return None
            current_event_date = None
            for date_key in ("decision_date", "data_date"):
                if selected.get(date_key):
                    try:
                        if _iso_date(selected[date_key], field_name=date_key) > cutoff:
                            return None
                    except CurrentRestatedMLRegistryError:
                        return None
        index_lines: list[tuple[Path, bytes]] = []
        for registry_root in self._registry_roots_for_read():
            index_path = registry_root / "run_index.jsonl"
            try:
                index_bytes = _read_stable_bytes(
                    index_path, role="ML registry index", max_bytes=_MAX_INDEX_BYTES
                )
            except CurrentRestatedMLRegistryError as exc:
                if not index_path.exists() and not index_path.is_symlink():
                    continue
                raise exc
            lines = index_bytes.splitlines()
            if len(lines) > _MAX_INDEX_ROWS:
                raise CurrentRestatedMLRegistryError("ML registry index has too many runs")
            index_lines.extend((registry_root, line) for line in lines)
        if not index_lines:
            return None
        candidates: list[tuple[datetime, str, dict[str, Any]]] = []
        for registry_root, line in index_lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CurrentRestatedMLRegistryError("ML registry index contains malformed JSON") from exc
            if not isinstance(entry, Mapping) or entry.get("schema_version") != _INDEX_SCHEMA:
                raise CurrentRestatedMLRegistryError("ML registry index entry schema is invalid")
            run_id = str(entry.get("run_id", ""))
            relative = str(entry.get("record_path", ""))
            if not run_id or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise CurrentRestatedMLRegistryError("ML registry index record path is unsafe")
            record_path = registry_root / relative
            try:
                resolved_record = record_path.resolve(strict=True)
                resolved_record.relative_to(registry_root.resolve(strict=True))
            except (OSError, ValueError) as exc:
                raise CurrentRestatedMLRegistryError("ML registry record escaped its root") from exc
            record, record_bytes = _read_json_object(record_path, role="immutable ML run registry record")
            if sha256(record_bytes).hexdigest() != _sha256_text(
                entry.get("record_sha256"), field_name="indexed record SHA"
            ):
                raise CurrentRestatedMLRegistryError("ML registry record actual-byte SHA mismatch")
            if (
                record.get("schema_version") != _REGISTRY_SCHEMA
                or record.get("run_id") != run_id
                or record.get("status") != "verified_research_sidecar"
                or record.get("historical_pit_eligible") is not False
                or record.get("formal_calibration_performed") is not False
                or record.get("formal_qualified") is not False
                or record.get("production_action_allowed") is not False
            ):
                raise CurrentRestatedMLRegistryError("ML registry record capability/status contract is invalid")
            symbols = record.get("symbols")
            if not isinstance(symbols, list) or code not in symbols:
                continue
            if record.get("scope_mode") != requested_mode:
                continue
            if requested_mode == "current_stock_research" and (
                current_event_date is None
                or record.get("event_date") != current_event_date.isoformat()
            ):
                continue
            if requested_mode == "current_stock_research":
                fingerprints = record.get("current_price_row_fingerprint_sha256_by_symbol")
                if (
                    not isinstance(fingerprints, Mapping)
                    or str(fingerprints.get(code, "")).lower() != requested_fingerprint.lower()
                    or not record.get("cycle_id")
                ):
                    continue
                pinned_rows_path = record.get("current_price_rows_source_path")
                pinned_rows_sha = record.get("current_price_rows_source_sha256")
                if not isinstance(pinned_rows_path, str) or not isinstance(pinned_rows_sha, str):
                    continue
                try:
                    resolved_rows_path = resolve_ml_research_output_path(
                        Path(pinned_rows_path), repository_root=self.repository_root
                    )
                    pinned_rows = _read_stable_bytes(
                        resolved_rows_path,
                        role="pinned current price-row projection observations",
                        max_bytes=64 * 1024 * 1024,
                    )
                except CurrentRestatedMLRegistryError:
                    continue
                if sha256(pinned_rows).hexdigest() != _sha256_text(
                    pinned_rows_sha, field_name="pinned price-row projection SHA"
                ):
                    continue
            source_identity = record.get("context_identity")
            if not isinstance(source_identity, Mapping):
                raise CurrentRestatedMLRegistryError("ML registry source identity is missing")
            if requested_mode == "selected_saved_decision" and any(
                str(source_identity.get(key, "") or "").strip() != value
                for key, value in selected.items()
                if key in _CONTEXT_IDENTITY_FIELDS and value
            ):
                continue
            event_date = _iso_date(record.get("event_date"), field_name="registry event date")
            if event_date > cutoff:
                continue
            inference_at = _aware_datetime(record.get("inference_at"), field_name="registry inference time")
            available_at = _aware_datetime(record.get("available_at"), field_name="registry generated/available time")
            model_available_at = _aware_datetime(record.get("model_available_at"), field_name="registry model available time")
            generated_at = _aware_datetime(record.get("generated_at"), field_name="registry generated time")
            if (
                not (model_available_at <= inference_at <= available_at == generated_at <= now)
                or generated_at > now
                or inference_at.astimezone(_TAIPEI).date() > cutoff
                or generated_at.astimezone(_TAIPEI).date() > cutoff
            ):
                continue
            prediction_rows = record.get("rows_by_symbol")
            if not isinstance(prediction_rows, Mapping) or not isinstance(prediction_rows.get(code), Mapping):
                raise CurrentRestatedMLRegistryError("registry run lacks exact symbol row")
            row = prediction_rows[code]
            target_metric = str(row.get("target_metric", ""))
            predicted_values = row.get("predicted_benchmark_excess_return_bp")
            manifest_path = resolve_ml_research_output_path(
                Path(str(record.get("model_manifest_path", ""))),
                repository_root=self.repository_root,
            )
            manifest_payload, manifest_bytes = _read_json_object(
                manifest_path,
                role="pinned model manifest",
                max_bytes=_MAX_JSON_BYTES,
            )
            if sha256(manifest_bytes).hexdigest() != record.get("model_manifest_sha256"):
                continue
            bundle_meta = manifest_payload.get("model_bundle")
            model_keys = bundle_meta.get("model_keys") if isinstance(bundle_meta, Mapping) else None
            bundle_name = str(bundle_meta.get("filename", "")).strip() if isinstance(bundle_meta, Mapping) else ""
            if not bundle_name or Path(bundle_name).name != bundle_name:
                continue
            try:
                bundle_bytes = _read_stable_bytes(
                    manifest_path.parent / bundle_name,
                    role="pinned current-restated model bundle",
                    max_bytes=512 * 1024 * 1024,
                )
            except CurrentRestatedMLRegistryError:
                continue
            if (
                target_metric != _TARGET_METRIC
                or not isinstance(predicted_values, Mapping)
                or not isinstance(model_keys, list)
                or set(predicted_values) != set(model_keys)
                or sha256(bundle_bytes).hexdigest() != record.get("model_bundle_sha256")
            ):
                continue
            h5 = row.get("h5")
            if not isinstance(h5, Mapping):
                raise CurrentRestatedMLRegistryError("registry H5 result is missing")
            h5_status = str(h5.get("status", ""))
            if h5_status == "mature_gross_label":
                horizon_end = _iso_date(h5.get("horizon_end_date"), field_name="H5 horizon end")
                if horizon_end > cutoff:
                    h5 = {
                        "status": "not_mature_as_of_cutoff",
                        "horizon": h5.get("horizon"),
                        "gross_stock_return_bp": None,
                        "gross_benchmark_return_bp": None,
                        "benchmark_excess_after_standard_80bp_cost": None,
                        "after_lane_cost_stock_return_bp": None,
                        "horizon_end_date": "",
                    }
                    h5_status = "not_mature_as_of_cutoff"
            candidate = {
                "stock_code": code,
                "status": "research_prediction_only",
                "scope_mode": requested_mode,
                "model_version": f"current-restated-core19:{record['model_manifest_sha256'][:16]}",
                "dataset_version": str(record["source_pins"].get("direct_manifest_sha256", "")),
                "inference_at": inference_at.isoformat(),
                "model_available_at": model_available_at.isoformat(),
                "available_at": generated_at.isoformat(),
                "research_or_formal": "research_only",
                "source_id": f"current_restated_ml_run:{run_id}",
                "run_id": run_id,
                "cycle_id": str(record.get("cycle_id", "")),
                "event_date": event_date.isoformat(),
                "model_manifest_sha256": record["model_manifest_sha256"],
                "model_bundle_sha256": record["model_bundle_sha256"],
                "source_snapshot_hash": record["source_context_sha256"],
                "current_price_row_fingerprint_sha256": str(
                    record.get("current_price_row_fingerprint_sha256_by_symbol", {}).get(code, "")
                ),
                "source_context_sha256": record["source_context_sha256"],
                "context_identity": dict(source_identity),
                "target_metric": target_metric,
                "predicted_benchmark_excess_return_bp": dict(predicted_values),
                "prediction_keys": tuple(model_keys),
                "input_quality_summary": dict(row["input_quality_summary"]),
                "core19_numeric_vector_sha256": row["core19_numeric_vector_sha256"],
                "h5": dict(h5),
                "h5_status": h5_status,
                "h5_horizon": h5.get("horizon"),
                "h5_gross_stock_return_bp": h5.get("gross_stock_return_bp"),
                "h5_gross_benchmark_return_bp": h5.get("gross_benchmark_return_bp"),
                "h5_benchmark_excess_after_standard_80bp_cost": h5.get("benchmark_excess_after_standard_80bp_cost"),
                "h5_after_lane_cost_stock_return_bp": h5.get("after_lane_cost_stock_return_bp"),
                "h5_horizon_end_date": h5.get("horizon_end_date", ""),
                "scope_symbols": tuple(symbols),
                "qualification": (
                    "僅供當下重述研究；不具歷史 PIT 資格。",
                    "未完成正式校準、推薦資格評定或生產操作授權。",
                    "範圍僅限本次執行紀錄內的股票群組，不可外推。",
                ),
                "research_only": True,
                "historical_pit_eligible": False,
                "formal_qualified": False,
                "production_action_allowed": False,
            }
            candidates.append((inference_at, run_id, candidate))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[-1][2]

    def _find_index_entry(self, run_id: str) -> Mapping[str, Any] | None:
        if not self.index_path.exists():
            return None
        payload = _read_stable_bytes(
            self.index_path, role="ML registry index", max_bytes=_MAX_INDEX_BYTES
        )
        for line in payload.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CurrentRestatedMLRegistryError("ML registry index contains malformed JSON") from exc
            if isinstance(value, Mapping) and value.get("run_id") == run_id:
                return value
        return None


@dataclass(frozen=True, slots=True)
class PortfolioExitReadModel:
    stock_code: str
    position_id: str
    portfolio_id: str
    status: str
    reasons: tuple[str, ...]
    source_id: str
    source_snapshot_hash: str
    data_as_of: str
    available_at: str
    research_only: bool = True
    auto_action_allowed: bool = False


class PortfolioExitReadProvider:
    """由既有 current Position Health 投影非執行 Exit 候選狀態。"""

    def __call__(
        self,
        stock_code: str,
        as_of_date: date,
        *,
        context: object | None = None,
        position: object | None = None,
        quote_snapshot: object | None = None,
        condition_result: object | None = None,
        health_result: object | None = None,
    ) -> PortfolioExitReadModel | None:
        del context
        if position is None or quote_snapshot is None or health_result is None:
            return None
        code = str(stock_code or "").strip()
        position_code = str(getattr(position, "stock_code", "") or "").strip()
        health_code = str(getattr(health_result, "stock_code", "") or "").strip()
        if not code or position_code != code or health_code != code:
            return None
        if condition_result is None:
            return None
        quote_hash = str(getattr(quote_snapshot, "source_snapshot_hash", "") or "").strip()
        quote_date_text = str(getattr(quote_snapshot, "data_date", "") or "").strip()
        try:
            quote_date = _iso_date(quote_date_text, field_name="report price data_date")
        except CurrentRestatedMLRegistryError:
            return None
        if quote_date > as_of_date or not _SHA256_RE.fullmatch(quote_hash):
            return None
        try:
            quote_stock_code = getattr(quote_snapshot, "stock_code")
        except AttributeError:
            quote_stock_code = None
            quote_has_stock_code = False
        else:
            quote_has_stock_code = True
        if quote_has_stock_code and str(quote_stock_code or "").strip() != code:
            return None
        try:
            expected_quote_hash = stock_price_row_fingerprint_sha256(
                stock_code=code,
                data_date=quote_date,
                open_price=getattr(quote_snapshot, "open_price", None),
                high_price=getattr(quote_snapshot, "high_price", None),
                low_price=getattr(quote_snapshot, "low_price", None),
                close_price=getattr(quote_snapshot, "close_price", None),
                volume=getattr(quote_snapshot, "volume", None),
                turnover=getattr(quote_snapshot, "turnover", None),
            )
        except (TypeError, ValueError):
            return None
        normalized_quote_hash = quote_hash.lower()
        if normalized_quote_hash.startswith("sha256:"):
            normalized_quote_hash = normalized_quote_hash[7:]
        if expected_quote_hash != normalized_quote_hash:
            return None
        position_id = str(getattr(position, "position_id", "") or "").strip()
        portfolio_id = str(getattr(position, "portfolio_id", "") or "").strip()
        if not position_id or not portfolio_id:
            return None
        state = getattr(health_result, "state", "")
        status = str(getattr(state, "value", state) or "").strip()
        if not status:
            return None
        reasons = tuple(
            str(item).strip()
            for item in getattr(health_result, "reasons", ())
            if str(item).strip()
        )
        return PortfolioExitReadModel(
            stock_code=code,
            position_id=position_id,
            portfolio_id=portfolio_id,
            status=status,
            reasons=reasons,
            source_id=str(getattr(quote_snapshot, "source_id", "") or "").strip(),
            source_snapshot_hash=quote_hash.lower(),
            data_as_of=quote_date.isoformat(),
            available_at=str(getattr(quote_snapshot, "available_at", "") or "").strip(),
        )


def publish_current_restated_stock_research_run(
    *,
    repository_root: Path | None = None,
    research_output_root: Path | None = None,
    sidecar_receipt_path: Path | str,
    expected_sidecar_receipt_sha256: str,
    model_manifest_path: Path | str,
    expected_model_manifest_sha256: str,
    expected_model_bundle_sha256: str,
    context_identity: Mapping[str, object] | None = None,
    scope_mode: str = "current_stock_research",
    cycle_id: str = "",
    current_price_row_fingerprint_sha256_by_symbol: Mapping[str, object] | None = None,
    current_price_rows_source_path: Path | str | None = None,
    expected_current_price_rows_source_sha256: str | None = None,
    now_provider: Callable[[], datetime] | None = None,
    model_loader: Callable[..., object] | None = None,
) -> PublishedCurrentRestatedMLRun:
    """以明示載入器發布既有 exact-hash current-restated sidecar。"""

    return CurrentRestatedMLRunRegistry(
        repository_root=repository_root,
        research_output_root=research_output_root,
        now_provider=now_provider,
        model_loader=model_loader,
    ).publish_sidecar(
        sidecar_receipt_path=sidecar_receipt_path,
        expected_sidecar_receipt_sha256=expected_sidecar_receipt_sha256,
        model_manifest_path=model_manifest_path,
        expected_model_manifest_sha256=expected_model_manifest_sha256,
        expected_model_bundle_sha256=expected_model_bundle_sha256,
        context_identity=context_identity,
        scope_mode=scope_mode,
        cycle_id=cycle_id,
        current_price_row_fingerprint_sha256_by_symbol=current_price_row_fingerprint_sha256_by_symbol,
        current_price_rows_source_path=current_price_rows_source_path,
        expected_current_price_rows_source_sha256=expected_current_price_rows_source_sha256,
    )


__all__ = [
    "CurrentRestatedMLRegistryError",
    "CurrentRestatedMLRunRegistry",
    "PortfolioExitReadModel",
    "PortfolioExitReadProvider",
    "PublishedCurrentRestatedMLRun",
    "publish_current_restated_stock_research_run",
    "stock_price_row_fingerprint_sha256",
]
