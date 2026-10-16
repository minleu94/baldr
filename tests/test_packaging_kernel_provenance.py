"""固定建置必須核驗成對的kernel source，不能漏件或沿舊hash。"""
import hashlib
import json

import pytest

from app_module.packaging_provenance import create_build_metadata
from app_module.build_identity import detect_build_identity
from tests.test_build_identity import _lock


_V2_RULE_SOURCES = (
    "decision_module/strategies/stable_conservative_executor.py",
    "decision_module/strategies/momentum_aggressive_executor.py",
    "ui_qt/views/backtest/research_run_metadata.py",
)


def _v2_source_fixture(root, *, declarations=_V2_RULE_SOURCES):
    (root / "ui_qt").mkdir()
    (root / "ui_qt/app_icon.png").write_bytes(b"isolated-icon")
    for relative in _V2_RULE_SOURCES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 隔離 v2 規則原件\n", encoding="utf-8")
    spec = root / "packaging/baldr.spec"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("for relative_source in " + repr(tuple(declarations)) + ":\n    pass\n", encoding="utf-8")


@pytest.mark.parametrize("relative", _V2_RULE_SOURCES)
@pytest.mark.parametrize("change", ["tamper", "missing"])
def test_frozen_v2_rule_sources_must_match_original_bytes(tmp_path, relative, change):
    _v2_source_fixture(tmp_path)
    metadata = create_build_metadata(tmp_path, "a" * 40, _lock(tmp_path))
    for name in _V2_RULE_SOURCES:
        assert metadata["resource_sha256"][name] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    metadata_path = tmp_path / "application_build.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert detect_build_identity(repository_root=tmp_path, metadata_path=metadata_path, frozen=True).channel == "release"
    changed = tmp_path / relative
    if change == "tamper":
        changed.write_text("# 不同的 v2 原件\n", encoding="utf-8")
    else:
        changed.unlink()
    assert detect_build_identity(repository_root=tmp_path, metadata_path=metadata_path, frozen=True).channel == "unverified"


@pytest.mark.parametrize("missing", _V2_RULE_SOURCES)
def test_declared_v2_bundle_rejects_missing_source_before_build(tmp_path, missing):
    _v2_source_fixture(tmp_path)
    (tmp_path / missing).unlink()
    with pytest.raises(ValueError, match="完整三檔"):
        create_build_metadata(tmp_path, "a" * 40, "b" * 64)


def test_partial_v2_bundle_declaration_is_rejected(tmp_path):
    _v2_source_fixture(tmp_path, declarations=_V2_RULE_SOURCES[:2])
    with pytest.raises(ValueError, match="完整三檔"):
        create_build_metadata(tmp_path, "a" * 40, "b" * 64)


def test_legacy_spec_does_not_claim_new_v2_resources(tmp_path):
    _v2_source_fixture(tmp_path, declarations=("app_module/backtest_service.py",))
    # 舊 spec 不打包新原件，即使舊專案也已有這些程式，不得新加不存在的資源身份。
    metadata = create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    assert not set(_V2_RULE_SOURCES).intersection(metadata["resource_sha256"])


def test_v2_source_names_in_comments_or_description_are_not_bundle_declarations(tmp_path):
    _v2_source_fixture(tmp_path, declarations=("app_module/backtest_service.py",))
    spec = tmp_path / "packaging/baldr.spec"
    with spec.open("a", encoding="utf-8") as stream:
        stream.write("\n# 舊版說明：" + repr(_V2_RULE_SOURCES) + "\n")
        stream.write("description = " + repr(str(_V2_RULE_SOURCES)) + "\n")
    metadata = create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    assert not set(_V2_RULE_SOURCES).intersection(metadata["resource_sha256"])


def test_kernel_source_bytes_are_bound_to_build_resources(tmp_path):
    icon = tmp_path / "ui_qt/app_icon.png"
    icon.parent.mkdir()
    icon.write_bytes(b"isolated-icon")
    root = tmp_path / "analysis_module/technical_analysis"
    root.mkdir(parents=True)
    files = [root / "technical_indicators.py", root / "indicator_kernels.py"]
    for index, path in enumerate(files):
        path.write_bytes(f"# isolated kernel source {index}\n".encode())
    metadata = create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    hashes = metadata["resource_sha256"]
    for path in files:
        assert hashes[path.relative_to(tmp_path).as_posix()] == hashlib.sha256(path.read_bytes()).hexdigest()
    old = hashes[files[0].relative_to(tmp_path).as_posix()]
    files[0].write_bytes(b"# revised kernel source\n")
    revised = create_build_metadata(tmp_path, "a" * 40, "b" * 64)
    assert revised["resource_sha256"][files[0].relative_to(tmp_path).as_posix()] != old


@pytest.mark.parametrize("missing", ["technical_indicators.py", "indicator_kernels.py"])
def test_incomplete_kernel_source_pair_is_rejected(tmp_path, missing):
    root = tmp_path / "analysis_module/technical_analysis"
    root.mkdir(parents=True)
    other = "indicator_kernels.py" if missing == "technical_indicators.py" else "technical_indicators.py"
    (root / other).write_bytes(b"# isolated source\n")
    with pytest.raises(ValueError, match="完整成對"):
        create_build_metadata(tmp_path, "a" * 40, "b" * 64)


@pytest.mark.parametrize("change", ["tamper", "missing"])
def test_frozen_build_identity_rejects_changed_kernel_bytes(tmp_path, change):
    icon = tmp_path / "ui_qt/app_icon.png"
    icon.parent.mkdir()
    icon.write_bytes(b"isolated-icon")
    root = tmp_path / "analysis_module/technical_analysis"
    root.mkdir(parents=True)
    for name in ("technical_indicators.py", "indicator_kernels.py"):
        (root / name).write_bytes(b"# isolated kernel source\n")
    metadata = create_build_metadata(tmp_path, "a" * 40, _lock(tmp_path))
    metadata_path = tmp_path / "application_build.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    identity = detect_build_identity(repository_root=tmp_path, metadata_path=metadata_path, frozen=True)
    assert identity.channel == "release"
    kernel = root / "indicator_kernels.py"
    if change == "tamper":
        kernel.write_bytes(b"# changed source\n")
    else:
        kernel.unlink()
    identity = detect_build_identity(repository_root=tmp_path, metadata_path=metadata_path, frozen=True)
    assert identity.channel == "unverified"


@pytest.mark.parametrize("change", ["tamper", "missing"])
def test_frozen_single_backtest_sources_are_bound_and_rechecked(tmp_path, change):
    icon = tmp_path / "ui_qt/app_icon.png"
    icon.parent.mkdir()
    icon.write_bytes(b"isolated-icon")
    sources = (
        "decision_module/strategies/baseline_score_executor.py",
        "decision_module/score_threshold_policy.py",
        "backtest_module/broker_simulator.py",
        "app_module/backtest_service.py",
    )
    for relative in sources:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 隔離回測來源\n", encoding="utf-8")
    metadata = create_build_metadata(tmp_path, "a" * 40, _lock(tmp_path))
    for relative in sources:
        assert metadata["resource_sha256"][relative] == hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
    metadata_path = tmp_path / "application_build.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert detect_build_identity(repository_root=tmp_path, metadata_path=metadata_path, frozen=True).channel == "release"
    changed = tmp_path / sources[0]
    if change == "tamper":
        changed.write_text("# 改寫過的來源\n", encoding="utf-8")
    else:
        changed.unlink()
    assert detect_build_identity(repository_root=tmp_path, metadata_path=metadata_path, frozen=True).channel == "unverified"
