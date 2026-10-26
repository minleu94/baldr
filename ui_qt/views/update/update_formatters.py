"""UpdateView 的純格式化與顯示文字函式。"""

from typing import Any, Mapping

from app_module.program_readiness_projection import PROGRAM_READINESS_LANE_ORDER


def format_machine_status_classification(classification: Any) -> str:
    """Render the handling class without implying human approval or gate credit."""

    raw = str(classification or "unknown").strip().lower()
    mapping = {
        "source_missing": "來源缺件（機器狀態，不需人工簽核）",
        "waiting_for_time": "等待自然時間（機器狀態）",
        "invalid_evidence": "證據無效（機器拒絕）",
        "human_review": "需要實質人工判讀",
        "machine_candidate": "機器候選（尚未正式驗證）",
        "machine_verified": "機器 consumer 已驗證",
        "machine_degraded": "機器觀測降級",
        "stale": "最後可信資料（stale，需重新載入）",
        "unknown": "狀態未知（尚無可信讀取）",
    }
    return mapping.get(raw, f"未分類機器狀態（{raw or 'unknown'}）")


def _safe_nonnegative_int(value: Any) -> int:
    """把 malformed 計數 fail-closed 成 0，避免狀態頁因顯示而中止。"""

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def format_status_token(status: Any) -> str:
    raw_status = str(status or "").strip()
    normalized = raw_status.lower()
    if normalized.startswith(("error", "failed", "failure", "exception")):
        return "異常"
    mapping = {
        "ok": "正常",
        "success": "正常",
        "current": "正常",
        "normal": "正常",
        "warning": "需注意",
        "degraded": "需注意",
        "partial": "部分完成",
        "passed": "正常",
        "completed": "正常",
        "passed_with_warnings": "需注意",
        "waiting_for_external_input": "等待外部輸入",
        "action_required": "需處理",
        "error": "異常",
        "missing": "缺漏",
        "empty": "缺漏",
        "unavailable": "不可用",
        "official_no_data": "官方無資料",
        "stale_fallback_observed": "取得較早日期資料（非查詢日）",
        "source_date_mismatch": "來源資料日期早於查詢日",
        "no_data": "官方無資料",
        "schema_blocked": "格式不符",
        "schema_mismatch": "格式不符",
        "network_failed": "網路失敗",
        "network_error": "網路失敗",
        "transport_error": "傳輸失敗",
        "date_mismatch": "日期不符",
        "registry_error": "登錄檔異常",
        "audit_unavailable": "稽核不可用",
        "blocked_provenance": "來源證據受阻",
        "blocked_insufficient_storage": "磁碟空間不足",
        "direct_chain_storage_preflight_blocked": "磁碟空間不足",
        "production_canary_storage_preflight_blocked": "正式 canary 磁碟空間不足",
        "research_shadow": "研究影子",
        "contract_only": "僅有契約",
        "candidate_only": "僅限候選",
        "candidate_evidence_only": "僅限候選證據",
        "source_missing": "來源缺件",
        "invalid_evidence": "證據無效",
        "machine_candidate": "機器候選",
        "machine_verified": "機器已驗證",
        "machine_degraded": "機器觀測降級",
        "governance_review": "待治理審核",
        "needs_named_owner_reviewer": "待具名 owner／reviewer",
        "ready_for_owner_review": "可交 owner 審核",
        "needs_input_evidence": "待補來源證據",
        "unknown_input_evidence": "來源證據未知",
        "input_evidence_invalid": "來源證據無效",
        "machine_verified": "機器 consumer 已驗證",
        "machine_verified_candidate": "機器候選證據",
        "pending_capacity_owner_review": "待容量 owner 審核",
        "pending_production_pool_review": "待 production pool 審核",
        "observed_staging_only": "僅觀測 staging",
        "not_supplied": "未提供",
        "not_observed": "未觀測",
        "not_available": "尚未觀測",
        "lagging": "待更新",
        "stale": "待更新",
        "summary": "已讀取摘要",
        "candidate_available": "候選可用",
        "formal_available": "正式可用",
        "ready": "已讀取",
        "ready_for_merge": "可併入候選",
        "already_merged": "已併入",
        "not_computable": "尚不可計算",
        "not_computable_cost_ledger_missing": "尚不可計算（成本帳缺漏）",
        "waiting_for_formal_inputs": "等待 Formal 輸入",
        "waiting_for_time": "等待真實時間",
        "pending_human_review": "待人工覆核",
        "manual_review_required": "待人工覆核",
        "blocked": "已阻擋",
        "merge_blocked": "合併受阻",
        "running": "執行中",
        "in_progress": "進行中",
        "skipped_non_trading_day": "休市略過",
        "preview": "預覽",
        "staging": "候選暫存",
        "not_configured": "尚未設定",
        "not_found": "找不到",
        "research_only": "僅限研究",
        "research_only_degraded": "研究受限",
        "no_data_skipped_dates": "官方無資料",
        "operational": "正常",
        "guarded": "受控",
        "attention": "需處理",
        "conflict": "有衝突",
        "invalid": "候選無效",
        "unknown": "未知",
        "正常": "正常",
        "待更新": "待更新",
        "未檢查": "未檢查",
    }
    return mapping.get(normalized, raw_status or "未知")


def format_p0_license_capture_status(status: Any) -> str:
    """Render a P0 license-capture token without hiding its machine value."""

    raw_status = str(status or "not_supplied").strip()
    normalized = raw_status.lower()
    labels = {
        "captured_candidate": "已取得候選指紋",
        "capture_partial": "部分取得，仍需複核",
        "preview_not_captured": "預覽未擷取",
        "capture_transport_error": "傳輸失敗",
        "capture_http_error": "HTTP 失敗",
        "capture_incomplete": "擷取未完成",
        "not_supplied": "未提供",
    }
    label = labels.get(normalized)
    if label is None:
        return raw_status or "未知"
    return f"{label}（{raw_status}）"


