"""隔離式 ML 研究產物的失敗即拒絕路徑邊界。"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Sequence

from data_module.config import TWStockConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
APPROVED_ML_RESEARCH_ROOT = REPO_ROOT / "output" / "ml_research"


class MLResearchOutputBoundaryError(ValueError):
    """研究輸出路徑越界，或經由 reparse alias 繞過路徑檢查。"""


def resolve_ml_research_output_path(
    path: os.PathLike[str] | str,
    *,
    repository_root: Path | None = None,
    extra_forbidden_roots: Sequence[Path] = (),
) -> Path:
    """解析唯一核准的 repository research output 及其子路徑。

    此函式只驗證路徑，不建立目錄或檔案。相對路徑以 repository root
    為基準；測試可明確注入暫存 repository root，正式呼叫端不提供覆寫值。
    """

    root = Path(repository_root or REPO_ROOT).expanduser()
    if not root.is_absolute():
        raise MLResearchOutputBoundaryError("repository_root must be absolute")
    raw_root = Path(os.path.abspath(root))
    approved_raw = raw_root / "output" / "ml_research"

    candidate = Path(path).expanduser()
    if any(part == ".." for part in candidate.parts):
        raise MLResearchOutputBoundaryError("research output path cannot contain '..'")
    if not candidate.is_absolute():
        candidate = raw_root / candidate
    candidate_raw = Path(os.path.abspath(candidate))

    _assert_no_reparse_aliases(candidate_raw)
    _assert_no_reparse_aliases(approved_raw)

    candidate_resolved = candidate_raw.resolve(strict=False)
    approved_resolved = approved_raw.resolve(strict=False)
    if not _is_same_or_child(candidate_resolved, approved_resolved):
        raise MLResearchOutputBoundaryError(
            "ML research output must be inside repository output/ml_research"
        )

    for forbidden in _configured_forbidden_roots(raw_root, extra_forbidden_roots):
        forbidden_resolved = forbidden.expanduser().resolve(strict=False)
        if _paths_overlap(candidate_resolved, forbidden_resolved):
            raise MLResearchOutputBoundaryError(
                f"ML research output overlaps a protected root: {forbidden_resolved}"
            )
    return candidate_resolved


def _configured_forbidden_roots(
    repository_root: Path,
    extra_forbidden_roots: Sequence[Path],
) -> tuple[Path, ...]:
    data_field = TWStockConfig.__dataclass_fields__.get("data_root")
    output_field = TWStockConfig.__dataclass_fields__.get("output_root")
    if (
        data_field is None
        or output_field is None
        or not callable(data_field.default_factory)
        or not callable(output_field.default_factory)
    ):
        raise MLResearchOutputBoundaryError(
            "TWStockConfig data/output roots cannot be resolved without side effects"
        )
    data_root_factory = data_field.default_factory
    output_root_factory = output_field.default_factory
    data_root_value = data_root_factory()
    output_root_value = output_root_factory()
    if not isinstance(data_root_value, (str, os.PathLike)) or not isinstance(
        output_root_value, (str, os.PathLike)
    ):
        raise MLResearchOutputBoundaryError("TWStockConfig roots have invalid types")

    roots = [
        Path(data_root_value),
        Path(output_root_value) / "release_v4",
        repository_root / "output" / "release_v4",
        repository_root / "output" / "v4_ml_derived_h5_20260907_real_v2",
    ]
    roots.extend(Path(item) for item in extra_forbidden_roots)
    return tuple(roots)


def _is_same_or_child(candidate: Path, parent: Path) -> bool:
    candidate_key = _path_key(candidate)
    parent_key = _path_key(parent)
    return candidate_key == parent_key or candidate_key.startswith(
        parent_key.rstrip("\\/") + os.sep.casefold()
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_same_or_child(left, right) or _is_same_or_child(right, left)


def _path_key(path: Path) -> str:
    resolved = os.path.normpath(str(path.resolve(strict=False)))
    return os.path.normcase(resolved).casefold()


def _assert_no_reparse_aliases(path: Path) -> None:
    parts = path.parts
    if not parts:
        raise MLResearchOutputBoundaryError("research output path is empty")
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise MLResearchOutputBoundaryError(
                f"research output path component cannot be inspected: {current}"
            ) from exc
        attributes = getattr(info, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        is_junction = getattr(current, "is_junction", None)
        if (
            stat.S_ISLNK(info.st_mode)
            or bool(attributes & reparse_flag)
            or (callable(is_junction) and is_junction())
        ):
            raise MLResearchOutputBoundaryError(
                f"research output path cannot traverse a symlink or junction: {current}"
            )
