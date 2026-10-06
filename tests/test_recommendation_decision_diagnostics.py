"""Decision-owned recommendation diagnostics stay pure and wire-compatible."""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from decision_module.recommendation.contracts import (
    CandidateAssessment,
    RecommendationItem,
)
from decision_module.recommendation.diagnostics import (
    CandidateDiagnosticFacts,
    RecommendationDiagnosticContext,
    build_candidate_diagnostic_payload,
    enrich_evaluation_result,
)
from decision_module.recommendation.evaluate import (
    CandidateEvaluationOutcome,
    RecommendationEvaluationPolicy,
    RecommendationEvaluator,
    RecommendationScore,
)


ROOT = Path(__file__).resolve().parents[1]
INVOCATION_ID = "diagnostic-test-call"
DECISION_DATE = date(2026, 5, 20)


@pytest.fixture(autouse=True)
def _isolated_temp_test_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))


def _policy(
    *,
    threshold_mode: str = "fixed",
    top_n: int = 50,
    minimum_percentile_bp: int | None = None,
    minimum_universe_size: int | None = None,
) -> RecommendationEvaluationPolicy:
    return RecommendationEvaluationPolicy(
        invocation_id=INVOCATION_ID,
        decision_date=DECISION_DATE,
        decision_date_text=DECISION_DATE.isoformat(),
        threshold_mode=threshold_mode,
        top_n=top_n,
        minimum_percentile_bp=minimum_percentile_bp,
        minimum_universe_size=minimum_universe_size,
        ranking_method=("nearest_rank" if threshold_mode == "quantile" else "fixed"),
        eligible_universe_date=DECISION_DATE,
    )


def _facts(code: str, *, threshold_mode: str = "fixed") -> CandidateDiagnosticFacts:
    return CandidateDiagnosticFacts(
        stock_code=code,
        stock_name=f"{code} name",
        industry="半導體",
        total_score_text="80.0000",
        threshold_mode=threshold_mode,
        invocation_id=INVOCATION_ID,
    )


def _context() -> RecommendationDiagnosticContext:
    return RecommendationDiagnosticContext(
        invocation_id=INVOCATION_ID,
        as_of_date=DECISION_DATE.isoformat(),
        data_fingerprint="data-hash-1",
    )


def _rankable(code: str, score: Decimal, score_bp: int) -> CandidateEvaluationOutcome:
    return CandidateEvaluationOutcome(
        invocation_id=INVOCATION_ID,
        stock_code=code,
        status="fail",
        quality="observed",
        stage="candidate_scored",
        reason_codes=("pending_final_selection",),
        item=RecommendationItem(
            stock_code=code,
            stock_name=f"{code} name",
            rule_score=score,
            close_price=Decimal("10"),
            price_change=Decimal("1"),
            indicator_score=Decimal("1"),
            pattern_score=Decimal("1"),
            volume_score=Decimal("1"),
            industry="半導體",
            reason_text="selected",
            regime_match=False,
        ),
        assessment=CandidateAssessment(stock_code=code, eligible=True),
        score=RecommendationScore(score, score_bp),
    )


def test_decision_diagnostics_preserve_legacy_negative_and_liquidity_evidence() -> None:
    outcome = CandidateEvaluationOutcome(
        invocation_id=INVOCATION_ID,
        stock_code="LIQ",
        status="skipped",
        quality="degraded",
        stage="volume_gate",
        reason_codes=("liquidity_volume_ratio_below_min",),
        threshold_name="liquidity.volume_ratio_min",
        observed_value="0",
        required_value="1",
        assessment=CandidateAssessment(stock_code="LIQ", eligible=False),
    )
    policy = _policy()
    result = RecommendationEvaluator().evaluate_batch_result((outcome,), policy)
    facts = _facts("LIQ")
    context = _context()

    payload = build_candidate_diagnostic_payload(
        result.dispositions[0], facts, context, policy
    )
    assert payload == {
        "stock_code": "LIQ",
        "stock_name": "LIQ name",
        "status": "skipped",
        "reason_codes": ["liquidity_volume_ratio_below_min"],
        "quality": "degraded",
        "stage": "volume_gate",
        "threshold_name": "liquidity.volume_ratio_min",
        "observed_value": "0",
        "required_value": "1",
        "total_score": "80.0000",
        "score_bp": None,
        "score_percentile_bp": None,
        "eligible_universe_size": None,
        "threshold_mode": "fixed",
        "warnings": [],
        "industry": "半導體",
        "as_of_date": "2026-05-20",
        "data_fingerprint": "data-hash-1",
    }

    enriched = enrich_evaluation_result(result, (facts,), context, policy)
    candidate = enriched.decision.assessments[0]
    filter_outcome = candidate.filter_outcomes["legacy:volume_gate"]
    frozen_payload = {
        **payload,
        "reason_codes": tuple(payload["reason_codes"]),
        "warnings": tuple(payload["warnings"]),
    }
    assert filter_outcome.passed is False
    assert filter_outcome.reason == "liquidity_volume_ratio_below_min"
    assert dict(filter_outcome.evidence or {}) == frozen_payload
    assert [item.evidence_id for item in candidate.negative_evidence] == [
        "legacy:LIQ:0:liquidity_volume_ratio_below_min"
    ]
    assert dict(candidate.negative_evidence[0].details or {}) == frozen_payload
    assert candidate.liquidity is not None
    assert candidate.liquidity.acceptable is False
    assert candidate.liquidity.reasons == ("liquidity_volume_ratio_below_min",)
    assert dict(candidate.liquidity.observations or {}) == frozen_payload
    assert candidate.missing_data == ()


