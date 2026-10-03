import json
import time
import requests
import pandas as pd
import logging
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Mapping, Optional, Callable
from decimal import Decimal, InvalidOperation

from data_module.p0_official_source_parsers import (
    OfficialParserResult,
    RawFetchEnvelope,
    parse_tdcc_shareholding,
    parse_tpex_credit_openapi,
)

logger = logging.getLogger(__name__)

# User-Agent to prevent 403 Forbidden
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

OFFICIAL_PAYLOAD_MAX_ATTEMPTS = 3
OFFICIAL_PAYLOAD_RETRY_SECONDS = 30
TDCC_OPENAPI_URL = "https://openapi.tdcc.com.tw/v1/opendata/1-5"
TDCC_OPENAPI_SOURCE_VERSION = "tdcc-openapi-1-5.v1"
TDCC_OPENAPI_MAX_BYTES = 16 * 1024 * 1024
TPEX_CREDIT_OPENAPI_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance"
TPEX_CREDIT_OPENAPI_SOURCE_VERSION = "tpex-mainboard-margin-openapi.v1"


class OfficialPayloadNotReady(ValueError):
    """官方端點已回應，但指定交易日的明細尚未完成發布。"""


class _PayloadSizeLimitExceeded(ValueError):
    """Bounded official fetch exceeded its source-specific response cap."""


def observed_only_availability_fields() -> Dict[str, Any]:
    """官方未提供 publication timestamp 時，只保存本次實際觀測時間。"""
    first_observed_at = datetime.now(timezone.utc).isoformat()
    return {
        "publication_at": None,
        "first_observed_at": first_observed_at,
        "available_at": first_observed_at,
        "available_date": None,
        "quality": "degraded",
    }

def to_roc_date(dt: date) -> str:
    """轉換為民國年格式: YYY/MM/DD"""
    return f"{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}"

def safe_int(val) -> int:
    """安全轉換字串為整數，處理逗號與空值，不依賴 float。"""
    if pd.isna(val) or val is None or val == '':
        return 0
    if isinstance(val, str):
        val = val.replace(',', '').strip()
        if not val or val == 'X':
            return 0
        try:
            return int(Decimal(val).to_integral_value())
        except Exception:
            return 0
    try:
        return int(Decimal(str(val)).to_integral_value())
    except Exception:
        return 0


def _strict_credit_int(value: Any, *, field: str) -> int:
    """Parse one required credit quantity without converting malformed text to zero."""

    if value is None or pd.isna(value):
        raise ValueError(f"missing credit quantity: {field}")
    text = str(value).replace(",", "").strip()
    if text == "X":
        return 0
    if not text:
        raise ValueError(f"empty credit quantity: {field}")
    try:
        quantity = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid credit quantity for {field}: {text!r}") from exc
    if not quantity.is_finite() or quantity != quantity.to_integral_value():
        raise ValueError(f"non-integral credit quantity for {field}: {text!r}")
    parsed = int(quantity)
    if parsed < 0:
        raise ValueError(f"negative credit quantity for {field}: {text!r}")
    return parsed

def safe_request(
    url: str,
    params: Optional[Dict] = None,
    *,
    timeout_seconds: int = 10,
    max_attempts: int = 3,
) -> requests.Response:
    """帶可明確限定逾時與重試次數的安全請求。"""
    if timeout_seconds <= 0 or max_attempts <= 0:
        raise ValueError("timeout_seconds and max_attempts must be positive")
    last_http_status: int | None = None
    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout_seconds)
            if resp.status_code == 200:
                return resp
            last_http_status = int(resp.status_code)
            message = "正在重試..." if attempt + 1 < max_attempts else "不再重試。"
            logger.warning(f"請求失敗: {url}, 狀態碼: {resp.status_code}, {message}")
            resp.close()
        except requests.RequestException as e:
            message = "正在重試..." if attempt + 1 < max_attempts else "不再重試。"
            logger.warning(f"請求例外: {url}, 錯誤: {e}, {message}")
        if attempt + 1 < max_attempts:
            time.sleep(3)
    status_suffix = (
        f" (last HTTP status={last_http_status})"
        if last_http_status is not None
        else ""
    )
    raise RuntimeError(f"無法取得資料: {url}{status_suffix}")