def format_p0_route_probe_statuses(value: Any) -> str:
    """Render bounded P0 route probe outcomes without implying acceptance."""

    if not isinstance(value, (list, tuple)) or not value:
        return "未提供"
    labels = {
        "observed": "已觀測",
        "failed": "失敗",
        "official_no_data": "官方無資料",
        "date_mismatch": "日期不符",
        "no_accepted_rows": "無通過列",
        "schema_mismatch": "格式不符",
        "not_usable": "不可用",
        "not_attempted": "未嘗試",
    }
    rendered: list[str] = []
    for raw in value[:8]:
        if not isinstance(raw, Mapping):
            continue
        route_id = str(raw.get("route_id") or "未提供").strip() or "未提供"
        status = str(raw.get("status") or "not_usable").strip().lower()
        status_text = labels.get(status, status)
        markers = []
        if raw.get("selected") is True:
            markers.append("已選")
        if raw.get("fallback") is True:
            markers.append("fallback")
        marker_text = f"（{'／'.join(markers)}）" if markers else ""
        rendered.append(f"{route_id}：{status_text}（{status}）{marker_text}")
    if not rendered:
        return "未提供"
    suffix = f"；另 {len(value) - len(rendered)} 條未顯示" if len(value) > len(rendered) else ""
    return "\n".join(rendered) + suffix


def format_manual_update_summary(
    operation: Any,
    status: Any,
    message: Any = "",
    *,
    start_date: Any = None,
    end_date: Any = None,
    updated_count: Any = None,
    failed_count: Any = None,
    failed_step: Any = None,
    warnings: Any = (),
    progress: Any = None,
) -> str:
    """Render the current UI update attempt without conflating it with scheduler state.

    Manual source updates and scheduled ``latest_status.json`` artifacts have
    different provenance.  Keeping this summary local to the current action
    prevents a failed/ cancelled manual run from leaving the previous
    successful scheduler timeline as the only visible explanation.
    """

    raw_status = str(status or "unknown").strip().lower() or "unknown"
    status_labels = {
        "success": "完成",
        "passed": "完成",
        "completed": "完成",
        "failed": "失敗",
        "failure": "失敗",
        "error": "錯誤",
        "running": "執行中",
        "in_progress": "執行中",
        "cancelled": "已取消",
    }
    status_label = status_labels.get(raw_status, format_status_token(raw_status))
    operation_text = str(operation or "資料更新").strip() or "資料更新"
    lines = [f"本次手動更新：{status_label}（{raw_status}）", f"操作：{operation_text}"]

    start_text = str(start_date or "").strip()
    end_text = str(end_date or "").strip()
    if start_text or end_text:
        lines.append(f"資料區間：{start_text or '未提供'} ~ {end_text or '未提供'}")

    try:
        progress_value = int(progress) if progress is not None else None
    except (TypeError, ValueError):
        progress_value = None
    if progress_value is not None:
        lines.append(f"目前進度：{max(0, min(100, progress_value))}%")

    message_text = str(message or "").strip()
    if message_text:
        lines.append(f"訊息：{message_text}")

    if updated_count is not None:
        lines.append(f"成功日期：{_safe_nonnegative_int(updated_count):,} 個")
    if failed_count is not None:
        lines.append(f"失敗日期：{_safe_nonnegative_int(failed_count):,} 個")
    failed_step_text = str(failed_step or "").strip()
    if failed_step_text:
        lines.append(f"失敗步驟：{failed_step_text}")

    if isinstance(warnings, (list, tuple, set)):
        warning_items = warnings
    elif warnings in (None, ""):
        warning_items = ()
    else:
        warning_items = (warnings,)
    warning_values = [
        str(item).strip() for item in warning_items if str(item).strip()
    ]
    if warning_values:
        lines.append("提醒：" + "；".join(warning_values[:3]))

    lines.append("排程時間軸仍只讀取明確 status artifact；兩者不互相回填。")
    return "\n".join(lines)


def format_program_readiness_summary(payload: Mapping[str, Any]) -> str:
    """Render the bounded, read-only program readiness projection."""

    raw_status = str(payload.get("status") or "unknown").strip().lower() or "unknown"
    lines = [
        f"整體狀態：{format_status_token(raw_status)}",
    ]
    workstreams = payload.get("workstreams")
    lane_values = (
        [value for value in workstreams.values() if isinstance(value, Mapping)]
        if isinstance(workstreams, Mapping)
        else []
    )
    lane_order = payload.get("lane_order")
    expected_lanes = (
        [
            str(item).strip()
            for item in lane_order
            if str(item).strip() in PROGRAM_READINESS_LANE_ORDER
        ]
        if isinstance(lane_order, list)
        else list(PROGRAM_READINESS_LANE_ORDER)
    )
    expected_lanes = list(dict.fromkeys(expected_lanes)) or list(
        PROGRAM_READINESS_LANE_ORDER
    )
    blocker_count = sum(
        len(value.get("blockers") or [])
        for value in lane_values
        if isinstance(value.get("blockers"), (list, tuple))
    )
    external_count = sum(
        value.get("external_input_required") is True for value in lane_values
    )
    lines.append(
        f"資料檢查區：{len(lane_values)}/{len(expected_lanes)} 個；"
        f"待處理原因：{blocker_count} 項；待外部資料／操作週期／人工審查：{external_count} 區"
    )

    generated_at = str(payload.get("generated_at") or "").strip()
    if generated_at:
        lines.append(f"產生時間：{generated_at}")
    path = str(payload.get("path") or "").strip()
    if path:
        lines.append(f"Artifact：{path}")

    boundary = payload.get("boundary")
    if isinstance(boundary, Mapping):
        lines.append(
            "安全邊界：唯讀；"
            f"允許資料寫入={bool(boundary.get('writes_allowed') is True)}；"
            f"允許下單={bool(boundary.get('broker_order_allowed') is True)}；"
            f"允許 Formal OOS={bool(boundary.get('formal_oos_allowed') is True)}；"
            f"允許正式排程={bool(boundary.get('production_scheduler_allowed') is True)}"
        )

    diagnostics = [str(item).strip() for item in payload.get("diagnostics", []) if str(item).strip()]
    if diagnostics:
        lines.append("診斷：" + "；".join(diagnostics[:3]))
    return "\n".join(lines)


