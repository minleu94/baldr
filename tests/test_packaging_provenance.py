"""固定 commit archive 與依賴不符的實際阻擋。"""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import zipfile

import pytest

from app_module import packaging_provenance as provenance


def test_locked_environment_is_exact_and_extra_dependency_fails(tmp_path, monkeypatch):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"schema": provenance.LOCK_SCHEMA,
                               "python": platform.python_version(), "machine": platform.machine(),
                               "dependencies": {"example": "1.2.3"}}), encoding="utf-8")
    monkeypatch.setattr(provenance, "installed_dependency_snapshot", lambda: {"example": "1.2.3"})
    assert provenance.verify_dependency_lock(lock) == hashlib.sha256(lock.read_bytes()).hexdigest()
    monkeypatch.setattr(provenance, "installed_dependency_snapshot",
                        lambda: {"example": "1.2.3", "unexpected": "1"})
    with pytest.raises(ValueError, match="unexpected"):
        provenance.verify_dependency_lock(lock)


def test_branch_and_short_commit_are_not_release_sources(tmp_path):
    for value in ("dev", "main", "bf9207fb", "A" * 40, "0" * 39):
        with pytest.raises(ValueError, match="完整"):
            provenance.resolve_fixed_commit(tmp_path, value)


def test_archive_long_member_extracts_and_verifies_without_changing_logical_destination(tmp_path):
    from app_module.personal_data_paths import to_internal_io_path
    archive = tmp_path / "long.zip"
    member = "docs/" + "/".join(["long-source-directory"] * 14) + "/source.py"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(member, "# 長路徑原件\n")
    destination = tmp_path / "source"
    provenance.extract_source_archive(archive, destination)
    assert len(str(destination / member)) > 260
    assert Path(to_internal_io_path(destination / member)).read_text(encoding="utf-8") == "# 長路徑原件\n"
    provenance.verify_exported_source(archive, destination)
    assert not str(destination).startswith("\\\\?\\")
    with pytest.raises(ValueError, match="不能覆寫"):
        provenance.extract_source_archive(archive, destination)


@pytest.mark.parametrize("name", ["../outside.py", "C:/outside.py", "a/../../outside.py"])
def test_archive_rejects_path_escape_before_creating_destination(tmp_path, name):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name, "unsafe")
    with pytest.raises(ValueError, match="不安全"):
        provenance.extract_source_archive(archive, tmp_path / "source")
    assert not (tmp_path / "source").exists()


def test_export_reads_exact_commit_and_preserves_other_builds(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    expected = subprocess.check_output(["git", "show", f"{commit}:ui_qt/main.py"], cwd=repository)
    source = provenance.export_fixed_source(repository, commit, tmp_path / "job")
    # Git archive 依此 repo 的 Windows checkout 屬性轉為 CRLF。
    assert (source / "ui_qt/main.py").read_bytes().replace(b"\r\n", b"\n") == expected
    assert not (source / ".git").exists()
    with pytest.raises(ValueError, match="已存在"):
        provenance.export_fixed_source(repository, commit, tmp_path / "job")
    assert (source / "ui_qt/main.py").read_bytes().replace(b"\r\n", b"\n") == expected


def test_metadata_binds_source_dependency_and_resources(tmp_path):
    resource = tmp_path / "ui_qt" / "app_icon.png"
    resource.parent.mkdir()
    resource.write_bytes(b"known-fixture")
    value = provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    assert value["version"] == "2026.10.06+aaaaaaaaaaaa"
    assert value["source_commit"] == "a" * 40
    assert value["dependency_lock_sha256"] == "b" * 64
    assert value["dirty"] is False
    assert value["resource_sha256"] == {"ui_qt/app_icon.png": hashlib.sha256(b"known-fixture").hexdigest()}


def test_metadata_uses_explicit_gregorian_version_date(tmp_path):
    value = provenance.create_build_metadata(
        tmp_path, "a" * 40, "b" * 64, version_date="2026.10.21",
    )
    assert value["version"] == "2026.10.21+aaaaaaaaaaaa"


@pytest.mark.parametrize("version_date", [
    "2026-10-21", "2026.1.21", "2026.10.1", "2026.02.29", "2026.13.01", "2026.10.21x",
])
def test_metadata_rejects_invalid_version_date(tmp_path, version_date):
    with pytest.raises(ValueError, match="版本日期"):
        provenance.create_build_metadata(
            tmp_path, "a" * 40, "b" * 64, version_date=version_date,
        )


def test_p07_packaged_source_manifest_is_complete_and_bound(tmp_path):
    sources = (
        "decision_module/strategies/baldr_bollinger_executor.py",
        "decision_module/strategies/baldr_bollinger_contract.py",
        "decision_module/strategies/baldr_w_bottom_executor.py",
        "decision_module/strategies/baldr_w_bottom_contract.py",
        "analysis_module/pattern_analysis/causal_w_bottom.py",
        "analysis_module/technical_analysis/technical_date_support.py",
        "backtest_module/conservative_fill_policy.py",
        "financial_module/units.py",
    )
    spec = tmp_path / "packaging" / "baldr.spec"
    spec.parent.mkdir()
    spec.write_text("for relative_source in " + repr(sources) + ":\n    pass\n", encoding="utf-8")
    for relative in sources:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))

    metadata = provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    assert {relative: hashlib.sha256(relative.encode("utf-8")).hexdigest() for relative in sources} == {
        relative: metadata["resource_sha256"][relative] for relative in sources
    }

    missing = tmp_path / sources[-1]
    missing.unlink()
    with pytest.raises(ValueError, match="P07.*完整八檔"):
        provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    missing.write_bytes(b"restored")
    spec.write_text("for relative_source in " + repr(sources[:-1]) + ":\n    pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="P07.*完整八檔"):
        provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)


