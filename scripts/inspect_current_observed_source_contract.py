"""唯讀輸出 daily_prices 的 current-observed 研究來源契約。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app_module.current_observed_source_contract import (  # noqa: E402
    SCHEMA_VERSION,
    build_current_observed_source_contract,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以唯讀、有界窗口檢視 daily_prices，輸出 current-observed research manifest。"
    )
    parser.add_argument("--db-path", required=True, help="SQLite 檔案路徑；以 mode=ro 開啟。")
    parser.add_argument("--source-ref", help="明確來源參照；省略時使用絕對路徑與 daily_prices。")
    parser.add_argument("--decision-cutoff", required=True, help="含時區 ISO-8601，例如 2026-10-05T16:00:00+08:00。")
    parser.add_argument("--as-of-date", required=True, help="Asia/Taipei 的 YYYY-MM-DD 決策日期。")
    parser.add_argument("--window-trading-days", required=True, type=int, help="必填且最多 60 個來源交易日；不是暖機門檻。")
    parser.add_argument("--symbols", nargs="*", help="明示研究 cohort；省略時分母為 unknown，不代表全市場。")
    parser.add_argument("--source-pin-file", help="可選 JSON 檔，欄位比對目前來源 stat/schema pin。")
    parser.add_argument("--expected-scope-identity", help="可選 symbols-sha256:... scope pin。")
    parser.add_argument("--expected-rowset-sha256", help="可選前次 scoped rowset content hash pin。")
    parser.add_argument("--feature-spec-file", help="可選 JSON list 或 {'features': [...]}；省略時 feature/warm-up 為 unknown。")
    parser.add_argument("--company-classification-csv", help="可選目前公司分類 CSV；只作 current-only metadata。")
    parser.add_argument("--benchmark-evidence-file", help="可選 caller-provided benchmark identity/window JSON；本工具不驗證。")
    parser.add_argument("--output", help="可選新 JSON 檔；只允許寫入 repo output/qa/，且不覆寫既有檔案。")
    return parser


def _read_json(path: str | None) -> Any:
    if path is None:
        return None
    with Path(path).expanduser().open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _parse_cutoff(raw: str) -> datetime:
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    cutoff = datetime.fromisoformat(value)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("decision-cutoff 必須含時區。")
    return cutoff


def _qa_output_path(raw_path: str | None, db_path: str) -> Path | None:
    if raw_path is None:
        return None
    output_path = Path(raw_path).expanduser().resolve()
    qa_root = (REPOSITORY_ROOT / "output" / "qa").resolve()
    try:
        output_path.relative_to(qa_root)
    except ValueError as exc:
        raise ValueError("--output 只允許寫入 repository output/qa/ 目錄。") from exc
    if output_path == Path(db_path).expanduser().resolve():
        raise ValueError("--output 不可指向來源 SQLite。")
    if output_path.suffix.lower() != ".json":
        raise ValueError("--output 必須使用 .json 副檔名。")
    if output_path.exists():
        raise FileExistsError("--output 只建立新 QA receipt，不覆寫既有檔案。")
    return output_path


def _write_result(payload: dict[str, Any], output_path: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered + "\n")
    print(rendered)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output_path = _qa_output_path(args.output, args.db_path)
        cutoff = _parse_cutoff(args.decision_cutoff)
        as_of_date = date.fromisoformat(args.as_of_date)
        source_pin = _read_json(args.source_pin_file)
        feature_spec_payload = _read_json(args.feature_spec_file)
        if isinstance(feature_spec_payload, dict):
            if "features" not in feature_spec_payload:
                raise ValueError("feature spec JSON object 必須包含 features 清單")
            feature_specs = feature_spec_payload["features"]
        elif feature_spec_payload is None:
            feature_specs = []
        else:
            feature_specs = feature_spec_payload
        benchmark = _read_json(args.benchmark_evidence_file)
        if source_pin is not None and not isinstance(source_pin, dict):
            raise ValueError("source pin JSON 必須是 object")
        if not isinstance(feature_specs, list) or any(
            not isinstance(item, dict) for item in feature_specs
        ):
            raise ValueError("feature spec 必須是 object 清單")
        if benchmark is not None and not isinstance(benchmark, dict):
            raise ValueError("benchmark evidence JSON 必須是 object")
        contract = build_current_observed_source_contract(
            args.db_path,
            decision_cutoff=cutoff,
            as_of_date=as_of_date,
            window_trading_days=args.window_trading_days,
            symbols=args.symbols,
            source_ref=args.source_ref,
            expected_source_pin=source_pin,
            expected_scope_identity=args.expected_scope_identity,
            expected_rowset_sha256=args.expected_rowset_sha256,
            feature_specs=feature_specs,
            company_classification_csv=args.company_classification_csv,
            benchmark_evidence=benchmark,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        contract = {
            "schema_version": SCHEMA_VERSION,
            "status": "rejected",
            "research_only": True,
            "historical_pit_eligible": False,
            "formal_training_eligible": False,
            "published_snapshot": False,
            "blockers": [
                {"code": "invalid_request", "message": f"輸入或輸出檢查失敗：{type(exc).__name__}。"}
            ],
        }
        output_path = None
        if args.output:
            try:
                output_path = _qa_output_path(args.output, args.db_path)
            except (OSError, ValueError):
                output_path = None
    _write_result(contract, output_path)
    return 2 if contract.get("status") == "rejected" else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
