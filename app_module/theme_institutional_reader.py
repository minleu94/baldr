"""把明選 TPEx 法人原股數投影成題材研究的診斷觀察。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from app_module.institutional_daily_snapshot import (
    InstitutionalDailyRow,
    InstitutionalDailySnapshotBatchRead,
    InstitutionalDailySnapshotPin,
    read_institutional_daily_snapshot_batch,
)
from app_module.institutional_source_use import (
    InstitutionalSourceUsePin,
    InstitutionalSourceUseRead,
    TPEX_INSTITUTIONAL_USE_SCOPE,
)
from app_module.theme_daily_service import ThemeFlowObservation, ThemeMarketInput
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from data_module.tpex_institutional_openapi import TPEX_OPENAPI_VERSION


_TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
_FOUR_DIGIT_STOCK = re.compile(r"[0-9]{4}", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_DIAGNOSTIC_WARNING = "institutional_tpex_diagnostics_only"
_TPEx_CAPTURE_SCOPE = "tpex_openapi_institutional"


class TPExThemeFlowReader:
    """以同一固定 TPEx 批次提供明選成員的三大法人診斷觀察。"""

    def __init__(
        self,
        pin: InstitutionalDailySnapshotPin,
        *,
        source_use_pin: InstitutionalSourceUsePin,
        eligible_stock_ids: tuple[str, ...],
    ) -> None:
        if type(pin) is not InstitutionalDailySnapshotPin:
            raise TypeError("法人診斷讀者須提供精確固定批次 pin")
        if type(source_use_pin) is not InstitutionalSourceUsePin:
            raise TypeError("法人診斷讀者須提供精確 TPEx 用途 pin")
        if (
            type(eligible_stock_ids) is not tuple
            or len(eligible_stock_ids) > 5000
            or any(
                type(stock_id) is not str
                or _FOUR_DIGIT_STOCK.fullmatch(stock_id) is None
                for stock_id in eligible_stock_ids
            )
            or len(set(eligible_stock_ids)) != len(eligible_stock_ids)
        ):
            raise ValueError("TPEx 題材成員須為唯一四碼代號tuple，最多5000檔")
        self.pin = pin
        self.source_use_pin = source_use_pin
        self.eligible_stock_ids = eligible_stock_ids
        self._eligible_stock_id_set = frozenset(eligible_stock_ids)

    def read(
        self,
        stock_ids: tuple[str, ...],
        data_date: date,
        known_at: datetime,
    ) -> ThemeMarketInput:
        """只投影指定日期的原三類 net 股數，不補日期、股票或金額。"""

        if (
            type(stock_ids) is not tuple
            or len(stock_ids) > 5000
            or any(
                type(stock_id) is not str
                or _FOUR_DIGIT_STOCK.fullmatch(stock_id) is None
                for stock_id in stock_ids
            )
            or len(set(stock_ids)) != len(stock_ids)
        ):
            raise ValueError("法人題材成員須為唯一四碼代號tuple，最多5000檔")
        if type(data_date) is not date:
            raise TypeError("法人題材觀察資料日必須是date")
        if (
            not isinstance(known_at, datetime)
            or known_at.tzinfo is None
            or known_at.utcoffset() is None
        ):
            raise ValueError("法人題材查詢時間必須包含時區")
        if data_date > known_at.astimezone(_TAIPEI).date():
            raise ValueError("法人題材資料日不得晚於台北查詢日期")

        selected = tuple(
            stock_id for stock_id in stock_ids
            if stock_id in self._eligible_stock_id_set
        )
        warnings = [_DIAGNOSTIC_WARNING]
        if len(selected) != len(stock_ids):
            warnings.append("non_tpex_members_excluded")
        if not selected:
            warnings.append("no_selected_members")
            return ThemeMarketInput(warnings=tuple(warnings))

        batch = read_institutional_daily_snapshot_batch(
            self.pin,
            stock_codes=selected,
            decision_cutoff=known_at,
            source_use_pin=self.source_use_pin,
            _expected_scope=_TPEx_CAPTURE_SCOPE,
        )
        source_use = self._validate_batch(batch, selected, known_at)

        rows_by_code: dict[str, InstitutionalDailyRow] = {}
        codes_with_other_dates: set[str] = set()
        codes_with_any_rows: set[str] = set()
        seen_code_dates: set[tuple[str, date]] = set()
        for row in batch.rows:
            if type(row) is not InstitutionalDailyRow:
                raise TypeError("TPEx 法人批次含非型別化原始列")
            if row.stock_code not in selected:
                raise ValueError("TPEx 法人批次回傳未明選股票")
            if type(row.decision_date) is not str:
                raise ValueError("TPEx 法人原列資料日格式不符")
            try:
                row_date = date.fromisoformat(row.decision_date)
            except ValueError as exc:
                raise ValueError("TPEx 法人原列資料日格式不符") from exc
            if row_date.isoformat() != row.decision_date:
                raise ValueError("TPEx 法人原列資料日非標準ISO日期")
            identity = (row.stock_code, row_date)
            if identity in seen_code_dates:
                raise ValueError("TPEx 法人同一股票同日原列重複")
            seen_code_dates.add(identity)
            codes_with_any_rows.add(row.stock_code)
            if row_date != data_date:
                codes_with_other_dates.add(row.stock_code)
                continue
            self._validate_daily_row(row)
            rows_by_code[row.stock_code] = row

        for stock_id in selected:
            if stock_id in rows_by_code:
                continue
            if stock_id in codes_with_other_dates:
                warnings.append("institutional_date_mismatch")
            elif stock_id not in codes_with_any_rows:
                warnings.append("institutional_selected_member_not_found")

        accepted_at = source_use.acceptance.accepted_at
        available_at = max(batch.available_hour, accepted_at)
        if available_at > known_at:
            raise ValueError("TPEx 法人批次／用途接受時間晚於查詢時間")

        flows: list[ThemeFlowObservation] = []
        for stock_id in selected:
            selected_row = rows_by_code.get(stock_id)
            if selected_row is None:
                continue
            net_shares = (
                selected_row.foreign_investor_net
                + selected_row.investment_trust_net
                + selected_row.dealer_net
            )
            source_id = (
                "TPEx diagnostics only; "
                f"stock_id={stock_id}; "
                f"source_version={selected_row.source_version}; "
                f"raw_sha256={selected_row.raw_sha256}; "
                f"daily_manifest_sha256={batch.pin.manifest_sha256}; "
                f"daily_receipt_sha256={batch.pin.receipt_sha256}; "
                f"source_use_sha256={self.source_use_pin.sha256}; "
                f"attribution={source_use.attribution}"
            )
            flows.append(
                ThemeFlowObservation(
                    stock_id=stock_id,
                    data_date=data_date,
                    available_at=available_at,
                    source_id=source_id,
                    net_shares=net_shares,
                    net_turnover_twd=None,
                )
            )

        return ThemeMarketInput(
            flows=tuple(flows),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _validate_batch(
        self,
        batch: object,
        selected: tuple[str, ...],
        known_at: datetime,
    ) -> InstitutionalSourceUseRead:
        if type(batch) is not InstitutionalDailySnapshotBatchRead:
            raise TypeError("TPEx 法人讀者未回傳精確批次型別")
        if (
            type(batch.pin) is not InstitutionalDailySnapshotPin
            or batch.pin != self.pin
            or type(batch.stock_codes) is not tuple
            or batch.stock_codes != selected
            or type(batch.rows) is not tuple
            or type(batch.total_records) is not int
            or batch.total_records < len(batch.rows)
        ):
            raise ValueError("TPEx 法人批次 pin／明選股票不符")
        if (
            batch.market != "TPEx"
            or batch.candidate_only is not True
            or batch.source_use_accepted is not True
            or batch.historical_pit_eligible is not False
        ):
            raise ValueError("法人批次不符合 TPEx diagnostics-only 用途")
        source_use = batch.source_use
        if type(source_use) is not InstitutionalSourceUseRead:
            raise TypeError("TPEx 法人批次缺少型別化用途讀回")
        if source_use.pin != self.source_use_pin:
            raise ValueError("TPEx 法人批次用途 pin 與明選來源不符")
        acceptance = source_use.acceptance
        if type(acceptance) is not DailySourceUseAcceptance:
            raise TypeError("TPEx 法人來源用途缺少精確接受型別")
        if (
            acceptance.scope != TPEX_INSTITUTIONAL_USE_SCOPE
            or acceptance.authorization_scope != "diagnostics"
        ):
            raise ValueError("TPEx 法人來源用途未接受、scope不符或晚於查詢時間")
        if (
            not isinstance(batch.available_hour, datetime)
            or batch.available_hour.tzinfo is None
            or batch.available_hour.utcoffset() is None
        ):
            raise ValueError("TPEx 法人批次可用時間必須包含時區")
        if (
            not isinstance(acceptance.accepted_at, datetime)
            or acceptance.accepted_at.tzinfo is None
            or acceptance.accepted_at.utcoffset() is None
        ):
            raise ValueError("TPEx 法人用途接受時間必須包含時區")
        if acceptance.accepted_at > known_at:
            raise ValueError("TPEx 法人來源用途接受晚於查詢時間")
        return source_use

    @staticmethod
    def _validate_daily_row(row: InstitutionalDailyRow) -> None:
        if (
            type(row.source_version) is not str
            or row.source_version != TPEX_OPENAPI_VERSION
            or type(row.raw_sha256) is not str
            or _SHA256.fullmatch(row.raw_sha256) is None
        ):
            raise ValueError("TPEx 法人原列缺少正確source version或raw SHA")
        net_fields = (
            row.foreign_investor_net,
            row.investment_trust_net,
            row.dealer_net,
        )
        if any(type(value) is not int for value in net_fields):
            raise ValueError("TPEx 法人三類 net 股數必須是整數")
