"""保留 Top-N 最佳化結果的探索性穩定性摘要。

這裡刻意不把 retained Top-N 當成完整參數面、信賴區間或 OOS 證明。
所有 objective／範圍計算在 application boundary 先轉 Decimal；呈現層再把
結果格式化成文字，避免把新的裸 float 計算帶進回測核心。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import Counter
from typing import Any, Mapping, Sequence


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "未知"
    return format(value.normalize(), "f")


def _result_parts(result: object) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if isinstance(result, Mapping):
        params = result.get("params", {})
        metrics = result.get("metrics", {})
        return (
            params if isinstance(params, Mapping) else {},
            metrics if isinstance(metrics, Mapping) else {},
        )
    params = getattr(result, "params", {})
    metrics = getattr(result, "metrics", {})
    return (
        params if isinstance(params, Mapping) else {},
        metrics if isinstance(metrics, Mapping) else {},
    )


@dataclass(frozen=True)
class OptimizationParameterStability:
    name: str
    unique_count: int
    minimum: str
    maximum: str
    value_kind: str
    range_text: str
    top5_concentration_bp: int | None
    top5_present_count: int
    top5_total_count: int


@dataclass(frozen=True)
class OptimizationStabilitySummary:
    status: str
    sample_count: int
    objective_sample_count: int
    objective_name: str
    objective_top: str | None
    objective_median: str | None
    objective_worst: str | None
    objective_dispersion: str | None
    parameters: tuple[OptimizationParameterStability, ...]
    note: str

    @property
    def is_insufficient(self) -> bool:
        return self.status != "available"

    def to_text(self) -> str:
        if self.status != "available":
            return (
                f"Top-N 穩定性（探索性）：insufficient（保留樣本 N={self.sample_count}；"
                f"objective valid n={self.objective_sample_count} / retained N={self.sample_count}）。"
                f" {self.note}"
            )
        objective = (
            f"{self.objective_name} top/median/worst="
            f"{self.objective_top}/{self.objective_median}/{self.objective_worst}；"
            f"dispersion={self.objective_dispersion}"
        )
        parameter_text = "、".join(
            f"{item.name}: unique={item.unique_count}, {item.range_text}, "
            f"Top-5 modal share={('未知' if item.top5_concentration_bp is None else str(item.top5_concentration_bp) + ' bp')} "
            f"(present {item.top5_present_count}/{item.top5_total_count})"
            for item in self.parameters
        ) or "無可用變動參數"
        return (
            f"Top-N 穩定性（探索性）：retained N={self.sample_count}；"
            f"objective valid n={self.objective_sample_count} / retained N={self.sample_count}；"
            f"{objective}。"
            f" 參數：{parameter_text}。{self.note}"
        )


def build_optimization_stability_summary(
    results: Sequence[object] | None,
    *,
    objective_key: str = "sharpe_ratio",
    objective_label: str | None = None,
    top_n_concentration: int = 5,
) -> OptimizationStabilitySummary:
    """摘要目前保留的最佳化結果，不宣稱參數穩健。"""

    retained = list(results or [])
    note = (
        "僅根據目前保留的 Top-N 結果；不是完整 parameter surface、confidence interval 或 OOS 證明。"
        " 請另跑 Walk-forward／OOS 驗證。"
    )
    objective_rows: list[tuple[Decimal, Mapping[str, Any]]] = []
    all_parts: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for result in retained:
        params, metrics = _result_parts(result)
        all_parts.append((params, metrics))
        objective = _decimal(metrics.get(objective_key))
        if objective is not None:
            objective_rows.append((objective, params))

    if len(retained) < 2 or not objective_rows:
        return OptimizationStabilitySummary(
            status="insufficient",
            sample_count=len(retained),
            objective_sample_count=len(objective_rows),
            objective_name=objective_label or objective_key,
            objective_top=None,
            objective_median=None,
            objective_worst=None,
            objective_dispersion=None,
            parameters=(),
            note=note,
        )

    ordered = sorted(objective_rows, key=lambda item: item[0], reverse=True)
    values = [item[0] for item in ordered]
    midpoint = len(values) // 2
    if len(values) % 2:
        median = values[midpoint]
    else:
        median = (values[midpoint - 1] + values[midpoint]) / Decimal("2")
    top_value = values[0]
    worst_value = values[-1]
    dispersion = top_value - worst_value

    parameter_names: list[str] = []
    for params, _metrics in all_parts:
        for name in params:
            if name not in parameter_names:
                parameter_names.append(str(name))

    top_slice = ordered[: max(1, top_n_concentration)]
    parameter_rows: list[OptimizationParameterStability] = []
    for name in parameter_names:
        values_for_param = [
            next((value for key, value in params.items() if str(key) == name), None)
            for _objective, params in objective_rows
        ]
        present_values = [value for value in values_for_param if value is not None]
        display_values = [str(value) for value in present_values]
        unique_values = list(dict.fromkeys(display_values))
        numeric_values = [_decimal(value) for value in present_values]
        is_numeric = bool(present_values) and all(value is not None for value in numeric_values)
        missing_count = len(values_for_param) - len(present_values)
        if is_numeric:
            numeric_present = [value for value in numeric_values if value is not None]
            minimum = _format_decimal(min(numeric_present))
            maximum = _format_decimal(max(numeric_present))
            range_text = f"numeric range={minimum}~{maximum}"
            value_kind = "numeric"
        else:
            minimum = "未知"
            maximum = "未知"
            categories = "、".join(unique_values) if unique_values else "未知"
            range_text = f"categorical values={categories}"
            value_kind = "categorical"
        if missing_count:
            range_text += f"；missing={missing_count}"

        top_values = [
            next((value for key, value in params.items() if str(key) == name), None)
            for _objective, params in top_slice
        ]
        top_present = [str(value) for value in top_values if value is not None]
        top_total = len(top_slice)
        concentration = None
        if top_present:
            modal_count = Counter(top_present).most_common(1)[0][1]
            concentration = int(
                (Decimal(modal_count) / Decimal(len(top_present)) * Decimal("10000"))
                .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        parameter_rows.append(
            OptimizationParameterStability(
                name=name,
                unique_count=len(unique_values),
                minimum=minimum,
                maximum=maximum,
                value_kind=value_kind,
                range_text=range_text,
                top5_concentration_bp=concentration,
                top5_present_count=len(top_present),
                top5_total_count=top_total,
            )
        )

    return OptimizationStabilitySummary(
        status="available",
        sample_count=len(retained),
        objective_sample_count=len(objective_rows),
        objective_name=objective_label or objective_key,
        objective_top=_format_decimal(top_value),
        objective_median=_format_decimal(median),
        objective_worst=_format_decimal(worst_value),
        objective_dispersion=_format_decimal(dispersion),
        parameters=tuple(parameter_rows),
        note=note,
    )


__all__ = [
    "OptimizationParameterStability",
    "OptimizationStabilitySummary",
    "build_optimization_stability_summary",
]