_READINESS_BLOCKER_LABELS = {
    "decision_time_availability_not_proven": "決策時間可得性尚未證明",
    "fallback_observation_date_mismatch": "只取得較早日期資料；指定日期仍缺資料，不能當作該日或 PIT 證據",
    "official_no_data_for_requested_date": "官方未回傳指定日期資料",
    "downstream_eligibility_none": "下游使用資格尚未開放",
    "formal_oos_disabled": "Formal OOS 尚未開放",
    "insufficient_dry_run_days": "多日 dry-run 天數不足",
    "insufficient_weekly_history_records": "weekly 歷史週期不足",
    "legal_and_license_acceptance_required": "需要法務／授權審核",
    "license_not_accepted": "來源授權尚未接受",
    "official_publication_timestamp_missing": "官方發布時間戳缺漏",
    "p0_source_acceptance_pending": "P0 來源接受決議待處理",
    "paper_weekly_report_not_computable": "Paper 週報尚不可計算",
    "production_scheduler_disabled": "正式排程維持關閉",
    "source_acceptance_decision_missing": "尚未提供來源接受決議",
    "source_acceptance_deferred": "Owner 已決議延後，來源目前不具接受資格",
    "source_acceptance_rejected": "Owner 已決議拒絕此來源",
    "source_acceptance_disabled": "Owner 已決議停用此來源",
    "source_acceptance_not_authorized": "來源尚未取得允許用途的授權",
    "direct_chain_storage_preflight_blocked": "Direct/OOC 容量預檢受阻",
    "technical_production_single_writer_canary_not_completed": "technical 正式 single-writer canary 尚未完成",
    "formal_credit_not_authorized": "Formal credit 尚未授權",
    "performance_owner_packet_invalid": "效能 owner packet 無法驗證",
    "p0_projection_invalid": "P0 來源盤點資料無法讀取",
    "p0_live_audit_not_supplied": "尚未取得近期官方來源盤點",
    "p0_source_acceptance_pending": "官方來源仍待逐項接受或限用途審查",
    "p0_downstream_eligibility_not_granted": "來源尚未取得下游使用資格",
    "evidence_readiness_inspection_failed": "週期證據盤點讀取失敗",
    "formal_ml_readiness_inspection_failed": "Formal／ML 輸入盤點讀取失敗",
    "paper_readiness_inspection_failed": "Paper 輸入盤點讀取失敗",
    "paper_weekly_report_boundary_mismatch": "Paper 與基準的報告日期範圍不一致",
    "paper_weekly_report_not_computable": "Paper 週報尚不可計算",
    "paper_weekly_report_requires_two_snapshots": "至少需要兩個有效 Paper 快照才能計算週報",
    "paper_weekly_report_benchmark_observations_missing": "Paper 週報缺少對應日期的基準資料",
    "paper_snapshot_history_missing": "Paper 持倉快照尚未提供",
    "paper_snapshot_db_missing": "Paper 持倉資料庫不存在",
    "paper_snapshot_table_missing": "Paper 持倉資料表不存在",
    "paper_snapshot_positions_table_missing": "Paper 持倉明細資料表不存在",
    "paper_trade_ledger_path_not_configured": "尚未設定 Paper 成交帳路徑",
    "paper_trade_ledger_db_missing": "Paper 成交帳資料庫不存在",
    "paper_trade_ledger_empty": "Paper 成交帳目前沒有成交資料",
    "paper_trade_ledger_schema_mismatch": "Paper 成交帳欄位格式與契約不符",
    "paper_weekly_report_cost_turnover_missing": "Paper 週報缺少交易成本或週轉資料",
    "paper_weekly_report_execution_gap_missing": "Paper 週報缺少實際成交與預期執行差異",
    "paper_weekly_report_requires_two_benchmarks": "至少需要兩期基準資料才能計算週報",
    "paper_daily_status_missing": "尚未提供 Paper 每日狀態紀錄",
    "paper_daily_status_invalid": "Paper 每日狀態紀錄無效",
    "paper_daily_status_schema_mismatch": "Paper 每日狀態紀錄格式不符",
    "paper_snapshot_future_dated": "Paper 持倉快照日期晚於檢查日",
    "paper_daily_status_future_dated": "Paper 每日狀態日期晚於檢查日",
    "paper_daily_status_state_db_path_mismatch": "Paper 狀態紀錄與目前選定的資料庫不一致",
    "paper_snapshot_db_unavailable": "Paper 持倉資料庫無法讀取",
    "paper_trade_ledger_db_unavailable": "Paper 成交帳資料庫無法讀取",
    "equal_weight_benchmark_db_missing": "Equal Weight 基準資料庫不存在",
    "equal_weight_benchmark_table_missing": "Equal Weight 基準資料表不存在",
    "equal_weight_benchmark_db_unavailable": "Equal Weight 基準資料庫無法讀取",
    "training_as_of_required": "Formal／ML 盤點缺少帶時區的訓練截止時間",
    "training_as_of_invalid": "Formal／ML 訓練截止時間格式無效",
    "training_as_of_timezone_required": "Formal／ML 訓練截止時間缺少時區",
    "formal_oos_disabled": "Formal 樣本外驗證目前未開放",
    "formal_credit_not_authorized": "正式週證據尚未逐筆完成核准",
    "runtime_readiness_inspection_failed": "執行環境權限盤點失敗",
    "runtime_write_probe_not_supplied_or_missing": "尚未提供正式主機寫入權限探針",
    "runtime_staging_write_probe_failed": "隔離環境寫入與回復探針未通過",
    "runtime_registry_snapshot_probe_not_supplied_or_missing": "尚未提供正式 Registry 的隔離交易探針",
    "runtime_registry_snapshot_probe_failed": "正式 Registry 隔離交易／回復探針未通過",
    "technical_performance_baseline_not_supplied": "尚未提供 Technical 實測效能基線",
    "broker_performance_baseline_not_supplied": "尚未提供 Broker 實測效能基線",
    "direct_chain_storage_preflight_blocked": "ML Direct／OOC 可用磁碟空間不足",
    "direct_chain_storage_failure_observed": "ML Direct／OOC 最近一次維護遇到磁碟空間不足",
    "ml_direct_chain_status_invalid": "ML Direct／OOC 維護狀態資料無效",
    "update_history_not_observed": "尚未觀察到資料更新歷史",
}

_READINESS_LANE_LABELS = {
    "p0": "P0 來源",
    "evidence": "Evidence 週期證據",
    "paper": "Paper Portfolio",
    "formal_ml": "Formal／ML",
    "runtime": "執行環境",
    "performance": "效能基線",
    "update_history": "更新歷史",
}

_FORMAL_INPUT_LABELS = {
    "causal_non_cash_portfolio_ledger": "因果模擬持倉帳",
    "formal_rule_champion_snapshot_history": "Rule Champion 歷史快照",
    "pit_sector_membership": "PIT 產業成分",
}


