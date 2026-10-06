"""UX20：固定 MA 研究母體的完整對照 capture；不授自然／PIT／入選資格。"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from itertools import islice
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
from typing import Any, Protocol

from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA, DailyMarketSnapshotRepository,
    VerifiedDailyMarketSnapshot,
)
from app_module.daily_market_feature_snapshot import feature_contract_for_version
from app_module.multi_method_research_consensus import (
    adapt_daily_market_snapshot, build_multi_method_consensus,
)

CAPTURE_SCHEMA = "rule-research-sample-capture.v1"
RECEIPT_SCHEMA = "rule-research-sample-receipt.v1"
MAX_CAPTURE_BYTES = 256 * 1024
MAX_RETAINED_BYTES = 8 * 1024 * 1024
MAX_CAPTURES = 128
SAFETY_RESERVE_BYTES = 200 * 1024 ** 3
_SHA = re.compile(r"[0-9a-f]{64}")
_POLICY = {"research_only": True, "historical_pit_eligible": False,
           "natural_authority": False, "formal_eligible": False,
           "training_eligible": False, "selection_predicate": None,
           "selection_status": "unknown", "selected_count": 0,
           "availability_policy": "source_unknown_preserved_no_backfill"}


class RuleSampleCaptureError(ValueError):
    """可由整合端明示的穩定拒絕理由。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class VerifiedResearchCapture(Protocol):
    """共用有界原子保存封裝；各 capture schema 自行驗語意。"""
    @property
    def body_json(self) -> str: ...
    @property
    def identity_sha256(self) -> str: ...
    def to_dict(self) -> dict[str, Any]: ...


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise RuleSampleCaptureError(code)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _clock(value: datetime) -> str:
    _require(isinstance(value, datetime) and value.tzinfo is not None
             and value.utcoffset() is not None, "clock_timezone_missing")
    return value.astimezone(timezone.utc).isoformat()


def _identity(body: dict[str, Any]) -> str:
    # 重跑只變觀測時鐘時沿用首次證據；來源修訂／as-of 改變則是新身份。
    return _digest(_json({k: v for k, v in body.items()
                          if k not in {"capture_identity_sha256", "observed_at"}}).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class RuleResearchCapture:
    """以 canonical JSON 隔離可變 verified DTO；不持有 raw／DB。"""

    body_json: str

    def to_dict(self) -> dict[str, Any]:
        _require(isinstance(self.body_json, str)
                 and len(self.body_json.encode("utf-8")) <= MAX_CAPTURE_BYTES, "capture_byte_limit")
        body = json.loads(self.body_json)
        _require(isinstance(body, dict) and _json(body) == self.body_json,
                 "capture_noncanonical")
        _require(len(self.body_json.encode("utf-8")) <= MAX_CAPTURE_BYTES, "capture_byte_limit")
        _require(body.get("schema_version") == CAPTURE_SCHEMA, "capture_version_mismatch")
        _require(body.get("policy") == _POLICY, "capture_policy_mismatch")
        _require(body.get("capture_identity_sha256") == _identity(body), "capture_identity_mismatch")
        try:
            contract = feature_contract_for_version(str(body.get("feature_contract_version") or ""))
        except ValueError as exc:
            raise RuleSampleCaptureError("feature_version_mismatch") from exc
        _require(body.get("method_contracts") == contract.method_contracts
                 and body.get("method_contracts_sha256") == contract.method_contracts_sha256,
                 "capture_method_version_mismatch")
        _require(body.get("source_observed_at") is None and body.get("source_available_at") is None,
                 "source_clock_backfill_rejected")
        _require(body.get("source_sha256") == _digest(_json({"source_ref": body.get("source_ref"),
                 "source_refs": body.get("source_refs")}).encode("utf-8")), "capture_source_hash_mismatch")
        rows = body.get("rows")
        _require(isinstance(rows, list) and len(contract.condition_keys) <= len(rows)
                 <= 32 * len(contract.condition_keys), "capture_row_bound")
        seen: set[tuple[str, str]] = set()
        for row in rows:
            _require(isinstance(row, dict) and row.get("state") in
                     {"matched", "notmatched", "unknown", "excluded"}
                     and row.get("selected") is False
                     and row.get("source_observed_at") is None
                     and row.get("source_available_at") is None, "capture_row_invalid")
            pair = (row["method_id"], row["stock_code"])
            _require(pair not in seen, "capture_duplicate_row")
            seen.add(pair)
        _require(type(body.get("included_denominator")) is int
                 and 1 <= body["included_denominator"] <= 16
                 and type(body.get("represented_denominator")) is int
                 and body["included_denominator"] <= body["represented_denominator"] <= 32,
                 "capture_denominator_invalid")
        counts = body.get("method_counts")
        expected_ids = {m["method_id"] for m in contract.method_contracts.values()}
        _require(isinstance(counts, list) and len(counts) == len(expected_ids)
                 and {c["method_id"] for c in counts} == expected_ids
                 and {r["method_id"] for r in rows} == expected_ids,
                 "capture_methods_missing")
        scopes = []
        for count in counts:
            members = [r for r in rows if r["method_id"] == count["method_id"]]
            scopes.append({r["stock_code"] for r in members})
            tally = Counter(r["state"] for r in members)
            _require(count == {"method_id": count["method_id"],
                "included_denominator": body["included_denominator"],
                "represented_denominator": body["represented_denominator"],
                **{s: tally[s] for s in ("matched", "notmatched", "unknown", "excluded")}}
                and len(members) == body["represented_denominator"]
                and len(members) - tally["excluded"] == body["included_denominator"],
                "capture_counts_mismatch")
        _require(all(scope == scopes[0] for scope in scopes), "capture_method_scope_mismatch")
        _validate_saved_semantics(body)
        return body

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["capture_identity_sha256"])


