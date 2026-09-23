"""歷史日價格來源修訂的 fail-closed guard。

修復工具在變更 SQLite 前寫入 pending marker，交易完成後再寫入 final
receipt。PIT/export 與唯讀歷史 snapshot 會從資料庫資料根目錄自動尋找
sidecar，caller 省略選配 CSV 參數也不能繞過 hold。本模組只讀 JSON metadata，
不開啟資料庫，也不載入模型 artifact。
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


REPAIR_SCHEMA = "historical-price-spike-repair-20260921.v1"
REPAIR_RECEIPT_RELATIVE_DIR = Path(
    "output",
    "scheduled",
    "daily_price_repair_receipts",
    "20260520",
    "historical_price_spike_20260921",
)

# 先前訓練的 derived h5 release 之事故專用 immutable identity。release 仍保留
# 作為證據與重現用途，但來源包含 2026-05-20 修訂前的 daily_prices.ohlc；
# loader 必須標示 stale，並在 artifact 反序列化前停止。
KNOWN_MODEL_SOURCE_REVISION_QUARANTINES: dict[str, dict[str, str]] = {
    "sha256:aa152ebb8e8d7913a6a2274a0526620d8b8ce151a5f667d8de446df9724c895c": {
        "source_date": "2026-05-20",
        "identity": "repo:v4_ml_derived_h5_20260907_real_v2/release_manifest.json",
        "release_manifest_hash": "sha256:c306c1ea53ccef112204a8412a605b575e4d107b4503b2b5be5d6d5ee50910ea",
        "status": "stale_source_revision",
    },
    "sha256:92668aa574967990fa560aef8a48e595296eb22f3fef2a4264cff08210d78b6d": {
        "source_date": "2026-05-20",
        "identity": "FA_Data/output/release_v4/ml_allocation_bounded_v4_operational/training_manifest_v2.json",
        "status": "stale_source_revision",
    },
}


class DailyPriceSourceRevisionError(ValueError):
    """來源修訂命中 PIT cutoff，舊資料流程必須停止。"""


def assert_model_artifact_source_revision_safe(artifact_hash: str) -> None:
    """在 wrapper 反序列化前拒絕已知的修復前 artifact。"""

    quarantine = KNOWN_MODEL_SOURCE_REVISION_QUARANTINES.get(str(artifact_hash))
    if quarantine is None:
        return
    raise DailyPriceSourceRevisionError(
        "model artifact is quarantined by a daily-price source revision; "
        f"artifact_hash={artifact_hash} source_date={quarantine['source_date']} "
        f"status={quarantine['status']} identity={quarantine['identity']} "
        f"{('release_manifest_hash=' + quarantine['release_manifest_hash'] + ' ') if quarantine.get('release_manifest_hash') else ''}"
        "rebuild and revalidate the model"
    )


def source_revision_receipt_candidates(
    *, database_path: Path,
    explicit_path: Path | None = None,
) -> tuple[Path, ...]:
    """找出既有 repair sidecar。

    ``database_path`` 通常位於 ``<data-root>/sqlite``；測試與隔離資料庫則
    可直接位於資料根目錄。正式路徑不需要 caller 另傳旗標，pending 與 final
    都會被檢查。
    """

    database_root = database_path.resolve().parent
    if database_root.name.casefold() == "sqlite":
        database_root = database_root.parent
    receipt_dir = database_root / REPAIR_RECEIPT_RELATIVE_DIR
    automatic = tuple(
        path
        for path in (receipt_dir / "pending.json", receipt_dir / "receipt.json")
        if path.is_file()
    )
    if explicit_path is None:
        return automatic
    explicit = explicit_path.resolve()
    explicit_paths = (
        (explicit / "pending.json", explicit / "receipt.json")
        if explicit.is_dir()
        else (explicit,)
    )
    existing_explicit = (
        tuple(path for path in explicit_paths if path.is_file())
        if explicit.is_dir()
        else explicit_paths
    )
    return tuple(dict.fromkeys((*automatic, *existing_explicit)))


def check_daily_price_source_revision(
    *,
    database_path: Path,
    decision_date: date | datetime | str,
    symbols: Iterable[str] | None = None,
    explicit_path: Path | None = None,
) -> dict[str, Any] | None:
    """以決策 cutoff 檢查所有找到的 receipt。

    修復日是來源修訂日，不是新的歷史 ``available_at``。因此即使
    ``history_start_date`` 較晚，決策日到達修訂日仍會阻擋：rolling feature
    與較早 horizon label 可能依賴修正列。pending marker 代表 SQLite 交易
    可能已 commit 但 final receipt 尚未寫入，故視為 all-symbol hold。
    """

    cutoff = _as_date(decision_date)
    from data_module.formal_market_revision import assert_market_revision_safe
    from data_module.historical_session_revision import assert_session_revision_safe

    try:
        assert_market_revision_safe(database_path, cutoff)
        assert_session_revision_safe(database_path, cutoff)
    except ValueError as exc:
        raise DailyPriceSourceRevisionError(str(exc)) from exc
    normalized_symbols = (
        None
        if symbols is None
        else frozenset(str(symbol).strip() for symbol in symbols if str(symbol).strip())
    )
    if normalized_symbols is not None and not normalized_symbols:
        raise ValueError("symbols must not be empty when supplied")

    receipts = source_revision_receipt_candidates(
        database_path=database_path,
        explicit_path=explicit_path,
    )
    if not receipts:
        return None

    summaries = [
        _check_receipt(
            path=path,
            decision=cutoff,
            symbols=normalized_symbols,
        )
        for path in receipts
    ]
    return {
        "schema_version": REPAIR_SCHEMA,
        "checked_receipt_count": len(summaries),
        "checked_receipts": summaries,
        "relevant_row_count": sum(
            int(summary["relevant_row_count"]) for summary in summaries
        ),
        "policy": "fail_closed_until_repaired_source_rebuild",
    }


def _check_receipt(
    *,
    path: Path,
    decision: date,
    symbols: frozenset[str] | None,
) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file() or path.is_symlink():
        raise DailyPriceSourceRevisionError(
            f"source revision receipt is missing: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"source revision receipt is unreadable: {path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise DailyPriceSourceRevisionError(
            f"source revision receipt must be a JSON object: {path}"
        )
    if payload.get("schema_version") != REPAIR_SCHEMA:
        raise DailyPriceSourceRevisionError(
            "source revision receipt schema is unsupported; expected "
            f"{REPAIR_SCHEMA}: {path}"
        )
    receipt_kind = payload.get("receipt_kind")
    if receipt_kind not in {
        "historical_price_spike_repair_pending",
        "historical_price_spike_repair",
    }:
        raise DailyPriceSourceRevisionError(
            "historical price repair receipt kind is unsupported: "
            f"{path}"
        )

    source_date = _required_date(payload.get("source_date"), "source_date", path)
    raw_rows = payload.get("rows")
    if raw_rows is not None and not isinstance(raw_rows, list):
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt rows must be a list: {path}"
        )

    rows: list[tuple[date, str]] = []
    if isinstance(raw_rows, list):
        for index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, Mapping):
                raise DailyPriceSourceRevisionError(
                    f"historical price repair receipt row {index} is invalid: {path}"
                )
            symbol = _row_symbol(raw_row)
            if not symbol:
                raise DailyPriceSourceRevisionError(
                    f"historical price repair receipt row {index} requires symbol: {path}"
                )
            row_date = _required_date(
                raw_row.get("date", raw_row.get("source_date", source_date.isoformat())),
                f"row {index} date",
                path,
            )
            if row_date != source_date:
                raise DailyPriceSourceRevisionError(
                    f"historical price repair receipt row {index} is outside source_date: {path}"
                )
            rows.append((row_date, symbol))

    try:
        allowlist_count = int(payload.get("allowlist_count", len(rows)))
    except (TypeError, ValueError) as exc:
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt allowlist_count is invalid: {path}"
        ) from exc
    if allowlist_count <= 0:
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt allowlist_count must be positive: {path}"
        )
    if rows and allowlist_count != len(rows):
        raise DailyPriceSourceRevisionError(
            "historical price repair receipt allowlist_count does not match rows: "
            f"{path}"
        )

    # Pending sidecar 刻意省略完整 rows；空的 final affected list 也保守處理，
    # 避免空 ``affected_rows`` 靜默繞過修訂 hold。
    all_symbols = not rows
    affected_rows = rows or [(source_date, "<all-symbols>")]
    relevant_rows = [
        (row_date, symbol)
        for row_date, symbol in affected_rows
        if row_date <= decision
        and (symbols is None or all_symbols or symbol in symbols)
    ]
    known_at = next(
        (
            str(payload[key])
            for key in ("corrected_at", "created_at", "official_capture_at")
            if isinstance(payload.get(key), str) and payload.get(key)
        ),
        None,
    )
    summary: dict[str, Any] = {
        "schema_version": REPAIR_SCHEMA,
        "receipt_path": str(path),
        "receipt_hash": _file_sha256(path),
        "receipt_kind": str(payload.get("receipt_kind", "")),
        "status": str(payload.get("status", "")),
        "source_date": source_date.isoformat(),
        "known_at": known_at,
        "known_after_decision": None,
        "affected_row_count": allowlist_count,
        "scope_mode": "all_symbols_conservative" if all_symbols else "row_exact",
        "relevant_row_count": len(relevant_rows),
        "relevant_dates": sorted({row_date.isoformat() for row_date, _ in relevant_rows}),
        "relevant_symbols": (
            ["<all-requested-symbols>"]
            if all_symbols and relevant_rows
            else sorted({symbol for _, symbol in relevant_rows})
        ),
        "policy": "fail_closed_until_repaired_source_rebuild",
    }
    if relevant_rows:
        raise DailyPriceSourceRevisionError(
            "historical price repair receipt blocks this PIT prefix; "
            f"source_date={source_date.isoformat()} decision={decision.isoformat()} "
            f"status={payload.get('status', '')!s} path={path}; "
            "rebuild features/labels with a revision-aware research or formal process"
        )
    return summary


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) >= 8 and text[:8].isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text[:10])


def _required_date(value: object, label: str, path: Path) -> date:
    if value is None or not str(value).strip() or str(value).strip().casefold() == "none":
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt requires {label}: {path}"
        )
    try:
        return _as_date(str(value))
    except (TypeError, ValueError) as exc:
        raise DailyPriceSourceRevisionError(
            f"historical price repair receipt {label} is invalid: {path}"
        ) from exc


def _row_symbol(row: Mapping[str, Any]) -> str:
    value = row.get("symbol") or row.get("stock_code") or row.get("證券代號")
    symbol = "" if value is None else str(value).strip()
    if symbol.endswith(".0") and symbol[:-2].isdigit():
        symbol = symbol[:-2]
    return symbol.zfill(4) if symbol.isdigit() else symbol


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
