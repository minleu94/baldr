"""TPEx資料集11856的明確OpenAPI aggregate股數契約；不推斷缺少的分項。"""

from __future__ import annotations

from datetime import date, datetime
import json
import re
from hashlib import sha256
from typing import Any

from data_module.institutional_credit_flows_service import (
    EndpointSpec, FlowCaptureError, MAX_RESPONSE_BYTES, ParsedSource, _base_row,
)

TPEX_OPENAPI_URL = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
TPEX_OPENAPI_VERSION = "tpex-openapi-3insti-daily.v1"
TPEX_OPENAPI_ENDPOINT = "tpex:openapi:3insti_daily_trading"
# 拼字與前置空白都是原Swagger及實際回應的欄名，不以suffix猜不同群組。
EX_FOREIGN = (
    "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Buy",
    " Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Sell",
    "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference",
)
FOREIGN_DEALERS = ("Foreign Dealers-Total Buy", "Foreign Dealers-TotalSell", "ForeignDealers-Difference")
FOREIGN_TOTAL = ("ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy",
                 "ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell",
                 "ForeignInvestorsInclude MainlandAreaInvestors-Difference")
TRUST = ("SecuritiesInvestmentTrustCompanies-TotalBuy", "SecuritiesInvestmentTrustCompanies-TotalSell",
         "SecuritiesInvestmentTrustCompanies-Difference")
DEALER = ("Dealers-TotalBuy", "Dealers-TotalSell", "Dealers-Difference")
FIELDS = frozenset(("Date", "SecuritiesCompanyCode", "CompanyName", "Dealers -TotalSell", "TotalDifference",
                    *EX_FOREIGN, *FOREIGN_DEALERS, *FOREIGN_TOTAL, *TRUST, *DEALER))


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise FlowCaptureError("TPEx OpenAPI duplicate field")
        result[key] = value
    return result


def _invalid_number(value: str) -> Any:
    raise FlowCaptureError("TPEx OpenAPI JSON numeric value not allowed: " + value[:32])


def _quantity(row: dict[str, str], name: str, *, signed: bool = False) -> int:
    text = row[name]
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", text) is None:
        raise FlowCaptureError("TPEx OpenAPI noncanonical integer: " + name)
    value = int(text)
    if not signed and value < 0:
        raise FlowCaptureError("TPEx OpenAPI negative buy/sell: " + name)
    return value


def parse_tpex_institutional_openapi(payload: bytes, *, requested_date: str, completed_at: datetime,
                                      spec: EndpointSpec, payload_sha256: str) -> ParsedSource:
    """嚴格完整單日；首個品質錯誤保留原件並拒絕整包，不補零。"""
    if (spec.url, spec.endpoint_id, spec.source_version, spec.quantity_unit, spec.market, dict(spec.params), spec.source_id) != (
        TPEX_OPENAPI_URL, TPEX_OPENAPI_ENDPOINT, TPEX_OPENAPI_VERSION, "shares", "TPEx", {}, "institutional_flows",
    ):
        raise FlowCaptureError("TPEx OpenAPI endpoint/version/unit mismatch")
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_RESPONSE_BYTES:
        raise FlowCaptureError("TPEx OpenAPI size/type mismatch")
    if sha256(payload).hexdigest() != payload_sha256:
        raise FlowCaptureError("TPEx OpenAPI raw hash mismatch")
    body = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                      parse_float=_invalid_number, parse_int=_invalid_number, parse_constant=_invalid_number)
    if type(body) is not list or not body:
        raise FlowCaptureError("TPEx OpenAPI requires nonempty daily rows")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in body:
        if type(raw) is not dict or set(raw) != FIELDS or any(type(value) is not str for value in raw.values()):
            raise FlowCaptureError("TPEx OpenAPI field schema/type mismatch")
        if re.fullmatch(r"[0-9]{7}", raw["Date"]) is None or int(raw["Date"][:3]) < 1:
            raise FlowCaptureError("TPEx OpenAPI report date mismatch")
        try:
            actual_date = date(int(raw["Date"][:3]) + 1911, int(raw["Date"][3:5]), int(raw["Date"][5:])).isoformat()
        except ValueError as exc:
            raise FlowCaptureError("TPEx OpenAPI report date mismatch") from exc
        if actual_date != requested_date:
            raise FlowCaptureError("TPEx OpenAPI report date mismatch")
        symbol = raw["SecuritiesCompanyCode"]
        if re.fullmatch(r"[A-Za-z0-9]{4,12}", symbol) is None or symbol in seen or not raw["CompanyName"].strip():
            raise FlowCaptureError("TPEx OpenAPI duplicate/invalid security identity")
        seen.add(symbol)
        groups = []
        for names in (EX_FOREIGN, FOREIGN_DEALERS, FOREIGN_TOTAL, TRUST, DEALER):
            values = tuple(_quantity(raw, name, signed=(i == 2)) for i, name in enumerate(names))
            if values[0] - values[1] != values[2]:
                raise FlowCaptureError("TPEx OpenAPI buy/sell/net conservation mismatch")
            groups.append(values)
        foreign = groups[2]
        if any(groups[0][i] + groups[1][i] != foreign[i] for i in range(3)):
            raise FlowCaptureError("TPEx OpenAPI foreign subtotal mismatch")
        trust, dealer = groups[3], groups[4]
        if foreign[2] + trust[2] + dealer[2] != _quantity(raw, "TotalDifference", signed=True):
            raise FlowCaptureError("TPEx OpenAPI declared total mismatch")
        if _quantity(raw, "Dealers -TotalSell") > dealer[1]:
            raise FlowCaptureError("TPEx OpenAPI hedge sell exceeds dealer total")
        item = _base_row(symbol=symbol, requested_date=requested_date, source_version=spec.source_version,
                         completed_at=completed_at, publication_at=None, endpoint_id=spec.endpoint_id,
                         market=spec.market, payload_sha256=payload_sha256, quantity_unit="shares")
        for actor, values in zip(("foreign_investor", "investment_trust", "dealer"), (foreign, trust, dealer)):
            item.update({f"{actor}_{suffix}": value for suffix, value in zip(("buy", "sell", "net"), values)})
        rows.append(item)
    return ParsedSource(tuple(rows), (), requested_date, None, "first_observed_only", "shares")
