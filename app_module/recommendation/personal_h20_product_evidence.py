"""個人 H20 公開讀回的產品投影；不建立推薦、不推論、不訓練。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Literal, Mapping
import hashlib
import json
import os
from pathlib import Path
import uuid

from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation, _activation_paths, read_personal_h20_activation,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.personal_store_selection import assert_personal_store_path
from app_module.recommendation.queries import _read_regular_file_no_follow


@dataclass(frozen=True, slots=True)
class PersonalH20ProductEvidence:
    stock_code: str
    status: Literal["available", "pending", "disabled", "unavailable"]
    reason: str
    gross_return_bp: int | None = None
    decision_date: str | None = None
    source_date: str | None = None
    feature_date: str | None = None
    observed_at: str | None = None
    candidate_id: str | None = None
    sample_id: str | None = None
    prediction_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"available", "pending", "disabled", "unavailable"} or not self.stock_code:
            raise ValueError("personal_h20_product_status_or_stock_required")
        if self.status == "available":
            if (type(self.gross_return_bp) is not int or not self.candidate_id
                    or not self.sample_id or not self.prediction_id or not self.observed_at
                    or not self.decision_date or not self.source_date or not self.feature_date):
                raise ValueError("personal_h20_product_available_evidence_required")
            if date.fromisoformat(self.feature_date) >= date.fromisoformat(self.decision_date):
                raise ValueError("personal_h20_product_future_feature")
            if date.fromisoformat(self.source_date) > date.fromisoformat(self.decision_date):
                raise ValueError("personal_h20_product_future_source")
            clock = datetime.fromisoformat(self.observed_at)
            if clock.tzinfo is None or clock.utcoffset() is None:
                raise ValueError("personal_h20_product_clock_unknown")


def project_personal_h20_product_evidence(
    capture: Mapping[str, Any], *, stock_code: str,
    expected_candidate_id: str, expected_contract_hash: str,
) -> PersonalH20ProductEvidence:
    """只消費 public reader 已驗原 capture；另核 caller 選股／啟用模型。"""
    source, contract, prediction = capture["source_binding"], capture["contract_binding"], capture["prediction"]
    if (capture["identity"]["symbol"] != stock_code
            or contract["candidate_id"] != expected_candidate_id
            or contract["contract_hash"] != expected_contract_hash
            or prediction["request"]["symbol"] != stock_code):
        raise ValueError("personal_h20_product_identity_mismatch")
    if (capture["research_only"] is not True or any(capture.get(key) is not False for key in
            ("historical_pit_eligible", "formal_training_allowed", "production_action_allowed", "promotion_credit_created"))
            or prediction["status"] != "h20_gross_available"
            or type(prediction["predicted_gross_return_bp"]) is not int):
        raise ValueError("personal_h20_product_qualification_or_output_mismatch")
    observed = datetime.fromisoformat(capture["observed_at"])
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("personal_h20_product_clock_unknown")
    decision = source["decision_date"]
    source_date = source["pins"]["cycle_source_date"]
    feature_date = prediction["request"]["feature_as_of_date"]
    if date.fromisoformat(feature_date) >= date.fromisoformat(decision):
        raise ValueError("personal_h20_product_future_feature")
    date.fromisoformat(source_date)
    return PersonalH20ProductEvidence(stock_code, "available", "自然結果待原entry與20交易日核驗",
        prediction["predicted_gross_return_bp"], decision, source_date, feature_date,
        capture["observed_at"], expected_candidate_id, capture["sample_id"], prediction["prediction_id"])


def personal_h20_product_text(evidence: PersonalH20ProductEvidence) -> str:
    if evidence.status != "available" or evidence.gross_return_bp is None:
        labels = {"pending": "等待受驗預測", "disabled": "已停用", "unavailable": "目前無法核驗"}
        return "個人 H20 模型：" + labels.get(evidence.status, "未知") + "｜" + evidence.reason
    magnitude = abs(evidence.gross_return_bp)
    sign = "-" if evidence.gross_return_bp < 0 else "+"
    percent = f"{sign}{magnitude // 100}.{magnitude % 100:02d}%"
    holdout = ("holdout 比 null 差230 bp，after-cost 未證明"
        if evidence.candidate_id == "rec-cal-3f8b2c276ef316e28de3806d"
        else "此讀回未證明優於基準或扣成本結果")
    return (f"個人研究模型已啟用｜未扣成本的20交易日預測：{percent}（{evidence.gross_return_bp} bp）\n"
        f"預測日 {evidence.decision_date}｜來源日 {evidence.source_date}｜特徵截至 {evidence.feature_date}\n"
        f"模型 {evidence.candidate_id}｜原觀測 {evidence.observed_at}\n"
        f"自然結果待核驗；{holdout}；不授交易或正式/PIT資格。")


def publish_personal_h20_product_reference(
    activation: PersonalH20Activation, *, receipt_path: str, receipt_sha256: str,
    decision_date: str, cycle_id: str,
) -> None:
    """只發佈原producer收據的指標，不存另一份prediction。"""
    root = Path(activation.personal_root)
    selected = Path(receipt_path)
    if not activation.enabled or not selected.is_relative_to(root) or selected == root:
        raise ValueError("personal_h20_product_receipt_outside_root")
    if len(receipt_sha256) != 71 or not receipt_sha256.startswith("sha256:"):
        raise ValueError("personal_h20_product_receipt_pin_required")
    int(receipt_sha256[7:], 16)
    date.fromisoformat(decision_date)
    body = {"schema_version": "personal-h20-product-reference.v1", "receipt_path": receipt_path,
        "receipt_sha256": receipt_sha256, "decision_date": decision_date, "cycle_id": cycle_id,
        "activation_revision": activation.revision, "scope_id": activation.scope_id,
        "candidate_id": activation.candidate_id, "contract_hash": activation.model_contract_hash}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    paths = _activation_paths(activation.market_root, activation.personal_root)
    pointer = root / "h20_product_reference.json"
    lock = root / "h20_product_reference.lock"
    assert_personal_store_path(paths, lock)
    with open(to_internal_io_path(lock), "xb"):
        pass
    temporary = root / (".h20-product-" + uuid.uuid4().hex + ".json")
    try:
        if read_personal_h20_activation(activation.config_path) != activation:
            raise ValueError("personal_h20_activation_changed_before_reference")
        assert_personal_store_path(paths, pointer)
        if pointer.exists():
            current = json.loads(_read_regular_file_no_follow(pointer, root, max_bytes=64 * 1024))
            if current["decision_date"] > decision_date:
                raise ValueError("personal_h20_product_reference_regression")
        history = root / ("h20_product_reference." + hashlib.sha256(raw).hexdigest() + ".json")
        assert_personal_store_path(paths, history)
        if history.exists():
            if _read_regular_file_no_follow(history, root, max_bytes=64 * 1024) != raw:
                raise ValueError("personal_h20_product_history_conflict")
        else:
            with open(to_internal_io_path(history), "xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        assert_personal_store_path(paths, temporary)
        with open(to_internal_io_path(temporary), "xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if read_personal_h20_activation(activation.config_path) != activation:
            raise ValueError("personal_h20_activation_changed_during_reference")
        assert_personal_store_path(paths, pointer)
        os.replace(to_internal_io_path(temporary), to_internal_io_path(pointer))
        if _read_regular_file_no_follow(pointer, root, max_bytes=64 * 1024) != raw:
            raise ValueError("personal_h20_product_reference_readback_mismatch")
    finally:
        assert_personal_store_path(paths, lock)
        Path(to_internal_io_path(lock)).unlink()


def save_personal_h20_daily_manifest(
    activation: PersonalH20Activation, result: Mapping[str, Any], *, expected_symbols: list[str],
    prediction_reader: Callable[..., Mapping[str, Any]],
) -> tuple[Path, str, Mapping[str, Any]]:
    """驗原producer全分母後保存單一metadata manifest，沒有prediction副本。"""
    root = Path(activation.personal_root)
    if (result["status"] != "completed" or result["candidate_id"] != activation.candidate_id
            or result["contract_hash"] != activation.model_contract_hash
            or not expected_symbols or len(set(expected_symbols)) != len(expected_symbols)
            or len(result["captures"]) != len(expected_symbols)):
        raise ValueError("personal_h20_manifest_full_scope_required")
    captures = []
    decisions = set()
    for pin in result["captures"]:
        capture = prediction_reader(pin["path"], root=root, expected_sha256=pin["raw_sha256"])
        symbol = capture["identity"]["symbol"]
        project_personal_h20_product_evidence(capture, stock_code=symbol,
            expected_candidate_id=activation.candidate_id, expected_contract_hash=activation.model_contract_hash)
        if capture["source_binding"]["cycle_id"] != result["cycle_id"]:
            raise ValueError("personal_h20_manifest_cycle_mismatch")
        decisions.add(capture["source_binding"]["decision_date"])
        captures.append({"symbol": symbol, "path": pin["path"], "raw_sha256": pin["raw_sha256"],
            "sample_id": capture["sample_id"], "prediction_id": capture["prediction"]["prediction_id"]})
    if sorted(pin["symbol"] for pin in captures) != sorted(expected_symbols) or len(decisions) != 1:
        raise ValueError("personal_h20_manifest_complete_denominator_mismatch")
    body = {"schema_version": "personal-h20-daily-manifest.v1", "status": "completed",
        "candidate_id": activation.candidate_id, "contract_hash": activation.model_contract_hash,
        "cycle_id": result["cycle_id"], "decision_date": decisions.pop(), "symbols": sorted(expected_symbols),
        "captures": sorted(captures, key=lambda item: item["symbol"]),
        "historical_pit_eligible": False, "formal_training_allowed": False, "production_action_allowed": False}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > 64 * 1024:
        raise ValueError("personal_h20_manifest_over_budget")
    paths = _activation_paths(activation.market_root, activation.personal_root)
    directory = root / "h20_daily_receipts"
    pointer = directory / (hashlib.sha256(raw).hexdigest() + ".json")
    assert_personal_store_path(paths, pointer)
    Path(to_internal_io_path(directory)).mkdir(exist_ok=True)
    assert_personal_store_path(paths, pointer)
    if not pointer.exists():
        temporary = directory / (".h20-manifest-" + uuid.uuid4().hex + ".json")
        assert_personal_store_path(paths, temporary)
        with open(to_internal_io_path(temporary), "xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            assert_personal_store_path(paths, pointer)
            try:
                os.link(to_internal_io_path(temporary), to_internal_io_path(pointer))
            except FileExistsError:
                pass
        finally:
            Path(to_internal_io_path(temporary)).unlink()
    assert_personal_store_path(paths, pointer)
    if _read_regular_file_no_follow(pointer, directory, max_bytes=64 * 1024) != raw:
        raise ValueError("personal_h20_manifest_create_only_conflict")
    return pointer, "sha256:" + hashlib.sha256(raw).hexdigest(), body


def read_personal_h20_daily_manifest(
    path: str | Path, *, root: Path, expected_sha256: str,
    prediction_reader: Callable[..., Mapping[str, Any]], selected_stock: str | None = None,
) -> Mapping[str, Any]:
    """讀原manifest raw pin；產品僅選股的重source核驗，其他列不借身份。"""
    file = Path(path)
    if file.parent != root / "h20_daily_receipts":
        raise ValueError("personal_h20_manifest_outside_store")
    raw = _read_regular_file_no_follow(file, file.parent, max_bytes=64 * 1024)
    if ("sha256:" + hashlib.sha256(raw).hexdigest() != expected_sha256
            or file.name != hashlib.sha256(raw).hexdigest() + ".json"):
        raise ValueError("personal_h20_manifest_raw_pin_mismatch")
    body = json.loads(raw)
    symbols = body["symbols"]
    if (body["schema_version"] != "personal-h20-daily-manifest.v1" or body["status"] != "completed"
            or symbols != sorted(set(symbols)) or not 1 <= len(symbols) <= 50
            or sorted(pin["symbol"] for pin in body["captures"]) != symbols
            or any(body.get(key) is not False for key in
                ("historical_pit_eligible", "formal_training_allowed", "production_action_allowed"))):
        raise ValueError("personal_h20_manifest_schema_or_scope_mismatch")
    for pin in body["captures"]:
        if selected_stock is not None and pin["symbol"] != selected_stock:
            continue
        capture = prediction_reader(pin["path"], root=root, expected_sha256=pin["raw_sha256"])
        project_personal_h20_product_evidence(capture, stock_code=pin["symbol"],
            expected_candidate_id=body["candidate_id"], expected_contract_hash=body["contract_hash"])
        if (capture["source_binding"]["cycle_id"] != body["cycle_id"]
                or capture["source_binding"]["decision_date"] != body["decision_date"]
                or capture["sample_id"] != pin["sample_id"]
                or capture["prediction"]["prediction_id"] != pin["prediction_id"]):
            raise ValueError("personal_h20_manifest_original_capture_mismatch")
    return body


def read_personal_h20_product_for_stock(
    config_path: Path, *, stock_code: str, market_root: Path,
    daily_reader: Callable[..., Mapping[str, Any]], prediction_reader: Callable[..., Mapping[str, Any]],
) -> PersonalH20ProductEvidence:
    """同一公開store受驗讀回；失敗回缺件，絕不呼predictor或補存。"""
    try:
        activation = read_personal_h20_activation(config_path)
        if Path(activation.market_root) != market_root:
            raise ValueError("personal_h20_product_market_mismatch")
        if not activation.enabled:
            return PersonalH20ProductEvidence(stock_code, "disabled", "已停止新增模型研究預測；原保存值保留")
        root = Path(activation.personal_root)
        pointer = root / "h20_product_reference.json"
        paths = _activation_paths(activation.market_root, activation.personal_root)
        assert_personal_store_path(paths, pointer)
        body = json.loads(_read_regular_file_no_follow(pointer, root, max_bytes=64 * 1024))
        if (body["schema_version"] != "personal-h20-product-reference.v1"
                or body["activation_revision"] != activation.revision
                or body["scope_id"] != activation.scope_id
                or body["candidate_id"] != activation.candidate_id
                or body["contract_hash"] != activation.model_contract_hash):
            raise ValueError("personal_h20_product_reference_identity_mismatch")
        selected_receipt = Path(body["receipt_path"])
        if not selected_receipt.is_absolute() or not selected_receipt.is_relative_to(root):
            raise ValueError("personal_h20_product_receipt_outside_root")
        assert_personal_store_path(paths, selected_receipt)
        daily = daily_reader(str(selected_receipt), root=root, expected_sha256=body["receipt_sha256"],
                            selected_stock=stock_code)
        if (daily["status"] != "completed" or daily["candidate_id"] != activation.candidate_id
                or daily["contract_hash"] != activation.model_contract_hash or daily["cycle_id"] != body["cycle_id"]):
            raise ValueError("personal_h20_product_daily_identity_mismatch")
        matches = []
        for pin in daily["captures"]:
            # manifest須帶symbol；exact原capture由其public reader再核。
            if pin["symbol"] == stock_code:
                matches.append(pin)
        if not matches:
            return PersonalH20ProductEvidence(stock_code, "pending", "此股不在已保存每日模型範圍；不借用其他股票")
        if len(matches) != 1:
            raise ValueError("personal_h20_product_duplicate_selected_stock")
        pin = matches[0]
        capture = prediction_reader(pin["path"], root=root, expected_sha256=pin["raw_sha256"])
        if capture["source_binding"]["decision_date"] != body["decision_date"]:
            raise ValueError("personal_h20_product_decision_mismatch")
        evidence = project_personal_h20_product_evidence(capture, stock_code=stock_code,
            expected_candidate_id=activation.candidate_id, expected_contract_hash=activation.model_contract_hash)
        if read_personal_h20_activation(config_path) != activation:
            raise ValueError("personal_h20_activation_changed_during_product_read")
        return evidence
    except FileNotFoundError:
        return PersonalH20ProductEvidence(stock_code, "pending", "等待每日已保存收據／配置；不以QA檔代替")
    except Exception as exc:
        return PersonalH20ProductEvidence(stock_code, "unavailable", str(exc)[:300])