def _validate_saved_semantics(body: dict[str, Any]) -> None:
    """讀回也驗母體／版本／時鐘；重算 bytes hash 不能替代語意契約。"""
    try:
        clocks = [datetime.fromisoformat(body[k]) for k in
                  ("decision_cutoff", "artifact_published_at", "as_of", "observed_at")]
        for clock in clocks:
            _clock(clock)
        _require(clocks == sorted(clocks), "capture_clock_order_invalid")
        _require(clocks[0].date().isoformat() == body["decision_date"], "capture_date_mismatch")
    except (TypeError, KeyError, ValueError) as exc:
        if isinstance(exc, RuleSampleCaptureError):
            raise
        raise RuleSampleCaptureError("capture_clock_invalid") from exc
    universe = body.get("universe")
    _require(isinstance(universe, dict)
             and body.get("universe_sha256") == _digest(_json(universe).encode("utf-8")),
             "capture_universe_hash_mismatch")
    assert isinstance(universe, dict)
    legacy = universe.get("scope") == "legacy_declared_research_only"
    included = universe.get("declared_stock_codes" if legacy else "included_stock_codes")
    excluded = [] if legacy else universe.get("excluded_stock_codes")
    _require(isinstance(included, list) and 1 <= len(included) <= 16
             and all(isinstance(c, str) and c.strip() == c and c for c in included)
             and len(set(included)) == len(included), "capture_universe_members_invalid")
    _require(isinstance(excluded, list) and len(excluded) <= 16
             and all(isinstance(e, dict) and isinstance(e.get("stock_code"), str)
                     and isinstance(e.get("reason"), str) and e["reason"] for e in excluded),
             "capture_exclusions_invalid")
    assert isinstance(included, list) and isinstance(excluded, list)
    excluded_by_code = {e["stock_code"]: e["reason"] for e in excluded}
    _require(len(excluded_by_code) == len(excluded) and not set(included).intersection(excluded_by_code),
             "capture_exclusions_invalid")
    represented = set(included) | set(excluded_by_code)
    _require(body["included_denominator"] == len(included)
             and body["represented_denominator"] == len(represented), "capture_universe_denominator_mismatch")
    if legacy:
        _require(universe == {"scope": "legacy_declared_research_only", "cohort_identity": body["cohort_sha256"],
                 "declared_stock_codes": included} and body.get("population_count") is None
                 and body.get("population_status") == "unknown_full_market_population",
                 "capture_population_mismatch")
    else:
        _require(universe.get("scope") == "bounded_research_cohort"
                 and universe.get("universe_id") == body["cohort_id"]
                 and universe.get("as_of_date") == body["decision_date"]
                 and universe.get("research_only") is True
                 and universe.get("complete_fixed_cohort") is True
                 and type(body.get("population_count")) is int
                 and universe.get("population_count") == body["population_count"] == len(represented)
                 and body.get("population_status") == "declared_fixed_cohort", "capture_population_mismatch")
    descriptor = feature_contract_for_version(str(body.get("feature_contract_version") or ""))
    contracts = {c["method_id"]: c for c in descriptor.method_contracts.values()}
    for method_id, contract in contracts.items():
        rows = [r for r in body["rows"] if r["method_id"] == method_id]
        _require({r["stock_code"] for r in rows} == represented, "capture_control_members_mismatch")
        for row in rows:
            _require(row.get("method_version") == contract["version"], "capture_row_version_mismatch")
            _require(isinstance(row.get("reason"), str) and bool(row["reason"]), "capture_row_reason_missing")
            excluded_reason = excluded_by_code.get(row["stock_code"])
            _require((row["state"] == "excluded") == (excluded_reason is not None)
                     and (excluded_reason is None or row["reason"] == excluded_reason), "capture_exclusion_mismatch")
            if body.get("completeness") == "partial_research" and excluded_reason is None:
                _require(row["state"] == "unknown", "capture_partial_control_mismatch")
    _require(body.get("completeness") in {"complete_declared_cohort", "partial_research"}, "capture_completeness_invalid")