def format_program_readiness_blockers(
    value: Any,
    *,
    include_raw: bool = True,
) -> str:
    """以白話中文呈現阻擋原因，必要時保留代碼供追查。"""

    if not isinstance(value, (list, tuple)) or not value:
        return "無"
    rendered: list[str] = []
    for raw_value in value[:8]:
        raw = str(raw_value or "").strip()
        if not raw:
            continue
        if raw.startswith("readiness_lane_not_supplied:"):
            lane = raw.split(":", 1)[1].strip()
            label = f"缺少{_READINESS_LANE_LABELS.get(lane, 'readiness')}盤點資料"
        elif raw.startswith("formal_input_"):
            prefix, _, input_name = raw.partition(":")
            readable_input = _FORMAL_INPUT_LABELS.get(
                input_name.strip(), input_name.strip() or "未命名輸入"
            )
            if prefix == "formal_input_not_ready":
                label = f"Formal 輸入尚未通過驗證：{readable_input}"
            elif prefix == "formal_input_source_missing":
                label = f"缺少 Formal 輸入資料：{readable_input}"
            elif prefix == "formal_input_machine_candidate":
                label = f"Formal 輸入仍是機器候選：{readable_input}"
            elif prefix == "formal_input_evidence_invalid":
                label = f"Formal 輸入證據無效：{readable_input}"
            elif prefix == "formal_input_evidence_unknown":
                label = f"Formal 輸入證據狀態未知：{readable_input}"
            elif prefix == "formal_input_evidence_unclassified":
                label = f"Formal 輸入證據尚未分類：{readable_input}"
            else:
                label = f"Formal 輸入尚未就緒：{readable_input}"
        elif raw.startswith("scheduled_tasks_missing_or_unavailable:"):
            label = "排程工作未完整可用"
        elif raw.startswith("paper_daily_status_boundary_violation:"):
            key = raw.split(":", 1)[1].strip()
            label = f"Paper 每日狀態違反安全邊界：{key or '欄位未命名'}"
        elif raw.startswith("paper_daily_status_"):
            suffix = raw.removeprefix("paper_daily_status_")
            label = {
                "missing": "尚未提供 Paper 每日狀態紀錄",
                "invalid": "Paper 每日狀態紀錄無效",
                "schema_mismatch": "Paper 每日狀態紀錄格式不符",
                "future_dated": "Paper 每日狀態日期晚於檢查日",
                "state_db_path_mismatch": "Paper 狀態紀錄與目前選定的資料庫不一致",
                "passed": "Paper 每日狀態已通過",
                "failed": "Paper 每日狀態未通過",
                "pending": "Paper 每日狀態待處理",
            }.get(suffix, "Paper 每日狀態需查看完整診斷")
        else:
            label = _READINESS_BLOCKER_LABELS.get(raw, "其他阻擋原因，請查看完整診斷")
        if include_raw and label != raw:
            rendered.append(f"{label}（{raw}）")
        else:
            rendered.append(label)
    return "；".join(rendered) or "無"


def format_p0_owner_decision_details(value: Mapping[str, Any]) -> str:
    """分開呈現 P0 Owner 決議、證據缺口及後續動作。"""

    decision = str(value.get("decision_status") or "not_supplied").strip().lower()
    decision_labels = {
        "not_supplied": "尚無 Owner／Reviewer 決議",
        "deferred": "已記錄延後決議",
        "rejected": "已記錄拒絕決議",
        "disabled": "已記錄停用決議",
        "limited": "已記錄限用途決議",
        "accepted": "已記錄接受決議",
    }
    label = str(value.get("label") or value.get("source_id") or "所選來源")
    machine_status = str(value.get("machine_status") or "not_observed")
    license_status = str(value.get("license_status") or "not_supplied")
    blockers = value.get("blockers")
    actions = value.get("owner_actions")
    allowed_use_cases = value.get("allowed_use_cases")
    source_contract_requirements = value.get("source_contract_requirements")
    blocker_text = format_program_readiness_blockers(blockers, include_raw=True)
    action_text = "；".join(
        str(item).strip()
        for item in actions
        if str(item).strip()
    ) if isinstance(actions, (list, tuple)) else "依資料缺口補件後重新盤點"
    allowed_text = "、".join(
        str(item).strip()
        for item in allowed_use_cases
        if str(item).strip()
    ) if isinstance(allowed_use_cases, (list, tuple)) else ""
    lines = [
        f"{label}｜目前決議：{decision_labels.get(decision, f'狀態 {decision}')}（{decision}）",
        f"證據缺口：{blocker_text}",
        f"Machine：{machine_status}；License：{license_status}；下游資格：none。Machine 狀態不等於來源接受。",
        f"下一步：{action_text or '未提供'}",
    ]
    if allowed_text:
        lines.append(f"核准用途：{allowed_text}")
    if isinstance(source_contract_requirements, (list, tuple)) and source_contract_requirements:
        lines.append("來源契約查核項目（政策／路徑描述，不代表證據已取得）：")
        lines.extend(
            f"• {str(item).strip()[:500]}"
            for item in source_contract_requirements[:16]
            if str(item).strip()
        )
    return "\n".join(lines)


