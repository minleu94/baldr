"""驗證不可變、僅供研究的 MOPS T164 至發行人 PDF 列級橋接。"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from data_module.mops_statement_candidate_adapter import load_mops_statement_candidate


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_COUNTS = {
    "balance_sheet": 57,
    "income_statement": 37,
    "cash_flows_statement": 78,
}
_SUMMARY_STATUSES = {
    "direct",
    "code_alias",
    "aggregates",
    "zero_vs_dash",
    "no_independent_pdf_row",
    "unresolved",
}


def validate_mops_t164_pdf_disposition_bundle(
    *,
    candidate_path: Path,
    official_pdf_path: Path,
    summary_path: Path,
    balance_sheet_pdf_bridge_path: Path,
    balance_sheet_open_data_bridge_path: Path,
    income_statement_bridge_path: Path,
    cash_flow_bridge_path: Path,
) -> dict[str, Any]:
    """檢查 172 列候選是否被 statement bridges 完整且唯一地分類。

    驗證 bridge 檔案對候選與 PDF 的 hash binding、row identity、列數、列級
    classification 及摘要計數。此工具不重讀 PDF、不抽取財務值，也不替來源
    授權、正式版本認領、品質狀態、Gate、PIT 或 ML 給予資格。
    """
    paths = {
        "candidate": Path(candidate_path),
        "official_pdf": Path(official_pdf_path),
        "summary": Path(summary_path),
        "balance_sheet_pdf": Path(balance_sheet_pdf_bridge_path),
        "balance_sheet_open_data": Path(balance_sheet_open_data_bridge_path),
        "income_statement": Path(income_statement_bridge_path),
        "cash_flows_statement": Path(cash_flow_bridge_path),
    }
    payloads = {
        name: _load_json(path)
        for name, path in paths.items()
        if name != "official_pdf"
    }
    hashes = {name: _file_sha256(path) for name, path in paths.items()}
    candidate = payloads["candidate"]
    summary = payloads["summary"]

    _require(candidate.get("schema_version") == "mops-statement-pit-candidate.v2", "candidate schema unsupported")
    _require(candidate.get("source_id") == "mops.statement.publication", "candidate source is unsupported")
    _require(candidate.get("research_only") is True, "candidate must remain research_only")
    for field in ("formal_oos_allowed", "formal_credit_authorized"):
        _require(candidate.get(field) is False, f"candidate {field} must be false")

    candidate_sha = hashes["candidate"]
    pdf_sha = hashes["official_pdf"]
    _require(_is_sha256(candidate_sha), "candidate file SHA-256 is invalid")
    _require(summary.get("schema_version") == "baldr.q2.t164_v2.full_pdf_content_bridge_summary.v1", "summary schema unsupported")
    _require(summary.get("candidate_projection_sha256") == candidate_sha, "summary candidate hash mismatch")
    _require(_is_sha256(pdf_sha), "official PDF file SHA-256 is invalid")
    pdf_reference_status = {
        name: _pdf_reference_status(payload.get("official_pdf_sha256"), pdf_sha)
        for name, payload in payloads.items()
        if name != "candidate"
    }
    _require(
        all(status in {"exact", "single_character_omission"} for status in pdf_reference_status.values()),
        "a PDF bridge reference does not match the official PDF bytes",
    )
    _require(summary.get("company") == "2330" and summary.get("period") == "2026-Q2", "summary identity is not the expected Q2 slice")

    rows = candidate.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("candidate rows are missing")
    candidate_by_code: dict[str, Mapping[str, Any]] = {}
    counts_by_statement: Counter[str] = Counter()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"candidate row {index} must be an object")
        code = _required_text(row, "item_code", f"candidate row {index}")
        _require(code not in candidate_by_code, f"duplicate candidate item_code: {code}")
        _require(row.get("stock_code") == "2330", f"candidate row {code} has wrong company")
        _require(row.get("period") == "2026-Q2", f"candidate row {code} has wrong period")
        _require(row.get("statement_scope") == "consolidated", f"candidate row {code} is not consolidated")
        statement_type = _required_text(row, "statement_type", f"candidate row {code}")
        _require(statement_type in _EXPECTED_COUNTS, f"unsupported candidate statement type: {statement_type}")
        candidate_by_code[code] = row
        counts_by_statement[statement_type] += 1
    _require(dict(counts_by_statement) == _EXPECTED_COUNTS, "candidate statement row counts do not match expected counts")
    consumer_rows = load_mops_statement_candidate(paths["candidate"])
    _require(len(consumer_rows) == len(candidate_by_code), "candidate consumer row count mismatch")
    consumer_identity = {
        (row.item_code, row.statement_type, row.period, row.period_basis, row.value_unit, row.value_scale)
        for row in consumer_rows
    }
    candidate_identity = {
        (
            code,
            str(row["statement_type"]),
            str(row["period"]),
            str(row["period_basis"]),
            str(row["value_unit"]),
            int(row["value_scale"]),
        )
        for code, row in candidate_by_code.items()
    }
    _require(consumer_identity == candidate_identity, "candidate consumer contract identity mismatch")

    statement_rows: dict[str, list[tuple[str, str]]] = {
        "balance_sheet": [],
        "income_statement": [],
        "cash_flows_statement": [],
    }
    _verify_common_bridge(
        payloads["balance_sheet_pdf"], candidate_sha, pdf_sha,
        company="2330", period="2026-Q2", row_field="rows",
    )
    for item in payloads["balance_sheet_pdf"]["rows"]:
        code = _bridge_code(item, "balance-sheet PDF row")
        mapping = _required_text(item, "pdf_mapping", f"balance-sheet PDF row {code}")
        status = _balance_sheet_pdf_status(mapping)
        statement_rows["balance_sheet"].append((code, status))

    open_data = payloads["balance_sheet_open_data"]
    _require(open_data.get("official_pdf_sha256") == pdf_sha, "balance-sheet Open Data bridge must provide the exact PDF byte hash")
    _verify_common_bridge(
        open_data, candidate_sha, pdf_sha,
        company="2330", period="2026-Q2", row_field="rows",
    )
    _require(open_data.get("candidate_source_version") == candidate.get("source_version"), "balance-sheet Open Data source version mismatch")
    for item in open_data["rows"]:
        code = _bridge_code(item, "balance-sheet Open Data row")
        candidate_row = candidate_by_code.get(code)
        if candidate_row is None:
            raise ValueError(f"Open Data bridge row is absent from candidate: {code}")
        for bridge_field, candidate_field in (
            ("numeric_source_row_sha256", "numeric_source_row_sha256"),
            ("official_item_name", "official_item_name"),
            ("period_basis", "period_basis"),
            ("unit", "value_unit"),
            ("scale", "value_scale"),
        ):
            _require(item.get(bridge_field) == candidate_row.get(candidate_field), f"Open Data bridge {bridge_field} mismatch for {code}")
        _require(item.get("period") == candidate_row.get("period"), f"Open Data bridge period mismatch for {code}")
        comparison = _required_text(item, "pdf_comparison", f"balance-sheet Open Data row {code}")
        status = "code_alias" if "alias" in comparison else "direct"
        statement_rows["balance_sheet"].append((code, status))

    _verify_common_bridge(
        payloads["income_statement"], candidate_sha, pdf_sha,
        company="2330", period="2026-Q2", row_field="rows",
    )
    for item in payloads["income_statement"]["rows"]:
        code = _bridge_code(item, "income-statement row")
        comparison = _required_text(item, "comparison", f"income-statement row {code}")
        status = _income_status(comparison)
        statement_rows["income_statement"].append((code, status))

    _verify_common_bridge(
        payloads["cash_flows_statement"], candidate_sha, pdf_sha,
        company="2330", period="2026-Q2", row_field="rows",
    )
    for item in payloads["cash_flows_statement"]["rows"]:
        code = _bridge_code(item, "cash-flow row")
        comparison = _required_text(item, "comparison", f"cash-flow row {code}")
        status = _cash_flow_status(comparison)
        statement_rows["cash_flows_statement"].append((code, status))

    all_classifications: dict[str, str] = {}
    actual_counts: dict[str, dict[str, int]] = {}
    for statement_type, classifications in statement_rows.items():
        _require(len(classifications) == _EXPECTED_COUNTS[statement_type], f"{statement_type} bridge row count mismatch")
        local_codes: set[str] = set()
        counter: Counter[str] = Counter()
        for code, status in classifications:
            _require(code in candidate_by_code, f"bridge row not found in candidate: {code}")
            _require(code not in local_codes, f"duplicate {statement_type} bridge row: {code}")
            _require(candidate_by_code[code].get("statement_type") == statement_type, f"bridge statement identity mismatch for {code}")
            _require(status in _SUMMARY_STATUSES, f"unsupported classification status for {code}: {status}")
            local_codes.add(code)
            all_classifications[code] = status
            counter[status] += 1
        expected_codes = {
            code for code, row in candidate_by_code.items()
            if row.get("statement_type") == statement_type
        }
        _require(local_codes == expected_codes, f"{statement_type} bridge does not account for every candidate row")
        actual_counts[statement_type] = dict(sorted(counter.items()))

    _require(set(all_classifications) == set(candidate_by_code), "classification bundle does not cover every candidate row")
    _validate_summary_counts(summary, actual_counts)
    unresolved_codes = sorted(code for code, status in all_classifications.items() if status == "unresolved")
    _require(unresolved_codes == sorted(summary.get("unresolved_codes", [])), "summary unresolved codes mismatch")
    _require(summary.get("candidate_rows_classified") == len(candidate_by_code), "summary total row count mismatch")
    _require(summary.get("total_statuses") == dict(sorted(Counter(all_classifications.values()).items())), "summary total classification counts mismatch")

    for payload_name in ("balance_sheet_pdf", "balance_sheet_open_data", "income_statement", "cash_flows_statement", "summary"):
        _require_fail_closed(payloads[payload_name], payload_name)

    return {
        "schema_version": "baldr.mops-t164-pdf-disposition-integrity.v1",
        "research_only": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "candidate_sha256": candidate_sha,
        "official_pdf_sha256": pdf_sha,
        "pdf_reference_status": pdf_reference_status,
        "pdf_reference_corrections": {
            name: {
                "observed_reference": payloads[name].get("official_pdf_sha256"),
                "verified_pdf_bytes_sha256": pdf_sha,
            }
            for name, status in pdf_reference_status.items()
            if status == "single_character_omission"
        },
        "candidate_row_count": len(candidate_by_code),
        "classified_row_count": len(all_classifications),
        "statement_row_counts": dict(sorted(counts_by_statement.items())),
        "statement_status_counts": actual_counts,
        "total_status_counts": dict(sorted(Counter(all_classifications.values()).items())),
        "unresolved_codes": unresolved_codes,
        "bridge_sha256": {
            name: hashes[name]
            for name in (
                "balance_sheet_pdf",
                "balance_sheet_open_data",
                "income_statement",
                "cash_flows_statement",
            )
        },
        "summary_sha256": hashes["summary"],
        "bridge_artifact_binding_verified": True,
        "row_accounting_verified": True,
        "candidate_consumer_contract_validated": True,
        "pdf_content_reopened": False,
        "formal_db_write": False,
        "formal_source_acceptance": False,
        "quality_release": False,
        "gate_credit": False,
        "pit_credit": False,
        "ml_credit": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON artifact: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _required_text(row: Mapping[str, Any], field: str, label: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} missing {field}")
    return value.strip()


def _bridge_code(row: object, label: str) -> str:
    if not isinstance(row, Mapping):
        raise ValueError(f"{label} must be an object")
    return _required_text(row, "item_code", label)


def _verify_common_bridge(
    payload: Mapping[str, Any],
    candidate_sha: str,
    pdf_sha: object,
    *,
    company: str,
    period: str,
    row_field: str,
) -> None:
    _require(payload.get("company") == company and payload.get("period") == period, "bridge company/period mismatch")
    _require(
        _pdf_reference_status(payload.get("official_pdf_sha256"), str(pdf_sha))
        in {"exact", "single_character_omission"},
        "bridge official PDF hash mismatch",
    )
    candidate_hashes = {
        payload.get("candidate_projection_sha256"),
        payload.get("candidate_sha256"),
        payload.get("candidate_artifact_sha256"),
    }
    candidate_hashes.discard(None)
    _require(candidate_hashes == {candidate_sha}, "bridge candidate hash mismatch")
    rows = payload.get(row_field)
    if not isinstance(rows, list) or not rows:
        raise ValueError("bridge rows are missing")
    for field in ("formal_db_write", "gate_credit", "numeric_values_emitted"):
        _require(payload.get(field) is False, f"bridge {field} must be false")
    if "ml_credit" in payload:
        _require(payload.get("ml_credit") is False, "bridge ml_credit must be false")


def _pdf_reference_status(reference: object, official_sha256: str) -> str:
    """僅接受精確 PDF hash，或可由實際 PDF hash 刪去單一字元得到的舊引用。"""
    if reference == official_sha256:
        return "exact"
    if not isinstance(reference, str) or len(reference) != 63:
        return "mismatch"
    for index in range(len(official_sha256)):
        if official_sha256[:index] + official_sha256[index + 1 :] == reference:
            return "single_character_omission"
    return "mismatch"


def _balance_sheet_pdf_status(mapping: str) -> str:
    if mapping == "direct_pdf_code_label_value_match":
        return "direct"
    if mapping == "candidate_zero_pdf_dash":
        return "zero_vs_dash"
    if mapping == "no_standalone_pdf_page4_row":
        return "no_independent_pdf_row"
    if mapping.startswith("pdf_") and "_aggregate" in mapping:
        return "aggregates"
    raise ValueError(f"unsupported balance-sheet PDF mapping: {mapping}")


def _income_status(comparison: str) -> str:
    if comparison == "exact_visual_match":
        return "direct"
    if comparison == "label_and_value_match_code_differs":
        return "code_alias"
    if comparison == "candidate_value_reconciles_to_pdf_components":
        return "aggregates"
    if comparison == "no_independent_pdf_line":
        return "no_independent_pdf_row"
    if comparison == "candidate_zero_rendered_as_dash":
        return "zero_vs_dash"
    raise ValueError(f"unsupported income-statement comparison: {comparison}")


def _cash_flow_status(comparison: str) -> str:
    if comparison == "direct_label_value_match":
        return "direct"
    if comparison == "candidate_zero_pdf_dash":
        return "zero_vs_dash"
    if comparison == "candidate_aggregates_multiple_pdf_lines":
        return "aggregates"
    if comparison.startswith("no_standalone_pdf_row"):
        return "no_independent_pdf_row"
    if comparison.startswith("unresolved_"):
        return "unresolved"
    raise ValueError(f"unsupported cash-flow comparison: {comparison}")


def _validate_summary_counts(summary: Mapping[str, Any], actual: Mapping[str, Mapping[str, int]]) -> None:
    statements = summary.get("statements")
    if not isinstance(statements, list):
        raise ValueError("summary statement counts are missing")
    expected_by_statement = {
        "balance_sheet": {"direct": 50, "code_alias": 1, "aggregates": 3, "zero_vs_dash": 1, "no_independent_pdf_row": 2, "unresolved": 0},
        "income_statement": {"direct": 33, "code_alias": 1, "aggregates": 1, "zero_vs_dash": 1, "no_independent_pdf_row": 1, "unresolved": 0},
        "cash_flows_statement": {"direct": 64, "code_alias": 0, "aggregates": 1, "zero_vs_dash": 2, "no_independent_pdf_row": 7, "unresolved": 4},
    }
    rows_by_type = {item.get("statement"): item for item in statements if isinstance(item, Mapping)}
    _require(set(rows_by_type) == set(_EXPECTED_COUNTS), "summary statement identities are incomplete")
    for statement_type, expected_counts in expected_by_statement.items():
        row = rows_by_type[statement_type]
        _require(row.get("rows") == _EXPECTED_COUNTS[statement_type], f"summary {statement_type} row count mismatch")
        observed_counts = {status: int(row.get(status, 0)) for status in _SUMMARY_STATUSES}
        _require(observed_counts == expected_counts, f"summary {statement_type} counts are unexpected")
        _require(actual.get(statement_type) == {key: value for key, value in expected_counts.items() if value}, f"{statement_type} row classifications differ from summary")


def _require_fail_closed(payload: Mapping[str, Any], label: str) -> None:
    for field in ("formal_db_write", "gate_credit", "pit_credit", "ml_credit"):
        if field in payload:
            _require(payload.get(field) is False, f"{label} {field} must be false")
    for field in ("source_acceptance", "formal_source_acceptance"):
        if field in payload:
            _require(payload.get(field) is False, f"{label} {field} must be false")

\n