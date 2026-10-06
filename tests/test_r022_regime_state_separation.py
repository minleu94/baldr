from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

import pandas as pd
import pytest

from app_module.regime_history_store import (
    RegimeHistoryConflict,
    RegimeHistoryStore,
)
from app_module.regime_service import RegimeService
from decision_module.market_regime_detector import MarketRegimeDetector
from decision_module.market_regime_policy import (
    RegimeAssessment,
    RegimeTransition,
    transition_regime,
)


class _CandidateDetector(MarketRegimeDetector):
    """讓 service/state adapter 測試可固定候選序列，不改公式。"""

    def __init__(self, candidates: Mapping[str, str]):
        super().__init__()
        self.candidates = dict(candidates)

    def detect_regime(
        self,
        market_frame: pd.DataFrame,
        date: str | None = None,
        prior_history: Mapping[str, object] | None = None,
    ) -> RegimeAssessment:
        del market_frame
        if date is None:
            raise ValueError("測試候選需要明確日期")
        candidate = self.candidates[date]
        transition = transition_regime(candidate, date, prior_history or {})
        return RegimeAssessment(
            regime=transition.effective_regime,
            confidence=0.5,
            details={"date": date},
            transition=transition,
        )


def _service(
    output_dir: Path,
    candidates: Mapping[str, str],
    *,
    persistent: bool = True,
    provider=None,
) -> RegimeService:
    return RegimeService(
        SimpleNamespace(resolve_output_path=lambda _name: output_dir),
        regime_detector=_CandidateDetector(candidates),
        use_persistent_history=persistent,
        market_frame_provider=provider or (lambda: pd.DataFrame()),
    )


def _read_history(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_detector_accepts_market_frame_and_state_without_io(tmp_path, monkeypatch) -> None:
    frame = pd.DataFrame(
        {
            "Date": pd.date_range("2026-01-01", periods=80, freq="D"),
            "Close": [100.0 + index for index in range(80)],
            "High": [101.0 + index for index in range(80)],
            "Low": [99.0 + index for index in range(80)],
        }
    )
    monkeypatch.setattr(
        pd,
        "read_csv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected file read")),
    )

    assessment = MarketRegimeDetector().detect_regime(
        frame,
        date="2026-03-21",
        prior_history={"2026-03-20": {"regime": "Trend", "timestamp": "prior"}},
    )

    assert assessment.details["date"] == "2026-03-21"
    assert assessment.transition.transition_date == "2026-03-21"
    assert assessment.transition.prior_regime == "Trend"
    assert assessment.transition.persist_candidate is True
    assert not list(tmp_path.iterdir())


def test_persistent_multi_day_and_cooldown_sequence_preserves_write_timing(tmp_path) -> None:
    candidates = {
        "2026-08-03": "Trend",
        "2026-08-04": "Breakout",
        "2026-08-05": "Breakout",
        "2026-08-06": "Trend",
        "2026-08-07": "Trend",
    }
    history_path = tmp_path / "regime_history.json"
    service = _service(tmp_path, candidates)

    results = {
        day: service.detect_regime(date=day).regime
        for day in candidates
    }

    assert results == {
        "2026-08-03": "Trend",
        "2026-08-04": "Trend",
        "2026-08-05": "Breakout",
        "2026-08-06": "Breakout",
        "2026-08-07": "Breakout",
    }
    history = _read_history(history_path)
    assert {day: entry["regime"] for day, entry in history.items()} == {
        "2026-08-03": "Trend",
        "2026-08-04": "Breakout",
        "2026-08-05": "Breakout",
    }
    assert all(set(entry) == {"regime", "timestamp"} for entry in history.values())
    for entry in history.values():
        datetime.fromisoformat(entry["timestamp"])


def test_same_day_rerun_replaces_that_date_using_prior_dates_only(tmp_path) -> None:
    history_path = tmp_path / "regime_history.json"
    service = _service(
        tmp_path,
        {"2026-08-03": "Trend", "2026-08-04": "Breakout"},
    )
    service.detect_regime(date="2026-08-03")
    first = service.detect_regime(date="2026-08-04")
    assert first.regime == "Trend"
    assert _read_history(history_path)["2026-08-04"]["regime"] == "Breakout"

    rerun = _service(tmp_path, {"2026-08-04": "Reversion"})
    result = rerun.detect_regime(date="2026-08-04")

    assert result.regime == "Trend"
    history = _read_history(history_path)
    assert history["2026-08-04"]["regime"] == "Reversion"
    assert history["2026-08-03"]["regime"] == "Trend"


def test_isolated_mode_never_reads_or_changes_seeded_history(tmp_path) -> None:
    history_path = tmp_path / "regime_history.json"
    history_path.write_text(
        '{"2099-01-01": {"regime": "Trend", "timestamp": "future"}}',
        encoding="utf-8",
    )
    before = history_path.read_bytes()
    service = _service(
        tmp_path,
        {"2026-08-03": "Breakout"},
        persistent=False,
    )

    result = service.detect_regime(date="2026-08-03")

    assert result.regime == "Breakout"
    assert service._isolated_history["2026-08-03"]["regime"] == "Breakout"
    assert "2099-01-01" not in service._isolated_history
    assert history_path.read_bytes() == before
    assert not history_path.with_name("regime_history.json.lock").exists()


def test_source_failure_is_degraded_and_does_not_publish_state(tmp_path) -> None:
    history_path = tmp_path / "regime_history.json"

    def broken_provider() -> pd.DataFrame:
        raise RuntimeError("synthetic_source_failure")

    service = _service(
        tmp_path,
        {"2026-08-03": "Trend"},
        provider=broken_provider,
    )

    result = service.detect_regime_dto("2026-08-03")

    assert result.quality == "degraded"
    assert result.details["error"] == "synthetic_source_failure"
    assert result.regime == "Trend"
    assert result.warnings == (
        "market_regime_effective_date_unknown",
        "market_regime_detector_degraded",
    )
    assert not history_path.exists()


