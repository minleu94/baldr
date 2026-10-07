"""固定建置必須核驗成對的kernel source，不能漏件或沿舊hash。"""
import hashlib
import json

import pytest

from app_module.packaging_provenance import create_build_metadata
from app_module.build_identity import detect_build_identity
from tests.test_build_identity import _lock


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
