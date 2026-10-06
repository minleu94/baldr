"""既有 parent 收據的固定觀測日接受 policy；明示日期，不挑 latest 或排程。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from itertools import islice
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app_module.daily_market_method_contract import method_contracts_sha256
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION, feature_contract_for_version,
)
from app_module.daily_market_research_universe import _object, _text
from app_module.rule_research_parent_capture import (
    BoundedRuleResearchParentWriter, _sha, _validate_universe, load_parent_universe,
)
from app_module.rule_research_sample_capture import (
    MAX_CAPTURE_BYTES, MAX_CAPTURES, BoundedRuleResearchCaptureWriter,
    _clock, _digest, _identity, _json, _read_file, _require, _safe_path,
)
from app_module.rule_research_sample_readiness import read_saved_parent_rule_sample_readiness

OBSERVATION_POLICY_SCHEMA = "rule-research-observation-policy.v1"
ACCEPTANCE_SCHEMA = "rule-research-observation-acceptance.v1"
_TAIPEI = ZoneInfo("Asia/Taipei")
_QUALIFICATION = {"research_only": True, "natural_authority": False, "formal_eligible": False,
                  "training_eligible": False, "historical_pit_eligible": False,
                  "selection_status": "unknown", "source_availability": "unknown", "market_calendar": "unknown"}


def _local_time(value: Any) -> time:
    _require(isinstance(value, str), "observation_time_invalid")
    result = time.fromisoformat(value)
    _require(result.tzinfo is None and result.isoformat() == value and result.microsecond == 0,
             "observation_time_invalid")
    return result


def _validate_config(value: Any) -> None:
    _require(isinstance(value, dict) and set(value) - {"feature_contract_version"} == {
        "schema_version", "policy_id", "version", "timezone", "decision_cutoff_time",
        "observation_start_time", "observation_end_time", "expected_observation_dates",
        "universe_template_source", "research_only"}, "observation_policy_fields")
    observation_feature_contract_version(value)
    _require(value["schema_version"] == OBSERVATION_POLICY_SCHEMA
             and value["timezone"] == "Asia/Taipei" and value["research_only"] is True,
             "observation_policy_scope")
    _text(value["policy_id"], "policy_id", 96)
    _text(value["version"], "version", 32)
    clocks = [_local_time(value[k]) for k in ("decision_cutoff_time", "observation_start_time", "observation_end_time")]
    _require(clocks == sorted(clocks), "observation_window_order")
    days = value["expected_observation_dates"]
    _require(isinstance(days, list) and 1 <= len(days) <= 31
             and all(isinstance(d, str) and date.fromisoformat(d).isoformat() == d for d in days)
             and days == sorted(set(days)), "observation_dates_invalid")
    _require(isinstance(value["universe_template_source"], str)
             and Path(value["universe_template_source"]).is_absolute(), "observation_template_absolute_required")


def observation_feature_contract_version(value: dict[str, Any]) -> str:
    """版號必須明示有效；舊 policy 缺欄維持原 v2。"""
    version = value.get("feature_contract_version", DAILY_MARKET_FEATURE_CONTRACT_VERSION)
    _require(isinstance(version, str), "observation_feature_contract_version_invalid")
    feature_contract_for_version(version)
    return version


def _validate_policy(policy: Any) -> None:
    _require(isinstance(policy, dict) and set(policy) == {
        "value", "source_ref", "source_sha256", "universe_template", "method_contracts_sha256"},
        "observation_policy_binding_invalid")
    _validate_config(policy["value"])
    _require(policy["method_contracts_sha256"] == feature_contract_for_version(
        observation_feature_contract_version(policy["value"])).method_contracts_sha256,
        "observation_method_contract_binding_invalid")
    _require(_sha(policy["source_sha256"]) and Path(policy["source_ref"]).is_absolute()
             and _sha(policy["method_contracts_sha256"]), "observation_policy_pin_invalid")
    template = policy["universe_template"]
    _require(isinstance(template, dict) and set(template) == {"value", "source_ref", "source_sha256"}
             and _sha(template["source_sha256"])
             and Path(template["source_ref"]).is_absolute(), "observation_template_pin_invalid")
    _validate_universe(template["value"])
    _require(str(Path(policy["value"]["universe_template_source"]).absolute()) == template["source_ref"],
             "observation_template_binding_invalid")


def load_observation_policy(path: str | Path) -> dict[str, Any]:
    raw_path = Path(path).absolute()
    raw = _read_file(raw_path, 64 * 1024)
    value = json.loads(raw, object_pairs_hook=_object)
    _validate_config(value)
    template = load_parent_universe(value["universe_template_source"])
    policy = {"value": value, "source_ref": str(raw_path.resolve()), "source_sha256": _digest(raw),
              "universe_template": template, "method_contracts_sha256": feature_contract_for_version(
                  observation_feature_contract_version(value)).method_contracts_sha256}
    _validate_policy(policy)
    return policy


def _universe_definition(value: dict[str, Any]) -> dict[str, Any]:
    # 日期由每個 parent 自己核對；其餘全母體成員／排除／版本仍須完全一致。
    return {k: v for k, v in value.items() if k != "as_of_date"}


def _parent(path: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selected = Path(path).absolute()
    _safe_path(selected)
    _require(selected.name == "receipt.json" and selected.parent.parent.name == "parents", "parent_receipt_selection_invalid")
    writer = BoundedRuleResearchParentWriter(selected.parent.parent)
    package = writer.read(selected.parent.name)
    body = package["capture"]
    _require(str(selected.parent.parent.parent.resolve()) == body["capture_root"], "parent_root_binding_mismatch")
    ready = read_saved_parent_rule_sample_readiness(body["snapshot_root"], body["capture_root"],
        universe_path=body["universe"]["source_ref"], identity_sha256=selected.parent.name)
    # parent completeness 是保存包/控制組完整；固定日接受另核每股資料日。
    child_writer = BoundedRuleResearchCaptureWriter(Path(body["capture_root"]) / "samples" / body["plan_sha256"])
    missing: set[str] = set()
    for batch in body["batches"]:
        if batch["status"] != "captured":
            missing.update(batch["included_stock_codes"])
            continue
        child = child_writer.read(batch["capture_identity_sha256"])["capture"]
        missing.update(r["stock_code"] for r in child["rows"]
                       if r["state"] != "excluded" and r["data_as_of"] != ready["decision_date"])
    ready["missing_target_data_members"] = sorted(missing)
    ready["target_data_day_status"] = "exact_declared_day" if not missing else "insufficient_or_stale"
    _require(writer.read(selected.parent.name) == package, "observation_parent_changed")
    pin = {"receipt_ref": str(selected), "parent_identity_sha256": selected.parent.name,
           "parent_capture_sha256": package["receipt"]["capture_sha256"], "parent_capture_observed_at": body["observed_at"]}
    return body, ready, pin


@dataclass(frozen=True, slots=True)
class RuleResearchObservationAcceptance:
    body_json: str

    def to_dict(self) -> dict[str, Any]:
        _require(len(self.body_json.encode("utf-8")) <= MAX_CAPTURE_BYTES, "observation_byte_bound")
        body = json.loads(self.body_json)
        _require(isinstance(body, dict) and set(body) == {
            "schema_version", "capture_identity_sha256", "policy", "policy_sha256", "qualification",
            "parent_pin", "decision_date", "decision_cutoff", "as_of", "observed_at",
            "source_binding_sha256", "cohort_status", "source_completeness", "target_data_day_status",
            "missing_target_data_members", "acceptance_status", "reason"}
            and _json(body) == self.body_json and body["schema_version"] == ACCEPTANCE_SCHEMA
            and body["qualification"] == _QUALIFICATION, "observation_envelope_invalid")
        _validate_policy(body["policy"])
        _require(body["policy_sha256"] == _digest(_json(body["policy"]).encode("utf-8"))
                 and body["capture_identity_sha256"] == _identity(body), "observation_identity_invalid")
        pin = body["parent_pin"]
        _require(isinstance(pin, dict) and set(pin) == {"receipt_ref", "parent_identity_sha256", "parent_capture_sha256", "parent_capture_observed_at"}
                 and _sha(pin["parent_identity_sha256"]) and _sha(pin["parent_capture_sha256"])
                 and Path(pin["receipt_ref"]).is_absolute()
                 and Path(pin["receipt_ref"]).name == "receipt.json"
                 and Path(pin["receipt_ref"]).parent.name == pin["parent_identity_sha256"], "observation_parent_pin_invalid")
        day = date.fromisoformat(body["decision_date"])
        config = body["policy"]["value"]
        _require(day.isoformat() in config["expected_observation_dates"], "observation_unexpected_date")
        cutoff, as_of, observed = [datetime.fromisoformat(body[k]) for k in ("decision_cutoff", "as_of", "observed_at")]
        parent_observed = datetime.fromisoformat(pin["parent_capture_observed_at"])
        for clock in (cutoff, as_of, observed, parent_observed):
            _clock(clock)
        _require(cutoff == datetime.combine(day, _local_time(config["decision_cutoff_time"]), tzinfo=_TAIPEI)
                 and datetime.combine(day, _local_time(config["observation_start_time"]), tzinfo=_TAIPEI)
                 <= as_of <= datetime.combine(day, _local_time(config["observation_end_time"]), tzinfo=_TAIPEI)
                 and cutoff <= as_of <= parent_observed <= observed <= datetime.now(timezone.utc), "observation_clock_mismatch")
        _require(body["source_binding_sha256"] is None or _sha(body["source_binding_sha256"]), "observation_revision_pin_invalid")
        _require(body["cohort_status"] in {"complete", "incomplete", "cancelled"}
                 and body["source_completeness"] in {"complete_declared_cohort", "partial_research"}, "observation_source_status_invalid")
        missing = body["missing_target_data_members"]
        _require(isinstance(missing, list) and all(isinstance(c, str) for c in missing)
                 and missing == sorted(set(missing))
                 and set(missing).issubset(body["policy"]["universe_template"]["value"]["included_stock_codes"])
                 and body["target_data_day_status"] == ("insufficient_or_stale" if missing else "exact_declared_day"),
                 "observation_target_day_invalid")
        accepted = body["cohort_status"] == "complete" and body["source_completeness"] == "complete_declared_cohort" and not missing
        _require(body["acceptance_status"] == ("accepted_research_observation" if accepted else "recorded_incomplete_observation")
                 and body["reason"] == ("fixed_day_parent_verified" if accepted else "parent_or_target_day_incomplete")
                 and (not accepted or _sha(body["source_binding_sha256"])), "observation_false_acceptance")
        return body

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["capture_identity_sha256"])


class BoundedRuleResearchObservationWriter(BoundedRuleResearchCaptureWriter):
    """同一 atomic envelope/容量/partial 邊界，只新增接受記錄 decoder。"""
    def _decode_capture(self, raw: bytes) -> dict[str, Any]:
        return RuleResearchObservationAcceptance(raw.decode("utf-8")).to_dict()

    def _make_receipt(self, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
        return {"schema_version": "rule-research-observation-receipt.v1", "status": "complete",
                "capture_identity_sha256": body["capture_identity_sha256"], "capture_sha256": _digest(raw),
                "observed_at": body["observed_at"], "research_only": True,
                "acceptance_status": body["acceptance_status"], "decision_date": body["decision_date"]}


def build_observation_acceptance(policy_path: str | Path, parent_receipt: str | Path) -> RuleResearchObservationAcceptance:
    policy = load_observation_policy(policy_path)
    body, ready, pin = _parent(parent_receipt)
    _require(body.get("feature_contract_version", DAILY_MARKET_FEATURE_CONTRACT_VERSION)
             == observation_feature_contract_version(policy["value"]), "observation_feature_contract_mismatch")
    _require(_universe_definition(body["universe"]["value"]) == _universe_definition(policy["universe_template"]["value"]),
             "observation_universe_mismatch")
    _require(body["method_contracts_sha256"] == policy["method_contracts_sha256"], "observation_method_mismatch")
    accepted = ready["cohort_status"] == "complete" and ready["source_completeness"] == "complete_declared_cohort" and not ready["missing_target_data_members"]
    result = {"schema_version": ACCEPTANCE_SCHEMA, "policy": policy,
              "policy_sha256": _digest(_json(policy).encode("utf-8")), "qualification": dict(_QUALIFICATION),
              "parent_pin": pin, "decision_date": ready["decision_date"], "decision_cutoff": ready["decision_cutoff"],
              "as_of": ready["as_of"], "observed_at": datetime.now(timezone.utc).isoformat(),
              "source_binding_sha256": body["source_binding_sha256"], "cohort_status": ready["cohort_status"],
              "source_completeness": ready["source_completeness"],
              "target_data_day_status": ready["target_data_day_status"],
              "missing_target_data_members": ready["missing_target_data_members"],
              "acceptance_status": "accepted_research_observation" if accepted else "recorded_incomplete_observation",
              "reason": "fixed_day_parent_verified" if accepted else "parent_or_target_day_incomplete"}
    result["capture_identity_sha256"] = _identity(result)
    capture = RuleResearchObservationAcceptance(_json(result))
    capture.to_dict()
    return capture


def read_observation_days(policy_path: str | Path, acceptance_root: str | Path, *, evaluated_at: datetime,
        outcome_root: str | Path | None = None) -> dict[str, Any]:
    """顯式預期觀測日與exact保存包對照；每個revision都保留，不選latest。"""
    _clock(evaluated_at)
    _require(evaluated_at <= datetime.now(timezone.utc), "observation_future_evaluation")
    policy = load_observation_policy(policy_path)
    policy_sha = _digest(_json(policy).encode("utf-8"))
    writer = BoundedRuleResearchObservationWriter(acceptance_root)
    def inventory_pin() -> list[tuple[str, int, int]] | None:
        _safe_path(writer.output_root)
        if not writer.output_root.exists():
            return None
        _require(not (writer.output_root / ".writer.lock").exists(), "observation_store_busy")
        entries = list(islice(writer.output_root.iterdir(), MAX_CAPTURES + 1))
        _require(len(entries) <= MAX_CAPTURES, "retention_entry_limit")
        return sorted((p.name, p.stat().st_ino, p.stat().st_mtime_ns) for p in entries)
    before_inventory = inventory_pin()
    rows: dict[str, list[dict[str, Any]]] = {d: [] for d in policy["value"]["expected_observation_dates"]}
    other_policy_records = 0
    if writer.output_root.exists():
        _require(not (writer.output_root / ".writer.lock").exists(), "observation_store_busy")
        writer._inventory()
        for entry in islice(writer.output_root.iterdir(), MAX_CAPTURES + 1):
            package = writer.read(entry.name)
            b = package["capture"]
            if b["policy_sha256"] != policy_sha:
                other_policy_records += 1
                continue
            valid, error = True, ""
            try:
                current = build_observation_acceptance(policy_path, b["parent_pin"]["receipt_ref"])
                _require(current.identity_sha256 == b["capture_identity_sha256"], "observation_saved_binding_changed")
            except Exception as exc:
                valid, error = False, str(exc)
            # 此一明示評估時刻之前的觀測才有資格出現在日覆蓋，不借後來資料。
            visible = datetime.fromisoformat(b["parent_pin"]["parent_capture_observed_at"]) <= evaluated_at
            rows[b["decision_date"]].append({"identity_sha256": entry.name,
                "parent_identity_sha256": b["parent_pin"]["parent_identity_sha256"],
                "source_binding_sha256": b["source_binding_sha256"], "as_of": b["as_of"],
                "parent_capture_observed_at": b["parent_pin"]["parent_capture_observed_at"],
                "acceptance_record_observed_at": b["observed_at"],
                "acceptance_status": b["acceptance_status"], "saved_verified": valid,
                "target_data_day_status": b["target_data_day_status"],
                "missing_target_data_members": b["missing_target_data_members"],
                "visible_at_evaluation": visible, "error_code": error})
    days: list[dict[str, Any]] = []
    for day, records in rows.items():
        records.sort(key=lambda r: r["identity_sha256"])
        accepted = [r for r in records if r["saved_verified"] and r["visible_at_evaluation"]
                    and r["acceptance_status"] == "accepted_research_observation"]
        close = datetime.combine(date.fromisoformat(day), _local_time(policy["value"]["observation_end_time"]), tzinfo=_TAIPEI)
        start = datetime.combine(date.fromisoformat(day), _local_time(policy["value"]["observation_start_time"]), tzinfo=_TAIPEI)
        revisions = {r["source_binding_sha256"] for r in accepted}
        status = ("observed_multiple_revision_pins" if len(revisions) > 1 else "observed") if accepted else (
            "missing_complete_observation" if evaluated_at > close else "not_due" if evaluated_at < start else "awaiting_complete_observation")
        days.append({"decision_date": day, "status": status, "accepted_count": len(accepted),
                     "revision_pin_count": len(revisions), "records": records})
    _require(load_observation_policy(policy_path) == policy, "observation_policy_changed")
    _require(inventory_pin() == before_inventory, "observation_inventory_changed")
    if outcome_root is not None:
        from app_module.rule_research_forward_store import read_forward_revision_index
        forward_index: dict[str, list[dict[str, Any]]] = {}
        forward_error = ""
        try:
            forward_index = read_forward_revision_index(outcome_root, evaluated_at=evaluated_at)
        except Exception as exc:
            forward_error = str(exc)
        for day_row in days:
            for record in day_row["records"]:
                try:
                    _require(not forward_error, forward_error)
                    _require(record["saved_verified"], "forward_parent_record_unverified")
                    outcomes = forward_index.get(record["parent_identity_sha256"], [])
                    _require(all(o["decision_date"] == day_row["decision_date"] for o in outcomes), "forward_day_binding_mismatch")
                    record["forward_outcomes"] = outcomes
                    record["forward_status"] = "saved_revisions" if any(o["visible_at_evaluation"] for o in outcomes) else "awaiting_source_or_outcome"
                except Exception as exc:
                    record.update(forward_outcomes=[], forward_status="unavailable_or_unverified", forward_error=str(exc))
    return {"status": "readonly", "policy_id": policy["value"]["policy_id"], "policy_sha256": policy_sha,
            "policy_version": policy["value"]["version"], "other_policy_record_count": other_policy_records,
            "evaluated_at": _clock(evaluated_at), "days": days,
            "missing_observation_dates": [d["decision_date"] for d in days if d["status"] == "missing_complete_observation"],
            "qualification": dict(_QUALIFICATION)}


def preview_or_accept_observation(policy_path: str | Path, parent_receipt: str | Path,
        acceptance_root: str | Path, *, accept: bool = False, evaluated_at: datetime) -> dict[str, Any]:
    writer = BoundedRuleResearchObservationWriter(acceptance_root)
    capture = build_observation_acceptance(policy_path, parent_receipt)
    # 避免把保存記錄寫進producer/parent來源樹或其ancestor。
    parent, _, _ = _parent(parent_receipt)
    for source_root in (Path(parent["snapshot_root"]), Path(parent["capture_root"])):
        _require(not writer.output_root.is_relative_to(source_root.resolve())
                 and not source_root.resolve().is_relative_to(writer.output_root), "observation_source_output_overlap")
    for source_file in (Path(policy_path).absolute(), Path(parent["universe"]["source_ref"]),
                        Path(capture.to_dict()["policy"]["universe_template"]["source_ref"])):
        _require(not source_file.resolve().is_relative_to(writer.output_root), "observation_source_output_overlap")
    _clock(evaluated_at)
    _require(evaluated_at <= datetime.now(timezone.utc), "observation_future_evaluation")
    result: dict[str, Any] = {"status": "preview", "acceptance_capture_status": "not_written",
                             "candidate": capture.to_dict(), "acceptance_saved": False}
    if accept:
        saved = writer.write(capture, revalidate=lambda: build_observation_acceptance(policy_path, parent_receipt))
        result.update(status="saved", acceptance_capture_status=saved["status"], acceptance=saved, acceptance_saved=True)
    try:
        result["day_readiness"] = read_observation_days(policy_path, acceptance_root, evaluated_at=evaluated_at)
        result["day_readiness_status"] = "verified"
    except Exception as exc:
        result.update(day_readiness_status="rejected", error_code=str(exc))
    return result
