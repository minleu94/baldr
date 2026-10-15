"""TWSE 官方注意公告只按原始個股研究證據顯示。"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_module.stock_research_report_dtos import (
    StockOfficialAttentionDTO,
    StockOfficialAttentionRowDTO,
    StockResearchReportDTO,
)
from ui_qt.views.stock_research_report_view import StockResearchReportView


def _app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication(sys.argv)
    return instance


def _view() -> StockResearchReportView:
    _app()
    return StockResearchReportView(SimpleNamespace())


def _attention_row(*, stock_code: str = "2330") -> StockOfficialAttentionRowDTO:
    return StockOfficialAttentionRowDTO(
        stock_code=stock_code,
        stock_name="台積電",
        official_date_original_text="2026/10/14",
        announcement_count_original_text="第 3 次",
        reason_text="<b>注意交易資訊</b>，原始說明",
        closing_price_original_text="1,460.00",
        pe_original_text="24.08",
    )


def _available_attention(
    *, rows: tuple[StockOfficialAttentionRowDTO, ...] | None = None
) -> StockOfficialAttentionDTO:
    return StockOfficialAttentionDTO(
        status="available",
        query_date="2026-10-14",
        source_url="https://www.twse.com.tw/example/t86",
        rows=(_attention_row(),) if rows is None else rows,
        manifest_sha256="sha256:" + "a" * 64,
        receipt_sha256="sha256:" + "b" * 64,
        available_hour="2026-10-14T15:00:00+08:00",
        availability_basis="batch_published_hour",
    )


def test_available_official_attention_preserves_row_text_and_pins() -> None:
    view = _view()
    try:
        report = StockResearchReportDTO(
            stock_code="2330",
            attention_reasons=("另一份研究理由，不是官方公告",),
            official_attention=_available_attention(),
        )
        view._render_report(report)

        text = view.official_attention_label.text()
        evidence = view.official_attention_evidence_label.text()
        assert "TWSE 官方注意公告原文" in text
        assert "股票：2330 台積電" in text
        assert "公告日期（原文）：2026/10/14" in text
        assert "原累計公告次數（原文；不代表連續日數）：第 3 次" in text
        assert "原因（原文）：<b>注意交易資訊</b>，原始說明" in text
        assert "收盤價（原文）：1,460.00" in text
        assert "本益比（原文）：24.08" in text
        assert "另一份研究理由" not in text
        assert view.official_attention_label.textFormat() == Qt.TextFormat.PlainText
        assert "2026-10-14" in evidence
        assert "https://www.twse.com.tw/example/t86" in evidence
        assert "2026-10-14T15:00:00+08:00" in evidence
        assert "batch_published_hour" in evidence
        assert "sha256:" + "a" * 9 + "…" + "a" * 8 in evidence
        assert "sha256:" + "b" * 9 + "…" + "b" * 8 in evidence
        assert "sha256:" + "a" * 64 in view.official_attention_evidence_label.toolTip()
        assert "sha256:" + "b" * 64 in view.official_attention_evidence_label.toolTip()
        assert view.market_status_label.text() != text
    finally:
        view.close()


def test_available_without_rows_does_not_claim_other_market_state() -> None:
    view = _view()
    try:
        view._render_report(
            StockResearchReportDTO(
                stock_code="2330",
                official_attention=_available_attention(rows=()),
            )
        )
        assert view.official_attention_label.text() == (
            "此TWSE公告日查無此代碼；未判定其他市場。"
        )
        assert "未判定其他市場" in view.official_attention_label.text()
        assert "上市／交易狀態" not in view.official_attention_label.text()
    finally:
        view.close()


def test_unknown_attention_displays_named_limitations_and_evidence() -> None:
    view = _view()
    try:
        attention = StockOfficialAttentionDTO(
            status="unknown",
            query_date="2026-10-14",
            source_url="https://www.twse.com.tw/example/t86",
            manifest_sha256="sha256:" + "c" * 64,
            receipt_sha256="sha256:" + "d" * 64,
            available_hour="2026-10-14T15:00:00+08:00",
            availability_basis="batch_published_hour",
            limitations=("本批次未含可讀的 TWSE 注意公告列。",),
        )
        view._render_report(
            StockResearchReportDTO(stock_code="2330", official_attention=attention)
        )
        assert "官方注意公告狀態：未知" in view.official_attention_label.text()
        assert "本批次未含可讀的 TWSE 注意公告列。" in view.official_attention_label.text()
        assert "不得推論查無公告" not in view.official_attention_label.text()
        assert "可用時間依據：batch_published_hour" in view.official_attention_evidence_label.text()
        assert "Manifest SHA-256" in view.official_attention_evidence_label.text()
        assert "Receipt SHA-256" in view.official_attention_evidence_label.text()
    finally:
        view.close()


def test_cross_stock_clear_removes_previous_official_attention_evidence() -> None:
    view = _view()
    try:
        view._render_report(
            StockResearchReportDTO(
                stock_code="2330",
                official_attention=_available_attention(),
            )
        )
        assert "2330 台積電" in view.official_attention_label.text()
        assert "sha256:" + "a" * 9 in view.official_attention_evidence_label.text()

        view._active_code = "2317"
        view._clear_loaded_report()
        assert view.official_attention_label.text() == "TWSE 官方注意公告：尚未載入本股。"
        assert view.official_attention_evidence_label.text() == "尚未載入官方注意公告來源證據。"
        assert view.official_attention_evidence_label.toolTip() == ""

        view._render_report(
            StockResearchReportDTO(
                stock_code="2317",
                official_attention=StockOfficialAttentionDTO(
                    status="unknown",
                    limitations=("2317 尚無獨立公告來源。",),
                ),
            )
        )
        text = view.official_attention_label.text()
        assert "2317 尚無獨立公告來源。" in text
        assert "2330 台積電" not in text
        assert "注意交易資訊" not in text
    finally:
        view.close()
