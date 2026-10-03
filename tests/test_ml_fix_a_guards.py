from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from data_module.portfolio_ml_out_of_core_store import (
    InsufficientMatureHistoryError,
    PortfolioMLOutOfCoreStoreBuilder,
)


def _rows_database(
    path: Path,
    *,
    train_available_at: str,
    train_label_end: str,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE rows (
                local_row_index INTEGER PRIMARY KEY,
                decision_date TEXT NOT NULL,
                max_label_available_at TEXT NOT NULL,
                max_horizon_end_date TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO rows VALUES (?, ?, ?, ?)",
            (
                (0, "2020-01-01", train_available_at, train_label_end),
                (1, "2020-01-02", "2026-10-02T00:00:00+00:00", "2020-01-10"),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _build_indexes(root: Path, *, train_available_at: str, train_label_end: str):
    rows_path = root / "year=2020" / "rows.sqlite"
    rows_path.parent.mkdir(parents=True)
    _rows_database(
        rows_path,
        train_available_at=train_available_at,
        train_label_end=train_label_end,
    )
    return PortfolioMLOutOfCoreStoreBuilder()._build_fold_indexes(
        run_directory=root,
        folds=(
            {
                "fold_id": "fold-001",
                "train_end_date": "2020-01-01",
                "test_start": "2020-01-02",
                "test_end": "2020-01-02",
                "purge_trading_days": 60,
                "embargo_trading_days": 5,
            },
        ),
        year_manifests=({"year": 2020, "year_ordinal": 0},),
        batch_size=8,
        year_rows_paths={2020: rows_path},
        training_as_of="2026-10-03T00:30:00+00:00",
    )


def test_fold_indexes_keep_event_purge_and_real_training_clock_separate(
    tmp_path: Path,
) -> None:
    result = _build_indexes(
        tmp_path / "valid",
        train_available_at="2026-10-02T00:23:25.887429+00:00",
        train_label_end="2020-01-01",
    )

    assert len(result) == 1
    assert result[0]["train"]["row_count"] == 1
    assert result[0]["test"]["row_count"] == 1


def test_fold_indexes_reject_train_label_horizon_reaching_test_start(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="label horizon reaches test_start"):
        _build_indexes(
            tmp_path / "leaked-label",
            train_available_at="2026-10-02T00:23:25+00:00",
            train_label_end="2020-01-02",
        )


def test_fold_indexes_reject_source_availability_after_real_fit_cutoff(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="exceeds real training_as_of"):
        _build_indexes(
            tmp_path / "late-source",
            train_available_at="2026-10-03T00:30:01+00:00",
            train_label_end="2020-01-01",
        )


def test_insufficient_history_classification_is_typed() -> None:
    error = InsufficientMatureHistoryError("four mature folds required")

    assert error.classification == "insufficient_mature_history"
