"""私有長路徑套件回歸；不修改原日期、PIT、來源資格或舊 test。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import joblib
import pytest

import app_module.recommendation_calibration_consumer as consumer_module
import ml_module.model_artifact_loader as loader_module
import ml_module.recommendation_calibration_learning_runner as runner_module
import ml_module.recommendation_training_lineage as lineage_module
from ml_module.model_artifact_loader import ArtifactCompatibilityExpectation, SafeShadowModelArtifactLoader
from ml_module.recommendation_calibration_authority import _verify_candidate_identity
from runtime.file_io_path import (
    canonical_path_from_os_result,
    canonical_scandir_child,
    io_path,
    iterdir_canonical,
    resolve_canonical_path,
    to_internal_io_path,
)
from tests.test_daily_recommendation_learning_loop import _candidate, _runner, _samples


def _units(path: Path) -> int:
    return len(str(path).encode("utf-16-le")) // 2


def _exact_root(base: Path, filename: str, *, candidate_id: str | None = None) -> Path:
    """不縮 basetemp；在既有私有根內建精確 261 字元 artifact。"""
    suffix = Path(filename) if candidate_id is None else Path(candidate_id) / filename
    padding = 261 - _units(base / suffix) - 1
    assert 1 <= padding <= 200, "原私有 basetemp 無法容納精確261；須記錄而非縮根"
    root = base / ("x" * padding)
    if candidate_id is not None:
        root /= candidate_id
    assert _units(root / filename) == 261
    return root


@pytest.fixture
def source_candidate(tmp_path: Path) -> tuple[Any, Path, dict[str, object]]:
    # 固定沿用原 historical-research fixture；不賦予模型金融或來源 Gate。
    return _candidate(tmp_path / "source-fixture", shift=0, candidate_day="2026-10-02")


def _expectation(result: Any) -> ArtifactCompatibilityExpectation:
    manifest = result.manifest
    return ArtifactCompatibilityExpectation(
        expected_model_family=manifest.model_family,
        expected_feature_registry_hash=manifest.feature_registry_hash,
        expected_label_registry_hash=manifest.label_registry_hash,
        expected_feature_schema=manifest.feature_schema,
        installed_library_versions=manifest.library_versions,
    )


def test_relative_dotdot_resolver_preserves_original_strict_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "child").mkdir()
    (tmp_path / "other").mkdir()
    monkeypatch.chdir(tmp_path)
    for path in (Path("child"), Path("child") / ".." / "other"):
        for strict in (False, True):
            assert resolve_canonical_path(path, strict=strict) == path.resolve(strict=strict)
    assert resolve_canonical_path(Path("missing")) == Path("missing").resolve()
    with pytest.raises(FileNotFoundError):
        resolve_canonical_path(Path("missing"), strict=True)


@pytest.mark.skipif(os.name != "nt", reason="261 ordinary/extended 對照屬 Windows")
def test_result_persist_exact261_and_nonempty_conflict(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]]) -> None:
    result, _, _ = source_candidate
    root = _exact_root(tmp_path / "persist", result.manifest.artifact_filename, candidate_id=result.candidate_id)
    assert result.persist(root) == root
    artifact = root / result.manifest.artifact_filename
    raw = io_path(artifact).read_bytes()
    assert raw == result.artifact_bytes
    assert "sha256:" + hashlib.sha256(raw).hexdigest() == result.artifact_hash
    with pytest.raises(FileExistsError):
        result.persist(root)
    assert io_path(artifact).read_bytes() == raw


@pytest.mark.skipif(os.name != "nt", reason="精確261 Windows producer／reader")
def test_package261_readback_inventory_authority_and_loader(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]]) -> None:
    result, _, metadata = source_candidate
    root = _exact_root(tmp_path / "package", result.manifest.artifact_filename, candidate_id=result.candidate_id)
    lineage_path = Path(str(metadata["training_lineage_manifest_path"]))
    lineage = lineage_module.read_recommendation_training_lineage(lineage_path)
    runner_module._persist_candidate_package(result, root, metadata)
    runner_module._verify_persisted_candidate_package(
        result=result, candidate_root=root, candidate_payload=metadata,
        lineage=lineage, lineage_path=lineage_path,
    )
    assert _verify_candidate_identity(candidate_id=result.candidate_id, candidate_root=root, candidate_metadata=metadata) is None
    inventory = runner_module._candidate_package_file_inventory(root)
    assert {item["path"] for item in inventory} == {"candidate.json", "manifest.json", result.manifest.artifact_filename}
    assert all(not str(item["path"]).startswith("\\\\?\\") for item in inventory)
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal")
    legacy = loader.load(root, expectation=_expectation(result))
    same = loader.load_same_bytes_with_manifest_v1(root, expectation=_expectation(result))
    assert legacy.status == "shadow_model_ready"
    assert same.status == "shadow_model_ready"
    assert same.captured_artifact_sha256 == result.artifact_hash
    assert same.loaded_serialized_bytes_sha256 == result.artifact_hash
    assert str(root) in str(root.resolve())
    assert not str(root).startswith("\\\\?\\")


@pytest.mark.skipif(os.name != "nt", reason="長 artifact 的 hash 必須在 deserialize 前守衛")
def test_long_artifact_hash_mismatch_never_deserializes(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]]) -> None:
    result, _, metadata = source_candidate
    root = _exact_root(tmp_path / "tamper", result.manifest.artifact_filename, candidate_id=result.candidate_id)
    runner_module._persist_candidate_package(result, root, metadata)
    artifact = root / result.manifest.artifact_filename
    original = io_path(artifact).read_bytes()
    assert original
    io_path(artifact).write_bytes(bytes([original[0] ^ 1]) + original[1:])
    calls: list[Path] = []
    def forbidden(path: Path) -> Any:
        calls.append(path)
        raise AssertionError("hash mismatch 不得到 deserialize")
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal", deserializer=forbidden)
    rejected = loader.load(root, expectation=_expectation(result))
    assert rejected.blockers == ("artifact_hash_mismatch",)
    assert calls == []
    assert _verify_candidate_identity(candidate_id=result.candidate_id, candidate_root=root, candidate_metadata=metadata) == "candidate_artifact_hash_mismatch"


@pytest.mark.skipif(os.name != "nt", reason="長path custom仍接canonical，verified-buffer仍拒custom")
def test_custom_path_callback_keeps_canonical_contract(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]]) -> None:
    result, _, metadata = source_candidate
    root = _exact_root(tmp_path / "custom", result.manifest.artifact_filename, candidate_id=result.candidate_id)
    runner_module._persist_candidate_package(result, root, metadata)
    calls: list[Path] = []
    def custom(path: Path) -> Any:
        calls.append(path)
        assert not str(path).startswith("\\\\?\\")
        return joblib.load(io_path(path))
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal", deserializer=custom)
    assert loader.load(root, expectation=_expectation(result)).status == "shadow_model_ready"
    assert calls == [root / result.manifest.artifact_filename]
    same = loader.load_same_bytes_v1(root, expectation=_expectation(result))
    assert same.blockers == ("verified_buffer_requires_default_joblib",)
    assert same.captured_artifact_sha256 is None
    assert same.loaded_serialized_bytes_sha256 is None


@pytest.mark.skipif(os.name != "nt", reason="長lineage hard-link／cleanup／relative公開接口")
def test_lineage_long_publish_preserves_hardlink_and_relative_api(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]], monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, metadata = source_candidate
    lineage = lineage_module.read_recommendation_training_lineage(Path(str(metadata["training_lineage_manifest_path"])))
    store = tmp_path / ("l" * 100)
    io_path(store).mkdir(parents=True)
    real_link = os.link
    link_counts: list[int] = []
    def observe_link(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
        real_link(source, destination, *args, **kwargs)
        link_counts.append(os.lstat(destination).st_nlink)
    monkeypatch.setattr(lineage_module.os, "link", observe_link)
    monkeypatch.chdir(tmp_path)
    relative = store.relative_to(tmp_path)
    published = lineage_module.persist_recommendation_training_lineage(relative, lineage)
    assert published.is_absolute()
    assert _units(published) > 260
    assert published == lineage_module.training_lineage_path(relative, lineage)
    assert link_counts and all(count >= 2 for count in link_counts)
    assert io_path(published).lstat().st_nlink == 1
    before = io_path(published).read_bytes()
    assert lineage_module.persist_recommendation_training_lineage(relative, lineage) == published
    assert io_path(published).read_bytes() == before
    assert [path.name for path in iterdir_canonical(published.parent)] == ["lineage.json"]
    assert lineage_module.read_recommendation_training_lineage(published).to_dict() == lineage.to_dict()


@pytest.mark.skipif(os.name != "nt", reason="長candidate JSON／manifest pair read仍拒替換")
def test_long_consumer_pair_reads_reject_mutation(tmp_path: Path) -> None:
    root = tmp_path / ("p" * 160)
    io_path(root).mkdir(parents=True)
    candidate = root / "candidate.json"
    manifest = root / "manifest.json"
    assert _units(candidate) > 260
    original = b'{"synthetic":true}\n'
    io_path(candidate).write_bytes(original)
    io_path(manifest).write_bytes(original)
    assert consumer_module._candidate_json_path_matches_bytes(root, original)
    consumer = object.__new__(consumer_module.RecommendationCalibrationConsumer)
    consumer._model_resolution_captured_manifest_paths_and_bytes = [(manifest, original)]
    assert consumer._recheck_captured_model_manifests()
    io_path(candidate).write_bytes(b'{"synthetic":false}\n')
    io_path(manifest).write_bytes(b'{"synthetic":false}\n')
    assert not consumer_module._candidate_json_path_matches_bytes(root, original)
    assert not consumer._recheck_captured_model_manifests()


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse必須實建驗證；建不了不得冒稱PASS")
def test_long_no_follow_guard_rejects_leaf_and_ancestor_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "file").write_bytes(b"private")
    parent = tmp_path / ("n" * 160)
    io_path(parent).mkdir(parents=True)
    alias = parent / "alias"
    try:
        os.symlink(to_internal_io_path(target), to_internal_io_path(alias), target_is_directory=True)
    except OSError as exc:
        pytest.fail(f"私有symlink未建立，no-follow未驗證：{type(exc).__name__}:{exc}")
    assert not runner_module._is_plain_directory(alias)
    assert not runner_module._path_has_no_reparse_components(alias / "file")
    leaf = parent / "leaf"
    os.symlink(to_internal_io_path(target / "file"), to_internal_io_path(leaf))
    assert not runner_module._is_plain_file(leaf)
    assert not runner_module._plain_path_chain(parent, leaf, final_file=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows internal child結果不可污染identity")
def test_scandir_inverse_checks_exact_parent_and_no_caller_alias(tmp_path: Path) -> None:
    root = tmp_path / ("s" * 160)
    io_path(root).mkdir(parents=True)
    child = root / "file"
    io_path(child).write_bytes(b"private")
    entries = list(iterdir_canonical(root))
    assert entries == [child]
    with os.scandir(to_internal_io_path(root)) as iterator:
        entry = next(iterator)
        assert canonical_scandir_child(root, entry.name, entry.path) == child
    with pytest.raises(ValueError):
        canonical_scandir_child(root, "file", to_internal_io_path(tmp_path / "other" / "file"))
    with pytest.raises(ValueError):
        to_internal_io_path(to_internal_io_path(root))
    assert canonical_path_from_os_result(to_internal_io_path(root)) == root


def test_relative_result_persist_and_loader_relative_guard(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]], monkeypatch: pytest.MonkeyPatch) -> None:
    result, _, _ = source_candidate
    monkeypatch.chdir(tmp_path)
    relative = Path("relative-result")
    persisted = result.persist(relative)
    assert persisted == relative.resolve()
    assert persisted.is_absolute()
    loader = SafeShadowModelArtifactLoader(data_root=tmp_path / "formal")
    assert loader.load(relative, expectation=_expectation(result)).blockers == ("artifact_root_not_shadow_safe",)


@pytest.mark.skipif(os.name != "nt", reason="長same-run恢復必須核原identity／binding而非重訓")
def test_long_same_run_reuses_candidate_without_training_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / ("r" * 100)
    runner = _runner(output, data_root=tmp_path / "formal")
    kwargs = dict(decision_date="2026-10-02", samples=_samples(), natural_evidence=None, training_as_of="2026-10-02")
    first = runner.run(**kwargs)
    assert first.status == "completed"
    assert first.candidate_root is not None
    root = Path(first.candidate_root)
    manifest = json.loads(io_path(root / "manifest.json").read_text(encoding="utf-8"))
    assert _units(root / str(manifest["artifact_filename"])) > 260
    def forbidden_fit(**kwargs: Any) -> Any:
        raise AssertionError("same-run identity相同不得重訓")
    monkeypatch.setattr(runner.training_service, "fit", forbidden_fit)
    second = runner.run(**kwargs)
    assert second.status == "completed"
    assert second.idempotent_replay
    assert second.candidate_root == first.candidate_root
    assert second.training_lineage_manifest_hash == first.training_lineage_manifest_hash
    assert not str(second.candidate_root).startswith("\\\\?\\")


def _original_os_outcome(operation: Any) -> tuple[Any, ...]:
    """只用在測試對照原 OS 結果／例外；不更動任何產品 fallback。"""
    try:
        value = operation()
    except Exception as exc:
        return (
            "error", type(exc), exc.args, getattr(exc, "errno", None),
            getattr(exc, "winerror", None), getattr(exc, "filename", None),
            getattr(exc, "filename2", None),
        )
    if isinstance(value, os.stat_result):
        return (
            "stat", value.st_mode, value.st_ino, value.st_dev, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
    return ("result", value)


def test_short_relative_dotdot_io_receiver_matches_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "child").mkdir()
    file = tmp_path / "file"
    file.write_bytes(b"owned-short-transport")
    monkeypatch.chdir(tmp_path)
    paths = (Path("file"), Path("child") / ".." / "file", file, tmp_path / "child" / ".." / "file")
    for path in paths:
        assert io_path(path) == path
        for method in ("lstat", "stat", "is_file", "read_bytes"):
            assert _original_os_outcome(getattr(io_path(path), method)) == _original_os_outcome(getattr(path, method))
        for strict in (False, True):
            assert _original_os_outcome(lambda: resolve_canonical_path(path, strict=strict)) == _original_os_outcome(lambda: path.resolve(strict=strict))


@pytest.mark.skipif(os.name != "nt", reason="Windows alias／ADS／reserved不增加transport新拒絕")
def test_windows_ambiguous_transport_preserves_original_os_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "owned-file"
    file.write_bytes(b"owned-alias-target")
    monkeypatch.chdir(tmp_path)
    alias = Path("\\\\?\\" + str(file))
    paths = (
        alias, tmp_path / "missing:ads", tmp_path / "missing.",
        tmp_path / "missing ", tmp_path / "CON", Path("missing:ads"),
        Path("missing."), Path("CON"),
    )
    for path in paths:
        assert io_path(path) == path
        # 只讀metadata，不開啟reserved console/device stream。
        for method in ("lstat", "stat", "is_file"):
            assert _original_os_outcome(getattr(io_path(path), method)) == _original_os_outcome(getattr(path, method))
        for strict in (False, True):
            assert _original_os_outcome(lambda: resolve_canonical_path(path, strict=strict)) == _original_os_outcome(lambda: path.resolve(strict=strict))
    with pytest.raises(ValueError):
        to_internal_io_path(alias)


def test_relative_iterdir_scandir_exact_parent_returns_and_negatives(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "child").mkdir()
    monkeypatch.chdir(tmp_path)
    short = Path("enum-short")
    long = Path("e" * 160)
    for root in (short, long):
        io_path(root).mkdir()
        io_path(root / "file").write_bytes(b"owned-enumeration")
    if os.name == "nt":
        assert _units(long.absolute()) >= 248
    paths = (short, long, Path("child") / ".." / short)
    for parent in paths:
        expected = parent / "file"
        assert list(iterdir_canonical(parent)) == [expected]
        with os.scandir(io_path(parent)) as iterator:
            entry = next(iterator)
            assert canonical_scandir_child(parent, entry.name, entry.path) == expected
            with pytest.raises(ValueError):
                canonical_scandir_child(parent, "other-name", entry.path)
        with pytest.raises(ValueError):
            canonical_scandir_child(parent, "file", Path("other-parent") / "file")
        with pytest.raises(ValueError):
            canonical_scandir_child(parent, "file", tmp_path / "other-parent" / "file")
    run = Path("relative-run")
    candidate = run / "candidates" / "candidate"
    candidate.mkdir(parents=True)
    (candidate / "candidate.json").write_bytes(b"{}")
    assert runner_module._candidate_directories(run) == (candidate,)
    inventory = runner_module._candidate_package_file_inventory(candidate)
    assert [item["path"] for item in inventory] == ["candidate.json"]


@pytest.mark.skipif(os.name != "nt", reason="relative symlink的lstat保持no-follow原時點")
def test_short_relative_symlink_io_keeps_no_follow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import stat
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.chdir(tmp_path)
    alias = Path("relative-link")
    try:
        os.symlink(target, alias, target_is_directory=True)
    except OSError as exc:
        pytest.fail(f"私有symlink未建立，relative no-follow未驗證：{type(exc).__name__}:{exc}")
    assert io_path(alias) == alias
    original = alias.lstat()
    transported = io_path(alias).lstat()
    assert stat.S_ISLNK(transported.st_mode) or transported.st_file_attributes & 0x400
    assert _original_os_outcome(alias.lstat) == _original_os_outcome(io_path(alias).lstat)
    assert original.st_ino == transported.st_ino
    assert not runner_module._is_plain_directory(alias)
    assert not runner_module._path_has_no_reparse_components(alias)


def test_public_frozen_relative_same_run_preserves_original_guards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path / "frozen-output", data_root=tmp_path / "formal")
    kwargs = dict(decision_date="2026-10-02", samples=_samples(), natural_evidence=None, training_as_of="2026-10-02")
    first = runner.run(**kwargs)
    assert first.status == "completed"
    assert first.candidate_root is not None
    canonical = Path(first.candidate_root)
    monkeypatch.chdir(tmp_path)
    relative = canonical.relative_to(tmp_path)
    assert not relative.is_absolute()
    assert runner_module._is_plain_directory(relative)
    assert runner_module._path_has_no_reparse_components(relative)
    def forbidden_fit(**kwargs: Any) -> Any:
        raise AssertionError("relative frozen候選不得重訓")
    monkeypatch.setattr(runner.training_service, "fit", forbidden_fit)
    frozen_kwargs = {**kwargs, "run_scope": "relative-frozen", "frozen_candidate_root": relative}
    second = runner.run(**frozen_kwargs)
    assert second.status == "completed"
    assert second.candidate_root == str(canonical)
    assert second.training_lineage_manifest_hash == first.training_lineage_manifest_hash
    third = runner.run(**frozen_kwargs)
    assert third.status == "completed"
    assert third.idempotent_replay
    assert third.candidate_root == str(canonical)
    assert third.training_lineage_manifest_hash == first.training_lineage_manifest_hash


def test_force_extended_short_transport_preserves_default_and_guards(tmp_path: Path) -> None:
    # 強制渲染只供自有 canonical tempdir；預設與原詞法拒絕保持不變。
    short = tmp_path / "owned-tempdir"
    assert short.is_absolute()
    assert _units(short) < 248, "保留既有 basetemp；此案例必須使用短 canonical 根"
    assert to_internal_io_path(short) == str(short)
    forced = to_internal_io_path(short, force_extended=True)
    if os.name == "nt":
        assert forced == "\\\\?\\" + str(short)
        unc = Path(r"\\server\share\owned-tempdir")
        assert to_internal_io_path(unc) == str(unc)
        assert to_internal_io_path(unc, force_extended=True) == r"\\?\UNC\server\share\owned-tempdir"
        invalid = (
            Path(r"\\?\C:\owned"), Path(r"\\.\C:\owned"),
            short / "name:stream", short / "trailing.", short / "trailing ", short / "CON",
        )
        for value in invalid:
            for force in (False, True):
                with pytest.raises(ValueError, match="ambiguous_windows_path"):
                    to_internal_io_path(value, force_extended=force)
    else:
        assert forced == str(short)
    for value in (Path("relative"), short / ".." / "other"):
        for force in (False, True):
            with pytest.raises(ValueError, match="absolute_path_required"):
                to_internal_io_path(value, force_extended=force)


@pytest.mark.skipif(os.name != "nt", reason="短parent加入tempfile leaf跨260屬 Windows")
def test_lineage_short_parent_long_temporary_leaf_keeps_publication_guards(tmp_path: Path, source_candidate: tuple[Any, Path, dict[str, object]], monkeypatch: pytest.MonkeyPatch) -> None:
    # 使用真實 producer/readback；不縮 basetemp，也不替換 tempfile 名稱或 OS 寫入。
    import errno

    _, _, metadata = source_candidate
    lineage = lineage_module.read_recommendation_training_lineage(Path(str(metadata["training_lineage_manifest_path"])))
    base = tmp_path / "temp-leaf-boundary"
    parent_without_padding = lineage_module.training_lineage_path(base, lineage).parent
    padding = 241 - _units(parent_without_padding) - 1
    assert 1 <= padding <= 200, "保留原私有 basetemp；無法構造241 parent須記錄"
    store = base / ("b" * padding)
    published = lineage_module.training_lineage_path(store, lineage)
    assert _units(published.parent) == 241
    assert _units(published.parent) < 248
    assert _units(published) == 254
    assert to_internal_io_path(published.parent) == str(published.parent)
    real_mkstemp = lineage_module.tempfile.mkstemp
    real_link = os.link
    captures: list[tuple[str, str, str, int, str]] = []
    links: list[tuple[str, str, int, int]] = []

    def observe_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        descriptor, name = real_mkstemp(*args, **kwargs)
        captures.append((str(kwargs["dir"]), str(kwargs["prefix"]), str(kwargs["suffix"]), descriptor, name))
        return descriptor, name

    def observe_link(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
        real_link(source, destination, *args, **kwargs)
        links.append((str(source), str(destination), os.lstat(source).st_nlink, os.lstat(destination).st_nlink))

    monkeypatch.setattr(lineage_module.tempfile, "mkstemp", observe_mkstemp)
    monkeypatch.setattr(lineage_module.os, "link", observe_link)
    assert lineage_module.persist_recommendation_training_lineage(store, lineage) == published
    assert len(captures) == 1
    rendered_dir, prefix, suffix, descriptor, temporary_name = captures[0]
    assert rendered_dir == to_internal_io_path(published.parent, force_extended=True)
    assert rendered_dir.startswith("\\\\?\\")
    assert prefix == ".lineage-" and suffix == ".tmp"
    temporary = canonical_path_from_os_result(temporary_name)
    assert temporary.parent == published.parent
    assert len(temporary.name) == 21
    assert len(temporary.name[len(prefix):-len(suffix)]) == 8
    assert _units(temporary) == 263
    assert _units(temporary) > 260
    assert temporary_name.startswith("\\\\?\\")
    assert len(links) == 1
    source, destination, source_links, destination_links = links[0]
    assert canonical_path_from_os_result(source) == temporary
    assert canonical_path_from_os_result(destination) == published
    assert source_links >= 2 and destination_links >= 2
    assert io_path(published).lstat().st_nlink == 1
    with pytest.raises(OSError) as closed:
        os.fstat(descriptor)
    assert closed.value.errno == errno.EBADF
    assert not io_path(temporary).exists()
    assert [path.name for path in iterdir_canonical(published.parent)] == ["lineage.json"]
    assert not str(published).startswith("\\\\?\\")
    before = published.read_bytes()
    readback = lineage_module.read_recommendation_training_lineage(published, expected_manifest_hash=lineage.manifest_hash)
    assert readback.to_dict() == lineage.to_dict()
    assert readback.manifest_hash == lineage.manifest_hash
    assert lineage_module.persist_recommendation_training_lineage(store, lineage) == published
    assert published.read_bytes() == before
    assert len(captures) == 1 and len(links) == 1
