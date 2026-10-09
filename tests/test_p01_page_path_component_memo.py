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


def test_component_tuple_cache_uses_exact_lexical_key_and_shared_budget(
    tmp_path: Path,
) -> None:
    path = tmp_path / "CaseSensitive" / "child"
    other_spelling = tmp_path / "casesensitive" / "child"
    expected = tuple(reversed((path, *path.parents)))

    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        first = personal_data_paths._p01_page_operation_path_components(path)
        assert first == expected
        assert personal_data_paths._p01_page_operation_path_components(path) is first

        # 不以 Path equality 作 key；大小寫不同的原始 spelling 各自占一個項目。
        second_spelling = personal_data_paths._p01_page_operation_path_components(
            other_spelling
        )
        assert str(second_spelling[-2]) != str(first[-2])
        assert len(memo._components) == 2

        rendered = personal_data_paths.to_internal_io_path(path)
        assert rendered == personal_data_paths._render_internal_io_path(path)
        assert len(memo._values) == 1
        assert len(memo._values) + len(memo._components) == 3
        expected_bytes = sum(
            _utf16_bytes(key[1])
            + sum(_utf16_bytes(str(component)) for component in components)
            for key, components in memo._components.items()
        ) + sum(
            _utf16_bytes(key[1]) + _utf16_bytes(value)
            for key, value in memo._values.items()
        )
        assert memo._used_utf16_bytes == expected_bytes


def test_component_tuple_cache_falls_back_when_shared_budget_is_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "one" / "two"
    monkeypatch.setattr(
        personal_data_paths, "_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES", 1
    )
    monkeypatch.setattr(
        personal_data_paths, "_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES", 1
    )

    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        first = personal_data_paths._p01_page_operation_path_components(path)
        assert first == tuple(reversed((path, *path.parents)))
        # Tuple payload連同key超出共享byte budget，不能被保留。
        assert memo._components == {}
        assert memo._used_utf16_bytes == 0

        # 渲染與祖先tuple共用同一entry/byte budget，容量不足仍走strict renderer。
        expected = personal_data_paths._render_internal_io_path(path)
        assert personal_data_paths.to_internal_io_path(path) == expected
        assert memo._values == {}
        assert memo._used_utf16_bytes == 0


def test_render_and_component_entries_share_the_4096_entry_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "entry-limit" / "file.bin"
    monkeypatch.setattr(
        personal_data_paths, "_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES", 1
    )

    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        personal_data_paths.to_internal_io_path(path)
        assert len(memo._values) == 1
        components = personal_data_paths._p01_page_operation_path_components(path)
        assert components == tuple(reversed((path, *path.parents)))
        assert memo._components == {}
        assert len(memo._values) + len(memo._components) == 1


def test_render_and_component_payloads_share_the_1_mib_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "shared-byte-budget" / "file.bin"
    components = tuple(reversed((path, *path.parents)))
    component_entry_bytes = _utf16_bytes(str(path)) + sum(
        _utf16_bytes(str(component)) for component in components
    )
    rendered = personal_data_paths._render_internal_io_path(path)
    render_entry_bytes = _utf16_bytes(str(path)) + _utf16_bytes(rendered)
    monkeypatch.setattr(
        personal_data_paths, "_PAGE_PATH_RENDER_MEMO_MAX_ENTRIES", 8
    )

    monkeypatch.setattr(
        personal_data_paths,
        "_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES",
        component_entry_bytes,
    )
    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        cached_components = personal_data_paths._p01_page_operation_path_components(path)
        assert cached_components == components
        assert memo._used_utf16_bytes == component_entry_bytes
        assert personal_data_paths.to_internal_io_path(path) == rendered
        assert memo._components
        assert memo._values == {}
        assert memo._used_utf16_bytes == component_entry_bytes

    monkeypatch.setattr(
        personal_data_paths,
        "_PAGE_PATH_RENDER_MEMO_MAX_UTF16_BYTES",
        render_entry_bytes,
    )
    with personal_data_paths._p01_page_operation_path_render_scope():
        memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert memo is not None
        assert personal_data_paths.to_internal_io_path(path) == rendered
        assert memo._values
        assert memo._used_utf16_bytes == render_entry_bytes
        uncached_components = personal_data_paths._p01_page_operation_path_components(path)
        assert uncached_components == components
        assert memo._components == {}
        assert memo._used_utf16_bytes == render_entry_bytes


def test_ineligible_paths_use_strict_tuple_without_populating_memo(
    tmp_path: Path,
) -> None:
    absolute = tmp_path / "eligible-parent"

    class DerivedPath(type(absolute)):
        pass

    derived = DerivedPath(str(absolute))
    relative = Path("relative") / "child"
    noncanonical = tmp_path / ".." / "noncanonical" / "child"
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


def test_cached_ancestor_tuple_still_checks_each_reparse_component(
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


def test_nested_strict_scope_and_foreign_thread_do_not_borrow_component_memo(
    tmp_path: Path,
) -> None:
    path = tmp_path / "root" / "nested"
    with personal_data_paths._p01_page_operation_path_render_scope():
        outer = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
        assert outer is not None
        outer_components = personal_data_paths._p01_page_operation_path_components(path)

        with personal_data_paths._suspend_p01_page_operation_path_render_scope():
            strict_components = personal_data_paths._p01_page_operation_path_components(path)
            assert strict_components == outer_components
            assert strict_components is not outer_components

        with personal_data_paths._p01_page_operation_path_render_scope():
            nested = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
            assert nested is not None and nested is not outer
            nested_components = personal_data_paths._p01_page_operation_path_components(path)
            assert nested_components == outer_components
            assert nested_components is not outer_components

        assert personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get() is outer
        assert personal_data_paths._p01_page_operation_path_components(path) is outer_components

        foreign_result: list[tuple[Path, ...]] = []
        copied_context = copy_context()

        thread = threading.Thread(
            target=lambda: foreign_result.append(
                copied_context.run(
                    personal_data_paths._p01_page_operation_path_components, path
                )
            )
        )
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert foreign_result == [outer_components]
        assert foreign_result[0] is not outer_components


def test_exception_clears_component_and_render_entries_and_restores_context(
    tmp_path: Path,
) -> None:
    path = tmp_path / "root" / "leaf"
    memo = None
    with pytest.raises(RuntimeError, match="cancel-like failure"):
        with personal_data_paths._p01_page_operation_path_render_scope():
            memo = personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get()
            assert memo is not None
            personal_data_paths._p01_page_operation_path_components(path)
            personal_data_paths.to_internal_io_path(path)
            assert memo._components and memo._values
            raise RuntimeError("cancel-like failure")
    assert memo is not None
    assert memo._closed
    assert memo._components == {}
    assert memo._values == {}
    assert memo._used_utf16_bytes == 0
    assert personal_data_paths._PAGE_OPERATION_PATH_RENDER_MEMO.get() is None


@pytest.mark.skipif(os.name != "nt", reason="真實 Windows junction/reparse 驗證")
def test_real_junction_is_rejected_after_component_tuple_is_cached(
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
            personal_data_paths._p01_page_operation_path_components(link_target)
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
