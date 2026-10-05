"""已核驗原生股票排名的呈現與讀回驗證輔助函式。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app_module.original_stock_ranking import VerifiedOriginalStockRanking


_PERIOD_LABELS = {"day": "日比較", "week": "週比較"}
_DIRECTION_LABELS = {"strong": "強勢", "weak": "弱勢"}


def ranking_matches_snapshot(
    snapshot: object,
    ranking: object,
    *,
    period: str,
    direction: str,
) -> bool:
    """僅當已核驗讀回綁定此 snapshot 與選取模式時回傳 True。"""

    if not isinstance(ranking, VerifiedOriginalStockRanking):
        return False
    manifest = getattr(snapshot, "manifest", None)
    if not isinstance(manifest, Mapping):
        return False
    metadata = getattr(ranking, "metadata", None)
    if not isinstance(metadata, Mapping):
        return False
    decision_date = str(manifest.get("decision_date") or "")
    parent_manifest_sha256 = str(metadata.get("parent_manifest_sha256") or "")
    parent_manifest_identity = str(
        metadata.get("parent_manifest_identity_sha256") or ""
    )
    return (
        period in _PERIOD_LABELS
        and direction in _DIRECTION_LABELS
        and getattr(ranking, "readiness", None) == "research_only"
        and getattr(ranking, "period", None) == period
        and getattr(ranking, "direction", None) == direction
        and getattr(ranking, "decision_date", None) == decision_date
        and parent_manifest_sha256 == getattr(snapshot, "manifest_sha256", None)
        and parent_manifest_identity
        == getattr(snapshot, "manifest_identity_sha256", None)
        and len(parent_manifest_sha256) == 64
        and len(parent_manifest_identity) == 64
    )


def ranking_rows_by_code(
    ranking: object,
) -> dict[str, Mapping[str, Any]] | None:
    """核對原生排名列並依股票代碼索引；格式錯誤或重複名次時拒絕使用。"""

    if not isinstance(ranking, VerifiedOriginalStockRanking):
        return None
    raw_rows = getattr(ranking, "rows", None)
    if isinstance(raw_rows, (str, bytes)) or not isinstance(raw_rows, Sequence):
        return None
    declared = getattr(ranking, "declared_stock_codes", None)
    if isinstance(declared, (str, bytes)) or not isinstance(declared, Sequence):
        return None
    declared_codes = {str(code).strip() for code in declared}
    if not declared_codes or "" in declared_codes or len(declared_codes) != len(declared):
        return None
    metadata = getattr(ranking, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    eligible_codes = metadata.get("eligible_stock_codes")
    eligible_size = getattr(ranking, "eligible_universe_size", None)
    if (
        isinstance(eligible_codes, (str, bytes))
        or not isinstance(eligible_codes, Sequence)
        or type(eligible_size) is not int
        or eligible_size < 0
    ):
        return None
    eligible_code_set = {str(code).strip() for code in eligible_codes}
    if (
        "" in eligible_code_set
        or len(eligible_code_set) != len(eligible_codes)
        or eligible_size != len(eligible_code_set)
        or not eligible_code_set.issubset(declared_codes)
    ):
        return None
    rows: dict[str, Mapping[str, Any]] = {}
    ranks: set[int] = set()
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            return None
        code = str(raw_row.get("stock_code") or "").strip()
        rank = raw_row.get("rank")
        score_label = str(raw_row.get("score_label") or "").strip()
        if (
            not code
            or code not in declared_codes
            or code in rows
            or type(rank) is not int
            or rank <= 0
            or rank in ranks
            or not score_label.startswith(("Top", "Bottom"))
        ):
            return None
        rows[code] = raw_row
        ranks.add(rank)
    if set(rows) != eligible_code_set:
        return None
    return rows


def original_rank_cell(ranking: object, stock_code: str) -> str:
    rows = ranking_rows_by_code(ranking)
    row = rows.get(str(stock_code).strip()) if rows is not None else None
    if row is None:
        return "未知"
    return f"{row['rank']} · {row['score_label']}"


def sort_by_original_rank(
    items: Sequence[object],
    ranking: object,
    *,
    stock_code: Callable[[object], str],
) -> tuple[object, ...] | None:
    """依原生名次遞增排序，缺少名次的股票維持未知並置於末端。"""

    rows = ranking_rows_by_code(ranking)
    if rows is None:
        return None
    values = tuple(items)
    codes = tuple(str(stock_code(item) or "").strip() for item in values)
    if any(not code for code in codes) or len(set(codes)) != len(codes):
        return None
    known = [
        (rows[code]["rank"], code, item)
        for code, item in zip(codes, values)
        if code in rows
    ]
    unknown = [
        (code, item)
        for code, item in zip(codes, values)
        if code not in rows
    ]
    known.sort(key=lambda entry: (entry[0], entry[1]))
    unknown.sort(key=lambda entry: entry[0])
    return tuple(item for _rank, _code, item in known) + tuple(
        item for _code, item in unknown
    )


def ranking_window_text(row: Mapping[str, Any]) -> str:
    comparison_date = str(row.get("comparison_date") or "").strip()
    latest_date = str(row.get("latest_date") or "").strip()
    if comparison_date and latest_date:
        return f"{comparison_date} → {latest_date}"
    if latest_date:
        return f"最新資料日 {latest_date}"
    return "比較區間未知"


def ranking_summary_text(ranking: object) -> str:
    if not isinstance(ranking, VerifiedOriginalStockRanking):
        return "原始排名：未知；尚無可核驗來源"
    rows = ranking_rows_by_code(ranking)
    if rows is None:
        return "原始排名：未知；排名列格式無效"
    metadata = getattr(ranking, "metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    full_run_id = str(metadata.get("run_id") or "來源 ID 未知")
    run_id = full_run_id[:12] + ("…" if len(full_run_id) > 12 else "")
    windows = {
        ranking_window_text(row)
        for row in rows.values()
    }
    window_text = (
        next(iter(windows))
        if len(windows) == 1
        else "各股原生比較窗，詳見排名列"
    )
    period = _PERIOD_LABELS.get(str(ranking.period), str(ranking.period))
    direction = _DIRECTION_LABELS.get(str(ranking.direction), str(ranking.direction))
    return (
        f"原生{period}{direction}排名 · {window_text} · {run_id} · "
        f"研究用途（舊引擎原生標籤；不可解讀為一般前幾％或勝率）"
    )


def ranking_audit_tooltip(ranking: object) -> str:
    if not isinstance(ranking, VerifiedOriginalStockRanking):
        return "原始排名來源未核驗；名次維持未知。"
    metadata = getattr(ranking, "metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    fields = (
        "run_id",
        "engine_method",
        "engine_version",
        "engine_parameters",
        "engine",
        "research_universe_id",
        "research_universe_version",
        "research_universe_source_sha256",
        "research_universe_identity",
        "source_db_path",
        "source_schema_sha256",
        "engine_file_sha256",
        "volume_window_size",
        "qualification",
        "comparison_rules",
        "captured_stock_codes",
        "eligible_stock_codes",
        "missing_rank_stock_codes",
        "missing_rank_reason",
    )
    details = [
        f"排名期間={ranking.period}; 方向={ranking.direction}; "
        f"決策日={ranking.decision_date}; readiness={ranking.readiness}",
        f"manifest_sha256={ranking.manifest_sha256}",
        f"manifest_identity_sha256={ranking.manifest_identity_sha256}",
        f"parent_manifest_sha256={metadata.get('parent_manifest_sha256')}",
        "parent_manifest_identity_sha256="
        f"{metadata.get('parent_manifest_identity_sha256')}",
    ]
    details.extend(
        f"{key}={metadata[key]}" for key in fields if key in metadata
    )
    details.extend(
        (
            f"eligible_universe_size={ranking.eligible_universe_size}",
            f"declared_stock_codes={ranking.declared_stock_codes}",
            f"missing_rank_stock_codes={ranking.missing_rank_stock_codes}",
            "score_label 原樣保留舊引擎標籤；排序依原生 rank。",
            "Top／Bottom 百分比不可解讀為一般百分位或勝率。",
            "舊引擎以 score_label 覆寫數值分數，因此不顯示原始數值分數。",
        )
    )
    return "\n".join(details)


def original_rank_row_tooltip(ranking: object, row: Mapping[str, Any] | None) -> str:
    if row is None:
        return ranking_audit_tooltip(ranking) + "\n此股票未提供原始名次；不重新排名。"
    return (
        ranking_audit_tooltip(ranking)
        + f"\n股票代碼={row.get('stock_code')}"
        + f"\n原生名次={row.get('rank')}"
        + f"\nscore_label={row.get('score_label')}"
        + f"\n原生比較窗={ranking_window_text(row)}"
        + f"\n價格變動百分比={row.get('price_change_percent')}"
        + f"\n成交量變動百分比={row.get('volume_change_percent')}"
    )
