"""以官方市場來源完整重建研究資料；固定原 62 欄與計算公式。"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from data_module.ml_restatement_official_market import (
    OfficialMarketCapture, load_official_market_capture,
)
from data_module.ml_restatement_research_dataset import (
    RestatedDatasetBuilder, canonical_hash, sha256_file,
)


V3_SCHEMA_VERSION = "portfolio-ml-restated-research-dataset.v3"
MARKET_SOURCE_CONTRACT = "twse-fmtqik-shares-mi5mins-ohlc.v1"
V3_IDENTITY_FIELDS = (
    "schema_version", "source_hashes", "source_manifest_hashes", "computation_source_hashes",
    "feature_count", "feature_ids", "feature_scales", "feature_order_hash", "feature_registry_hash",
    "feature_packs", "feature_value_dtype", "feature_missing_mask_semantics", "label_fields",
    "label_scales", "horizons", "horizon_dates_are_independent", "label_missing_mask_semantics",
    "target_fields", "target_missing_mask_semantics", "original_row_target_audit",
    "feature_event_semantics", "feature_available_at_semantics", "calendar_basis",
    "latest_inference_row_policy", "fold_policy", "fold_boundaries", "observed_session_dates",
    "kernel", "builder_code_sha256", "label_quality_recipe", "corporate_action_basis",
    "restated_research", "formal_historical_PIT", "formal_oos", "promotion_eligible", "research_only",
    "status", "training_as_of", "revision_observed_at", "revision", "row_count", "partition_files",
    "date_filter", "symbol_filter", "market_source", "dataset_created_at",
)
SOURCE_FILES = {
    "official_market_builder": "data_module/ml_restatement_research_dataset_v3.py",
    "stock_feature_label_builder": "data_module/ml_restatement_research_dataset.py",
    "official_market_reader": "data_module/ml_restatement_official_market.py",
    "causal_kernel_facade": "analysis_module/technical_analysis/technical_indicators.py",
    "causal_kernel_impl": "analysis_module/technical_analysis/indicator_kernels.py",
    "grouped_numeric_parser": "utils/numeric_text.py",
}


def computation_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {key: sha256_file(root / relative) for key, relative in SOURCE_FILES.items()}


def compute_v3_identity_hash(manifest: Mapping[str, Any]) -> str:
    if manifest.get("dataset_identity_fields") != list(V3_IDENTITY_FIELDS):
        raise ValueError("v3 identity 欄位與固定契約不符")
    try:
        payload = {"identity_fields": list(V3_IDENTITY_FIELDS), **{name: manifest[name] for name in V3_IDENTITY_FIELDS}}
    except KeyError as exc:
        raise ValueError(f"v3 identity 缺少欄位 {exc.args[0]}") from exc
    return canonical_hash(payload)


def expected_v3_source_pairs(manifest: Mapping[str, Any]) -> list[list[str]]:
    sources = manifest["source_hashes"]
    code = manifest["computation_source_hashes"]
    return [
        ["sqlite.daily_prices", sources["snapshot_db"]["sha256"]],
        ["direct.manifest", sources["direct_manifest"]["file_sha256"]],
        ["direct.discovery_cache", sources["discovery_cache"]["sha256"]],
        ["custody.transfer_receipt", sources["transfer_receipt"]["sha256"]],
        ["derived.causal_kernel", code["causal_kernel_facade"]],
        ["derived.label_quality_builder", code["stock_feature_label_builder"]],
        ["sidecar.corporate_action_adjustments", sources["corporate_action_manifest"]["sha256"]],
        ["official.twse_market", sources["official_market_capture"]["file_sha256"]],
        ["derived.official_market_builder", code["official_market_builder"]],
        ["derived.official_market_reader", code["official_market_reader"]],
        ["derived.causal_kernel.impl", code["causal_kernel_impl"]],
        ["derived.grouped_numeric_parser", code["grouped_numeric_parser"]],
    ]


def validate_v3_manifest_sources(manifest: Mapping[str, Any]) -> OfficialMarketCapture:
    """供訓練與當日 consumer 共用；原始回應仍逐份核對。"""
    if manifest.get("schema_version") != V3_SCHEMA_VERSION:
        raise ValueError("需要官方來源 v3 研究清冊")
    identity = compute_v3_identity_hash(manifest)
    if (
        manifest.get("dataset_identity_hash") != identity or manifest.get("manifest_hash") != identity
        or manifest.get("dataset_id") != "ml-restated-research-v3-" + identity[7:31]
        or manifest.get("status") != "complete_research_build"
        or manifest.get("research_only") is not True or manifest.get("restated_research") is not True
        or any(manifest.get(name) is not False for name in ("formal_historical_PIT", "formal_oos", "promotion_eligible"))
    ):
        raise ValueError("v3 identity 或研究限制不符")
    code = manifest.get("computation_source_hashes")
    if not isinstance(code, dict) or set(code) != set(SOURCE_FILES):
        raise ValueError("v3 computation sources 不完整")
    for value in code.values():
        if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
            raise ValueError("v3 computation source SHA 格式不符")
        int(value[7:], 16)
    if (
        manifest["source_manifest_hashes"] != expected_v3_source_pairs(manifest)
        or manifest["builder_code_sha256"] != code["official_market_builder"]
        or manifest["kernel"]["sha256"] != code["causal_kernel_facade"]
        or manifest["revision"] != manifest["source_hashes"]["snapshot_db"]["sha256"]
    ):
        raise ValueError("v3 來源 alias、builder 或 stock revision 不一致")
    source = manifest.get("market_source")
    expected_keys = {
        "contract", "manifest_path", "manifest_file_sha256", "available_at", "cutoff_date",
        "calendar_policy", "source_revision_id_semantics",
    }
    if not isinstance(source, dict) or set(source) != expected_keys:
        raise ValueError("v3 market source 欄位不完整")
    if (
        source["contract"] != MARKET_SOURCE_CONTRACT
        or source["calendar_policy"] != "official_report_dates; baseline rows preserved; non-session labels missing"
        or source["source_revision_id_semantics"] != "stock SQLite revision; official market is bound separately"
        or manifest["source_hashes"]["official_market_capture"] != {
            "path": source["manifest_path"], "file_sha256": source["manifest_file_sha256"],
        }
    ):
        raise ValueError("v3 市場來源契約不一致")
    observed = datetime.fromisoformat(manifest["revision_observed_at"])
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("v3 修訂鐘須含時區")
    if datetime.fromisoformat(manifest["training_as_of"]) != observed:
        raise ValueError("v3 training_as_of 與修訂鐘不一致")
    created = datetime.fromisoformat(manifest["dataset_created_at"])
    if created.tzinfo is None or created.utcoffset() is None or created < observed:
        raise ValueError("v3 dataset_created_at 早於來源修訂")
    capture = load_official_market_capture(
        Path(source["manifest_path"]), expected_file_sha256=source["manifest_file_sha256"], as_of=observed,
    )
    if (
        source["available_at"] != capture.available_at.isoformat()
        or source["cutoff_date"] != capture.cutoff_date.isoformat()
        or manifest["observed_session_dates"] != [day.isoformat() for day in sorted(capture.rows)]
    ):
        raise ValueError("v3 市場時鐘、截止日或交易日與官方來源不符")
    return capture


class OfficialMarketDatasetBuilder(RestatedDatasetBuilder):
    """沿用已驗證股票前綴／標籤公式；市場值與交易日改取核驗官方來源。"""

    def __init__(
        self, *, official_market_manifest: Path, official_market_hash: str,
        output_dir: Path, custody_dir: Path, symbols: Sequence[str] = (),
        decision_date_start: date | None = None, decision_date_end: date | None = None,
        limit_rows: int | None = None, include_appends: bool = True,
    ) -> None:
        self.started_at = datetime.now(timezone.utc)
        self.start_code_hashes = computation_hashes()
        self.official_market = load_official_market_capture(
            official_market_manifest, expected_file_sha256=official_market_hash, as_of=self.started_at,
        )
        self.custody_dir = custody_dir.resolve()
        if self.custody_dir == output_dir.resolve() or self.custody_dir.is_relative_to(output_dir.resolve()):
            raise ValueError("custody 目錄必須在封存資料集外")
        super().__init__(
            output_dir=output_dir, revision_observed_at=self.started_at.isoformat(),
            symbols=symbols, decision_date_start=decision_date_start, decision_date_end=decision_date_end,
            limit_rows=limit_rows, include_appends=include_appends,
        )
        self.start_source_verified_at = datetime.now(timezone.utc)
        self.revision_observed_at = self.start_source_verified_at.isoformat()
        self.observed_clock = self.start_source_verified_at

    def _load_market(self) -> dict[date, dict[str, Any]]:
        # base __init__ 仍驗證 run02 的唯一授權 SHA；它只提供股票來源。
        original = super()._load_market()
        official = self.official_market
        if (
            set(original) - set(official.rows) != set(official.original_calendar_missing)
            or set(official.rows) - set(original) != set(official.additional_official_dates)
        ):
            raise ValueError("官方交易日差異未精確對應這份 run02 快照")
        return {day: dict(row) for day, row in official.rows.items()}

    def _manifest_payload(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        if computation_hashes() != self.start_code_hashes:
            raise RuntimeError("官方市場資料建置期間程式來源變更")
        if sha256_file(self.snapshot_db) != self.snapshot_sha:
            raise RuntimeError("股票快照在資料建置期間變更")
        official = load_official_market_capture(
            self.official_market.manifest_path,
            expected_file_sha256=self.official_market.manifest_file_sha256,
            as_of=datetime.now(timezone.utc),
        )
        manifest = super()._manifest_payload(files)
        manifest.update({
            "schema_version": V3_SCHEMA_VERSION,
            "builder_code_sha256": self.start_code_hashes["official_market_builder"],
            "computation_source_hashes": dict(self.start_code_hashes),
            "revision": self.snapshot_sha,
            "dataset_created_at": datetime.now(timezone.utc).isoformat(),
            "calendar_basis": "TWSE official monthly report dates acquired at actual revision time; not historical PIT",
            "market_source": {
                "contract": MARKET_SOURCE_CONTRACT,
                "manifest_path": str(official.manifest_path),
                "manifest_file_sha256": official.manifest_file_sha256,
                "available_at": official.available_at.isoformat(),
                "cutoff_date": official.cutoff_date.isoformat(),
                "calendar_policy": "official_report_dates; baseline rows preserved; non-session labels missing",
                "source_revision_id_semantics": "stock SQLite revision; official market is bound separately",
            },
        })
        manifest["source_hashes"]["official_market_capture"] = {
            "path": str(official.manifest_path), "file_sha256": official.manifest_file_sha256,
        }
        manifest["source_manifest_hashes"] = expected_v3_source_pairs(manifest)
        manifest["dataset_identity_fields"] = list(V3_IDENTITY_FIELDS)
        identity = compute_v3_identity_hash(manifest)
        manifest.update({
            "manifest_hash": identity, "dataset_identity_hash": identity,
            "dataset_id": "ml-restated-research-v3-" + identity[7:31],
        })
        validate_v3_manifest_sources(manifest)
        return manifest

    def build(self) -> Path:
        self.custody_dir.mkdir(parents=True, exist_ok=False)
        start = {
            "schema_version": "model-repair-source-start.v1",
            "started_at": self.started_at.isoformat(),
            "source_verified_at": self.start_source_verified_at.isoformat(),
            "source_code_root": str(Path(__file__).resolve().parents[1]),
            "computation_source_hashes": self.start_code_hashes,
            "snapshot_db_sha256": self.snapshot_sha,
            "official_market_manifest_sha256": self.official_market.manifest_file_sha256,
            "direct_manifest_file_sha256": self.contract.direct_manifest_file_hash,
            "historical_pit": False,
        }
        start_path = self.custody_dir / "source_start.json"
        with start_path.open("x", encoding="utf-8") as stream:
            json.dump(start, stream, ensure_ascii=False, indent=2, sort_keys=True)
        manifest_path = super().build()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if computation_hashes() != self.start_code_hashes:
            raise RuntimeError("資料建置完成時程式來源變更")
        custody = {
            "schema_version": "model-repair-source-custody.v2",
            "dataset": {
                "manifest_path": str(manifest_path.resolve()), "manifest_file_sha256": sha256_file(manifest_path),
                "dataset_identity_hash": manifest["dataset_identity_hash"], "row_count": manifest["row_count"],
                "build_status": "complete_research_build",
            },
            "source_start": {"path": str(start_path), "file_sha256": sha256_file(start_path)},
            "job_clocks": {
                "started_at_observed": self.started_at.isoformat(),
                "start_source_verified_at": self.start_source_verified_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "revision_observed_at": self.revision_observed_at,
                "start_source_verification": "observed_before_build",
                "end_source_verification": "rechecked_before_manifest_publication",
            },
            "computation_source_hashes": self.start_code_hashes,
            "source_hashes": manifest["source_hashes"], "market_source": manifest["market_source"],
            "source_code_root": str(Path(__file__).resolve().parents[1]),
            "historical_pit": False,
        }
        with (self.custody_dir / "source_custody.json").open("x", encoding="utf-8") as stream:
            json.dump(custody, stream, ensure_ascii=False, indent=2, sort_keys=True)
        return manifest_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-market-manifest", type=Path, required=True)
    parser.add_argument("--official-market-hash", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--custody-dir", type=Path, required=True)
    parser.add_argument("--symbols", help="有界驗證用逗號分隔股票；完整建置不指定")
    parser.add_argument("--decision-date-start", type=date.fromisoformat)
    parser.add_argument("--decision-date-end", type=date.fromisoformat)
    parser.add_argument("--limit-rows", type=int)
    parser.add_argument("--no-appends", action="store_true")
    args = parser.parse_args(argv)
    builder = OfficialMarketDatasetBuilder(
        official_market_manifest=args.official_market_manifest, official_market_hash=args.official_market_hash,
        output_dir=args.output_dir, custody_dir=args.custody_dir,
        symbols=tuple(args.symbols.split(",")) if args.symbols else (),
        decision_date_start=args.decision_date_start, decision_date_end=args.decision_date_end,
        limit_rows=args.limit_rows, include_appends=not args.no_appends,
    )
    try:
        path = builder.build()
        print(json.dumps({"manifest_path": str(path), "manifest_file_sha256": sha256_file(path)}), flush=True)
    finally:
        builder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
