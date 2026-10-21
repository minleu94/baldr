from pathlib import Path

import pytest

from app_module.product_preferences import read_theme_catalog_root, save_theme_catalog_root


def test_theme_catalog_preference_read_does_not_create_and_fresh_read_preserves_selected_root(tmp_path):
    state = tmp_path / "state"
    assert read_theme_catalog_root(state) is None
    assert not state.exists()
    selected = tmp_path / "snapshots"
    selected.mkdir()
    save_theme_catalog_root(state, selected)
    assert read_theme_catalog_root(Path(str(state))) == selected.resolve()
    assert sorted(path.name for path in state.iterdir()) == ["v2_theme_catalog.json"]
    assert list(selected.iterdir()) == []


def test_theme_catalog_preference_rejects_relative_or_unknown_schema(tmp_path):
    with pytest.raises(ValueError):
        save_theme_catalog_root(tmp_path, Path("relative"))
    (tmp_path / "v2_theme_catalog.json").write_text('{"schema":"unknown","root":"relative"}')
    with pytest.raises(ValueError):
        read_theme_catalog_root(tmp_path)