def _safe_request_bounded_payload(
    url: str,
    *,
    max_response_bytes: int,
    timeout_seconds: int = 10,
    max_attempts: int = 3,
) -> tuple[bytes, dict[str, str], int]:
    """Stream a source-specific payload under a hard decoded-byte limit."""

    if max_response_bytes <= 0 or timeout_seconds <= 0 or max_attempts <= 0:
        raise ValueError("response cap, timeout, and attempts must be positive")
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        response = None
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout_seconds,
                stream=True,
            )
            if response.status_code != 200:
                last_error = RuntimeError(
                    f"HTTP status {response.status_code} for {url}"
                )
            else:
                headers = {str(key): str(value) for key, value in response.headers.items()}
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_bytes = int(content_length)
                    except (TypeError, ValueError) as exc:
                        raise ValueError("invalid Content-Length header") from exc
                    if declared_bytes < 0:
                        raise ValueError("negative Content-Length header")
                    if declared_bytes > max_response_bytes:
                        raise _PayloadSizeLimitExceeded(
                            f"Content-Length {declared_bytes} exceeds {max_response_bytes} bytes"
                        )

                chunks: list[bytes] = []
                received_bytes = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    received_bytes += len(chunk)
                    if received_bytes > max_response_bytes:
                        raise _PayloadSizeLimitExceeded(
                            f"response exceeds {max_response_bytes} bytes while streaming"
                        )
                    chunks.append(bytes(chunk))
                return b"".join(chunks), headers, int(response.status_code)
        except _PayloadSizeLimitExceeded:
            raise
        except requests.RequestException as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
        finally:
            if response is not None:
                response.close()
        if attempt + 1 < max_attempts:
            time.sleep(3)
    raise RuntimeError(
        f"bounded official request failed: {url}: "
        f"{type(last_error).__name__ if last_error else 'UnknownError'}: {last_error}"
    ) from last_error


def _request_ready_json(
    url: str,
    params: Dict[str, Any],
    *,
    source_label: str,
    validate: Callable[[Dict[str, Any]], None],
    max_attempts: int = OFFICIAL_PAYLOAD_MAX_ATTEMPTS,
    retry_seconds: int = OFFICIAL_PAYLOAD_RETRY_SECONDS,
) -> Dict[str, Any]:
    """對已連線但尚未發布完成的官方 payload 做有界重試。

    ``safe_request`` 負責 transport / HTTP 重試；這一層只處理 HTTP 200
    但 ``stat`` 或明細 table 尚未就緒的發布時點競態。日期不符等契約錯誤
    不在此重試，仍立即 fail-closed，避免錯日資料被接受。
    """

    if max_attempts <= 0 or retry_seconds < 0:
        raise ValueError("max_attempts must be positive and retry_seconds non-negative")
    for attempt in range(1, max_attempts + 1):
        payload = safe_request(url, params).json()
        try:
            validate(payload)
            return payload
        except OfficialPayloadNotReady as exc:
            if attempt >= max_attempts:
                raise
            logger.warning(
                "%s 已回應但資料尚未就緒（%d/%d）: %s；%d 秒後重試",
                source_label,
                attempt,
                max_attempts,
                exc,
                retry_seconds,
            )
            time.sleep(retry_seconds)
    raise RuntimeError(f"{source_label} payload retry exhausted")


_SECURITY_CODE_FIELD_NAMES = frozenset({"代號", "證券代號", "股票代號"})


def _validate_response_date(payload: Dict[str, Any], expected_date: str) -> None:
    """拒絕交易所回傳其他日期，避免 fallback 成為未來／錯日資料。"""

    response_date = str(payload.get("date", "")).strip().replace("/", "").replace("-", "")
    if response_date and response_date != expected_date:
        raise ValueError(
            f"官方回應日期不符：expected={expected_date}, actual={response_date}"
        )


