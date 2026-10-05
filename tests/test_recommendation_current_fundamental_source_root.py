from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
import pandas as pd

from app_module.recommendation.input_preparation import (
    build_default_recommendation_input_preparer,
)
from data_module import recommendation_current_fundamental_provider as current_provider_module
from data_module.current_official_valuation import capture_current_official_valuation
from scripts import run_personalization_recommendation
from scripts.scheduled import run_daily_recommendation_learning_pipeline as learning_pipeline
from scripts.scheduled import run_scheduled_recommendation_snapshot as snapshot


UTC = timezone.utc
REPORT_DATE = date(2026, 10, 2)
CAPTURE_AT = datetime(2026, 10, 4, 10, 0, tzinfo=UTC)
READ_AT = CAPTURE_AT + timedelta(minutes=1)


class _Response:
    def __init__(self, content: bytes, url: str, status_code: int = 200) -> None:
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}


class _OfficialSession:
    def __init__(self, *, pe: str) -> None:
        self._twse = json.dumps(
            [
                {
                    "Date": "115/10/02",
                    "Code": "2330",
                    "PEratio": pe,
                    "DividendYield": "2.10",
                    "PBratio": "6.25",
                }
            ]
        ).encode("utf-8")
        self._tpex = json.dumps(
            [
                {
                    "Date": "1151002",
                    "SecuritiesCompanyCode": "6488",
                    "CompanyName": "fixture",
                    "PriceEarningRatio": "57.77",
                    "DividendPerShare": "7.70",
                    "YieldRatio": "0.65",
                    "PriceBookRatio": "5.88",
                }
            ]
        ).encode("utf-8")

    def get(self, url: str, **_kwargs: object) -> _Response:
        if "openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL" in url:
            return _Response(self._twse, url)
        if "/openapi/v1/tpex_mainboard_peratio_analysis" in url:
            return _Response(self._tpex, url)
        return _Response(b"unavailable fixture route", url, status_code=503)


class _OfflineCalendar:
    def __init__(
        self,
        _database: Path,
        *,
        calendar_cache_path: Path | str | None = None,
        temporary_closure_path: Path | str | None = None,
    ) -> None:
        self.calendar_cache_path = calendar_cache_path
        self.temporary_closure_path = temporary_closure_path

    def is_official_trading_day(
        self, target_date: date, *, allow_online_probe: bool = False
    ) -> tuple[bool, str]:
        assert allow_online_probe is False
        return target_date == REPORT_DATE, "fixture_verified_session"


def _capture(root: Path, *, pe: str, run_id: str) -> None:
    capture_current_official_valuation(
        root,
        session=_OfficialSession(pe=pe),
        wrapper_run_id=run_id,
        clock=lambda: CAPTURE_AT,
    )


def _factory_config(tmp_path: Path, *, artifact_root: Path) -> SimpleNamespace:
    database = tmp_path / "source.sqlite"
    database.touch()
    return SimpleNamespace(
        db_file=database,
        output_root=artifact_root,
        use_sqlite=False,
        pit_market_scope=None,
    )


def test_default_preparer_reads_real_official_capture_from_separate_source_root(
    tmp_path: Path, monkeypatch
) -> None:
    canonical_root = tmp_path / "canonical-output"
    shadow_root = tmp_path / "shadow-artifacts"
    _capture(canonical_root, pe="24.50", run_id="canonical-pe-capture")
    _capture(shadow_root, pe="99.00", run_id="shadow-decoy-capture")
    monkeypatch.setattr(
        current_provider_module, "OfficialTradingCalendar", _OfflineCalendar
    )

    config = _factory_config(tmp_path, artifact_root=shadow_root)
    preparer = build_default_recommendation_input_preparer(
        config,
        market_data_provider=lambda: pd.DataFrame(),
        current_fundamental_source_root=canonical_root,
    )
    provider = preparer.current_fundamental_provider
    assert provider is not None
    assert provider.output_root == canonical_root.resolve()
    assert provider.monthly_source_root == canonical_root.resolve()

    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=READ_AT,
        expected_market_date=REPORT_DATE,
    )

    assert diagnostics == ()
    assert observation is not None
    assert observation.value == Decimal("24.50")
    assert observation.as_of_date == REPORT_DATE


def test_explicit_canonical_source_does_not_fall_back_to_shadow_or_wrong_session(
    tmp_path: Path, monkeypatch
) -> None:
    shadow_root = tmp_path / "shadow-artifacts"
    empty_canonical_root = tmp_path / "canonical-output-without-capture"
    _capture(shadow_root, pe="99.00", run_id="shadow-only-capture")
    monkeypatch.setattr(
        current_provider_module, "OfficialTradingCalendar", _OfflineCalendar
    )
    config = _factory_config(tmp_path, artifact_root=shadow_root)
    preparer = build_default_recommendation_input_preparer(
        config,
        market_data_provider=lambda: pd.DataFrame(),
        current_fundamental_source_root=empty_canonical_root,
    )
    provider = preparer.current_fundamental_provider
    assert provider is not None

    observation, diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=READ_AT,
        expected_market_date=REPORT_DATE,
    )
    wrong_session, wrong_session_diagnostics = provider.load_pe(
        stock_code="2330",
        cutoff_at=READ_AT,
        expected_market_date=date(2026, 10, 5),
    )

    assert observation is None
    assert any("capture_missing" in item for item in diagnostics)
    assert wrong_session is None
    assert any("not_latest_official_session" in item for item in wrong_session_diagnostics)