def format_program_readiness_lane_progress(lane: str, value: Mapping[str, Any]) -> str:
    """Render bounded progress facts for one projected readiness lane."""

    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping):
        return ""

    if lane == "p0":
        source_count = _safe_nonnegative_int(
            metrics.get("source_count", metrics.get("p0_source_count"))
        )
        accepted = _safe_nonnegative_int(metrics.get("accepted_count"))
        limited = _safe_nonnegative_int(metrics.get("limited_count"))
        verified = _safe_nonnegative_int(metrics.get("machine_verified_count"))
        degraded = _safe_nonnegative_int(metrics.get("machine_degraded_count"))
        parts: list[str] = []
        if source_count:
            parts.append(f"來源 {source_count} 項")
        if verified or degraded or source_count:
            parts.append(f"機器證據 {verified + degraded}/{source_count or verified + degraded}")
        parts.append(f"正式接受 {accepted}／限用途 {limited}")
        route_count = _safe_nonnegative_int(metrics.get("route_count"))
        route_attempted = _safe_nonnegative_int(metrics.get("route_attempted_count"))
        if route_count:
            parts.append(f"來源查詢已嘗試 {route_attempted}/{route_count}")
        return "；".join(parts)

    if lane == "evidence":
        parts = []
        weekly_required = _safe_nonnegative_int(metrics.get("weekly_required_count"))
        if weekly_required:
            parts.append(
                f"真實週證據 {_safe_nonnegative_int(metrics.get('weekly_observed_count'))}/{weekly_required}"
            )
        if "weekly_pending_count" in metrics:
            pending_text = (
                "待人工審核收集 "
                f"{_safe_nonnegative_int(metrics.get('weekly_pending_count'))} 筆"
            )
            if "weekly_unreviewable_count" in metrics:
                pending_text += (
                    "（需重收 "
                    f"{_safe_nonnegative_int(metrics.get('weekly_unreviewable_count'))}"
                )
                if "weekly_source_unavailable_count" in metrics:
                    pending_text += (
                        "；來源不可讀 "
                        f"{_safe_nonnegative_int(metrics.get('weekly_source_unavailable_count'))}"
                    )
                if "weekly_coverage_missing_count" in metrics:
                    pending_text += (
                        "；覆蓋資訊缺件 "
                        f"{_safe_nonnegative_int(metrics.get('weekly_coverage_missing_count'))}"
                    )
                pending_text += "；分類可重疊）"
            parts.append(pending_text)
        dry_required = _safe_nonnegative_int(metrics.get("dry_run_required_count"))
        if dry_required:
            parts.append(
                f"操作日 dry-run {_safe_nonnegative_int(metrics.get('dry_run_observed_count'))}/{dry_required}"
            )
        if "formal_credit_authorized" in metrics:
            parts.append(
                "正式週證據核准："
                + ("已授權" if metrics.get("formal_credit_authorized") is True else "未授權")
            )
        return "；".join(parts)

    if lane == "paper":
        parts = []
        for key, label in (
            ("snapshot_count", "持倉快照"),
            ("benchmark_observation_count", "基準觀測"),
            ("cost_record_count", "成本紀錄"),
            ("filled_event_count", "成交筆數"),
        ):
            if key in metrics:
                parts.append(f"{label} {_safe_nonnegative_int(metrics.get(key))}")
        cost_ledger_status = str(metrics.get("cost_ledger_status") or "").strip()
        if cost_ledger_status:
            parts.append(
                f"成交成本帳：{format_status_token(cost_ledger_status)}"
            )
        weekly_status = str(metrics.get("weekly_report_status") or "").strip()
        if weekly_status:
            parts.append(f"週報：{format_status_token(weekly_status)}")
        return "；".join(parts)

    if lane == "formal_ml":
        ready = _safe_nonnegative_int(metrics.get("ready_input_count"))
        total = _safe_nonnegative_int(metrics.get("input_count"))
        if not total:
            return ""
        parts = [f"Formal 正式讀取驗證 {ready}/{total} 項"]
        candidate = _safe_nonnegative_int(metrics.get("machine_candidate_input_count"))
        missing = _safe_nonnegative_int(metrics.get("missing_input_count"))
        unknown = _safe_nonnegative_int(metrics.get("unknown_input_count"))
        invalid = _safe_nonnegative_int(metrics.get("invalid_input_count"))
        if candidate:
            parts.append(f"僅機器候選 {candidate} 項")
        if missing:
            parts.append(f"缺少來源資料 {missing} 項")
        if unknown:
            parts.append(f"來源未知 {unknown}")
        if invalid:
            parts.append(f"來源無效 {invalid}")
        return "；".join(parts)

    if lane == "runtime":
        state = str(metrics.get("overall_state") or "").strip()
        probe = str(metrics.get("write_probe") or "").strip()
        parts = []
        if state:
            parts.append(f"host {format_status_token(state)}（{state}）")
        if probe:
            parts.append(f"probe={probe}")
        return "；".join(parts)

    if lane == "performance":
        parts = []
        for key, label in (
            ("technical_canary_status", "technical canary"),
            ("broker_status", "broker"),
            ("ml_direct_chain_status", "Direct/OOC"),
            ("owner_packet_status", "owner packet"),
        ):
            status = str(metrics.get(key) or "").strip()
            if status:
                parts.append(f"{label} {format_status_token(status)}（{status}）")
        if "pending_lane_count" in metrics or "review_lane_count" in metrics:
            pending = _safe_nonnegative_int(metrics.get("pending_lane_count"))
            total = _safe_nonnegative_int(metrics.get("review_lane_count"))
            parts.append(f"owner review 待處理 {pending}/{total}")
        return "；".join(parts)

    if lane == "update_history":
        parts = []
        if "unique_run_count" in metrics:
            parts.append(f"run {_safe_nonnegative_int(metrics.get('unique_run_count'))}")
        if "terminal_record_count" in metrics:
            parts.append(f"terminal {_safe_nonnegative_int(metrics.get('terminal_record_count'))}")
        task_count = _safe_nonnegative_int(metrics.get("scheduled_task_count"))
        if task_count:
            available = _safe_nonnegative_int(metrics.get("scheduled_available_count"))
            parts.append(f"排程 {available}/{task_count}")
        freshness = str(metrics.get("freshness_status") or "").strip()
        if freshness:
            parts.append(f"freshness {format_status_token(freshness)}（{freshness}）")
        return "；".join(parts)

    return ""


