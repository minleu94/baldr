"""Recommendation Portfolio V2 的精確期間金額契約。

此模組只驗證及序列化 caller 明示的 producer 原始值；不執行回測、損益公式、
Registry 寫入或 V1 dispatch。金額以 producer 提供的 canonical Decimal text 保留。
三字母 currency 語法檢查不驗證 ISO 清單成員資格；來源／幣別 authority 仍須由
producer 明示。完整性 digest 不是來源簽章或資格證明。測試中的合成封套不是實際
來源或期間樣本。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Literal, cast


RECOMMENDATION_PORTFOLIO_PERIOD_PRECISION_SCHEMA_V2 = (
    "recommendation-portfolio-period-precision.v2"
)
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_OBSERVATIONS = 20_000
_MAX_EXPECTED_DATES = 20_000
_MAX_IDENTITY_LENGTH = 256
_MAX_DECIMAL_TEXT_LENGTH = 128
_MAX_DECIMAL_DIGITS = 80
_MAX_MINOR_UNIT_EXPONENT = 9
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DECIMAL_TEXT_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_AWARE_DATETIME_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)
_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}\Z")
_STOCK_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")

CompletionStatusV2 = Literal["completed", "cancelled", "failed", "truncated"]
SourceQualityStatusV2 = Literal["verified", "unverified", "unknown"]


class RecommendationPortfolioPeriodPrecisionV2Error(ValueError):
    """期間精度契約欄位、完整性或序列化無效。"""


def _fail(message: str) -> RecommendationPortfolioPeriodPrecisionV2Error:
    return RecommendationPortfolioPeriodPrecisionV2Error(message)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise _fail("期間精度契約無法編成 canonical UTF-8 JSON") from exc


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_text(
    value: object,
    field_name: str,
    *,
    maximum: int = _MAX_IDENTITY_LENGTH,
) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise _fail(f"{field_name} 必須是有界、無首尾空白的非空字串")
    return cast(str, value)


def _require_optional_text(
    value: object,
    field_name: str,
    *,
    maximum: int = _MAX_IDENTITY_LENGTH,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name, maximum=maximum)


def _require_sha256_or_none(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise _fail(f"{field_name} 必須是 sha256:<64 小寫 hex> 或明示 None")
    return cast(str, value)


def _require_iso_date(value: object, field_name: str) -> str:
    if type(value) is not str or _DATE_PATTERN.fullmatch(value) is None:
        raise _fail(f"{field_name} 必須是 YYYY-MM-DD 日期文字")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise _fail(f"{field_name} 不是有效日曆日期") from exc
    return cast(str, value)


def _require_aware_datetime_or_none(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    text = _require_text(value, field_name, maximum=64)
    if _AWARE_DATETIME_PATTERN.fullmatch(text) is None:
        raise _fail(f"{field_name} 必須是有時區的 canonical ISO-8601 時間")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail(f"{field_name} 必須是 ISO-8601 時間") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail(f"{field_name} 必須明示時區")
    return text


def _parse_decimal_text(value: object, field_name: str) -> tuple[str, Decimal]:
    if (
        type(value) is not str
        or len(value) > _MAX_DECIMAL_TEXT_LENGTH
        or _DECIMAL_TEXT_PATTERN.fullmatch(value) is None
    ):
        raise _fail(f"{field_name} 必須是有界、不使用指數記號的 canonical Decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise _fail(f"{field_name} 不是有效 Decimal") from exc
    if not parsed.is_finite() or len(parsed.as_tuple().digits) > _MAX_DECIMAL_DIGITS:
        raise _fail(f"{field_name} 必須是有限且有界的 Decimal")
    return cast(str, value), parsed


def _decimal_add_equals(left_text: str, right_text: str, target_text: str) -> bool:
    """用整數係數精確核對 Decimal 相加，避免 ambient context 捨入。"""

    values = [Decimal(left_text), Decimal(right_text), Decimal(target_text)]
    parts: list[tuple[int, int]] = []
    for value in values:
        sign, digits, exponent = value.as_tuple()
        if not isinstance(exponent, int):
            raise _fail("Decimal identity 必須是有限數值")
        coefficient = int("".join(str(digit) for digit in digits) or "0")
        if sign:
            coefficient = -coefficient
        parts.append((coefficient, exponent))
    common_exponent = min(exponent for _, exponent in parts)
    scaled = [
        coefficient * (10 ** (exponent - common_exponent))
        for coefficient, exponent in parts
    ]
    return scaled[0] + scaled[1] == scaled[2]


def _exact_minor_units(value_text: str, exponent: int | None) -> int | None:
    if exponent is None:
        return None
    value = Decimal(value_text)
    sign, digits, decimal_exponent = value.as_tuple()
    if not isinstance(decimal_exponent, int):
        raise _fail("minor units 必須來自有限 Decimal")
    if value.is_zero():
        return 0
    coefficient = "".join(str(digit) for digit in digits)
    shift = decimal_exponent + exponent
    if shift >= 0:
        integer_text = coefficient + ("0" * shift)
    else:
        removed = -shift
        if removed > len(coefficient):
            return None
        suffix = coefficient[-removed:]
        if any(character != "0" for character in suffix):
            return None
        integer_text = coefficient[:-removed] or "0"
    integer_value = int(integer_text)
    return -integer_value if sign else integer_value


def _require_dates(value: object, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if type(value) not in (tuple, list):
        raise _fail(f"{field_name} 必須是有界日期序列或明示 None")
    sequence = cast(tuple[object, ...] | list[object], value)
    if not sequence or len(sequence) > _MAX_EXPECTED_DATES:
        raise _fail(f"{field_name} 不可為空且不得超過 {_MAX_EXPECTED_DATES} 日")
    dates = tuple(
        _require_iso_date(item, f"{field_name}[{index}]")
        for index, item in enumerate(sequence)
    )
    if any(right <= left for left, right in zip(dates, dates[1:])):
        raise _fail(f"{field_name} 必須唯一且嚴格遞增")
    return dates


def _strict_object(value: object, expected_keys: set[str], field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _fail(f"{field_name} 必須是 JSON object")
    mapping = cast(dict[str, object], value)
    if set(mapping) != expected_keys:
        raise _fail(f"{field_name} 欄位不完整或含未知欄位")
    return mapping


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail(f"JSON object 含重複 key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _fail(f"JSON 不允許非有限數值常數: {value}")


def _strict_json_load(raw: bytes | str) -> object:
    if type(raw) is bytes:
        if len(raw) > _MAX_JSON_BYTES:
            raise _fail("期間精度 JSON 超過 byte budget")
        payload = raw
    elif type(raw) is str:
        try:
            payload = raw.encode("utf-8")
        except UnicodeError as exc:
            raise _fail("期間精度 JSON 無法編成 UTF-8") from exc
        if len(payload) > _MAX_JSON_BYTES:
            raise _fail("期間精度 JSON 超過 byte budget")
    else:
        raise _fail("期間精度 JSON 必須是 bytes 或 str")
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except RecommendationPortfolioPeriodPrecisionV2Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise _fail("期間精度內容不是有效 UTF-8 JSON") from exc


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioPeriodObservationV2:
    """單一股票每日原始 Decimal observation；不含任何重算 P&L。"""

    session_date: str
    stock_code: str
    cash_decimal: str
    position_value_decimal: str
    equity_decimal: str
    realized_pnl_decimal: str | None = None
    unrealized_pnl_decimal: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_date", _require_iso_date(self.session_date, "session_date"))
        if type(self.stock_code) is not str or _STOCK_CODE_PATTERN.fullmatch(self.stock_code) is None:
            raise _fail("observation stock_code 必須是有界單一股票代號")
        for field_name in ("cash_decimal", "position_value_decimal", "equity_decimal"):
            text, _ = _parse_decimal_text(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, text)
        for field_name in ("realized_pnl_decimal", "unrealized_pnl_decimal"):
            value = getattr(self, field_name)
            if value is not None:
                text, _ = _parse_decimal_text(value, field_name)
                object.__setattr__(self, field_name, text)
        if not _decimal_add_equals(
            self.cash_decimal, self.position_value_decimal, self.equity_decimal
        ):
            raise _fail("observation equity 必須精確等於 cash + position_value")

    def _source_dict(self) -> dict[str, object]:
        return {
            "session_date": self.session_date,
            "stock_code": self.stock_code,
            "cash_decimal": self.cash_decimal,
            "position_value_decimal": self.position_value_decimal,
            "equity_decimal": self.equity_decimal,
            "realized_pnl_decimal": self.realized_pnl_decimal,
            "unrealized_pnl_decimal": self.unrealized_pnl_decimal,
        }

    @classmethod
    def from_dict(cls, value: object) -> RecommendationPortfolioPeriodObservationV2:
        fields = _strict_object(
            value,
            {
                "session_date",
                "stock_code",
                "cash_decimal",
                "position_value_decimal",
                "equity_decimal",
                "realized_pnl_decimal",
                "unrealized_pnl_decimal",
            },
            "observation",
        )
        return cls(
            session_date=cast(str, fields["session_date"]),
            stock_code=cast(str, fields["stock_code"]),
            cash_decimal=cast(str, fields["cash_decimal"]),
            position_value_decimal=cast(str, fields["position_value_decimal"]),
            equity_decimal=cast(str, fields["equity_decimal"]),
            realized_pnl_decimal=cast(str | None, fields["realized_pnl_decimal"]),
            unrealized_pnl_decimal=cast(str | None, fields["unrealized_pnl_decimal"]),
        )


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioPeriodPrecisionV2:
    """有界、版本化的精確期間來源封套，不是績效或資格認證。"""

    schema_version: ClassVar[str] = RECOMMENDATION_PORTFOLIO_PERIOD_PRECISION_SCHEMA_V2

    registry_run_id: str
    portfolio_parent_id: str
    strategy_id: str
    strategy_version: str
    stock_code: str
    initial_capital_decimal: str
    currency_code: str | None
    minor_unit_exponent: int | None
    currency_authority: str | None
    source_fingerprint_sha256: str | None
    source_manifest_sha256: str | None
    source_raw_sha256: str | None
    equity_parquet_sha256: str | None
    trades_parquet_sha256: str | None
    source_cutoff_at: str | None
    source_available_at: str | None
    source_availability_basis: str | None
    source_quality_status: SourceQualityStatusV2
    session_calendar_id: str | None
    session_calendar_version: str | None
    session_calendar_sha256: str | None
    expected_session_dates: tuple[str, ...] | None
    completion_status: CompletionStatusV2
    execution_contract_id: str
    execution_contract_version: str
    execution_contract_sha256: str | None
    cost_model_id: str
    cost_model_version: str
    cost_model_sha256: str | None
    observations: tuple[RecommendationPortfolioPeriodObservationV2, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "registry_run_id",
            "portfolio_parent_id",
            "strategy_id",
            "strategy_version",
            "execution_contract_id",
            "execution_contract_version",
            "cost_model_id",
            "cost_model_version",
        ):
            object.__setattr__(self, field_name, _require_text(getattr(self, field_name), field_name))
        if type(self.stock_code) is not str or _STOCK_CODE_PATTERN.fullmatch(self.stock_code) is None:
            raise _fail("period stock_code 必須是有界單一股票代號")

        initial_text, _ = _parse_decimal_text(self.initial_capital_decimal, "initial_capital_decimal")
        object.__setattr__(self, "initial_capital_decimal", initial_text)

        currency_code = _require_optional_text(self.currency_code, "currency_code", maximum=3)
        authority = _require_optional_text(self.currency_authority, "currency_authority")
        if currency_code is not None and _CURRENCY_PATTERN.fullmatch(currency_code) is None:
            raise _fail("currency_code 必須是大寫三字母 ISO 4217 代碼語法")
        if self.minor_unit_exponent is not None:
            if (
                type(self.minor_unit_exponent) is not int
                or self.minor_unit_exponent < 0
                or self.minor_unit_exponent > _MAX_MINOR_UNIT_EXPONENT
            ):
                raise _fail("minor_unit_exponent 必須是 0 到 9 的明示整數")
        if (currency_code is None) != (self.minor_unit_exponent is None):
            raise _fail("currency_code 與 minor_unit_exponent 必須同時明示或同時為 None")
        object.__setattr__(self, "currency_code", currency_code)
        object.__setattr__(self, "currency_authority", authority)

        for field_name in (
            "source_fingerprint_sha256",
            "source_manifest_sha256",
            "source_raw_sha256",
            "equity_parquet_sha256",
            "trades_parquet_sha256",
            "session_calendar_sha256",
            "execution_contract_sha256",
            "cost_model_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_sha256_or_none(getattr(self, field_name), field_name),
            )
        for field_name in (
            "source_cutoff_at",
            "source_available_at",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_aware_datetime_or_none(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "source_availability_basis",
            _require_optional_text(self.source_availability_basis, "source_availability_basis"),
        )
        if self.source_quality_status not in ("verified", "unverified", "unknown"):
            raise _fail("source_quality_status 必須是 verified/unverified/unknown")
        if type(self.source_quality_status) is not str:
            raise _fail("source_quality_status 必須是明確文字狀態")

        for field_name in ("session_calendar_id", "session_calendar_version"):
            object.__setattr__(
                self,
                field_name,
                _require_optional_text(getattr(self, field_name), field_name),
            )
        expected_dates = _require_dates(self.expected_session_dates, "expected_session_dates")
        object.__setattr__(self, "expected_session_dates", expected_dates)
        if self.completion_status not in ("completed", "cancelled", "failed", "truncated"):
            raise _fail("completion_status 必須是 typed completion 狀態")
        if type(self.completion_status) is not str:
            raise _fail("completion_status 必須是明確文字狀態")

        raw_observations = self.observations
        if type(raw_observations) not in (tuple, list):
            raise _fail("observations 必須是有界 tuple/list")
        if not raw_observations or len(raw_observations) > _MAX_OBSERVATIONS:
            raise _fail(f"observations 不可為空且不得超過 {_MAX_OBSERVATIONS} 列")
        observations = tuple(raw_observations)
        if any(type(row) is not RecommendationPortfolioPeriodObservationV2 for row in observations):
            raise _fail("observations 只能包含已驗證的 V2 observation DTO")
        if any(row.stock_code != self.stock_code for row in observations):
            raise _fail("observation stock_code 不得跨接 period 的單一股票")
        dates = tuple(row.session_date for row in observations)
        if any(right <= left for left, right in zip(dates, dates[1:])):
            raise _fail("observation 日期必須唯一且嚴格遞增")
        object.__setattr__(self, "observations", observations)

        exponent = self.minor_unit_exponent if currency_code is not None else None
        if exponent is not None:
            money_values = [initial_text]
            for row in observations:
                money_values.extend(
                    [row.cash_decimal, row.position_value_decimal, row.equity_decimal]
                )
                if row.realized_pnl_decimal is not None:
                    money_values.append(row.realized_pnl_decimal)
                if row.unrealized_pnl_decimal is not None:
                    money_values.append(row.unrealized_pnl_decimal)
            for value in money_values:
                if _exact_minor_units(value, exponent) is None:
                    raise _fail(
                        "明示 minor_unit_exponent 無法精確表示某筆 Decimal；禁止二次捨入"
                    )

    @classmethod
    def create(
        cls,
        *,
        registry_run_id: str,
        portfolio_parent_id: str,
        strategy_id: str,
        strategy_version: str,
        stock_code: str,
        initial_capital_decimal: str,
        currency_code: str | None,
        minor_unit_exponent: int | None,
        currency_authority: str | None,
        source_fingerprint_sha256: str | None,
        source_manifest_sha256: str | None,
        source_raw_sha256: str | None,
        equity_parquet_sha256: str | None,
        trades_parquet_sha256: str | None,
        source_cutoff_at: str | None,
        source_available_at: str | None,
        source_availability_basis: str | None,
        source_quality_status: SourceQualityStatusV2,
        session_calendar_id: str | None,
        session_calendar_version: str | None,
        session_calendar_sha256: str | None,
        expected_session_dates: tuple[str, ...] | list[str] | None,
        completion_status: CompletionStatusV2,
        execution_contract_id: str,
        execution_contract_version: str,
        execution_contract_sha256: str | None,
        cost_model_id: str,
        cost_model_version: str,
        cost_model_sha256: str | None,
        observations: tuple[RecommendationPortfolioPeriodObservationV2, ...]
        | list[RecommendationPortfolioPeriodObservationV2],
    ) -> RecommendationPortfolioPeriodPrecisionV2:
        """建立有界契約；所有來源與貨幣欄位均由 caller 明示。"""

        if type(observations) not in (tuple, list):
            raise _fail("observations 必須是有界 observation 序列")
        return cls(
            registry_run_id=registry_run_id,
            portfolio_parent_id=portfolio_parent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            stock_code=stock_code,
            initial_capital_decimal=initial_capital_decimal,
            currency_code=currency_code,
            minor_unit_exponent=minor_unit_exponent,
            currency_authority=currency_authority,
            source_fingerprint_sha256=source_fingerprint_sha256,
            source_manifest_sha256=source_manifest_sha256,
            source_raw_sha256=source_raw_sha256,
            equity_parquet_sha256=equity_parquet_sha256,
            trades_parquet_sha256=trades_parquet_sha256,
            source_cutoff_at=source_cutoff_at,
            source_available_at=source_available_at,
            source_availability_basis=source_availability_basis,
            source_quality_status=source_quality_status,
            session_calendar_id=session_calendar_id,
            session_calendar_version=session_calendar_version,
            session_calendar_sha256=session_calendar_sha256,
            expected_session_dates=_require_dates(expected_session_dates, "expected_session_dates"),
            completion_status=completion_status,
            execution_contract_id=execution_contract_id,
            execution_contract_version=execution_contract_version,
            execution_contract_sha256=execution_contract_sha256,
            cost_model_id=cost_model_id,
            cost_model_version=cost_model_version,
            cost_model_sha256=cost_model_sha256,
            observations=tuple(observations),
        )

    @property
    def actual_session_dates(self) -> tuple[str, ...]:
        return tuple(row.session_date for row in self.observations)

    @property
    def coverage_status(self) -> Literal["complete", "partial", "unknown"]:
        if self.expected_session_dates is None:
            return "unknown"
        if self.actual_session_dates == self.expected_session_dates:
            return "complete"
        return "partial"

    @property
    def money_comparable(self) -> bool:
        """Structural readiness only; it is not source, performance, or broker qualification."""

        return all(
            (
                self.completion_status == "completed",
                self.coverage_status == "complete",
                self.currency_code is not None,
                self.minor_unit_exponent is not None,
                self.currency_authority is not None,
                self.source_quality_status == "verified",
                self.source_fingerprint_sha256 is not None,
                self.source_manifest_sha256 is not None,
                self.source_raw_sha256 is not None,
                self.equity_parquet_sha256 is not None,
                self.trades_parquet_sha256 is not None,
                self.source_cutoff_at is not None,
                self.source_available_at is not None,
                self.source_availability_basis is not None,
                self.session_calendar_id is not None,
                self.session_calendar_version is not None,
                self.session_calendar_sha256 is not None,
                self.execution_contract_sha256 is not None,
                self.cost_model_sha256 is not None,
            )
        )

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    @property
    def performance_eligible(self) -> bool:
        return False

    @property
    def broker_eligible(self) -> bool:
        return False

    def _observation_document(
        self,
        row: RecommendationPortfolioPeriodObservationV2,
    ) -> dict[str, object]:
        exponent = self.minor_unit_exponent if self.currency_code is not None else None
        source = row._source_dict()
        minor_units = {
            "cash": _exact_minor_units(row.cash_decimal, exponent),
            "position_value": _exact_minor_units(row.position_value_decimal, exponent),
            "equity": _exact_minor_units(row.equity_decimal, exponent),
            "realized_pnl": (
                _exact_minor_units(row.realized_pnl_decimal, exponent)
                if row.realized_pnl_decimal is not None
                else None
            ),
            "unrealized_pnl": (
                _exact_minor_units(row.unrealized_pnl_decimal, exponent)
                if row.unrealized_pnl_decimal is not None
                else None
            ),
        }
        document = {**source, "minor_units": minor_units}
        return {**document, "observation_sha256": _digest(document)}

    def _payload_dict(self) -> dict[str, object]:
        observation_documents = [self._observation_document(row) for row in self.observations]
        expected_dates = (
            list(self.expected_session_dates)
            if self.expected_session_dates is not None
            else None
        )
        actual_dates = list(self.actual_session_dates)
        return {
            "schema_version": self.schema_version,
            "registry_run_id": self.registry_run_id,
            "portfolio_parent_id": self.portfolio_parent_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "stock_code": self.stock_code,
            "initial_capital_decimal": self.initial_capital_decimal,
            "currency_code": self.currency_code,
            "minor_unit_exponent": self.minor_unit_exponent,
            "currency_authority": self.currency_authority,
            "source_fingerprint_sha256": self.source_fingerprint_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "equity_parquet_sha256": self.equity_parquet_sha256,
            "trades_parquet_sha256": self.trades_parquet_sha256,
            "source_cutoff_at": self.source_cutoff_at,
            "source_available_at": self.source_available_at,
            "source_availability_basis": self.source_availability_basis,
            "source_quality_status": self.source_quality_status,
            "session_calendar_id": self.session_calendar_id,
            "session_calendar_version": self.session_calendar_version,
            "session_calendar_sha256": self.session_calendar_sha256,
            "expected_session_dates": expected_dates,
            "expected_session_count": (
                len(self.expected_session_dates)
                if self.expected_session_dates is not None
                else None
            ),
            "expected_session_dates_sha256": (
                _digest(expected_dates) if expected_dates is not None else None
            ),
            "actual_session_dates": actual_dates,
            "actual_start_date": actual_dates[0],
            "actual_end_date": actual_dates[-1],
            "actual_session_count": len(actual_dates),
            "actual_session_dates_sha256": _digest(actual_dates),
            "coverage_status": self.coverage_status,
            "completion_status": self.completion_status,
            "observation_count": len(observation_documents),
            "observations_sha256": _digest(observation_documents),
            "observations": observation_documents,
            "execution_contract_id": self.execution_contract_id,
            "execution_contract_version": self.execution_contract_version,
            "execution_contract_sha256": self.execution_contract_sha256,
            "cost_model_id": self.cost_model_id,
            "cost_model_version": self.cost_model_version,
            "cost_model_sha256": self.cost_model_sha256,
            "money_comparable": self.money_comparable,
            "historical_pit_eligible": False,
            "performance_eligible": False,
            "broker_eligible": False,
        }

    @property
    def payload_sha256(self) -> str:
        return _digest(self._payload_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self._payload_dict()
        return {**payload, "payload_sha256": _digest(payload)}

    def to_json(self) -> str:
        raw = _canonical_json_bytes(self.to_dict())
        if len(raw) > _MAX_JSON_BYTES:
            raise _fail("期間精度 JSON 超過 byte budget")
        return raw.decode("utf-8")

    @classmethod
    def from_dict(cls, value: object) -> RecommendationPortfolioPeriodPrecisionV2:
        expected_keys = {
            "schema_version",
            "registry_run_id",
            "portfolio_parent_id",
            "strategy_id",
            "strategy_version",
            "stock_code",
            "initial_capital_decimal",
            "currency_code",
            "minor_unit_exponent",
            "currency_authority",
            "source_fingerprint_sha256",
            "source_manifest_sha256",
            "source_raw_sha256",
            "equity_parquet_sha256",
            "trades_parquet_sha256",
            "source_cutoff_at",
            "source_available_at",
            "source_availability_basis",
            "source_quality_status",
            "session_calendar_id",
            "session_calendar_version",
            "session_calendar_sha256",
            "expected_session_dates",
            "expected_session_count",
            "expected_session_dates_sha256",
            "actual_session_dates",
            "actual_start_date",
            "actual_end_date",
            "actual_session_count",
            "actual_session_dates_sha256",
            "coverage_status",
            "completion_status",
            "observation_count",
            "observations_sha256",
            "observations",
            "execution_contract_id",
            "execution_contract_version",
            "execution_contract_sha256",
            "cost_model_id",
            "cost_model_version",
            "cost_model_sha256",
            "money_comparable",
            "historical_pit_eligible",
            "performance_eligible",
            "broker_eligible",
            "payload_sha256",
        }
        mapping = _strict_object(value, expected_keys, "period precision")
        if mapping["schema_version"] != cls.schema_version:
            raise _fail("不支援的期間精度 schema_version")
        serialized_observations = mapping["observations"]
        if type(serialized_observations) is not list or not serialized_observations:
            raise _fail("observations 必須是非空 JSON array")
        if len(serialized_observations) > _MAX_OBSERVATIONS:
            raise _fail("observations 超過列數 budget")
        observations: list[RecommendationPortfolioPeriodObservationV2] = []
        for index, item in enumerate(serialized_observations):
            row_mapping = _strict_object(
                item,
                {
                    "session_date",
                    "stock_code",
                    "cash_decimal",
                    "position_value_decimal",
                    "equity_decimal",
                    "realized_pnl_decimal",
                    "unrealized_pnl_decimal",
                    "minor_units",
                    "observation_sha256",
                },
                f"observations[{index}]",
            )
            observations.append(
                RecommendationPortfolioPeriodObservationV2.from_dict(
                    {
                        key: row_mapping[key]
                        for key in (
                            "session_date",
                            "stock_code",
                            "cash_decimal",
                            "position_value_decimal",
                            "equity_decimal",
                            "realized_pnl_decimal",
                            "unrealized_pnl_decimal",
                        )
                    }
                )
            )
        expected_dates_value = mapping["expected_session_dates"]
        if expected_dates_value is not None and type(expected_dates_value) is not list:
            raise _fail("expected_session_dates 必須是 JSON array 或 null")
        exponent_value = mapping["minor_unit_exponent"]
        if exponent_value is not None and type(exponent_value) is not int:
            raise _fail("minor_unit_exponent 必須是 JSON 整數或 null")
        candidate = cls.create(
            registry_run_id=cast(str, mapping["registry_run_id"]),
            portfolio_parent_id=cast(str, mapping["portfolio_parent_id"]),
            strategy_id=cast(str, mapping["strategy_id"]),
            strategy_version=cast(str, mapping["strategy_version"]),
            stock_code=cast(str, mapping["stock_code"]),
            initial_capital_decimal=cast(str, mapping["initial_capital_decimal"]),
            currency_code=cast(str | None, mapping["currency_code"]),
            minor_unit_exponent=cast(int | None, exponent_value),
            currency_authority=cast(str | None, mapping["currency_authority"]),
            source_fingerprint_sha256=cast(str | None, mapping["source_fingerprint_sha256"]),
            source_manifest_sha256=cast(str | None, mapping["source_manifest_sha256"]),
            source_raw_sha256=cast(str | None, mapping["source_raw_sha256"]),
            equity_parquet_sha256=cast(str | None, mapping["equity_parquet_sha256"]),
            trades_parquet_sha256=cast(str | None, mapping["trades_parquet_sha256"]),
            source_cutoff_at=cast(str | None, mapping["source_cutoff_at"]),
            source_available_at=cast(str | None, mapping["source_available_at"]),
            source_availability_basis=cast(str | None, mapping["source_availability_basis"]),
            source_quality_status=cast(SourceQualityStatusV2, mapping["source_quality_status"]),
            session_calendar_id=cast(str | None, mapping["session_calendar_id"]),
            session_calendar_version=cast(str | None, mapping["session_calendar_version"]),
            session_calendar_sha256=cast(str | None, mapping["session_calendar_sha256"]),
            expected_session_dates=cast(tuple[str, ...] | list[str] | None, expected_dates_value),
            completion_status=cast(CompletionStatusV2, mapping["completion_status"]),
            execution_contract_id=cast(str, mapping["execution_contract_id"]),
            execution_contract_version=cast(str, mapping["execution_contract_version"]),
            execution_contract_sha256=cast(str | None, mapping["execution_contract_sha256"]),
            cost_model_id=cast(str, mapping["cost_model_id"]),
            cost_model_version=cast(str, mapping["cost_model_version"]),
            cost_model_sha256=cast(str | None, mapping["cost_model_sha256"]),
            observations=observations,
        )
        if _canonical_json_bytes(candidate.to_dict()) != _canonical_json_bytes(mapping):
            raise _fail("期間精度序列化的來源欄位、派生欄位或 digest 不一致")
        return candidate

    @classmethod
    def from_json(cls, raw: bytes | str) -> RecommendationPortfolioPeriodPrecisionV2:
        return cls.from_dict(_strict_json_load(raw))


__all__ = [
    "CompletionStatusV2",
    "RECOMMENDATION_PORTFOLIO_PERIOD_PRECISION_SCHEMA_V2",
    "RecommendationPortfolioPeriodObservationV2",
    "RecommendationPortfolioPeriodPrecisionV2",
    "RecommendationPortfolioPeriodPrecisionV2Error",
    "SourceQualityStatusV2",
]