def build_rule_research_capture(snapshot: VerifiedDailyMarketSnapshot, *,
        as_of: datetime, observed_at: datetime) -> RuleResearchCapture:
    """純投影：只用已捕獲值；未知來源時鐘不從結果／發布時鐘補入。"""
    as_of_text, observed_text = _clock(as_of), _clock(observed_at)
    _require(observed_at >= as_of, "observation_before_as_of")
    _require(isinstance(snapshot, VerifiedDailyMarketSnapshot), "snapshot_type_invalid")
    manifest = deepcopy(dict(snapshot.manifest))
    _require(manifest.get("schema_version") == DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
             "snapshot_version_mismatch")
    try:
        feature_contract_for_version(str(manifest.get("feature_contract_version") or ""))
    except ValueError as exc:
        raise RuleSampleCaptureError("feature_version_mismatch") from exc
    _require(manifest.get("policy") == {"research_only": True, "historical_pit_eligible": False},
             "snapshot_policy_mismatch")
    _require(manifest.get("counts") == {"declared": len(manifest["declared_stock_codes"]),
              "published": len(manifest["stocks"]), "missing": len(manifest["missing_stocks"])},
             "snapshot_counts_mismatch")
    # 純的既有逐股 validator 不執行 IO；避免偽造 wrapper／重算 hash 就通過。
    validator = DailyMarketSnapshotRepository(Path("."))
    for record in manifest["stocks"]:
        payload = deepcopy(snapshot.stock_snapshots.get(record["stock_code"]))
        _require(isinstance(payload, dict), "stock_payload_missing")
        assert isinstance(payload, dict)
        validator._validate_snapshot_payload(payload, record=record,
            stock_code=record["stock_code"], decision_date=snapshot.decision_date,
            manifest=manifest)
    model = build_multi_method_consensus(adapt_daily_market_snapshot(snapshot, as_of=as_of))
    first = model.sources[0]
    rows: list[dict[str, Any]] = []
    counts: list[dict[str, Any]] = []
    state_names = {"selected": "matched", "not_selected": "notmatched", "unknown": "unknown"}
    refs = {item["stock_code"]: item["source_refs"] for item in json.loads(first.source_refs_json)}
    for source in model.sources:
        method_rows: list[dict[str, Any]] = []
        for row in model.rows:
            obs = dict(row.methods)[source.method_id]
            method_rows.append({"stock_code": row.stock_code,
                "method_id": source.method_id, "method_version": source.version,
                "state": state_names[obs.state], "reason": obs.reason,
                "unknown_reason": obs.unknown_reason, "relation": obs.relation,
                "data_as_of": obs.data_date, "artifact_sha256": obs.artifact_sha256,
                "stock_snapshot_sha256": obs.stock_snapshot_sha256,
                "input_sha256": obs.input_sha256, "source_refs": refs.get(row.stock_code),
                "source_observed_at": None, "source_available_at": None,
                "selected": False})
        for code, reason in model.excluded_stock_codes:
            method_rows.append({"stock_code": code, "method_id": source.method_id,
                "method_version": source.version, "state": "excluded", "reason": reason,
                "unknown_reason": "", "relation": "unknown", "data_as_of": None,
                "artifact_sha256": None, "stock_snapshot_sha256": None,
                "input_sha256": None, "source_refs": None,
                "source_observed_at": None, "source_available_at": None, "selected": False})
        tally = Counter(row["state"] for row in method_rows)
        counts.append({"method_id": source.method_id, "included_denominator": model.denominator,
            "represented_denominator": len(method_rows),
            **{state: tally[state] for state in ("matched", "notmatched", "unknown", "excluded")}})
        rows.extend(method_rows)
    body: dict[str, Any] = {"schema_version": CAPTURE_SCHEMA, "as_of": as_of_text,
        "observed_at": observed_text, "decision_date": first.decision_date,
        "decision_cutoff": first.decision_cutoff, "artifact_published_at": first.published_at,
        "source_observed_at": None, "source_available_at": None,
        "snapshot_id": first.snapshot_id, "snapshot_sha256": first.snapshot_sha256,
        "snapshot_schema": manifest["schema_version"],
        "feature_contract_version": manifest["feature_contract_version"],
        "cohort_id": first.cohort_id, "cohort_sha256": first.cohort_sha256,
        "universe": json.loads(first.universe_json), "universe_sha256": first.universe_sha256,
        "method_contracts": manifest["method_contracts"],
        "method_contracts_sha256": first.contracts_sha256,
        "source_ref": manifest.get("source_ref"), "source_refs": json.loads(first.source_refs_json),
        "source_sha256": _digest(_json({"source_ref": manifest.get("source_ref"),
                             "source_refs": json.loads(first.source_refs_json)}).encode("utf-8")),
        "completeness": first.completeness, "included_denominator": model.denominator,
        "represented_denominator": model.denominator + len(model.excluded_stock_codes),
        "population_count": model.population_count,
        "population_status": "declared_fixed_cohort" if json.loads(first.universe_json).get("complete_fixed_cohort")
                             else "unknown_full_market_population",
        "published_count": manifest["counts"]["published"],
        "missing_count": manifest["counts"]["missing"], "missing_stocks": manifest["missing_stocks"],
        "method_counts": counts, "rows": rows, "policy": deepcopy(_POLICY)}
    body["capture_identity_sha256"] = _identity(body)
    result = RuleResearchCapture(_json(body))
    result.to_dict()
    return result