def test_modified_or_extra_python_source_cannot_pass_fixed_archive_verification(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("main.py", "original\n")
    source = tmp_path / "source"
    provenance.extract_source_archive(archive, source)
    provenance.verify_exported_source(archive, source)
    (source / "main.py").write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="已變更"):
        provenance.verify_exported_source(archive, source)
    (source / "main.py").write_bytes(b"original\n")
    (source / "extra.py").write_bytes(b"extra\n")
    with pytest.raises(ValueError, match="程式"):
        provenance.verify_exported_source(archive, source)


@pytest.mark.parametrize("omission", [None, "ma_contract", "ma_file", "shared_sources"])
def test_ma_packaged_source_rejects_partial_or_missing_custody(tmp_path, omission):
    sources = (
        "decision_module/strategies/baldr_bollinger_executor.py",
        "decision_module/strategies/baldr_bollinger_contract.py",
        "decision_module/strategies/baldr_w_bottom_executor.py",
        "decision_module/strategies/baldr_w_bottom_contract.py",
        "analysis_module/pattern_analysis/causal_w_bottom.py",
        "analysis_module/technical_analysis/technical_date_support.py",
        "backtest_module/conservative_fill_policy.py", "financial_module/units.py",
        "decision_module/strategies/baldr_ma_alignment_executor.py",
        "decision_module/strategies/baldr_ma_alignment_contract.py",
    )
    declared = sources[:-1] if omission == "ma_contract" else sources[8:] if omission == "shared_sources" else sources
    spec = tmp_path / "packaging/baldr.spec"
    spec.parent.mkdir()
    spec.write_text("for relative_source in " + repr(declared) + ":\n    pass\n", encoding="utf-8")
    for relative in sources:
        if omission == "ma_file" and relative == sources[-1]:
            continue
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    if omission:
        with pytest.raises(ValueError, match="四均線.*完整兩檔"):
            provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    else:
        metadata = provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
        assert {relative: metadata["resource_sha256"][relative] for relative in sources} == {
            relative: hashlib.sha256(relative.encode()).hexdigest() for relative in sources}


@pytest.mark.parametrize("omission", [None, "file", "declaration", "shared"])
def test_squeeze_packaged_source_requires_both_files_and_shared_group(tmp_path, omission):
    shared = ("decision_module/strategies/baldr_bollinger_executor.py",
              "decision_module/strategies/baldr_bollinger_contract.py",
              "decision_module/strategies/baldr_w_bottom_executor.py",
              "decision_module/strategies/baldr_w_bottom_contract.py",
              "analysis_module/pattern_analysis/causal_w_bottom.py",
              "analysis_module/technical_analysis/technical_date_support.py",
              "backtest_module/conservative_fill_policy.py", "financial_module/units.py")
    squeeze = ("decision_module/strategies/baldr_bollinger_squeeze_executor.py",
               "decision_module/strategies/baldr_bollinger_squeeze_contract.py")
    declared = squeeze if omission == "shared" else shared + squeeze[:-1] if omission == "declaration" else shared + squeeze
    spec = tmp_path / "packaging/baldr.spec"
    spec.parent.mkdir()
    spec.write_text("for relative_source in " + repr(declared) + ":\n    pass\n", encoding="utf-8")
    for relative in shared + squeeze:
        if omission == "file" and relative == squeeze[-1]:
            continue
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    if omission:
        with pytest.raises(ValueError, match="布林帶寬.*完整兩檔"):
            provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    else:
        metadata = provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
        assert all(metadata["resource_sha256"][relative] == hashlib.sha256(relative.encode()).hexdigest() for relative in squeeze)