def test_decision_diagnostics_preserve_quantile_threshold_and_rank_evidence() -> None:
    outcomes = (
        _rankable("TOP", Decimal("90.0000"), 9000),
        _rankable("OUT", Decimal("80.0000"), 8000),
    )
    policy = _policy(
        threshold_mode="quantile",
        top_n=1,
        minimum_percentile_bp=4000,
        minimum_universe_size=2,
    )
    result = RecommendationEvaluator().evaluate_batch_result(outcomes, policy)
    facts = (_facts("TOP", threshold_mode="quantile"), _facts("OUT", threshold_mode="quantile"))
    enriched = enrich_evaluation_result(result, facts, _context(), policy)

    top = next(item for item in enriched.decision.assessments if item.stock_code == "TOP")
    top_payload = top.filter_outcomes["legacy:final_selection"].evidence
    assert top_payload is not None
    assert top_payload["threshold_name"] == "recommendation_min_percentile_bp"
    assert top_payload["observed_value"] == "10000"
    assert top_payload["required_value"] == "4000"
    assert top_payload["score_percentile_bp"] == 10000
    assert top_payload["eligible_universe_size"] == 2

    out = next(item for item in enriched.decision.assessments if item.stock_code == "OUT")
    out_payload = out.filter_outcomes["legacy:top_n_gate"].evidence
    assert out_payload is not None
    assert out_payload["threshold_name"] == "top_n"
    assert out_payload["observed_value"] == "2"
    assert out_payload["required_value"] == "1"
    assert out_payload["score_percentile_bp"] == 5000
    assert [item.evidence_id for item in out.negative_evidence] == [
        "legacy:OUT:0:recommendation_outside_top_n"
    ]


def _module_source_path(module_name: str) -> Path | None:
    module_path = ROOT.joinpath(*module_name.split("."))
    source_path = module_path.with_suffix(".py")
    if source_path.is_file():
        return source_path
    package_path = module_path / "__init__.py"
    return package_path if package_path.is_file() else None


def _module_and_package_sources(module_name: str) -> tuple[str, ...]:
    parts = module_name.split(".")
    modules = [
        ".".join(parts[:index])
        for index in range(1, len(parts))
        if (ROOT.joinpath(*parts[:index]) / "__init__.py").is_file()
    ]
    if _module_source_path(module_name) is not None:
        modules.append(module_name)
    return tuple(modules)