def read_rule_research_capture(repository: DailyMarketSnapshotRepository, *,
        manifest_sha256: str, cohort_id: str, decision_date: date,
        as_of: datetime, observed_at: datetime) -> RuleResearchCapture:
    """釘選唯讀 adapter；不碰 latest／live／排名／producer／個人資料。"""
    snapshot = repository.load_manifest(manifest_sha256, cohort_id, decision_date)
    return build_rule_research_capture(snapshot, as_of=as_of, observed_at=observed_at)


def _safe_path(path: Path) -> None:
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            _require(not stat.S_ISLNK(info.st_mode)
                     and not getattr(info, "st_file_attributes", 0) & 0x400,
                     "path_link_rejected")
            if stat.S_ISREG(info.st_mode):
                _require(info.st_nlink == 1, "path_hardlink_rejected")


def _read_file(path: Path, limit: int) -> bytes:
    _safe_path(path)
    before = path.stat()
    _require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "store_file_bound")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    _safe_path(path)
    current = path.stat()
    _require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
             == (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
             and len(raw) <= limit, "store_changed_during_read")
    return raw


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


class BoundedRuleResearchCaptureWriter:
    """小型隔離目錄 writer；同目錄 rename 一次提交 capture＋receipt。"""

    def __init__(self, output_root: str | Path) -> None:
        raw = Path(output_root).absolute()
        _safe_path(raw)
        root = raw.resolve()
        allowed = (Path(__file__).resolve().parents[1] / "output" / "qa",
                   Path(tempfile.gettempdir()).resolve())
        _require(any(root.is_relative_to(parent) and root != parent for parent in allowed),
                 "isolated_output_required")
        self.output_root = root

    def _free_bytes(self) -> int:
        return shutil.disk_usage(self.output_root).free

    def _inventory(self) -> tuple[int, int]:
        total = count = 0
        entries = list(islice(self.output_root.iterdir(), MAX_CAPTURES + 2))
        _require(len(entries) <= MAX_CAPTURES + 1, "retention_entry_limit")
        for entry in entries:
            if entry.name == ".writer.lock":
                continue
            _require(count < MAX_CAPTURES and _SHA.fullmatch(entry.name) is not None,
                     "store_unknown_or_partial_entry")
            _safe_path(entry)
            _require(entry.is_dir(), "store_entry_invalid")
            files = list(islice(entry.iterdir(), 3))
            _require(len(files) == 2 and {p.name for p in files} == {"capture.json", "receipt.json"},
                     "store_partial_entry")
            self._read_completed(entry)
            total += sum(p.stat().st_size for p in files)
            count += 1
            _require(total <= MAX_RETAINED_BYTES, "retention_byte_limit")
        return count, total

    def _read_completed(self, directory: Path) -> dict[str, Any]:
        _safe_path(directory)
        _require(directory.is_dir(), "store_entry_invalid")
        files = list(islice(directory.iterdir(), 3))
        _require(len(files) == 2 and {p.name for p in files} == {"capture.json", "receipt.json"},
                 "store_partial_entry")
        capture_raw = _read_file(directory / "capture.json", MAX_CAPTURE_BYTES)
        capture = self._decode_capture(capture_raw)
        receipt_raw = _read_file(directory / "receipt.json", 4096)
        receipt = json.loads(receipt_raw)
        expected = self._make_receipt(capture, capture_raw)
        _require(receipt == expected and _json(receipt).encode("utf-8") == receipt_raw
                 and directory.name == capture["capture_identity_sha256"], "receipt_binding_mismatch")
        return receipt

    def _decode_capture(self, raw: bytes) -> dict[str, Any]:
        return RuleResearchCapture(raw.decode("utf-8")).to_dict()

    def _make_receipt(self, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
        return {"schema_version": RECEIPT_SCHEMA, "status": "complete",
                "capture_identity_sha256": body["capture_identity_sha256"],
                "capture_sha256": _digest(raw), "rows_count": len(body["rows"]),
                "observed_at": body["observed_at"], "research_only": True}

    def read(self, identity_sha256: str) -> dict[str, Any]:
        """單一 immutable capture 有界讀回，不建立目錄／鎖或讀 latest。"""
        _require(isinstance(identity_sha256, str) and _SHA.fullmatch(identity_sha256) is not None,
                 "capture_pin_invalid")
        directory = self.output_root / identity_sha256
        receipt = self._read_completed(directory)
        body = self._decode_capture(_read_file(directory / "capture.json", MAX_CAPTURE_BYTES))
        _require(_digest(_json(body).encode("utf-8")) == receipt["capture_sha256"],
                 "readback_changed")
        return {"capture": body, "receipt": receipt}

    def write(self, capture: VerifiedResearchCapture, *,
              revalidate: Callable[[], VerifiedResearchCapture]) -> dict[str, Any]:
        """重讀來源前後一致才發布；中斷殘件保留且下次 fail closed。"""
        body = capture.to_dict()
        identity = capture.identity_sha256
        _require(self._decode_capture(capture.body_json.encode("utf-8")) == body
                 and body.get("capture_identity_sha256") == identity, "capture_envelope_mismatch")
        _safe_path(self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        _safe_path(self.output_root)
        lock = self.output_root / ".writer.lock"
        try:
            lock_handle = lock.open("xb")
        except FileExistsError as exc:
            raise RuleSampleCaptureError("writer_busy") from exc
        try:
            with lock_handle:
                lock_handle.write(identity.encode("ascii"))
                lock_handle.flush()
                os.fsync(lock_handle.fileno())
                count, retained = self._inventory()
                _require(revalidate().identity_sha256 == identity, "source_revision_during_capture")
                destination = self.output_root / identity
                if destination.exists():
                    receipt = self._read_completed(destination)
                    return {"status": "duplicate", "receipt": receipt,
                            "directory": str(destination)}
                raw = capture.body_json.encode("utf-8")
                receipt = self._make_receipt(body, raw)
                receipt_raw = _json(receipt).encode("utf-8")
                new_bytes = len(raw) + len(receipt_raw)
                _require(count < MAX_CAPTURES, "retention_entry_limit")
                _require(retained + new_bytes <= MAX_RETAINED_BYTES, "retention_byte_limit")
                _require(self._free_bytes() >= SAFETY_RESERVE_BYTES + 2 * new_bytes, "capacity_reserve")
                staging = self.output_root / (".partial-" + uuid.uuid4().hex)
                staging.mkdir()
                _write_file(staging / "capture.json", raw)
                _write_file(staging / "receipt.json", receipt_raw)
                _require(_read_file(staging / "capture.json", MAX_CAPTURE_BYTES) == raw
                         and _read_file(staging / "receipt.json", 4096) == receipt_raw,
                         "staged_readback_mismatch")
                _require(revalidate().identity_sha256 == identity, "source_revision_during_capture")
                _require(self._free_bytes() >= SAFETY_RESERVE_BYTES + new_bytes, "capacity_reserve")
                _safe_path(self.output_root)
                staging.rename(destination)
                saved = self._read_completed(destination)
                return {"status": "published", "receipt": saved, "directory": str(destination)}
        finally:
            # 僅移除本次持有的臨時 lock；partial 與已發布證據均保留。
            lock.unlink()

    def capture_pinned(self, repository: DailyMarketSnapshotRepository, *,
            manifest_sha256: str, cohort_id: str, decision_date: date,
            as_of: datetime) -> dict[str, Any]:
        """以實際 UTC 觀測時鐘保存；仍不授自然排程／當時可得權限。"""
        source_root = repository.output_root.absolute().resolve()
        _require(not self.output_root.is_relative_to(source_root)
                 and not source_root.is_relative_to(self.output_root), "source_output_overlap")
        observed = datetime.now(timezone.utc)
        def read() -> RuleResearchCapture:
            return read_rule_research_capture(repository, manifest_sha256=manifest_sha256,
                cohort_id=cohort_id, decision_date=decision_date, as_of=as_of,
                observed_at=observed)
        capture = read()
        return self.write(capture, revalidate=read)
