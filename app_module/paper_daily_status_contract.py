"""Paper daily-status receipt schema compatibility and custody guardrails."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PAPER_DAILY_STATUS_SCHEMA_VERSION = "paper-portfolio-daily-status.v1"
PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION = (
    "paper-portfolio-daily-isolated-scope.v1"
)
PAPER_DAILY_ISOLATED_PRODUCER = (
    "scripts.scheduled.run_paper_portfolio_daily_isolated"
)


def paper_daily_status_schema_supported(payload: Mapping[str, Any]) -> bool:
    """Accept the canonical status and a strictly bounded legacy receipt."""

    schema_version = payload.get("schema_version")
    if schema_version == PAPER_DAILY_STATUS_SCHEMA_VERSION:
        isolated_version = payload.get("isolated_scope_schema_version")
        return isolated_version in {
            None,
            PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION,
        }
    if schema_version != PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION:
        return False
    if payload.get("producer") != PAPER_DAILY_ISOLATED_PRODUCER:
        return False
    isolated_scope = payload.get("isolated_scope")
    if not isinstance(isolated_scope, Mapping):
        return False
    expected_outer = {
        "candidate_only": True,
        "formal_credit": False,
        "writes_D_source": False,
        "writes_market_database": False,
        "broker_execution": False,
    }
    if any(payload.get(key) is not value for key, value in expected_outer.items()):
        return False
    expected_scope = {
        "repository_state_scope": "repository_output_only",
        "formal_credit": False,
        "writes_D_source": False,
        "writes_market_database": False,
        "broker_execution": False,
    }
    return all(isolated_scope.get(key) == value for key, value in expected_scope.items())


__all__ = [
    "PAPER_DAILY_ISOLATED_PRODUCER",
    "PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION",
    "PAPER_DAILY_STATUS_SCHEMA_VERSION",
    "paper_daily_status_schema_supported",
]