def test_csv_read_failure_keeps_legacy_degraded_details_without_history_write(
    tmp_path, monkeypatch
) -> None:
    market_csv = tmp_path / "market_indices.csv"
    market_csv.write_text("Date,Close\n2026-08-03,100\n", encoding="utf-8")
    config = SimpleNamespace(
        use_sqlite=False,
        market_index_file=market_csv,
        resolve_output_path=lambda _name: tmp_path,
    )
    service = RegimeService(
        config,
        use_persistent_history=True,
    )

    def fail_csv_read(*_args, **_kwargs):
        raise pd.errors.ParserError("synthetic_csv_parse_failure")

    monkeypatch.setattr(pd, "read_csv", fail_csv_read)
    direct_result = service.detect_regime(date="2026-08-03")
    dto_result = service.detect_regime_dto("2026-08-03")

    assert direct_result.regime == "Trend"
    assert direct_result.confidence == 0.5
    assert direct_result.details == {"error": "synthetic_csv_parse_failure"}
    assert dto_result.quality == "degraded"
    assert dto_result.regime == "Trend"
    assert dto_result.details == {"error": "synthetic_csv_parse_failure"}
    assert "market_regime_detector_degraded" in dto_result.warnings
    assert not (tmp_path / "regime_history.json").exists()


def test_history_conflict_is_explicit_and_not_a_source_fallback(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, {"2026-08-03": "Trend"})
    store = service._regime_history_store
    assert store is not None

    def conflict(**_kwargs):
        raise RegimeHistoryConflict("synthetic_history_conflict")

    monkeypatch.setattr(store, "commit_candidate", conflict)

    with pytest.raises(RegimeHistoryConflict, match="synthetic_history_conflict"):
        service.detect_regime(date="2026-08-03")

    dto_result = service.detect_regime_dto("2026-08-03")
    assert dto_result.quality == "degraded"
    assert dto_result.regime is None
    assert dto_result.details == {"error": "synthetic_history_conflict"}
    assert dto_result.warnings == ("market_regime_error:synthetic_history_conflict",)


def test_compare_and_write_serializes_racers_and_loser_cannot_overwrite(
    tmp_path, monkeypatch
) -> None:
    history_path = tmp_path / "regime_history.json"
    candidates = {"2026-08-03": "Trend"}
    left = _service(tmp_path, candidates)
    right = _service(tmp_path, {"2026-08-03": "Breakout"})
    left_store = left._regime_history_store
    right_store = right._regime_history_store
    assert left_store is not None and right_store is not None

    snapshots_ready = threading.Barrier(2)
    original_left_read = left_store.read_snapshot
    original_right_read = right_store.read_snapshot

    def synchronized_left_read():
        snapshot = original_left_read()
        snapshots_ready.wait(timeout=5)
        return snapshot

    def synchronized_right_read():
        snapshot = original_right_read()
        snapshots_ready.wait(timeout=5)
        return snapshot

    monkeypatch.setattr(left_store, "read_snapshot", synchronized_left_read)
    monkeypatch.setattr(right_store, "read_snapshot", synchronized_right_read)

    import app_module.regime_history_store as store_module

    original_replace = store_module.os.replace
    first_replace_entered = threading.Event()
    release_first_replace = threading.Event()
    second_replace_entered = threading.Event()
    second_commit_attempt = threading.Event()
    replace_lock = threading.Lock()
    replace_count = 0

    original_commit = RegimeHistoryStore.commit_candidate

    def observed_commit(store, **kwargs):
        if threading.current_thread().name == "r022-right":
            second_commit_attempt.set()
        return original_commit(store, **kwargs)

    def controlled_replace(source, destination):
        nonlocal replace_count
        with replace_lock:
            replace_count += 1
            ordinal = replace_count
        if ordinal == 1:
            first_replace_entered.set()
            if not release_first_replace.wait(timeout=5):
                raise TimeoutError("test did not release first atomic replace")
        else:
            second_replace_entered.set()
        return original_replace(source, destination)

    monkeypatch.setattr(RegimeHistoryStore, "commit_candidate", observed_commit)
    monkeypatch.setattr(store_module.os, "replace", controlled_replace)
    outcomes: list[object] = []

    def run(service: RegimeService) -> None:
        try:
            outcomes.append(service.detect_regime(date="2026-08-03"))
        except Exception as exc:  # noqa: BLE001 - capture the CAS loser
            outcomes.append(exc)

    left_thread = threading.Thread(target=run, args=(left,), name="r022-left")
    right_thread = threading.Thread(target=run, args=(right,), name="r022-right")
    left_thread.start()
    right_thread.start()

    try:
        assert first_replace_entered.wait(timeout=5)
        # Both requests read the same absent-file fingerprint before either commit.
        assert snapshots_ready.n_waiting == 0
        assert second_commit_attempt.wait(timeout=5)
        assert not second_replace_entered.wait(timeout=0.2)
    finally:
        release_first_replace.set()
        left_thread.join(timeout=5)
        right_thread.join(timeout=5)

    assert not left_thread.is_alive()
    assert not right_thread.is_alive()
    assert replace_count == 1
    assert not second_replace_entered.is_set()
    assert sum(isinstance(item, RegimeHistoryConflict) for item in outcomes) == 1
    assert sum(hasattr(item, "regime") for item in outcomes) == 1
    final_history = _read_history(history_path)
    assert len(final_history) == 1
    assert final_history["2026-08-03"]["regime"] in {"Trend", "Breakout"}
