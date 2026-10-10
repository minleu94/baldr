from __future__ import annotations

import os
from contextvars import copy_context
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

from app_module import daily_market_technical_snapshot_v4_repository as repository
from app_module import personal_data_paths


def _utf16_bytes(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass"))


def _render_entry_bytes(path: Path, rendered: str) -> int:
    return _utf16_bytes(str(path)) + _utf16_bytes(rendered)


def test_component_validation_prefills_leaf_render_without_second_strict_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ordinary" / "leaf.bin"
    original_validate = personal_data_paths._validate_absolute_syntax
    original_render = personal_data_paths._render_internal_io_path
    original_validated_render = personal_data_paths._render_validated_internal_io_path
    validate_calls: list[str] = []
    render_calls: list[str] = []
    validated_render_calls: list[str] = []

    def observe_validate(value: str | Path) -> Path:
        validate_calls.append(str(value))
        return original_validate(value)

    def observe_render(value: str | Path) -> str:
        render_calls.append(str(value))
        return original_render(value)

    def observe_validated_render(value: Path) -> str:
        validated_render_calls.append(str(value))
        return original_validated_render(value)

    monkeypatch.setattr(personal_data_paths, "_validate_absolute_syntax", observe_validate)
    monkeypatch.setattr(personal_data_paths, "_render_internal_io_path", observe_render)
    monkeypatch.setattr(
        personal_data_paths,
        "_render_validated_internal_io_path",
        observe_validated_render,
    )

    # 嚴格基線：component leaf guard 與 strict renderer 各自驗證一次。
    strict_canonical = personal_data_paths._validate_absolute_syntax(path)
    strict_rendered = personal_data_paths._render_internal_io_path(path)
    assert strict_canonical == path
    assert validate_calls == [str(path), str(path)]
    assert render_calls == [str(path)]
    assert validated_render_calls == [str(path)]

    validate_calls.clear()
    render_calls.clear()
    validated_render_calls.clear()
    expected_components = tuple(reversed((path, *path.parents)))
    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        components = personal_data_paths._p01_page_operation_path_components(path)
        assert components == expected_components
        assert memo._values == {(type(path), str(path)): strict_rendered}
        assert memo._used_utf16_bytes == _render_entry_bytes(path, strict_rendered)
        candidate_rendered = personal_data_paths.to_internal_io_path(path)
        assert candidate_rendered == strict_rendered
        assert personal_data_paths.to_internal_io_path(path) == strict_rendered
        assert validate_calls == [str(path)]
        assert render_calls == []
        assert validated_render_calls == [str(path)]
    assert memo._closed
    assert memo._values == {}
    assert memo._used_utf16_bytes == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-path UTF-16 encoding behavior")
def test_unpaired_surrogate_keeps_component_tuple_and_defers_strict_renderer_error() -> None:
    path = Path("C:/p01-probe") / chr(0xD800)
    expected_components = tuple(reversed((path, *path.parents)))

    assert personal_data_paths._p01_page_operation_path_components(path) == expected_components
    with pytest.raises(UnicodeEncodeError):
        personal_data_paths._render_internal_io_path(path)

    memo = None
    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        assert personal_data_paths._p01_page_operation_path_components(path) == expected_components
        assert memo._values == {}
        assert memo._used_utf16_bytes == 0
        with pytest.raises(UnicodeEncodeError):
            personal_data_paths.to_internal_io_path(path)
        assert memo._values == {}

    assert memo is not None and memo._closed and memo._values == {}


def test_component_tuple_is_recomputed_with_exact_lexical_spelling_and_render_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "CaseSensitive" / "child"
    other_spelling = tmp_path / "casesensitive" / "child"
    expected = tuple(reversed((path, *path.parents)))
    other_expected = tuple(reversed((other_spelling, *other_spelling.parents)))
    original_validate = personal_data_paths._validate_absolute_syntax
    validated: list[str] = []

    def observe_validate(value: str | Path) -> Path:
        validated.append(str(value))
        return original_validate(value)

    original_render = personal_data_paths._render_internal_io_path
    expected_render = original_render(path)
    other_expected_render = original_render(other_spelling)
    rendered_inputs: list[str] = []
    validated_render_inputs: list[str] = []

    def observe_render(value: str | Path) -> str:
        rendered_inputs.append(str(value))
        return original_render(value)

    original_validated_render = personal_data_paths._render_validated_internal_io_path

    def observe_validated_render(value: Path) -> str:
        validated_render_inputs.append(str(value))
        return original_validated_render(value)

    monkeypatch.setattr(personal_data_paths, "_validate_absolute_syntax", observe_validate)
    monkeypatch.setattr(personal_data_paths, "_render_internal_io_path", observe_render)
    monkeypatch.setattr(
        personal_data_paths,
        "_render_validated_internal_io_path",
        observe_validated_render,
    )

    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        first = personal_data_paths._p01_page_operation_path_components(path)
        assert first == expected
        second = personal_data_paths._p01_page_operation_path_components(path)
        assert second == expected

        second_spelling = personal_data_paths._p01_page_operation_path_components(
            other_spelling
        )
        assert second_spelling == other_expected
        assert tuple(map(str, second_spelling)) != tuple(map(str, first))
        assert validated == [str(path), str(path), str(other_spelling)]
        assert memo._components == {}
        assert memo._values == {
            (type(path), str(path)): expected_render,
            (type(other_spelling), str(other_spelling)): other_expected_render,
        }
        assert memo._used_utf16_bytes == (
            _render_entry_bytes(path, expected_render)
            + _render_entry_bytes(other_spelling, other_expected_render)
        )

        rendered = personal_data_paths.to_internal_io_path(path)
        assert rendered == expected_render
        assert personal_data_paths.to_internal_io_path(path) == expected_render
        assert len(memo._values) == 2
        assert memo._components == {}
        assert rendered_inputs == []
        assert validated_render_inputs == [str(path), str(other_spelling)]
        assert rendered == expected_render


def test_deep_component_tuple_does_not_block_render_reuse_at_byte_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path
    for index in range(20):
        path = path / f"segment-{index:02d}-{'x' * 12}"
    path = path / "leaf.bin"
    expected_components = tuple(reversed((path, *path.parents)))
    component_bytes = _utf16_bytes(str(path)) + sum(
        _utf16_bytes(str(component)) for component in expected_components
    )
    original_render = personal_data_paths._render_internal_io_path
    rendered = original_render(path)
    render_bytes = _render_entry_bytes(path, rendered)
    assert component_bytes > render_bytes
    monkeypatch.setattr(
        personal_data_paths, "_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES", 8
    )
    monkeypatch.setattr(
        personal_data_paths, "_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES", render_bytes
    )
    rendered_inputs: list[str] = []

    def observe_render(value: str | Path) -> str:
        rendered_inputs.append(str(value))
        return original_render(value)

    monkeypatch.setattr(personal_data_paths, "_render_internal_io_path", observe_render)

    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        for _ in range(2):
            assert personal_data_paths._p01_page_operation_path_components(
                path
            ) == expected_components
        assert memo._components == {}
        assert memo._values == {(type(path), str(path)): rendered}
        assert memo._used_utf16_bytes == render_bytes
        assert personal_data_paths.to_internal_io_path(path) == rendered
        assert personal_data_paths.to_internal_io_path(path) == rendered
        assert rendered_inputs == []
        assert memo._values == {(type(path), str(path)): rendered}
        assert memo._used_utf16_bytes == render_bytes


def test_render_entries_keep_the_default_4096_entry_cap_without_component_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert personal_data_paths._PAGE_PATH_RENDER_MEMO_MAX_ENTRIES == 4096
    root = Path("C:/p01-cap") if os.name == "nt" else Path("/p01-cap")
    original_render = personal_data_paths._render_internal_io_path
    rendered_inputs: list[str] = []

    def observe_render(value: str | Path) -> str:
        rendered_inputs.append(str(value))
        return original_render(value)

    monkeypatch.setattr(personal_data_paths, "_render_internal_io_path", observe_render)
    inserted_bytes = 0

    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        for index in range(4097):
            path = root / f"{index:04d}"
            components = personal_data_paths._p01_page_operation_path_components(path)
            assert components == tuple(reversed((path, *path.parents)))
            rendered = original_render(path)
            before_calls = len(rendered_inputs)
            first = personal_data_paths.to_internal_io_path(path)
            second = personal_data_paths.to_internal_io_path(path)
            assert first == second == rendered
            if index < 4096:
                assert len(rendered_inputs) - before_calls == 0
                inserted_bytes += _render_entry_bytes(path, rendered)
            else:
                assert len(rendered_inputs) - before_calls == 2
                assert rendered_inputs[-2:] == [str(path), str(path)]
        assert len(memo._values) == 4096
        assert memo._components == {}
        assert memo._used_utf16_bytes == inserted_bytes
        assert memo._used_utf16_bytes < personal_data_paths._PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES


def test_render_entries_keep_the_default_1_mib_byte_cap_after_deep_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit = personal_data_paths._PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES
    assert limit == 1024 * 1024
    base = tmp_path
    for index in range(24):
        base = base / f"deep-{index:02d}-{'x' * 180}"
    original_render = personal_data_paths._render_internal_io_path
    rendered_inputs: list[str] = []

    def observe_render(value: str | Path) -> str:
        rendered_inputs.append(str(value))
        return original_render(value)

    monkeypatch.setattr(personal_data_paths, "_render_internal_io_path", observe_render)
    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        blocked_path: Path | None = None
        expected_used_bytes = 0
        inserted_count = 0
        for index in range(100):
            path = base / f"file-{index:04d}"
            components = personal_data_paths._p01_page_operation_path_components(path)
            assert components == tuple(reversed((path, *path.parents)))
            assert memo._components == {}
            rendered = original_render(path)
            entry_bytes = _render_entry_bytes(path, rendered)
            key = (type(path), str(path))
            was_prefilled = key in memo._values
            before_calls = len(rendered_inputs)
            assert personal_data_paths.to_internal_io_path(path) == rendered
            assert personal_data_paths.to_internal_io_path(path) == rendered
            calls_for_key = len(rendered_inputs) - before_calls
            if was_prefilled:
                assert calls_for_key == 0
                inserted_count += 1
                expected_used_bytes += entry_bytes
                assert memo._used_utf16_bytes == expected_used_bytes
                continue
            assert calls_for_key == 2
            blocked_path = path
            assert key not in memo._values
            assert expected_used_bytes + entry_bytes > limit
            break
        assert blocked_path is not None
        assert inserted_count > 1
        assert memo._used_utf16_bytes == expected_used_bytes <= limit
        assert (type(blocked_path), str(blocked_path)) not in memo._values
        assert rendered_inputs[-2:] == [str(blocked_path), str(blocked_path)]


def test_ineligible_paths_keep_legacy_tuple_fallback_without_render_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absolute = tmp_path / "eligible-parent"

    class DerivedPath(type(absolute)):
        pass

    derived = DerivedPath(str(absolute))
    relative = Path("relative") / "child"
    noncanonical = tmp_path / ".." / "noncanonical" / "child"
    original_validate = personal_data_paths._validate_absolute_syntax
    validated: list[str] = []

    def observe_validate(value: str | Path) -> Path:
        validated.append(str(value))
        return original_validate(value)

    monkeypatch.setattr(personal_data_paths, "_validate_absolute_syntax", observe_validate)
    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        assert personal_data_paths._p01_page_operation_path_components(
            derived
        ) == tuple(reversed((derived, *derived.parents)))
        assert personal_data_paths._p01_page_operation_path_components(
            relative
        ) == tuple(reversed((relative, *relative.parents)))
        assert ".." in noncanonical.parts
        assert personal_data_paths._p01_page_operation_path_components(
            noncanonical
        ) == tuple(reversed((noncanonical, *noncanonical.parents)))
        assert memo._components == {}
        assert memo._values == {}
        assert validated == [str(noncanonical)]


def test_strict_and_page_scoped_link_checks_keep_identical_lstat_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "root" / "nested"
    directory.mkdir(parents=True)
    target = directory / "file.bin"
    target.write_bytes(b"synthetic")
    observed: list[str] = []
    original_lstat = os.lstat

    def record_lstat(value: str | bytes | os.PathLike[str] | os.PathLike[bytes]):
        observed.append(os.fsdecode(value))
        return original_lstat(value)

    monkeypatch.setattr(os, "lstat", record_lstat)
    strict: list[str] = []
    for check in (personal_data_paths._reject_links, repository._reject_link_components):
        start = len(observed)
        check(target)
        strict.extend(observed[start:])

    scoped: list[str] = []
    with personal_data_paths._p01_page_operation_path_render_scope():
        for check in (personal_data_paths._reject_links, repository._reject_link_components):
            start = len(observed)
            check(target)
            scoped.extend(observed[start:])

    assert scoped == strict
    assert len(strict) == 2 * len(tuple(reversed((target, *target.parents))))


def test_recomputed_ancestor_tuple_still_checks_each_reparse_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "root" / "junction" / "child"
    visits: list[Path] = []
    reparse = SimpleNamespace(st_mode=0, st_file_attributes=0x400)

    def lstat_optional(path: Path):
        visits.append(path)
        if path == target.parent:
            return reparse
        return None

    monkeypatch.setattr(repository, "_lstat_optional", lstat_optional)
    with personal_data_paths._p01_page_operation_path_render_scope():
        components = personal_data_paths._p01_page_operation_path_components(target)
        with pytest.raises(repository.DailyMarketTechnicalSnapshotV4RepositoryError):
            repository._reject_link_components(target)
        stop_index = components.index(target.parent)
        assert tuple(visits) == components[: stop_index + 1]


def test_render_memo_is_isolated_for_suspended_nested_and_foreign_thread_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "root" / "nested"
    original_render = personal_data_paths._render_internal_io_path
    rendered_inputs: list[str] = []

    def observe_render(value: str | Path) -> str:
        rendered_inputs.append(str(value))
        return original_render(value)

    monkeypatch.setattr(personal_data_paths, "_render_internal_io_path", observe_render)
    with personal_data_paths._p01_page_operation_path_render_scope():
        outer = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert outer is not None
        outer_components = personal_data_paths._p01_page_operation_path_components(path)
        assert outer_components == tuple(reversed((path, *path.parents)))
        assert personal_data_paths.to_internal_io_path(path) == original_render(path)
        assert personal_data_paths.to_internal_io_path(path) == original_render(path)
        assert rendered_inputs == []

        with personal_data_paths._suspend_p01_page_operation_path_render_scope():
            strict_components = personal_data_paths._p01_page_operation_path_components(path)
            assert strict_components == outer_components
            assert strict_components is not outer_components
            assert personal_data_paths.to_internal_io_path(path) == original_render(path)
            assert rendered_inputs == [str(path)]

        with personal_data_paths._p01_page_operation_path_render_scope():
            nested = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
            assert nested is not None and nested is not outer
            nested_components = personal_data_paths._p01_page_operation_path_components(path)
            assert nested_components == outer_components
            assert nested_components is not outer_components
            assert personal_data_paths.to_internal_io_path(path) == original_render(path)
            assert personal_data_paths.to_internal_io_path(path) == original_render(path)
            assert rendered_inputs == [str(path)]
            assert len(nested._values) == 1
            assert nested._components == {}

        assert personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get() is outer
        assert personal_data_paths._p01_page_operation_path_components(path) == outer_components
        assert personal_data_paths.to_internal_io_path(path) == original_render(path)
        assert rendered_inputs == [str(path)]

        foreign_result: list[tuple[tuple[Path, ...], str]] = []
        copied_context = copy_context()

        def render_in_foreign_thread() -> None:
            foreign_result.append(
                (
                    personal_data_paths._p01_page_operation_path_components(path),
                    personal_data_paths.to_internal_io_path(path),
                )
            )

        thread = threading.Thread(
            target=lambda: copied_context.run(render_in_foreign_thread)
        )
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert foreign_result == [(outer_components, original_render(path))]
        assert foreign_result[0][0] is not outer_components
        assert rendered_inputs == [str(path), str(path)]
        assert len(outer._values) == 1
        assert outer._components == {}


def test_exception_clears_render_entries_and_restores_context_without_component_cache(
    tmp_path: Path,
) -> None:
    path = tmp_path / "root" / "leaf"
    memo = None
    with pytest.raises(RuntimeError, match="cancel-like failure"):
        with personal_data_paths._p01_page_operation_path_render_scope():
            memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
            assert memo is not None
            components = personal_data_paths._p01_page_operation_path_components(path)
            assert components == tuple(reversed((path, *path.parents)))
            personal_data_paths.to_internal_io_path(path)
            assert memo._components == {}
            assert memo._values
            raise RuntimeError("cancel-like failure")
    assert memo is not None
    assert memo._closed
    assert memo._components == {}
    assert memo._values == {}
    assert memo._used_utf16_bytes == 0
    assert personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None


@pytest.mark.skipif(os.name != "nt", reason="真實 Windows junction/reparse 驗證")
def test_real_junction_is_rejected_after_component_tuple_is_computed(
    tmp_path: Path,
) -> None:
    safe_root = tmp_path.resolve(strict=True)
    target_directory = safe_root / "target"
    target_directory.mkdir()
    junction = safe_root / "junction"
    assert target_directory.absolute().is_relative_to(safe_root)
    assert junction.absolute().is_relative_to(safe_root)
    result = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(target_directory)],
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        pytest.skip(
            "此 Windows 環境無法建立隔離 junction："
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        junction_info = junction.lstat()
        assert int(getattr(junction_info, "st_file_attributes", 0)) & 0x400
        assert target_directory.resolve(strict=True).is_relative_to(safe_root)
        link_target = junction / "child.bin"
        with personal_data_paths._p01_page_operation_path_render_scope():
            components = personal_data_paths._p01_page_operation_path_components(link_target)
            assert components == tuple(reversed((link_target, *link_target.parents)))
            with pytest.raises(personal_data_paths.PersonalDataPathError) as error:
                personal_data_paths._reject_links(link_target)
            assert error.value.code == "linked_path"
            with pytest.raises(
                repository.DailyMarketTechnicalSnapshotV4RepositoryError,
                match="technical_snapshot_v4_link_rejected",
            ):
                repository._reject_link_components(link_target)
    finally:
        assert Path(os.path.abspath(junction)).is_relative_to(safe_root)
        assert target_directory.resolve(strict=True).is_relative_to(safe_root)
        os.rmdir(junction)