def _security_table_rows(
    payload: Dict[str, Any],
    *,
    minimum_columns: int,
    strict_rows: bool = False,
) -> list[list[Any]]:
    """同時支援舊版 ``aaData`` 與現行 ``tables[].data`` shape。"""

    legacy_rows = payload.get("aaData")
    if isinstance(legacy_rows, list) and legacy_rows:
        if strict_rows and any(not isinstance(row, list) for row in legacy_rows):
            raise ValueError("official security table contains a non-row value")
        return [row for row in legacy_rows if isinstance(row, list)]

    for table in payload.get("tables", []):
        if not isinstance(table, dict):
            continue
        fields = table.get("fields", [])
        rows = table.get("data", [])
        if not isinstance(fields, list) or not isinstance(rows, list) or not rows:
            continue
        first_field = str(fields[0]).strip() if fields else ""
        if (
            len(fields) >= minimum_columns
            and first_field in _SECURITY_CODE_FIELD_NAMES
        ):
            if strict_rows and any(not isinstance(row, list) for row in rows):
                raise ValueError("official security table contains a non-row value")
            return [row for row in rows if isinstance(row, list)]
    return []


def _parse_legacy_credit_rows(
    rows: list[list[Any]],
    *,
    decision_date: date,
    source_version: str,
    minimum_columns: int,
    quantity_columns: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Accept one complete legacy market table or fail it as a whole."""

    if not rows:
        raise ValueError(f"{source_version} contains no valid detail rows")
    availability = observed_only_availability_fields()
    parsed_rows: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if len(row) < minimum_columns:
            raise ValueError(
                f"{source_version} row {index} is short: "
                f"expected at least {minimum_columns} columns, got {len(row)}"
            )
        stock_code = str(row[0] or "").strip()
        if not stock_code:
            raise ValueError(f"{source_version} row {index} has no stock code")
        if stock_code in seen_symbols:
            raise ValueError(f"{source_version} duplicate stock code: {stock_code}")
        seen_symbols.add(stock_code)
        quantities = {
            name: _strict_credit_int(row[column], field=f"{name}[{index}]")
            for name, column in quantity_columns.items()
        }
        parsed_rows.append(
            {
                "stock_code": stock_code,
                "decision_date": decision_date.isoformat(),
                "source_version": source_version,
                **availability,
                **quantities,
                "financing": None,
                "securities_lending": None,
            }
        )
    if not parsed_rows:
        raise ValueError(f"{source_version} contains no valid detail rows")
    return parsed_rows


def _table_count(payload: Dict[str, Any]) -> int:
    tables = payload.get("tables")
    return len(tables) if isinstance(tables, list) else 0


def _response_payload_bytes(response: Any) -> bytes:
    payload = getattr(response, "content", None)
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)
    text = getattr(response, "text", None)
    if isinstance(text, str):
        encoding = getattr(response, "encoding", None) or "utf-8"
        return text.encode(str(encoding))
    raise TypeError("官方回應缺少 bytes payload")


def _require_complete_parse(result: OfficialParserResult, source_name: str) -> None:
    if not result.accepted:
        raise ValueError(f"{source_name} payload has no accepted rows")
    if result.quarantine or result.duplicate_row_count or result.blocked_row_count:
        raise ValueError(
            f"{source_name} payload is incomplete: accepted={result.accepted_row_count}, "
            f"quarantined={result.quarantine_row_count}, "
            f"duplicates={result.duplicate_row_count}, blocked={result.blocked_row_count}"
        )
    if result.accepted_row_count != result.raw_row_count:
        raise ValueError(
            f"{source_name} payload row conservation failed: "
            f"raw={result.raw_row_count}, accepted={result.accepted_row_count}"
        )


def _fetch_tpex_credit_openapi(decision_date: date) -> list[dict[str, Any]]:
    """Read exact-date TPEx credit rows from its registered official OpenAPI."""

    response = safe_request(TPEX_CREDIT_OPENAPI_URL)
    payload = _response_payload_bytes(response)
    fetched_at = datetime.now(timezone.utc)
    envelope = RawFetchEnvelope(
        source_id="credit_transactions",
        source_version=TPEX_CREDIT_OPENAPI_SOURCE_VERSION,
        endpoint_id="tpex:openapi:tpex_mainboard_margin_balance",
        request_parameters={},
        fetched_at=fetched_at,
        http_status=int(getattr(response, "status_code", 200)),
        http_headers=dict(getattr(response, "headers", {}) or {}),
        payload=payload,
    )
    parsed = parse_tpex_credit_openapi(envelope)
    _require_complete_parse(parsed, "TPEx credit OpenAPI")
    requested_date = decision_date.isoformat()
    observed_dates = {row.observation_date for row in parsed.accepted}
    if observed_dates != {requested_date}:
        raise ValueError(
            "TPEx credit OpenAPI observation date mismatch: "
            f"expected {requested_date}, got {sorted(observed_dates)}"
        )

    availability = {
        "publication_at": None,
        "first_observed_at": fetched_at.isoformat(),
        "available_at": fetched_at.isoformat(),
        "available_date": None,
        "quality": "degraded",
    }
    rows: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for observation in parsed.accepted:
        if observation.symbol in seen_symbols:
            raise ValueError(
                f"TPEx credit OpenAPI duplicate symbol for {requested_date}: "
                f"{observation.symbol}"
            )
        seen_symbols.add(observation.symbol)
        quantities = observation.quantities
        rows.append(
            {
                "stock_code": observation.symbol,
                "decision_date": observation.observation_date,
                "source_version": observation.source_version,
                **availability,
                "margin_purchase": quantities["margin_purchase_shares"],
                "margin_balance": quantities["margin_balance_shares"],
                "short_sale": quantities["short_sale_shares"],
                "short_balance": quantities["short_balance_shares"],
                "financing": None,
                "securities_lending": None,
            }
        )
    return rows

# ==========================================
# 三大法人 (Institutional Flows)
# ==========================================
def fetch_institutional_flows(decision_date: date) -> pd.DataFrame:
    """抓取指定日期的三大法人買賣超 (上市 + 上櫃)"""
    date_ce = decision_date.strftime("%Y%m%d")
    date_roc = to_roc_date(decision_date)

    rows: list[dict[str, Any]] = []
    source_errors: list[str] = []

    # --- TWSE ---
    twse_url = "https://www.twse.com.tw/fund/T86"
    twse_params = {"response": "json", "date": date_ce, "selectType": "ALL"}
    logger.info(f"爬取 TWSE 法人: {twse_url}?date={date_ce}")
    try:
        def _validate_twse_institutional(data: Dict[str, Any]) -> None:
            _validate_response_date(data, date_ce)
            if data.get("stat") != "OK":
                raise OfficialPayloadNotReady(
                    f"TWSE T86 回應狀態非 OK: stat={data.get('stat')!r}"
                )
            if not data.get("data") or not data.get("fields"):
                raise OfficialPayloadNotReady(
                    "TWSE T86 回應缺少有效 data/fields"
                )

        data = _request_ready_json(
            twse_url,
            twse_params,
            source_label="TWSE T86",
            validate=_validate_twse_institutional,
        )
        availability = observed_only_availability_fields()
        fields = data["fields"]
        for row in data["data"]:
            if isinstance(row, list):
                item = dict(zip(fields, row))
                # 證交所欄位名稱可能變動，盡量包容
                fi_buy = safe_int(item.get("外陸資買進股數(不含外資自營商)", 0)) + safe_int(item.get("外資自營商買進股數", 0))
                fi_sell = safe_int(item.get("外陸資賣出股數(不含外資自營商)", 0)) + safe_int(item.get("外資自營商賣出股數", 0))
                fi_net = safe_int(item.get("外陸資買賣超股數(不含外資自營商)", 0)) + safe_int(item.get("外資自營商買賣超股數", 0))

                it_buy = safe_int(item.get("投信買進股數", 0))
                it_sell = safe_int(item.get("投信賣出股數", 0))
                it_net = safe_int(item.get("投信買賣超股數", 0))

                dl_buy = safe_int(item.get("自營商買進股數(自行買賣)", 0)) + safe_int(item.get("自營商買進股數(避險)", 0))
                dl_sell = safe_int(item.get("自營商賣出股數(自行買賣)", 0)) + safe_int(item.get("自營商賣出股數(避險)", 0))
                dl_net = safe_int(item.get("自營商買賣超股數(自行買賣)", 0)) + safe_int(item.get("自營商買賣超股數(避險)", 0))

                stock_code = str(item.get("證券代號") or "").strip()
                if not stock_code:
                    continue
                rows.append({
                    "stock_code": stock_code,
                    "decision_date": decision_date.isoformat(),
                    "source_version": "twse-official-T86",
                    **availability,
                    "foreign_investor_buy": fi_buy,
                    "foreign_investor_sell": fi_sell,
                    "foreign_investor_net": fi_net,
                    "investment_trust_buy": it_buy,
                    "investment_trust_sell": it_sell,
                    "investment_trust_net": it_net,
                    "dealer_buy": dl_buy,
                    "dealer_sell": dl_sell,
                    "dealer_net": dl_net,
                })
    except Exception as e:
        source_errors.append(f"TWSE T86: {type(e).__name__}: {e}")

    time.sleep(3) # 防 Ban

    # --- TPEX ---
    tpex_url = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
    tpex_params = {"l": "zh-tw", "o": "json", "d": date_roc, "se": "AL"}
    logger.info(f"爬取 TPEX 法人: {tpex_url}?d={date_roc}")
    try:
        def _validate_tpex_institutional(data: Dict[str, Any]) -> None:
            _validate_response_date(data, date_ce)
            if str(data.get("stat", "")).lower() != "ok":
                raise OfficialPayloadNotReady(
                    f"TPEX 三大法人回應狀態非 ok: stat={data.get('stat')!r}"
                )
            if not _security_table_rows(data, minimum_columns=17):
                raise OfficialPayloadNotReady(
                    "TPEX 三大法人回應缺少有效明細 table: "
                    f"tables={_table_count(data)}"
                )

        data = _request_ready_json(
            tpex_url,
            tpex_params,
            source_label="TPEX 3insti",
            validate=_validate_tpex_institutional,
        )
        tpex_rows = _security_table_rows(data, minimum_columns=17)
        availability = observed_only_availability_fields()
        for row in tpex_rows:
            if len(row) >= 17:
                try:
                    if len(row) >= 24:
                        # 現行 24 欄：外資小計 8:10、投信 11:13、
                        # 自營商小計 20:22；中間欄位是各子類別。
                        fi_buy = safe_int(row[8])
                        fi_sell = safe_int(row[9])
                        fi_net = safe_int(row[10])
                        it_buy = safe_int(row[11])
                        it_sell = safe_int(row[12])
                        it_net = safe_int(row[13])
                        dl_buy = safe_int(row[20])
                        dl_sell = safe_int(row[21])
                        dl_net = safe_int(row[22])
                    else:
                        # 舊 17 欄：外資與自營商各由兩個子類別相加。
                        fi_buy = safe_int(row[2]) + safe_int(row[5])
                        fi_sell = safe_int(row[3]) + safe_int(row[6])
                        fi_net = safe_int(row[4]) + safe_int(row[7])
                        it_buy = safe_int(row[8])
                        it_sell = safe_int(row[9])
                        it_net = safe_int(row[10])
                        dl_buy = safe_int(row[11]) + safe_int(row[14])
                        dl_sell = safe_int(row[12]) + safe_int(row[15])
                        dl_net = safe_int(row[13]) + safe_int(row[16])

                    stock_code = str(row[0]).strip()
                    if not stock_code:
                        continue
                    rows.append({
                        "stock_code": stock_code,
                        "decision_date": decision_date.isoformat(),
                        "source_version": "tpex-official-3itrade",
                        **availability,
                        "foreign_investor_buy": fi_buy,
                        "foreign_investor_sell": fi_sell,
                        "foreign_investor_net": fi_net,
                        "investment_trust_buy": it_buy,
                        "investment_trust_sell": it_sell,
                        "investment_trust_net": it_net,
                        "dealer_buy": dl_buy,
                        "dealer_sell": dl_sell,
                        "dealer_net": dl_net,
                    })
                except (IndexError, TypeError):
                    continue
    except Exception as e:
        source_errors.append(f"TPEX 3insti: {type(e).__name__}: {e}")

    if source_errors:
        raise RuntimeError("；".join(source_errors))

    return pd.DataFrame(rows)

# ==========================================
# 信用交易 (Credit Transactions)
# ==========================================
def fetch_credit_transactions(decision_date: date) -> pd.DataFrame:
    """抓取指定日期的信用交易/融資券 (上市 + 上櫃)"""
    date_ce = decision_date.strftime("%Y%m%d")
    date_roc = to_roc_date(decision_date)

    rows: list[dict[str, Any]] = []
    source_errors: list[str] = []

    # --- TWSE ---
    twse_url = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
    twse_params = {"response": "json", "date": date_ce, "selectType": "ALL"}
    logger.info(f"爬取 TWSE 融資券: {twse_url}?date={date_ce}")
    try:
        def _validate_twse_credit(data: Dict[str, Any]) -> None:
            _validate_response_date(data, date_ce)
            if data.get("stat") != "OK":
                raise OfficialPayloadNotReady(
                    f"TWSE MI_MARGN 回應狀態非 OK: stat={data.get('stat')!r}"
                )
            if not _security_table_rows(
                data,
                minimum_columns=13,
                strict_rows=True,
            ):
                raise OfficialPayloadNotReady(
                    "TWSE MI_MARGN 回應缺少有效明細 table: "
                    f"tables={_table_count(data)}"
                )

        data = _request_ready_json(
            twse_url,
            twse_params,
            source_label="TWSE MI_MARGN",
            validate=_validate_twse_credit,
        )
        twse_rows = _security_table_rows(
            data,
            minimum_columns=13,
            strict_rows=True,
        )
        parsed_twse_rows = _parse_legacy_credit_rows(
            twse_rows,
            decision_date=decision_date,
            source_version="twse-official-MI_MARGN",
            minimum_columns=13,
            quantity_columns={
                "margin_purchase": 2,
                "margin_balance": 6,
                "short_sale": 9,
                "short_balance": 12,
            },
        )
        rows.extend(parsed_twse_rows)
    except Exception as e:
        source_errors.append(f"TWSE MI_MARGN: {type(e).__name__}: {e}")

    time.sleep(3) # 防 Ban

    # --- TPEX ---
    tpex_url = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"
    tpex_params = {"l": "zh-tw", "o": "json", "d": date_roc}
    logger.info(f"爬取 TPEX 融資券: {tpex_url}?d={date_roc}")
    try:
        def _validate_tpex_credit(data: Dict[str, Any]) -> None:
            _validate_response_date(data, date_ce)
            if str(data.get("stat", "")).lower() != "ok":
                raise OfficialPayloadNotReady(
                    f"TPEX 信用交易回應狀態非 ok: stat={data.get('stat')!r}"
                )
            # 現行明細至少要含至「券餘額」(index 14)，避免誤選摘要表。
            if not _security_table_rows(
                data,
                minimum_columns=15,
                strict_rows=True,
            ):
                raise OfficialPayloadNotReady(
                    "TPEX 信用交易回應缺少有效明細 table: "
                    f"tables={_table_count(data)}"
                )

        data = _request_ready_json(
            tpex_url,
            tpex_params,
            source_label="TPEX margin",
            validate=_validate_tpex_credit,
        )
        tpex_rows = _security_table_rows(
            data,
            minimum_columns=15,
            strict_rows=True,
        )
        parsed_tpex_rows = _parse_legacy_credit_rows(
            tpex_rows,
            decision_date=decision_date,
            source_version="tpex-official-margin_bal",
            minimum_columns=15,
            quantity_columns={
                "margin_purchase": 3,
                "margin_balance": 6,
                "short_sale": 11,
                "short_balance": 14,
            },
        )
        rows.extend(parsed_tpex_rows)
    except Exception as primary_exc:
        try:
            fallback_rows = _fetch_tpex_credit_openapi(decision_date)
            rows.extend(fallback_rows)
            logger.warning(
                "TPEx margin legacy route failed; accepted exact-date registered "
                "OpenAPI fallback (%s rows): %s",
                len(fallback_rows),
                primary_exc,
            )
        except Exception as fallback_exc:
            source_errors.append(
                "TPEX margin legacy: "
                f"{type(primary_exc).__name__}: {primary_exc}; "
                "TPEX margin OpenAPI: "
                f"{type(fallback_exc).__name__}: {fallback_exc}"
            )

    if source_errors:
        raise RuntimeError("；".join(source_errors))

    return pd.DataFrame(rows)

# ==========================================
# TDCC 集保庫存 (Shareholding Tiers)
# ==========================================
def _fetch_tdcc_shareholding(expected_date: Optional[date]) -> pd.DataFrame:
    """讀取 TDCC 單週資料；只接受 canonical parser 驗證過的完整單一期間。"""

    legacy_url = "https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5"
    routes = (
        (
            "TDCC legacy CSV",
            "tdcc-official-od-1-5",
            "tdcc:1-5",
            legacy_url,
            False,
        ),
        (
            "TDCC OpenAPI",
            TDCC_OPENAPI_SOURCE_VERSION,
            "tdcc:openapi:1-5",
            TDCC_OPENAPI_URL,
            True,
        ),
    )
    route_errors: list[str] = []
    for label, source_version, endpoint_id, url, is_bounded in routes:
        logger.info("爬取 %s 集保庫存: %s", label, url)
        try:
            if is_bounded:
                payload, headers, http_status = _safe_request_bounded_payload(
                    url,
                    max_response_bytes=TDCC_OPENAPI_MAX_BYTES,
                )
            else:
                response = safe_request(url)
                payload = _response_payload_bytes(response)
                headers = {
                    str(key): str(value)
                    for key, value in dict(getattr(response, "headers", {}) or {}).items()
                }
                http_status = int(getattr(response, "status_code", 200))

            fetched_at = datetime.now(timezone.utc)
            envelope = RawFetchEnvelope(
                source_id="tdcc_shareholding",
                source_version=source_version,
                endpoint_id=endpoint_id,
                request_parameters={},
                fetched_at=fetched_at,
                http_status=http_status,
                http_headers=headers,
                payload=payload,
            )
            parsed = parse_tdcc_shareholding(envelope)
            _require_complete_parse(parsed, label)
            observation_dates = {row.observation_date for row in parsed.accepted}
            if len(observation_dates) != 1:
                raise ValueError(
                    f"{label} payload must contain one official data date; "
                    f"got {sorted(observation_dates)}"
                )
            data_date_str = next(iter(observation_dates))
            data_date = date.fromisoformat(data_date_str)
            if expected_date is not None and data_date != expected_date:
                raise ValueError(
                    f"{label} latest data date {data_date} does not match exact "
                    f"requested date {expected_date}"
                )

            grouped: dict[str, dict[int, dict[str, int]]] = {}
            seen_tiers: set[tuple[str, int]] = set()
            for observation in parsed.accepted:
                quantities = observation.quantities
                tier = quantities["holder_tier"]
                ratio_bp = quantities["holding_ratio_bp"]
                if not 1 <= tier <= 17:
                    raise ValueError(
                        f"{label} invalid holding tier {tier} for {observation.symbol}"
                    )
                if not 0 <= ratio_bp <= 10_000:
                    raise ValueError(
                        f"{label} invalid holding ratio {ratio_bp} bp for {observation.symbol}"
                    )
                holder_count = quantities["holder_count"]
                shares = quantities["shares"]
                if holder_count < 0 or shares < 0:
                    raise ValueError(
                        f"{label} negative holder count or shares at tier {tier} "
                        f"for {observation.symbol}"
                    )
                natural_key = (observation.symbol, tier)
                if natural_key in seen_tiers:
                    raise ValueError(
                        f"{label} duplicate symbol/tier row: {observation.symbol}/{tier}"
                    )
                seen_tiers.add(natural_key)
                grouped.setdefault(observation.symbol, {})[tier] = {
                    "holder_count": holder_count,
                    "shares": shares,
                    "holding_ratio_bp": ratio_bp,
                }

            rows = []
            expected_tiers = set(range(1, 18))
            for stock_code, tiers in sorted(grouped.items()):
                if set(tiers) != expected_tiers:
                    missing = sorted(expected_tiers - set(tiers))
                    unexpected = sorted(set(tiers) - expected_tiers)
                    raise ValueError(
                        f"{label} incomplete tier set for {stock_code}: "
                        f"missing={missing}, unexpected={unexpected}"
                    )

                # The captured complete official payload is row-conserved by
                # total shares = levels 1..15 minus level 16 and total holders
                # = levels 1..15. Levels 16/17 are integrity controls only;
                # their undocumented semantics are not projected as bands.
                total_shares = tiers[17]["shares"]
                observed_shares = sum(tiers[tier]["shares"] for tier in range(1, 16))
                adjustment_shares = tiers[16]["shares"]
                if total_shares != observed_shares - adjustment_shares:
                    raise ValueError(
                        f"{label} tier-17 share conservation failed for {stock_code}"
                    )
                total_holders = tiers[17]["holder_count"]
                observed_holders = sum(
                    tiers[tier]["holder_count"] for tier in range(1, 16)
                )
                if total_holders != observed_holders:
                    raise ValueError(
                        f"{label} tier-17 holder conservation failed for {stock_code}"
                    )

                large_bp = tiers[15]["holding_ratio_bp"]
                retail_bp = sum(
                    tiers[tier]["holding_ratio_bp"] for tier in range(1, 6)
                )
                rows.append(
                    {
                        "stock_code": stock_code,
                        "decision_date": data_date.isoformat(),
                        "source_version": source_version,
                        "publication_at": None,
                        "first_observed_at": fetched_at.isoformat(),
                        "available_at": fetched_at.isoformat(),
                        "available_date": None,
                        "quality": "degraded",
                        "shareholding_tiers": "weekly_distribution_available",
                        "large_holder_ratio_bp": large_bp,
                        "retail_holder_ratio_bp": retail_bp,
                        "dispersion_index_bp": retail_bp - large_bp,
                    }
                )
            if not rows:
                raise ValueError(f"{label} produced no symbol summaries")
            return pd.DataFrame(rows)
        except Exception as exc:
            route_errors.append(f"{label}: {type(exc).__name__}: {exc}")

    logger.error("TDCC 集保庫存官方來源均未通過：%s", "；".join(route_errors))
    return pd.DataFrame()


def fetch_tdcc_shareholding(decision_date: date) -> pd.DataFrame:
    """相容既有日期式呼叫；資料日不同時維持 fail-closed。"""

    return _fetch_tdcc_shareholding(decision_date)


def fetch_latest_tdcc_shareholding() -> pd.DataFrame:
    """唯讀取得官方最新週 snapshot，資料日一律採 payload 自帶日期。"""

    return _fetch_tdcc_shareholding(None)
