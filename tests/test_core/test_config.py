from pathlib import Path
import logging

from data_module.config import TWStockConfig


def test_config_builds_paths_from_injected_roots(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"

    config = TWStockConfig(
        data_root=data_root,
        output_root=output_root,
        profile="prod",
    )

    assert config.data_root == data_root
    assert config.output_root == output_root
    assert config.base_dir == data_root
    assert config.log_dir == output_root / "application_state" / "logs"
    assert config.daily_price_dir == data_root / "daily_price"
    assert config.meta_data_dir == data_root / "meta_data"
    assert config.technical_dir == data_root / "technical_analysis"
    assert config.db_file == data_root / "sqlite" / "twstock.db"
    assert (
        config.monthly_revenue_availability_file
        == data_root / "meta_data" / "monthly_revenue_availability.csv"
    )
    assert (
        config.statement_availability_file
        == data_root / "meta_data" / "fundamental_statement_availability.csv"
    )


def test_config_creates_required_directories(tmp_path: Path) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="prod",
    )

    assert config.daily_price_dir.is_dir()
    assert config.meta_data_dir.is_dir()
    assert config.technical_dir.is_dir()
    assert config.backup_dir.is_dir()
    assert config.sqlite_dir.is_dir()
    assert config.output_root.is_dir()
    assert config.log_dir.is_dir()
    assert not (config.data_root / "logs").exists()


def test_config_keeps_existing_data_root_log_unchanged(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    old_log = data_root / "logs" / "config.log"
    old_log.parent.mkdir(parents=True)
    old_log.write_bytes(b"existing formal log\n")
    before = old_log.stat()
    before_bytes = old_log.read_bytes()
    before_signature = (
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_ino,
    )

    logger = logging.getLogger("data_module.config")
    original_handlers = list(logger.handlers)
    logger.handlers.clear()
    try:
        config = TWStockConfig(
            data_root=data_root,
            output_root=output_root,
            profile="prod",
        )
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers[:] = original_handlers

    after = old_log.stat()
    assert config.log_dir == output_root / "application_state" / "logs"
    assert (config.log_dir / "config.log").is_file()
    assert old_log.read_bytes() == before_bytes
    assert (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_ino,
    ) == before_signature


def test_config_test_profile_suffixes_both_roots_before_log_path(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"

    config = TWStockConfig(
        data_root=data_root,
        output_root=output_root,
        profile="test",
    )

    assert config.data_root == data_root / "_test"
    assert config.output_root == output_root / "_test"
    assert config.log_dir == output_root / "_test" / "application_state" / "logs"
    assert config.log_dir.is_dir()
    assert not (data_root / "logs").exists()


def test_config_falls_back_to_console_when_log_file_is_unwritable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    logger = logging.getLogger("data_module.config")
    original_handlers = list(logger.handlers)
    file_handler_type = logging.FileHandler
    logger.handlers.clear()

    def raise_permission_error(*args, **kwargs):
        raise PermissionError("log path is read-only")

    monkeypatch.setattr(logging, "FileHandler", raise_permission_error)
    try:
        TWStockConfig(
            data_root=tmp_path / "data",
            output_root=tmp_path / "output",
            profile="prod",
        )

        assert any(
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, file_handler_type)
            for handler in logger.handlers
        )
        assert not any(isinstance(handler, file_handler_type) for handler in logger.handlers)
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers[:] = original_handlers
