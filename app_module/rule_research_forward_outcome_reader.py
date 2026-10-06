"""明示輸入檔與 exact 保存母體的有界唯讀 consumer；不查市場 DB。"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from app_module.rule_research_forward_outcome import (
    BenchmarkSpec, Calendar, CostPolicy, PricePoint,
    build_parent_rule_research_forward_outcome,
)
from app_module.rule_research_parent_capture import BoundedRuleResearchParentWriter
from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, _safe_path
from app_module.rule_research_sample_readiness import read_saved_parent_rule_sample_readiness

INPUT_SCHEMA = "rule-research-forward-input.v1"
MAX_INPUT_BYTES = 2 * 1024 * 1024


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("forward_input_duplicate_key")
        value[key] = item
    return value


def _input_bytes(path: Path) -> bytes:
    _safe_path(path)
    with path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("forward_input_size_bound")
    return raw


def read_saved_parent_forward_outcome(
    receipt_path: str, input_path: str, *, cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """每次重讀 receipt、原來源與 exact children，輸入變動即拒絕。"""
    cancel = cancel_callback or (lambda: False)
    if cancel():
        return {"cancelled": True}
    selected = Path(receipt_path).absolute()
    if selected.name != "receipt.json" or selected.parent.parent.name != "parents":
        raise ValueError("forward_parent_receipt_required")
    writer = BoundedRuleResearchParentWriter(selected.parent.parent)
    package = writer.read(selected.parent.name)
    body = package["capture"]
    if str(selected.parent.parent.parent.resolve()) != body["capture_root"]:
        raise ValueError("parent_root_binding_mismatch")
    source = Path(input_path).absolute()
    raw = _input_bytes(source)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    keys = {"schema_version", "parent_identity_sha256", "decision_date", "as_of_date",
            "calendar", "prices", "benchmark", "cost_policy"}
    if not isinstance(value, dict) or set(value) != keys or value["schema_version"] != INPUT_SCHEMA:
        raise ValueError("forward_input_schema_invalid")
    if value["parent_identity_sha256"] != selected.parent.name:
        raise ValueError("forward_input_parent_mismatch")
    if date.fromisoformat(value["as_of_date"]) > datetime.now(timezone.utc).date():
        raise ValueError("forward_input_as_of_in_future")
    calendar_value = value["calendar"]
    if not isinstance(calendar_value, dict) or not isinstance(calendar_value.get("trading_dates"), list):
        raise ValueError("forward_input_calendar_invalid")
    calendar = Calendar(**{**calendar_value, "trading_dates": tuple(calendar_value["trading_dates"])})
    benchmark = None if value["benchmark"] is None else BenchmarkSpec(**value["benchmark"])
    cost = None if value["cost_policy"] is None else CostPolicy(**value["cost_policy"])
    if not isinstance(value["prices"], list) or len(value["prices"]) > 513 * 21:
        raise ValueError("forward_input_prices_bound")
    prices = []
    for point in value["prices"]:
        if not isinstance(point, dict):
            raise ValueError("forward_input_price_invalid")
        price = point.get("price")
        if price is not None and not isinstance(price, str):
            raise ValueError("forward_input_price_must_be_decimal_text")
        prices.append(PricePoint(**{**point, "price": None if price is None else Decimal(price)}))
    if cancel():
        return {"cancelled": True}
    read_saved_parent_rule_sample_readiness(
        body["snapshot_root"], body["capture_root"], universe_path=body["universe"]["source_ref"],
        identity_sha256=selected.parent.name,
    )
    children = []
    child_writer = BoundedRuleResearchCaptureWriter(Path(body["capture_root"]) / "samples" / body["plan_sha256"])
    for batch in body["batches"]:
        if cancel():
            return {"cancelled": True}
        if batch["status"] == "captured":
            children.append(child_writer.read(batch["capture_identity_sha256"]))
    projection = build_parent_rule_research_forward_outcome(
        package, children, decision_date=value["decision_date"], as_of_date=value["as_of_date"],
        calendar=calendar, prices=prices, benchmark=benchmark, cost_policy=cost,
    )
    # 完成前再核 source readiness 與每個保存包，拒絕中途修訂。
    read_saved_parent_rule_sample_readiness(
        body["snapshot_root"], body["capture_root"], universe_path=body["universe"]["source_ref"],
        identity_sha256=selected.parent.name,
    )
    for child in children:
        if child_writer.read(child["capture"]["capture_identity_sha256"]) != child:
            raise ValueError("forward_child_changed_during_read")
    if writer.read(selected.parent.name) != package or _input_bytes(source) != raw:
        raise ValueError("forward_source_changed_during_read")
    if cancel():
        return {"cancelled": True}
    return {"cancelled": False, "projection": projection.to_dict(),
            "input_source": str(source), "input_sha256": hashlib.sha256(raw).hexdigest()}
