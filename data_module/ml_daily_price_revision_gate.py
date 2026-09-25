"""歷史日價格來源修訂的 fail-closed guard。

修復工具在變更 SQLite 前寫入 pending marker，交易完成後再寫入 final
receipt。PIT/export 與唯讀歷史 snapshot 會從資料庫資料根目錄自動尋找
sidecar，caller 省略選配 CSV 參數也不能繞過 hold。本模組只讀 JSON metadata，
不開啟資料庫，也不載入模型 artifact。
"""

from __future__ import annotations

import base64
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Iterable, Mapping

from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
)


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

    candidates, _, _, _ = _receipt_candidates_with_policy(
        database_path=database_path,
        explicit_path=explicit_path,
    )
    return candidates


def _receipt_candidates_with_policy(
    *,
    database_path: Path,
    explicit_path: Path | None,
    strict_explicit_slots: bool = False,
) -> tuple[tuple[Path, ...], frozenset[Path], Path, Mapping[Path, Path]]:
    database_root = database_path.resolve().parent
    if database_root.name.casefold() == "sqlite":
        database_root = database_root.parent
    database_root = database_root.resolve()
    automatic_pairs = _automatic_receipt_candidates(database_root)
    automatic = tuple(dict.fromkeys(path for path, _ in automatic_pairs))
    automatic_set = frozenset(automatic)
    automatic_sources = {
        path: source_path for path, source_path in automatic_pairs
    }
    if explicit_path is None:
        return automatic, automatic_set, database_root, automatic_sources
    explicit = explicit_path.resolve()
    explicit_paths = (
        (explicit / "pending.json", explicit / "receipt.json")
        if explicit.is_dir()
        else (explicit,)
    )
    if explicit.is_dir() and strict_explicit_slots:
        existing_explicit = tuple(
            resolved
            for path in explicit_paths
            if (resolved := _resolve_explicit_receipt_slot(path)) is not None
        )
    elif explicit.is_dir():
        # 舊 public gate 保留原有的 is_file() 篩選與 None 行為。
        existing_explicit = tuple(path for path in explicit_paths if path.is_file())
    else:
        existing_explicit = explicit_paths
    return (
        tuple(dict.fromkeys((*automatic, *existing_explicit))),
        automatic_set,
        database_root,
        automatic_sources,
    )


def _resolve_explicit_receipt_slot(path: Path) -> Path | None:
    """在 typed collection 中區分真正缺席與不完整的 explicit slot。"""

    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is unreadable: {path}"
        ) from exc

    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is unresolved: {path}"
        ) from exc
    try:
        file_info = resolved.lstat()
    except OSError as exc:
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is unreadable: {resolved}"
        ) from exc
    if not stat.S_ISREG(file_info.st_mode):
        raise DailyPriceSourceRevisionError(
            f"explicit receipt slot is not a regular file: {resolved}"
        )
    return resolved


def _automatic_receipt_candidates(database_root: Path) -> tuple[tuple[Path, Path], ...]:
    """逐段驗證固定自動搜尋路徑，只有普通缺席可代表無候選。"""

    try:
        root_info = database_root.lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt root is unreadable: {database_root}"
        ) from exc
    if not stat.S_ISDIR(root_info.st_mode):
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt root is not a directory: {database_root}"
        )

    current = database_root
    lexical_current = database_root
    for component in REPAIR_RECEIPT_RELATIVE_DIR.parts:
        lexical_current = lexical_current / component
        try:
            lexical_current.lstat()
        except FileNotFoundError:
            return ()
        except OSError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt path is unreadable: {lexical_current}"
            ) from exc
        current = _resolve_automatic_receipt_path(
            lexical_current,
            database_root=database_root,
            require_file=False,
        )
        if not current.is_dir():
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt path is not a directory: {current}"
            )

    candidates: list[tuple[Path, Path]] = []
    for filename in ("pending.json", "receipt.json"):
        child = lexical_current / filename
        try:
            child.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is unreadable: {child}"
            ) from exc
        candidates.append((
            _resolve_automatic_receipt_path(
                child,
                database_root=database_root,
                require_file=True,
            ),
            child,
        ))
    return tuple(dict.fromkeys(candidates))


def _resolve_automatic_receipt_path(
    path: Path,
    *,
    database_root: Path,
    require_file: bool,
) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt path is unresolved: {path}"
        ) from exc
    try:
        resolved.relative_to(database_root)
    except ValueError as exc:
        raise DailyPriceSourceRevisionError(
            f"automatic source revision receipt path is outside data root: {path}"
        ) from exc
    if require_file:
        try:
            file_info = resolved.lstat()
        except OSError as exc:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is unreadable: {resolved}"
            ) from exc
        if not stat.S_ISREG(file_info.st_mode):
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt is not a regular file: {resolved}"
            )
    return resolved


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
    from data_module.excluded_daily_price_revision import assert_excluded_source_revision_safe

    try:
        assert_market_revision_safe(database_path, cutoff)
        assert_session_revision_safe(database_path, cutoff)
        assert_excluded_source_revision_safe(database_path, cutoff)
    except ValueError as exc:
        raise DailyPriceSourceRevisionError(str(exc)) from exc
    normalized_symbols = (
        None
        if symbols is None
        else frozenset(str(symbol).strip() for symbol in symbols if str(symbol).strip())
    )
    if normalized_symbols is not None and not normalized_symbols:
        raise ValueError("symbols must not be empty when supplied")

    summary, _evidence_files = _inspect_daily_price_repair_receipts_once(
        database_path=database_path,
        decision=cutoff,
        symbols=normalized_symbols,
        explicit_path=explicit_path,
        strict_explicit_slots=False,
    )
    return summary