def _resolve_import_name(module_name: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    source_path = _module_source_path(module_name)
    package_name = (
        module_name
        if source_path is not None and source_path.name == "__init__.py"
        else module_name.rpartition(".")[0]
    )
    relative_name = "." * node.level + (node.module or "")
    from importlib.util import resolve_name

    return resolve_name(relative_name, package_name)


def _runtime_import_names(
    tree: ast.AST,
    module_name: str,
    *,
    package_initializer: bool,
) -> set[str]:
    imported_modules: set[str] = set()

    def visit(node: ast.AST) -> None:
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            for child in node.orelse:
                visit(child)
            return
        if package_initializer and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            return
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
            return
        if isinstance(node, ast.ImportFrom):
            imported_name = _resolve_import_name(module_name, node)
            if imported_name:
                imported_modules.add(imported_name)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return imported_modules


def _is_pure_diagnostics_dependency(module_name: str) -> bool:
    root = module_name.split(".", maxsplit=1)[0]
    if root == "decision_module":
        return (
            module_name == "decision_module"
            or module_name == "decision_module.recommendation"
            or module_name.startswith("decision_module.recommendation.")
            or module_name == "decision_module.recommendation_percentile_ranker"
        )
    if root == "data_module":
        return (
            module_name == "data_module"
            or module_name == "data_module.contracts"
            or module_name.startswith("data_module.contracts.")
        )
    return root in sys.stdlib_module_names


def test_decision_diagnostics_transitive_import_closure_stays_in_pure_domain() -> None:
    entry = "decision_module.recommendation.diagnostics"
    pending = list(_module_and_package_sources(entry))
    visited: set[str] = set()
    imported_by_module: dict[str, set[str]] = {}

    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        source_path = _module_source_path(module_name)
        if source_path is None:
            continue
        tree = ast.parse(
            source_path.read_text(encoding="utf-8-sig"), filename=str(source_path)
        )
        imported_modules = _runtime_import_names(
            tree,
            module_name,
            package_initializer=source_path.name == "__init__.py",
        )
        imported_by_module[module_name] = imported_modules
        pending.extend(
            local_module
            for imported_name in imported_modules
            for local_module in _module_and_package_sources(imported_name)
        )

    expected_local_dependencies = {
        "decision_module",
        "decision_module.recommendation",
        "decision_module.recommendation.contracts",
        "decision_module.recommendation.evaluate",
        "decision_module.recommendation_percentile_ranker",
        "data_module",
        "data_module.contracts",
        "data_module.contracts.market",
    }
    assert expected_local_dependencies <= visited
    disallowed = {
        module_name: sorted(
            imported_name
            for imported_name in imported_modules
            if not _is_pure_diagnostics_dependency(imported_name)
        )
        for module_name, imported_modules in imported_by_module.items()
    }
    assert {name: modules for name, modules in disallowed.items() if modules} == {}


def test_decision_diagnostics_import_and_call_boundary_blocks_providers(
    tmp_path: Path,
) -> None:
    script = textwrap.dedent(
        """
        import builtins
        from importlib.util import resolve_name

        original_import = builtins.__import__
        forbidden_roots = {"app_module", "ui_qt", "scripts", "ml_module"}

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            package = (globals or {}).get("__package__", "")
            target = resolve_name("." * level + name, package) if level else name
            root = target.split(".", 1)[0]
            if root in forbidden_roots:
                raise AssertionError(f"forbidden import attempted: {target}")
            if root == "data_module" and not (
                target == "data_module.contracts"
                or target.startswith("data_module.contracts.")
            ):
                raise AssertionError(f"non-contract data import attempted: {target}")
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = guarded_import

        from datetime import date
        from decision_module.recommendation.contracts import CandidateAssessment
        from decision_module.recommendation.diagnostics import (
            CandidateDiagnosticFacts,
            RecommendationDiagnosticContext,
            enrich_evaluation_result,
        )
        from decision_module.recommendation.evaluate import (
            CandidateEvaluationOutcome,
            RecommendationEvaluationPolicy,
            RecommendationEvaluator,
        )

        invocation_id = "isolated-diagnostics-smoke"
        decision_date = date(2026, 5, 20)
        outcome = CandidateEvaluationOutcome(
            invocation_id=invocation_id,
            stock_code="2330",
            status="skipped",
            quality="degraded",
            stage="volume_gate",
            reason_codes=("synthetic_gate",),
            assessment=CandidateAssessment(stock_code="2330", eligible=False),
        )
        policy = RecommendationEvaluationPolicy(
            invocation_id=invocation_id,
            decision_date=decision_date,
            decision_date_text=decision_date.isoformat(),
            eligible_universe_date=decision_date,
        )
        result = RecommendationEvaluator().evaluate_batch_result((outcome,), policy)
        enriched = enrich_evaluation_result(
            result,
            (CandidateDiagnosticFacts(
                stock_code="2330",
                stock_name="synthetic",
                total_score_text="",
                invocation_id=invocation_id,
            ),),
            RecommendationDiagnosticContext(
                invocation_id=invocation_id,
                as_of_date=decision_date.isoformat(),
                data_fingerprint="synthetic-fingerprint",
            ),
            policy,
        )
        assert enriched.decision.assessments[0].negative_evidence
        """
    )
    env = {
        **os.environ,
        "PROFILE": "test",
        "DATA_ROOT": str(tmp_path / "blocked-data"),
        "OUTPUT_ROOT": str(tmp_path / "blocked-output"),
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"isolated diagnostics smoke failed: stdout={completed.stdout!r}; "
        f"stderr={completed.stderr!r}"
    )