def format_monthly_revenue_candidate_lines(detail: Mapping[str, Any]) -> list[str]:
    """投影月營收數值 snapshot 與 availability mapping 候選的唯讀差異。"""

    lines: list[str] = []
    latest_period = str(detail.get("latest_period") or "").strip()
    snapshot_period = str(detail.get("candidate_latest_period") or "").strip()
    if snapshot_period:
        is_newer = latest_period in {"", "未知", "無"} or snapshot_period > latest_period
        label = "候選待套用期別" if is_newer else "候選快照期別"
        fetch_date = str(detail.get("candidate_fetch_date") or "").strip()
        suffix = f"（抓取日：{fetch_date}）" if fetch_date else ""
        lines.append(f"{label}：{snapshot_period}{suffix}")
    snapshot_status = str(detail.get("candidate_snapshot_status") or "").strip()
    snapshot_diagnostic = str(detail.get("candidate_snapshot_diagnostic") or "").strip()
    if snapshot_status in {"missing", "invalid", "error"}:
        lines.append(f"數值 snapshot 候選：{format_status_token(snapshot_status)}")
        if snapshot_diagnostic:
            lines.append(f"候選診斷：{snapshot_diagnostic}")

    mapping_period = str(
        detail.get("availability_candidate_latest_period") or ""
    ).strip()
    mapping_status = str(
        detail.get("availability_candidate_status") or ""
    ).strip()
    mapping_file = str(detail.get("availability_candidate_file") or "").strip()
    if mapping_period or mapping_status or mapping_file:
        status = format_status_token(mapping_status or "unknown")
        row_count = _safe_nonnegative_int(
            detail.get("availability_candidate_row_count")
        )
        available_date = str(
            detail.get("availability_candidate_latest_available_date") or ""
        ).strip()
        suffix = f"{row_count:,} 筆"
        if available_date:
            suffix += f"；可用日至 {available_date}"
        added = detail.get("availability_candidate_added_count")
        conflicts = detail.get("availability_candidate_conflict_count")
        if added is not None or conflicts is not None:
            suffix += (
                f"；新增 {_safe_nonnegative_int(added):,}"
                f"／衝突 {_safe_nonnegative_int(conflicts):,}"
            )
        lines.append(
            f"公告日 mapping 候選：{mapping_period or '未解析'}（{status}；{suffix}）"
        )
        diagnostics = detail.get("availability_candidate_diagnostics") or []
        for diagnostic in list(diagnostics)[:2]:
            if str(diagnostic).strip():
                lines.append(f"候選診斷：{diagnostic}")
    return lines


def format_monthly_revenue_freshness_gap(detail: Mapping[str, Any]) -> str:
    """顯示月營收目前期別與通常公告節奏的差距。

    `expected_latest_period` 只是一個操作提示，不能取代官方公告／可得日
    證據；若已有更新的 snapshot／mapping 候選，候選行會另外說明，不重複
    標成正式資料落後。
    """

    expected = str(detail.get("expected_latest_period") or "").strip()
    imported = str(detail.get("latest_period") or "").strip()
    candidate = str(
        detail.get("candidate_latest_period")
        or detail.get("availability_candidate_latest_period")
        or ""
    ).strip()
    if not expected or not imported or imported >= expected or candidate >= expected:
        return ""
    return (
        f"預期最新期別：{expected}（目前正式資料：{imported}；"
        "請先抓取候選快照／可得日 mapping）"
    )


def format_freshness_gap(detail: Mapping[str, Any]) -> str:
    """把來源相對 daily reference 的落後日期轉成可讀提示。"""

    freshness_status = str(detail.get("freshness_status") or "").strip().lower()
    if freshness_status not in {"lagging", "stale"}:
        return ""
    reference_date = detail.get("freshness_reference_date") or detail.get("reference_date")
    latest_date = detail.get("latest_date")
    if not reference_date or not latest_date:
        return ""
    return f"新鮮度基準日：{reference_date}（資料最新日：{latest_date}）"


def format_source_detail_summary(source: str, detail: Mapping[str, Any]) -> str:
    latest_date = detail.get("latest_date") or "未知"
    total_records = _safe_nonnegative_int(detail.get("total_records"))
    if source == "monthly_revenue":
        latest_period = detail.get("latest_period") or latest_date
        latest_available_period = detail.get("latest_available_period") or "尚無"
        latest_available_date = detail.get("latest_available_date") or "尚無"
        next_available_date = detail.get("next_available_date")
        pending_period_count = _safe_nonnegative_int(detail.get("pending_period_count"))
        monthly_freshness_gap = format_monthly_revenue_freshness_gap(detail)
        lines = [
            f"最新可用日：{latest_available_date}",
            f"已匯入期別：{latest_period}",
            f"目前可用期別：{latest_available_period}",
        ]
        if detail.get("current_observed_period"):
            lines = [
                f"目前查閱期別：{detail['current_observed_period']}（已公告公司）",
                f"現況觀測時間：{detail.get('current_observed_at', '未知')}",
                f"現況快照筆數：{detail.get('current_observed_records', 0):,}",
                f"歷史 PIT 可用期別：{latest_available_period}",
                "公告覆蓋未齊；現況資料不授予歷史 PIT 資格。",
            ]
        lines.extend(format_monthly_revenue_candidate_lines(detail))
        if monthly_freshness_gap:
            lines.append(monthly_freshness_gap)
        if pending_period_count and next_available_date:
            lines.append(
                f"待生效：{pending_period_count} 個期別（{next_available_date} 起可用）"
            )
        lines.extend([
            f"SQLite 筆數：{total_records:,}",
            "狀態："
            + format_status_token(
                "lagging" if monthly_freshness_gap else detail.get("status")
            ),
        ])
    elif source in {"institutional_flow", "credit_transaction", "tdcc_shareholding"}:
        earliest = str(detail.get("earliest_date") or "無")
        latest_candidate = str(detail.get("latest_date") or "無")
        coverage = str(detail.get("coverage_pct") or "無 checkpoint")
        lines = [
            f"最新日期：{latest_candidate}",
            f"正式入庫筆數：{total_records:,}" if detail.get("formal_records") else f"候選筆數：{total_records:,}",
            f"區間：{earliest} ~ {latest_candidate}",
            f"覆蓋說明：{coverage}" if detail.get("formal_records") else f"checkpoint 覆蓋率：{coverage}",
            f"狀態：{format_status_token(detail.get('status'))}",
        ]
        freshness_status = str(detail.get("freshness_status") or "").strip().lower()
        reference_date = str(detail.get("freshness_reference_date") or "").strip()
        if freshness_status in {"lagging", "stale"}:
            lines[-1] = "狀態：" + format_status_token("lagging")
        if freshness_status in {"lagging", "stale"} and reference_date:
            lines.append(
                f"新鮮度基準日：{reference_date}（候選最新日：{latest_candidate}）"
            )
    elif source == "scheduler_status":
        scheduler_state = str(
            detail.get("scheduler_state") or detail.get("status") or "unknown"
        ).strip()
        operation_count = _safe_nonnegative_int(
            detail.get("operation_count", detail.get("total_records"))
        )
        core_ready = _safe_nonnegative_int(detail.get("core_ready_count"))
        core_jobs = _safe_nonnegative_int(detail.get("core_job_count"))
        lines = [
            f"排程狀態：{format_status_token(scheduler_state)}（{scheduler_state}）",
            f"核心工作就緒：{core_ready:,}/{core_jobs:,}",
            f"已觀測工作：{operation_count:,}",
            f"正常：{_safe_nonnegative_int(detail.get('operational_count')):,}"
            f"／受控：{_safe_nonnegative_int(detail.get('guarded_count')):,}"
            f"／需處理：{_safe_nonnegative_int(detail.get('attention_count')):,}"
            f"／不可用：{_safe_nonnegative_int(detail.get('unavailable_count')):,}",
            f"狀態：{format_status_token(detail.get('status'))}",
        ]
    else:
        lines = [
            f"最新日期：{latest_date}",
            f"SQLite 筆數：{total_records:,}",
            f"狀態：{format_status_token(detail.get('status'))}",
        ]
    if source == "daily":
        csv_count = detail.get("csv_file_count") or detail.get("file_count")
        if csv_count is not None:
            lines.append(f"CSV 日檔數：{_safe_nonnegative_int(csv_count):,}")
        missing_dates = detail.get("missing_dates") or []
        if missing_dates:
            lines.append("缺漏日期：" + "、".join(str(date) for date in missing_dates[:8]))
    elif source == "broker_branch":
        lines.append(f"實際天數：{_safe_nonnegative_int(detail.get('date_count')):,}")
        lines.append(f"雙榜紀錄：{_safe_nonnegative_int(detail.get('dual_count')):,}")
        lines.append(f"張數榜專屬：{_safe_nonnegative_int(detail.get('e_only_count')):,}")
        lines.append(f"金額榜專屬：{_safe_nonnegative_int(detail.get('b_only_count')):,}")
    elif source in {"technical", "technical_indicators"} and detail.get("file_count") is not None:
        lines.append(f"指標檔數：{_safe_nonnegative_int(detail.get('file_count')):,}")
    elif source == "scheduler_status":
        scheduled_root = str(detail.get("scheduled_root") or "").strip()
        if scheduled_root:
            lines.append(f"狀態根目錄：{scheduled_root}")
        if detail.get("read_only") is True:
            lines.append("邊界：唯讀，不註冊或修改 Windows Task Scheduler")
    read_mode = str(detail.get("read_mode") or "").strip()
    if read_mode:
        lines.append(f"讀取模式：{read_mode}")
    warnings = detail.get("warnings") or detail.get("quality_warnings") or []
    if warnings:
        lines.append("提醒：" + "；".join(str(item) for item in warnings[:3]))
    if source not in {"institutional_flow", "credit_transaction", "tdcc_shareholding"}:
        freshness_gap = format_freshness_gap(detail)
        if freshness_gap:
            lines.append(freshness_gap)
    return "\n".join(lines)


