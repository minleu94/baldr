"""建立 Revision-Aware Research Raw Candidate 的 CLI 入口。

用法範例：
  .\\.venv\\Scripts\\python.exe scripts\\build_ml_revision_aware_raw_candidate.py `
    --snapshot-db output/qa/snapshot.sqlite `
    --expected-snapshot-sha256 sha256:... `
    --decision-at 2026-09-30 `
    --output-dir output/qa/ml_revision_aware_raw_candidates/candidate_01 `
    --custody-dir output/qa/ml_revision_aware_raw_candidates/candidate_01_custody
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.ml_revision_aware_raw_candidate import (
    RevisionAwareCandidateError,
    RevisionAwareRawCandidateBuilder,
    RevisionAwareRawRequest,
)


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an isolated, revision-aware research raw candidate dataset."
    )
    parser.add_argument(
        "--snapshot-db",
        type=Path,
        required=True,
        help="Path to verified read-only snapshot SQLite database.",
    )
    parser.add_argument(
        "--expected-snapshot-sha256",
        required=True,
        help="Required expected sha256 of the snapshot SQLite database (hex or sha256:hex).",
    )
    parser.add_argument(
        "--snapshot-context-receipt",
        type=Path,
        required=True,
        help="Required immutable receipt from the consistent read-only SQLite snapshot operation.",
    )
    parser.add_argument(
        "--expected-snapshot-context-receipt-sha256",
        required=True,
        help="Required actual-bytes SHA-256 pin for the snapshot context receipt.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Isolated output directory for research candidate shards and manifest.",
    )
    parser.add_argument(
        "--custody-dir",
        type=Path,
        required=True,
        help="Isolated custody directory for receipts and verification pins.",
    )
    parser.add_argument(
        "--decision-at",
        required=True,
        help="Decision freeze timestamp (YYYY-MM-DD or ISO 8601).",
    )
    parser.add_argument(
        "--history-start-date",
        default="2014-01-01",
        help="Earliest source date to admit to shards (default: 2014-01-01).",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Optional subset of symbols (e.g. 2330 2317).",
    )
    parser.add_argument(
        "--years",
        nargs="*",
        type=int,
        help="Optional list of years to partition (e.g. 2024 2025 2026).",
    )
    parser.add_argument(
        "--market-revision-receipts-dir",
        type=Path,
        help="Optional directory containing market revision receipts (plan, journal, receipt).",
    )
    parser.add_argument(
        "--source-custody-manifest",
        dest="source_custody_manifests",
        type=Path,
        action="append",
        default=[],
        help="Repeatable path to prospective daily candidate or projection manifest.",
    )
    parser.add_argument(
        "--expected-source-manifest-hash",
        dest="expected_source_manifest_hashes",
        action="append",
        default=[],
        help="Repeatable key=value pairs mapping manifest_path=expected_sha256.",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Perform preflight validation and pin discovery without writing candidate shards.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)

    # 解析 expected_source_manifest_hashes
    custody_hashes: dict[str, str] = {}
    for entry in args.expected_source_manifest_hashes:
        if "=" in entry:
            k, v = entry.split("=", 1)
            custody_hashes[str(Path(k.strip()).resolve())] = v.strip()
        else:
            print(
                json.dumps({
                    "status": "blocked",
                    "error": f"Invalid format for --expected-source-manifest-hash: {entry}. Use path=sha256",
                }, ensure_ascii=False),
                file=sys.stderr,
            )
            return 2

    # 解析 symbols
    normalized_symbols: tuple[str, ...] | None = None
    if args.symbols:
        s_list: list[str] = []
        for s in args.symbols:
            for item in s.split(","):
                clean = item.strip()
                if clean:
                    s_list.append(clean)
        normalized_symbols = tuple(s_list) if s_list else None

    # 解析 years
    normalized_years: tuple[int, ...] | None = None
    if args.years:
        normalized_years = tuple(sorted(set(args.years)))

    try:
        request = RevisionAwareRawRequest(
            snapshot_db=args.snapshot_db,
            output_dir=args.output_dir,
            custody_dir=args.custody_dir,
            decision_at=args.decision_at,
            history_start_date=args.history_start_date,
            symbols=normalized_symbols,
            years=normalized_years,
            expected_snapshot_sha256=args.expected_snapshot_sha256,
            snapshot_context_receipt_path=args.snapshot_context_receipt,
            expected_snapshot_context_receipt_sha256=args.expected_snapshot_context_receipt_sha256,
            market_revision_receipts_dir=args.market_revision_receipts_dir,
            source_custody_manifests=tuple(args.source_custody_manifests),
            expected_source_manifest_hashes=custody_hashes,
            preview_only=args.preview_only,
        )
        builder = RevisionAwareRawCandidateBuilder(request)
        result = builder.build()
        out_data = {
            "status": result.status,
            "manifest_path": str(result.manifest_path),
            "manifest_hash": result.manifest_hash,
            "manifest_file_sha256": result.manifest_file_sha256,
            "shard_count": len(result.shards),
            "row_count": result.row_count,
            "feature_value_count": result.feature_value_count,
            "research_only": True,
            "candidate_only": True,
            "formal_credit": False,
            "historical_pit": False,
            "source_revision_qualification": result.input_pins.get("market_revision", {}).get(
                "source_revision_qualification",
                "unverified_requires_separate_strict_inspection",
            ),
        }
        if result.completion_receipt_path:
            out_data["completion_receipt_path"] = str(result.completion_receipt_path)
        print(json.dumps(out_data, ensure_ascii=False, indent=2))
        return 0
    except (RevisionAwareCandidateError, ValueError, OSError, RuntimeError) as exc:
        err_data = {
            "status": "blocked",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "research_only": True,
            "candidate_only": True,
            "formal_credit": False,
        }
        print(json.dumps(err_data, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