@pytest.mark.parametrize("omission", [None, "file", "declaration", "shared"])
def test_vcp_packaged_sources_are_complete_without_squeeze_sources(tmp_path, omission):
    shared = ("analysis_module/technical_analysis/technical_date_support.py", "backtest_module/broker_simulator.py",
              "backtest_module/conservative_fill_policy.py", "financial_module/units.py",
              "app_module/backtest_service.py", "ui_qt/views/backtest/research_run_metadata.py")
    own = ("decision_module/strategies/baldr_vcp_contract.py", "decision_module/strategies/baldr_vcp_executor.py",
           "app_module/vcp_rule_card.py", "ui_qt/views/backtest/vcp_execution_source.py")
    # 保留既有整包的baseline／v2防線；VCP不替舊布林帶寬包新增前置。
    baseline = ("decision_module/strategies/baseline_score_executor.py", "decision_module/score_threshold_policy.py")
    v2 = ("decision_module/strategies/stable_conservative_executor.py", "decision_module/strategies/momentum_aggressive_executor.py")
    original_p07 = ("decision_module/strategies/baldr_bollinger_executor.py", "decision_module/strategies/baldr_bollinger_contract.py",
                    "decision_module/strategies/baldr_w_bottom_executor.py", "decision_module/strategies/baldr_w_bottom_contract.py",
                    "analysis_module/pattern_analysis/causal_w_bottom.py", "analysis_module/technical_analysis/technical_date_support.py",
                    "backtest_module/conservative_fill_policy.py", "financial_module/units.py")
    declared = own if omission == "shared" else shared + own[:-1] if omission == "declaration" else shared + own
    declared += v2 + original_p07 if omission != "shared" else ()
    spec = tmp_path / "packaging/baldr.spec"
    spec.parent.mkdir()
    spec.write_text("for relative_source in " + repr(declared) + ":\n    pass\n", encoding="utf-8")
    for relative in shared + own + baseline + v2 + original_p07:
        if omission == "file" and relative == own[-1]:
            continue
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    if omission:
        with pytest.raises(ValueError, match="三段收縮.*完整四檔"):
            provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    else:
        value = provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
        assert all(value["resource_sha256"][relative] == hashlib.sha256(relative.encode()).hexdigest() for relative in shared + own)


@pytest.mark.parametrize("omission", [None, "file", "declaration", "shared"])
def test_causal_score_packaged_source_requires_declared_inputs_and_original_shared_group(tmp_path, omission):
    shared = ("decision_module/strategies/stable_conservative_executor.py",
              "decision_module/strategies/momentum_aggressive_executor.py",
              "ui_qt/views/backtest/research_run_metadata.py")
    causal = ("analysis_module/technical_analysis/causal_score_input.py", "decision_module/indicator_reuse.py",
              "decision_module/strategy_configurator.py", "decision_module/scoring_engine.py", "decision_module/causal_score_pipeline.py")
    spec = tmp_path / "packaging/baldr.spec"
    spec.parent.mkdir()
    declared = causal if omission == "shared" else shared + causal[:-1] if omission == "declaration" else shared + causal
    spec.write_text("for relative_source in " + repr(declared) + ":\n    pass\n", encoding="utf-8")
    for relative in shared + causal:
        if omission == "file" and relative == causal[-1]:
            continue
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    if omission:
        with pytest.raises(ValueError, match="因果計分.*完整五檔"):
            provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    else:
        value = provenance.create_build_metadata(tmp_path, "a" * 40, "b" * 64)
        assert all(value["resource_sha256"][relative] == hashlib.sha256(relative.encode()).hexdigest() for relative in causal)