def format_scheduler_operations_detail(detail: Mapping[str, Any]) -> str:
    """Render scheduler operation artifacts as bounded human-readable lines.

    The scheduler detail endpoint is intentionally read-only.  Showing a raw
    JSON blob made a valid ``completed`` or ``skipped_non_trading_day`` result
    look like an error and forced users to decode state tokens themselves.  A
    compact projection keeps the raw token and diagnostic while making the
    action boundary visible.
    """

    operation_count = _safe_nonnegative_int(
        detail.get("operation_count", detail.get("total_records"))
    )
    lines = [
        f"排程工作明細：{operation_count:,} 個（中文狀態／原始 token）",
        f"operation_count={operation_count}",
    ]
    operations = detail.get("operations")
    if not isinstance(operations, (list, tuple)) or not operations:
        lines.append("尚未提供各工作明細；請重新檢查明確的 scheduled artifacts。")
    else:
        for operation in operations[:32]:
            if not isinstance(operation, Mapping):
                continue
            label = str(operation.get("label") or operation.get("job_id") or "未知工作").strip()
            raw_status = str(operation.get("raw_status") or "unknown").strip().lower() or "unknown"
            state = str(operation.get("state") or "unknown").strip().lower() or "unknown"
            line = f"{label}：{format_status_token(state)}（state={state}；raw={raw_status}）"
            diagnostic = str(operation.get("diagnostic") or "").strip()
            if diagnostic:
                line += f"；診斷={diagnostic}"
            updated_at = str(operation.get("updated_at") or "").strip()
            if updated_at:
                line += f"；觀測={updated_at}"
            lines.append(line)
    scheduled_root = str(detail.get("scheduled_root") or "").strip()
    if scheduled_root:
        lines.append(f"狀態根目錄：{scheduled_root}")
    if detail.get("read_only") is True:
        lines.append("邊界：唯讀，不註冊或修改 Windows Task Scheduler")
    return "\n".join(lines)


def format_data_freshness_preview(payload: Mapping[str, Any]) -> str:
    """Render one ``data_freshness`` artifact without exposing raw JSON.

    This is intentionally different from :func:`format_scheduler_operations_detail`:
    a freshness artifact describes one read-only check, not the health of every
    scheduled job.  Keep the machine token and the small set of freshness
    observations visible, while bounding warning/error output so a malformed or
    unexpectedly large artifact cannot take over the status panel.
    """

    raw_status = str(payload.get("status") or "unknown").strip().lower() or "unknown"
    lines = [
        "單一排程 artifact：資料新鮮度（非整體 Scheduler）",
        f"狀態：{format_status_token(raw_status)}（{raw_status}）",
    ]

    task = str(payload.get("task") or "").strip()
    if task:
        lines.append(f"工作：{task}")
    checked_at = str(
        payload.get("checked_at")
        or payload.get("generated_at")
        or payload.get("completed_at")
        or ""
    ).strip()
    if checked_at:
        lines.append(f"檢查時間：{checked_at}")

    checks = payload.get("checks")
    check_values = checks if isinstance(checks, Mapping) else payload
    daily_latest = str(
        check_values.get("daily_prices_latest_date")
        or check_values.get("daily_price_latest_date_key")
        or ""
    ).strip()
    technical_latest = str(
        check_values.get("technical_indicators_latest_date") or ""
    ).strip()
    if daily_latest:
        lines.append(f"日價最新日：{daily_latest}")
    if technical_latest:
        lines.append(f"技術指標最新日：{technical_latest}")

    quick_status = str(check_values.get("data_update_quick_status") or "").strip()
    quick_checked_date = str(
        check_values.get("data_update_quick_checked_date") or ""
    ).strip()
    quick_expected_date = str(
        check_values.get("data_update_quick_expected_date") or ""
    ).strip()
    if quick_status or quick_checked_date or quick_expected_date:
        quick_line = f"快速更新：{format_status_token(quick_status or 'unknown')}"
        if quick_status:
            quick_line += f"（{quick_status}）"
        if quick_checked_date or quick_expected_date:
            quick_line += (
                f"；檢查日={quick_checked_date or '未提供'}"
                f"；預期日={quick_expected_date or '未提供'}"
            )
        lines.append(quick_line)

    for label, key in (
        ("日價年齡（天）", "daily_prices_age_days"),
        ("技術指標年齡（天）", "technical_indicators_age_days"),
    ):
        if check_values.get(key) is not None:
            lines.append(f"{label}：{_safe_nonnegative_int(check_values.get(key))}")

    warnings = payload.get("warnings")
    errors = payload.get("errors")
    warning_items = (
        [str(item).strip() for item in warnings if str(item).strip()]
        if isinstance(warnings, (list, tuple, set))
        else ([str(warnings).strip()] if warnings not in (None, "") else [])
    )
    error_items = (
        [str(item).strip() for item in errors if str(item).strip()]
        if isinstance(errors, (list, tuple, set))
        else ([str(errors).strip()] if errors not in (None, "") else [])
    )
    if warning_items:
        lines.append("提醒：" + "；".join(warning_items[:3]))
    if error_items:
        lines.append("錯誤：" + "；".join(error_items[:3]))
    if not warning_items and not error_items:
        lines.append("診斷：無 warnings／errors")

    if payload.get("read_only") is True:
        lines.append("邊界：唯讀，只觀測 freshness artifact，不修改資料或 Scheduler")
    return "\n".join(lines)


