"""沿既有DailySourceUseAcceptance保存精確TPEx診斷用途；不接受P0整個來源桶。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, TypedDict, cast

from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _canonical_path, _decode_object, _file_signature, _read_exact_file,
)
from data_module.daily_source_snapshot import (
    DailySourceUseAcceptance, DailySourceUseScope, _to_taipei,
)
from data_module.tpex_institutional_openapi import (
    TPEX_OPENAPI_ENDPOINT, TPEX_OPENAPI_URL, TPEX_OPENAPI_VERSION,
)

_SCHEMA = "institutional-source-use.v1"
_POLICY = "tpex-institutional-daily-diagnostics.v1"
_ACTOR = "machine:official_document_scope_policy"
_MAX_ARTIFACT = 64 * 1024
# 最後必要metadata原件的真HTTP收據終態；用途接受不得早於已保存文件證據。
_NOT_BEFORE = datetime.fromisoformat("2026-10-15T23:06:40.284879+00:00")
class _DocumentPolicy(TypedDict):
    role: str
    url: str
    bytes: int
    sha256: str


_DOCUMENT_POLICY: tuple[_DocumentPolicy, ...] = (
    {"role": "license", "url": "https://data.gov.tw/license", "bytes": 484470,
     "sha256": "f36301ecb6ba3ac2cac5b820276e3fd2d4c7d12755afa1f49bf5379d6b3ce3f2"},
    {"role": "metadata", "url": "https://data.gov.tw/api/v2/rest/dataset/11856", "bytes": 4205,
     "sha256": "b807cf7f19d04f19ff6e445463ac86e9380d85d0fadc880e482563dfd518fe5f"},
    {"role": "dataset", "url": "https://data.gov.tw/dataset/11856", "bytes": 526503,
     "sha256": "4bb3a58a6dd708cf7d49a2cb3943feb85896184ca3a3748702db559ffef771c5"},
    {"role": "swagger", "url": "https://www.tpex.org.tw/openapi/swagger.json", "bytes": 476923,
     "sha256": "05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e"},
)
TPEX_INSTITUTIONAL_USE_SCOPE = DailySourceUseScope(
    dataset_id="data.gov.tw:11856", source_id=TPEX_OPENAPI_ENDPOINT, market="TPEx",
    parser_version=TPEX_OPENAPI_VERSION,
    source_schema_version="sha256:efda72f09eeea74a135dd63afd9c8fbc926d3464e9ba658144c7ab7d58f4e3cc",
    unit="shares", intended_use="diagnostics",
)
_BINDING = {
    "p0_source_id": "institutional_flows", "p0_family_accepted": False,
    "endpoint_id": TPEX_OPENAPI_ENDPOINT, "endpoint_url": TPEX_OPENAPI_URL,
    "acquisition_route_id": "tpex.tpex_3insti_daily_trading", "source_version": TPEX_OPENAPI_VERSION,
    "official_schema_sha256": TPEX_INSTITUTIONAL_USE_SCOPE.source_schema_version,
}
_ATTRIBUTION = (
    "資料提供：財團法人中華民國證券櫃檯買賣中心，2026，"
    "上櫃股票三大法人買賣明細資訊（tpex-openapi-3insti-daily.v1）。"
    "依政府資料開放授權條款第1版：https://data.gov.tw/license"
)


class InstitutionalSourceUseError(ValueError):
    """來源用途、文件版本或不可變原件不合；不沿用未驗資格。"""


def _sha(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InstitutionalSourceUseError("來源用途須提供外部小寫SHA256")
    return value


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _document_descriptors() -> list[dict[str, Any]]:
    return [{**item, "path": str(item["role"]) + ".raw"} for item in _DOCUMENT_POLICY]


def _evidence_identity() -> str:
    return sha256(_canonical({"policy": _POLICY, "binding": _BINDING,
                              "scope": TPEX_INSTITUTIONAL_USE_SCOPE.to_dict(),
                              "documents": _document_descriptors()})).hexdigest()


def _validate_acceptance(acceptance: DailySourceUseAcceptance) -> None:
    evidence = _evidence_identity()
    if (type(acceptance) is not DailySourceUseAcceptance or acceptance.scope != TPEX_INSTITUTIONAL_USE_SCOPE
            or acceptance.official_source_endpoint != TPEX_OPENAPI_URL
            or acceptance.document_chain != tuple(str(item["url"]) for item in _DOCUMENT_POLICY)
            or acceptance.authorization_scope != "diagnostics"
            or acceptance.acceptance_evidence_ref != "sha256:" + evidence
            or acceptance.acceptance_id != "machine:tpex-institutional:" + evidence):
        raise InstitutionalSourceUseError("用途接受未綁精確TPEx端點／schema／單位與diagnostics，不接受泛用決議")
    if acceptance.accepted_at < _NOT_BEFORE:
        raise InstitutionalSourceUseError("用途接受早於必要官方文件原件保存，不得回填接受時間")


@dataclass(frozen=True, slots=True)
class InstitutionalSourceUsePin:
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        _sha(self.sha256)
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise InstitutionalSourceUseError("請明選來源用途接受檔絕對路徑")


@dataclass(frozen=True, slots=True)
class InstitutionalSourceUseRead:
    pin: InstitutionalSourceUsePin
    acceptance: DailySourceUseAcceptance
    attribution: str

    def __post_init__(self) -> None:
        if type(self.pin) is not InstitutionalSourceUsePin or self.attribution != _ATTRIBUTION:
            raise InstitutionalSourceUseError("來源用途識別或顯名聲明不符")
        _validate_acceptance(self.acceptance)


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise InstitutionalSourceUseError("來源用途讀取／保存已取消")


def _read(path: Path, maximum: int, expected: str, pins: list[tuple[Path, tuple[int, ...], str]]) -> bytes:
    path = _canonical_path(path, "institutional_use_source", allow_missing=False)
    raw, signature = _read_exact_file(path, maximum=maximum)
    if sha256(raw).hexdigest() != _sha(expected):
        raise InstitutionalSourceUseError("來源用途文件SHA不符：" + path.name)
    pins.append((path, signature, expected))
    return raw


def _finish(pins: list[tuple[Path, tuple[int, ...], str]], callback: Callable[[], bool] | None) -> None:
    for path, signature, digest in pins:
        _cancel(callback)
        try:
            _canonical_path(path, "institutional_use_source", allow_missing=False)
            raw, current = _read_exact_file(path, maximum=max(signature[3], 1))
        except (OSError, ValueError) as exc:
            raise InstitutionalSourceUseError("來源用途文件在讀取期間改變") from exc
        if current != signature or sha256(raw).hexdigest() != digest or _file_signature(path) != signature:
            raise InstitutionalSourceUseError("來源用途文件在讀取期間改變")


def _barrier(directory: Path) -> None:
    if any(os.path.lexists(directory / name) for name in (".pending.json", "failure.json")):
        raise InstitutionalSourceUseError("來源用途接受仍pending或已失敗")


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _payload(acceptance: DailySourceUseAcceptance) -> dict[str, Any]:
    return {"schema_version": _SCHEMA, "policy_version": _POLICY, "decision_actor": _ACTOR,
            "acceptance": acceptance.to_dict(), "source_binding": dict(_BINDING),
            "documents": _document_descriptors(), "attribution": _ATTRIBUTION,
            "candidate_only": True, "historical_pit_eligible": False,
            "formal_oos_allowed": False, "production_scheduler_allowed": False,
            "legal_acceptance_inferred": False}


def read_tpex_institutional_source_use(
    pin: InstitutionalSourceUsePin, *, decision_cutoff: datetime,
    check_cancel: Callable[[], bool] | None = None,
) -> InstitutionalSourceUseRead:
    """同一來源用途可供多日批次重用；每天的原件品質與可得小時另驗。"""
    if type(pin) is not InstitutionalSourceUsePin:
        raise InstitutionalSourceUseError("來源用途須為具名pin，不接受generic P0決議")
    cutoff = _to_taipei(decision_cutoff, "decision_cutoff")
    _cancel(check_cancel)
    path = _canonical_path(pin.path, "institutional_use_artifact", allow_missing=False)
    _barrier(path.parent)
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    raw = _read(path, _MAX_ARTIFACT, pin.sha256, pins)
    try:
        payload = cast(dict[str, Any], _decode_object(raw, label="institutional_use", maximum=_MAX_ARTIFACT))
        acceptance = DailySourceUseAcceptance.from_dict(payload.get("acceptance"))
    except (TypeError, ValueError) as exc:
        raise InstitutionalSourceUseError("用途接受未綁有效來源契約：" + str(exc)) from exc
    _validate_acceptance(acceptance)
    if payload != _payload(acceptance) or _canonical(payload) != raw:
        raise InstitutionalSourceUseError("來源用途artifact欄位／版本／scope或canonical內容不符")
    if acceptance.accepted_at > cutoff:
        raise InstitutionalSourceUseError("決策時間早於此來源用途接受，不得回填歷史資格")
    for item in _DOCUMENT_POLICY:
        _cancel(check_cancel)
        document = path.parent / (str(item["role"]) + ".raw")
        body = _read(document, int(item["bytes"]), str(item["sha256"]), pins)
        if len(body) != item["bytes"]:
            raise InstitutionalSourceUseError("來源用途文件版本大小不符")
    _finish(pins, check_cancel)
    _barrier(path.parent)
    _cancel(check_cancel)
    return InstitutionalSourceUseRead(pin, acceptance, _ATTRIBUTION)


def write_tpex_institutional_source_use(
    *, evidence_files: Mapping[str, Path], output_directory: Path,
    clock: Callable[[], datetime] | None = None, check_cancel: Callable[[], bool] | None = None,
) -> InstitutionalSourceUsePin:
    """只接受Root已核的四文件版本；另存不可變契約，不寫正式P0或daily批次。"""
    started_at = datetime.now().astimezone()
    if not isinstance(evidence_files, Mapping) or set(evidence_files) != {item["role"] for item in _DOCUMENT_POLICY}:
        raise InstitutionalSourceUseError("須明選license／metadata／dataset／swagger四份原件")
    target = _canonical_path(output_directory, "institutional_use_output", allow_missing=True)
    for text in (os.getenv("DATA_ROOT", "F:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"),
                 os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if text and target.is_relative_to(Path(text).absolute()):
            raise InstitutionalSourceUseError("不可在正式／私人資料根寫來源用途接受")
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    bodies: list[tuple[str, bytes]] = []
    for item in _DOCUMENT_POLICY:
        _cancel(check_cancel)
        role = str(item["role"])
        raw = _read(evidence_files[role], int(item["bytes"]), str(item["sha256"]), pins)
        if len(raw) != item["bytes"]:
            raise InstitutionalSourceUseError("來源用途文件版本大小不符")
        bodies.append((role, raw))
    _finish(pins, check_cancel)
    target.mkdir(exist_ok=False)
    _canonical_path(target, "institutional_use_output", allow_missing=False)
    try:
        _write(target / ".pending.json", _canonical({"policy_version": _POLICY}))
        for role, raw in bodies:
            _cancel(check_cancel)
            _write(target / (role + ".raw"), raw)
        _finish(pins, check_cancel)
        accepted_at = _to_taipei((clock or (lambda: datetime.now().astimezone()))(), "accepted_at")
        evidence = _evidence_identity()
        acceptance = DailySourceUseAcceptance(
            scope=TPEX_INSTITUTIONAL_USE_SCOPE, acceptance_id="machine:tpex-institutional:" + evidence,
            accepted_at=accepted_at, official_source_endpoint=TPEX_OPENAPI_URL,
            document_chain=tuple(str(item["url"]) for item in _DOCUMENT_POLICY),
            acceptance_evidence_ref="sha256:" + evidence, authorization_scope="diagnostics",
        )
        raw = _canonical(_payload(acceptance))
        if len(raw) > _MAX_ARTIFACT:
            raise InstitutionalSourceUseError("來源用途artifact超過上限")
        path = target / "source_use.json"
        _write(path, raw)
        pin = InstitutionalSourceUsePin(path, sha256(raw).hexdigest())
        _validate_acceptance(acceptance)
        if acceptance.accepted_at < started_at:
            raise InstitutionalSourceUseError("不得回填早於本次真實保存開始的來源用途接受時間")
        _finish(pins, check_cancel)
        copied: list[tuple[Path, tuple[int, ...], str]] = []
        _read(path, _MAX_ARTIFACT, pin.sha256, copied)
        for item in _DOCUMENT_POLICY:
            _read(target / (str(item["role"]) + ".raw"), int(item["bytes"]), str(item["sha256"]), copied)
        _finish(copied, check_cancel)
        _cancel(check_cancel)
        (target / ".pending.json").unlink()
        read_tpex_institutional_source_use(pin, decision_cutoff=accepted_at, check_cancel=check_cancel)
        return pin
    except Exception as exc:
        try:
            _write(target / "failure.json", _canonical({"reason": str(exc)[:1024], "success": False}))
        except Exception as preservation_error:
            exc.add_note("來源用途失敗封存另有錯誤：" + str(preservation_error))
        raise
