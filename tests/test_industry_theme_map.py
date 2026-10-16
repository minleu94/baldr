"""Unit tests for standalone L2 Industry & Theme Extraction and Mapping (`decision_module/industry_theme_map.py`)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from data_module.config import TWStockConfig
from decision_module.industry_theme_map import (
    IndustryThemeMapService,
    METHOD_P1_OFFICIAL_IC,
    METHOD_P2_CURATED_TAXONOMY,
    METHOD_P3_KEYWORD_RULE,
    METHOD_P4_L1_FALLBACK,
    STANDARD_25_CHAINS,
    get_theme_map_paths,
    main as cli_main,
    normalize_iso_date,
    normalize_stock_id,
    normalize_theme_name,
    parse_ic_tpex_chain_html,
)


def _make_test_config(tmp_path: Path) -> TWStockConfig:
    data_root = tmp_path / "fa_data"
    output_root = tmp_path / "output"
    cfg = TWStockConfig(
        data_root=data_root,
        output_root=output_root,
        profile="test",
    )
    cfg.meta_data_dir.mkdir(parents=True, exist_ok=True)
    companies_csv = cfg.meta_data_dir / "companies.csv"
    sample_companies = [
        ("半導體業", "2330", "台積電", "twse", "2026-10-16", "2026-10-16"),
        ("半導體業", "3711", "日月光投控", "twse", "2026-10-16", "2026-10-16"),
        ("半導體業", "2449", "京元電子", "twse", "2026-10-16", "2026-10-16"),
        ("電子零組件業", "1802", "台玻", "twse", "2026-10-16", "2026-10-16"),
        ("電子零組件業", "1815", "富喬", "tpex", "2026-10-16", "2026-10-16"),
        ("電子零組件業", "5340", "建榮", "tpex", "2026-10-16", "2026-10-16"),
        ("塑膠工業", "1303", "南亞", "twse", "2026-10-16", "2026-10-16"),
        ("鋼鐵工業", "9991", "測試不鏽鋼甲", "twse", "2026-10-16", "2026-10-16"),
        ("鋼鐵工業", "9992", "測試不鏽鋼乙", "twse", "2026-10-16", "2026-10-16"),
        ("鋼鐵工業", "9993", "測試不鏽鋼丙", "twse", "2026-10-16", "2026-10-16"),
        ("水泥工業", "1101", "台泥", "twse", "2026-10-16", "2026-10-16"),
        ("水泥工業", "1102", "亞泥", "twse", "2026-10-16", "2026-10-16"),
        ("水泥工業", "1103", "嘉泥", "twse", "2026-10-16", "2026-10-16"),
    ]
    with companies_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["industry_category", "stock_id", "stock_name", "type", "date", "download_time"]
        )
        writer.writerows(sample_companies)
    return cfg


def test_paths_and_normalization_helpers(tmp_path: Path) -> None:
    cfg = _make_test_config(tmp_path)
    paths = get_theme_map_paths(cfg)
    assert paths.industry_chains_catalog_csv == cfg.meta_data_dir / "industry_chains_catalog.csv"
    assert paths.industry_themes_catalog_csv == cfg.meta_data_dir / "industry_themes_catalog.csv"
    assert paths.industry_theme_stock_map_csv == cfg.meta_data_dir / "industry_theme_stock_map.csv"

    assert normalize_stock_id("2330.TW") == "2330"
    assert normalize_stock_id("0050") == "0050"
    assert normalize_stock_id("1101B") == ""
    assert normalize_iso_date("20261016") == "2026-10-16"
    assert normalize_iso_date("2026/10/16") == "2026-10-16"

    assert normalize_theme_name("CoWoS") == "先進封裝(CoWoS)"
    assert normalize_theme_name("先進封裝") == "先進封裝(CoWoS)"
    assert normalize_theme_name("玻纖布") == "玻纖布/玻纖紗"
    assert normalize_theme_name("銅箔基板") == "銅箔基板CCL"
    assert normalize_theme_name("矽光子") == "光通訊/CPO"


def test_parse_ic_tpex_chain_html_extracts_tiers_and_companies() -> None:
    sample_html = """
    <div class="chain">
      <div class="chain-title-panel">上游</div>
      <div id="ic_link_L000_01" class="company-chain-panel">玻纖布</div>
    </div>
    <div class="chain">
      <div class="chain-title-panel">中游</div>
      <div id="ic_link_L000_02" class="company-chain-panel">銅箔基板</div>
    </div>
    <div id="companyList_L000_01" title="玻纖布" style="display:none;">
      <div>
        <a href="company_basic.php?stk_code=1802" title="台玻(1802)">台玻(1802)</a>
        <a href="company_basic.php?stk_code=1815" title="富喬(1815)">富喬(1815)</a>
        <a href="company_basic.php?stk_code=5340" title="建榮(5340)">建榮(5340)</a>
      </div>
    </div>
    <div id="companyList_L000_02" title="銅箔基板" style="display:none;">
      <div>
        <a href="company_basic.php?stk_code=2383" title="台光電(2383)">台光電(2383)</a>
      </div>
    </div>
    """
    rows = parse_ic_tpex_chain_html(
        sample_html,
        chain_name="電子零組件",
        snapshot_date="2026-10-16",
        available_date="2026-10-16",
    )
    assert len(rows) == 4
    first = rows[0]
    assert first.stock_id == "1802"
    assert first.stock_name == "台玻"
    assert first.chain_name == "電子零組件"
    assert first.chain_tier == "上游"
    assert first.theme_name == "玻纖布/玻纖紗"
    assert first.assignment_method == METHOD_P1_OFFICIAL_IC

    last = rows[-1]
    assert last.stock_id == "2383"
    assert last.chain_tier == "中游"
    assert last.theme_name == "銅箔基板CCL"


def test_refresh_theme_mapping_generates_three_files_and_assigns_methods(
    tmp_path: Path,
) -> None:
    cfg = _make_test_config(tmp_path)
    service = IndustryThemeMapService(cfg)

    rows, manifest = service.refresh_theme_mapping(
        snapshot_date="2026-10-01",
        available_date="2026-10-01",
        min_companies=3,
        persist=True,
    )
    assert len(rows) > 0
    assert manifest["total_chains"] == 25
    assert service.paths.industry_chains_catalog_csv.exists()
    assert service.paths.industry_themes_catalog_csv.exists()
    assert service.paths.industry_theme_stock_map_csv.exists()
    assert service.paths.snapshot_manifest_json.exists()

    # Check 產業檔案 (industry_chains_catalog.csv) has all 25 standard chains
    with service.paths.industry_chains_catalog_csv.open("r", encoding="utf-8-sig") as fh:
        chain_rows = list(csv.DictReader(fh))
    assert len(chain_rows) == 25
    assert [r["chain_name"] for r in chain_rows] == list(STANDARD_25_CHAINS)

    # Check 題材檔案 (industry_themes_catalog.csv) has >= 3 companies per theme
    with service.paths.industry_themes_catalog_csv.open("r", encoding="utf-8-sig") as fh:
        theme_rows = list(csv.DictReader(fh))
    assert len(theme_rows) == manifest["total_themes"]
    assert all(int(r["company_count"]) >= 3 for r in theme_rows)

    # Check 2330 multi-tags and single primary tag
    tsmc_info = service.inspect_stock_themes("2330", as_of_date="2026-10-16")
    assert tsmc_info["pit_status"] == "pit_snapshot_aligned"
    tsmc_themes = {t["theme_name"]: t for t in tsmc_info["themes"]}
    assert "晶圓代工" in tsmc_themes
    assert "先進封裝(CoWoS)" in tsmc_themes
    assert tsmc_themes["晶圓代工"]["is_primary"] is True
    assert sum(1 for t in tsmc_info["themes"] if t["is_primary"]) == 1

    # Check P3 keyword extraction on 9991/9992/9993 (不鏽鋼)
    kw_info = service.inspect_stock_themes("9991", as_of_date="2026-10-16")
    assert any(
        t["theme_name"] == "不鏽鋼" and t["assignment_method"] == METHOD_P3_KEYWORD_RULE
        for t in kw_info["themes"]
    )

    # Check P2 curated theme lookup with synonym normalization
    cowos_info = service.inspect_theme_constituents("CoWoS", as_of_date="2026-10-16")
    assert cowos_info["canonical_theme_name"] == "先進封裝(CoWoS)"
    assert cowos_info["company_count"] >= 3


def test_pit_mapping_warns_when_querying_date_prior_to_snapshot(tmp_path: Path) -> None:
    cfg = _make_test_config(tmp_path)
    service = IndustryThemeMapService(cfg)
    service.refresh_theme_mapping(
        snapshot_date="2026-10-01",
        available_date="2026-10-01",
        persist=True,
    )

    # Querying a historical date prior to 2026-10-01 must flag replay-only and emit warning
    _, snap_date, avail_date, pit_status, warnings = service.load_pit_mapping(
        "2026-06-15"
    )
    assert snap_date == "2026-10-01"
    assert avail_date == "2026-10-01"
    assert pit_status == "current_snapshot_replay_only"
    assert "theme_mapping_uses_post_hoc_snapshot" in warnings


def test_cli_commands_work_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _make_test_config(tmp_path)
    monkeypatch.setattr(
        "decision_module.industry_theme_map.IndustryThemeMapService.__init__",
        lambda self, config=None: (
            setattr(self, "config", cfg)
            or setattr(self, "paths", get_theme_map_paths(cfg))
        ),
    )

    assert cli_main(["build-files", "--snapshot-date", "2026-10-16"]) == 0
    out_build = json.loads(capsys.readouterr().out)
    assert out_build["persisted"] is True
    assert out_build["manifest"]["total_chains"] == 25

    assert cli_main(["inspect-stock", "--stock-id", "1802"]) == 0
    out_stock = json.loads(capsys.readouterr().out)
    assert out_stock["stock_id"] == "1802"

    assert cli_main(["inspect-theme", "--theme-name", "玻纖布"]) == 0
    out_theme = json.loads(capsys.readouterr().out)
    assert out_theme["canonical_theme_name"] == "玻纖布/玻纖紗"

    assert cli_main(["status"]) == 0
    out_status = json.loads(capsys.readouterr().out)
    assert out_status["industry_chains_catalog_exists"] is True
    assert out_status["industry_themes_catalog_exists"] is True
    assert out_status["industry_theme_stock_map_exists"] is True