def format_weekly_collection_details(packet: Mapping[str, Any]) -> str:
    """Render a bounded, read-only weekly collection review summary."""

    records = packet.get("records")
    if not isinstance(records, (list, tuple)):
        records = []
    lines = [
        "週 Evidence 收集明細（唯讀候選）",
        f"待審 {_safe_nonnegative_int(packet.get('pending_human_review_count'))} 筆；"
        f"需重收 {_safe_nonnegative_int(packet.get('recollection_required_count'))} 筆；"
        f"可供人工審查 {_safe_nonnegative_int(packet.get('reviewable_pending_count'))} 筆。",
        "本畫面不寫入審查決定、不產生核准 projection，也不授予 Gate credit。",
        "來源雜湊只綁定收集時來源快照；不代表品質、全市場覆蓋、PIT 或 License 已通過。",
        "",
    ]
    max_records = 30

    def optional_count(value: Any) -> str:
        if value is None or isinstance(value, bool):
            return "未提供"
        try:
            return str(max(0, int(value)))
        except (TypeError, ValueError):
            return "格式無效"

    for index, record in enumerate(records[:max_records]):
        if not isinstance(record, Mapping):
            continue
        payload = record.get("collection_payload")
        payload = payload if isinstance(payload, Mapping) else {}
        coverage = payload.get("source_coverage")
        coverage = coverage if isinstance(coverage, Mapping) else {}
        lines.extend(
            [
                f"{index + 1}. {record.get('period_start', '?')} ～ {record.get('period_end', '?')}",
                f"   收集 ID：{str(record.get('collection_id') or '未提供')[:80]}",
                f"   來源雜湊：{str(record.get('source_hash') or '未提供')[:80]}",
                f"   狀態／審查性：{record.get('collection_status', 'unknown')}／{record.get('reviewability_status', 'unknown')}",
                f"   最近交易日：{record.get('last_trading_date') or '未提供'}；覆蓋狀態：{coverage.get('status', '未提供')}",
                f"   覆蓋基準：{coverage.get('coverage_basis', '未提供')}；"
                f"全市場分母：{optional_count(coverage.get('expected_universe_count'))}；"
                f"完整覆蓋宣稱：{'是' if coverage.get('full_coverage_claimed') is True else '否／未宣稱'}",
                "   覆蓋統計："
                f"交易日 {optional_count(coverage.get('trading_day_count'))}；"
                f"觀測列 {optional_count(coverage.get('observed_row_count'))}；"
                f"觀測股票 {optional_count(coverage.get('observed_symbol_count'))}；"
                f"重複列 {optional_count(coverage.get('duplicate_symbol_rows'))}；"
                f"不完整列 {optional_count(coverage.get('incomplete_row_count'))}",
            ]
        )
        reasons = record.get("reviewability_reasons")
        if isinstance(reasons, (list, tuple)) and reasons:
            lines.append("   需重收原因：" + "、".join(str(item)[:100] for item in reasons[:8]))
        findings = coverage.get("quality_findings")
        if isinstance(findings, (list, tuple)) and findings:
            lines.append("   品質發現：" + "；".join(str(item)[:160] for item in findings[:12]))
        examples = coverage.get("integrity_examples")
        if isinstance(examples, (list, tuple)) and examples:
            lines.append("   完整性例子（最多 5 筆，僅顯示收據雜湊、不開啟路徑）：")
            for example in examples[:5]:
                if not isinstance(example, Mapping):
                    continue
                fields = example.get("missing_fields")
                fields_text = (
                    ", ".join(str(item)[:40] for item in fields[:8])
                    if isinstance(fields, (list, tuple))
                    else "未提供"
                )
                lines.append(
                    f"   - {example.get('date', '?')}／{example.get('symbol', '?')}；"
                    f"缺欄位 {fields_text}；分類 {str(example.get('classification') or '未提供')[:100]}；"
                    f"官方收據雜湊 {str(example.get('official_receipt_sha256') or '未核')[:80]}"
                )
        lines.append("")
    if len(records) > max_records:
        lines.append(f"其餘 {len(records) - max_records} 筆未展開；完整封包需走既有人工核對流程。")
    if not records:
        lines.append("目前沒有可列出的待人工審查週收集記錄。")
    return "\n".join(lines).rstrip()


def tpex_warning_messages(result: Mapping[str, Any]) -> list[str]:
    warnings = [str(item) for item in result.get("warnings", []) if str(item).strip()]
    failed_dates = sorted({str(item) for item in result.get("failed_dates", []) if str(item).strip()})
    if failed_dates:
        warnings.append(f"TPEX 每日股價缺少日期：{', '.join(failed_dates)}")
    return list(dict.fromkeys(warnings))


def get_update_type_name(update_type: str) -> str:
    names = {
        "daily": "每日股票數據",
        "market": "大盤指數數據",
        "industry": "產業指數數據",
        "broker_branch": "券商分點資料",
    }
    return names.get(update_type, update_type)