def collect_daily_price_repair_receipt_evidence(
    *,
    database_path: Path,
    decision_date: date | datetime | str,
    symbols: Iterable[str] | None = None,
    explicit_path: Path | None = None,
) -> ValidatedNamespaceEvidenceV1:
    """收集 direct daily-price receipt namespace 的同次 bytes 證據。

    此入口只負責 direct receipt namespace；同層的 market、session、excluded
    namespace 仍由其各自 collector 檢查。既有 public guard 仍保留那些 guard
    的呼叫順序與 ``dict | None`` 回傳 ABI。
    """

    cutoff = _as_date(decision_date)
    normalized_symbols = _normalized_receipt_symbols(symbols)
    _, evidence_files = _inspect_daily_price_repair_receipts_once(
        database_path=database_path,
        decision=cutoff,
        symbols=normalized_symbols,
        explicit_path=explicit_path,
        strict_explicit_slots=True,
    )
    presence = (
        SourceEvidencePresenceV1.PRESENT
        if evidence_files
        else SourceEvidencePresenceV1.EMPTY
    )
    return ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.DAILY_PRICE_REPAIR_RECEIPT,
        presence=presence,
        files=evidence_files,
    )


def _normalized_receipt_symbols(
    symbols: Iterable[str] | None,
) -> frozenset[str] | None:
    normalized = (
        None
        if symbols is None
        else frozenset(str(symbol).strip() for symbol in symbols if str(symbol).strip())
    )
    if normalized is not None and not normalized:
        raise ValueError("symbols must not be empty when supplied")
    return normalized


def _inspect_daily_price_repair_receipts_once(
    *,
    database_path: Path,
    decision: date,
    symbols: frozenset[str] | None,
    explicit_path: Path | None,
    strict_explicit_slots: bool,
) -> tuple[dict[str, Any] | None, tuple[ValidatedEvidenceFileV1, ...]]:
    """掃描候選一次，並以每份 receipt 的同次 bytes 同時產生摘要與證據。"""

    (
        receipts,
        automatic_receipts,
        database_root,
        automatic_sources,
    ) = _receipt_candidates_with_policy(
        database_path=database_path,
        explicit_path=explicit_path,
        strict_explicit_slots=strict_explicit_slots,
    )
    if not receipts:
        return None, ()

    summaries: list[dict[str, Any]] = []
    evidence_files: list[ValidatedEvidenceFileV1] = []
    for path in receipts:
        summary, receipt_sha256 = _check_receipt_with_evidence(
            path=path,
            decision=decision,
            symbols=symbols,
            containment_root=(database_root if path in automatic_receipts else None),
            automatic_source_path=automatic_sources.get(path),
        )
        summaries.append(summary)
        resolved_path = Path(str(summary["receipt_path"]))
        if path in automatic_receipts:
            try:
                relative_path = resolved_path.relative_to(database_root).as_posix()
            except ValueError as exc:
                raise DailyPriceSourceRevisionError(
                    f"automatic source revision receipt is outside data root: {resolved_path}"
                ) from exc
            role_token = base64.urlsafe_b64encode(
                relative_path.encode("utf-8")
            ).decode("ascii").rstrip("=")
            role_id = f"automatic/{role_token}"
        else:
            path_identity = resolved_path.as_posix().encode("utf-8")
            role_id = "explicit/" + hashlib.sha256(path_identity).hexdigest()
        evidence_files.append(
            ValidatedEvidenceFileV1(
                role_id=role_id,
                sha256=receipt_sha256,
            )
        )

    summary_result = {
        "schema_version": REPAIR_SCHEMA,
        "checked_receipt_count": len(summaries),
        "checked_receipts": summaries,
        "relevant_row_count": sum(
            int(summary["relevant_row_count"]) for summary in summaries
        ),
        "policy": "fail_closed_until_repaired_source_rebuild",
    }
    return summary_result, tuple(evidence_files)


def _check_receipt(
    *,
    path: Path,
    decision: date,
    symbols: frozenset[str] | None,
    containment_root: Path | None = None,
    automatic_source_path: Path | None = None,
) -> dict[str, Any]:
    summary, _receipt_sha256 = _check_receipt_with_evidence(
        path=path,
        decision=decision,
        symbols=symbols,
        containment_root=containment_root,
        automatic_source_path=automatic_source_path,
    )
    return summary


def _check_receipt_with_evidence(
    *,
    path: Path,
    decision: date,
    symbols: frozenset[str] | None,
    containment_root: Path | None = None,
    automatic_source_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    if containment_root is None:
        path = path.resolve()
    else:
        source_path = automatic_source_path or path
        expected_path = path
        path = _resolve_automatic_receipt_path(
            source_path,
            database_root=containment_root,
            require_file=True,
        )
        if path != expected_path:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt changed before read: {expected_path}"
            )
    if not path.is_file() or (containment_root is None and path.is_symlink()):
        raise DailyPriceSourceRevisionError(
            f"source revision receipt is missing: {path}"
        )
    try:
        receipt_bytes = path.read_bytes()
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyPriceSourceRevisionError(
            f"source revision receipt is unreadable: {path}"
        ) from exc
    if containment_root is not None:
        current_path = _resolve_automatic_receipt_path(
            automatic_source_path or path,
            database_root=containment_root,
            require_file=True,
        )
        if current_path != path:
            raise DailyPriceSourceRevisionError(
                f"automatic source revision receipt changed during read: {path}"
            )
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    receipt_hash = f"sha256:{receipt_sha256}"
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
        "receipt_hash": receipt_hash,
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
    return summary, receipt_sha256


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