def test_factory_default_keeps_config_root_for_existing_ui_callers(tmp_path: Path) -> None:
    canonical_root = tmp_path / "normal-output"
    config = _factory_config(tmp_path, artifact_root=canonical_root)
    preparer = build_default_recommendation_input_preparer(
        config,
        market_data_provider=lambda: pd.DataFrame(),
    )
    assert preparer.current_fundamental_provider is not None
    assert preparer.current_fundamental_provider.output_root == canonical_root.resolve()
    assert preparer.current_fundamental_provider.monthly_source_root == canonical_root.resolve()


def test_snapshot_source_root_precedence_ignores_artifact_output_argument(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    artifact_root = tmp_path / "shadow"
    canonical_root = tmp_path / "canonical"
    env_source = tmp_path / "env-current-source"
    monkeypatch.setenv("OUTPUT_ROOT", str(canonical_root))

    assert snapshot._resolve_current_fundamental_source_root(
        data_root=data_root,
        explicit_root=None,
        environ={"CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT": str(env_source), "OUTPUT_ROOT": str(canonical_root)},
    ) == env_source.resolve()
    assert snapshot._resolve_current_fundamental_source_root(
        data_root=data_root,
        explicit_root=None,
        environ={"OUTPUT_ROOT": str(canonical_root)},
    ) == canonical_root.resolve()
    assert snapshot._resolve_current_fundamental_source_root(
        data_root=data_root,
        explicit_root=env_source,
        environ={"CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT": str(canonical_root)},
    ) == env_source.resolve()
    assert artifact_root != canonical_root


def test_personalization_source_root_ignores_custom_artifact_root(
    tmp_path: Path, monkeypatch
) -> None:
    canonical_root = tmp_path / "canonical"
    env_source = tmp_path / "current-source"
    monkeypatch.setenv("OUTPUT_ROOT", str(canonical_root))
    monkeypatch.delenv("CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT", raising=False)

    assert run_personalization_recommendation._resolve_current_fundamental_source_root(
        data_root=tmp_path / "data",
        profile="prod",
        explicit_root=None,
    ) == canonical_root.resolve()
    assert run_personalization_recommendation._resolve_current_fundamental_source_root(
        data_root=tmp_path / "data",
        profile="prod",
        explicit_root=env_source,
    ) == env_source.resolve()


def test_learning_pipeline_forwards_separate_roots_to_snapshot_child(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "shadow"
    canonical_root = tmp_path / "canonical"
    arguments = learning_pipeline._recommendation_snapshot_child_arguments(
        data_root=tmp_path / "data",
        artifact_output_root=artifact_root,
        current_fundamental_source_root=canonical_root,
        max_stocks=100,
        top_n=20,
    )
    assert arguments[arguments.index("--output-root") + 1] == str(artifact_root)
    assert arguments[arguments.index("--current-fundamental-source-root") + 1] == str(canonical_root)


def test_standalone_snapshot_wrapper_passes_independent_source_root() -> None:
    wrapper = Path("scripts/scheduled/run_recommendation_snapshot.cmd").read_text(
        encoding="utf-8"
    )
    assert "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT" in wrapper
    assert "--current-fundamental-source-root \"%CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT%\"" in wrapper


def test_personalization_cli_accepts_separate_fundamental_source_root() -> None:
    args = run_personalization_recommendation._parser().parse_args(
        [
            "--data-root", "D:/fixture/data",
            "--output-root", "D:/fixture/shadow",
            "--current-fundamental-source-root", "D:/fixture/canonical/output",
            "--config-json", "fixture.json",
            "--result-id", "fixture-result",
            "--result-name", "fixture",
            "--as-of-date", "2026-10-02",
            "--scope-id", "fixture-scope",
            "--scope-type", "local",
            "--delivery-id", "fixture-delivery",
            "--request-id", "fixture-request",
        ]
    )
    assert args.current_fundamental_source_root == Path("D:/fixture/canonical/output")


def test_snapshot_main_passes_source_root_not_artifact_root_to_factory(
    tmp_path: Path, monkeypatch
) -> None:
    artifact_root = tmp_path / "shadow-artifacts"
    source_root = tmp_path / "canonical-output"
    captured: dict[str, object] = {}

    def build_preparer(config, *, current_fundamental_source_root):
        captured["config_output_root"] = config.output_root
        captured["source_root"] = current_fundamental_source_root
        return object()

    class _Service:
        def __init__(self, config, *, input_preparer, regime_service) -> None:
            captured["service_output_root"] = config.output_root
            captured["input_preparer"] = input_preparer

        def execute_recommendation(self, **_kwargs):
            raise RuntimeError("stop-after-source-routing-check")

    monkeypatch.setattr(snapshot, "build_default_recommendation_input_preparer", build_preparer)
    monkeypatch.setattr(snapshot, "RecommendationService", _Service)
    monkeypatch.setattr(snapshot, "RegimeService", lambda *_args, **_kwargs: object())

    result = snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(artifact_root),
            "--current-fundamental-source-root",
            str(source_root),
        ]
    )

    assert result == 1
    assert Path(captured["service_output_root"]) == artifact_root
    assert Path(captured["source_root"]) == source_root.resolve()
    status = json.loads(
        (
            artifact_root
            / "scheduled"
            / "recommendation_snapshot"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    assert status["current_fundamental_source_root"] == str(source_root.resolve())
