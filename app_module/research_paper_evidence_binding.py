"""供 V2 研究 Paper producer 使用的固定雜湊來源證據 reader。

外部 binding 表示明確選定來源及用途，不代表來源資格聲明。數值一律來自
個別驗證雜湊的來源原件；binding 只識別原件及逐項接受的用途。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext, Context
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.paper_portfolio_snapshot_repository import (
    PAPER_ACCOUNT_CASH_SEED_RECEIPT_SCHEMA_VERSION,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotReceipt,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_trade_ledger import (
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeLedgerRowsetSnapshot,
    PaperTradeTransition,
)
from app_module.personal_data_paths import PersonalDataPaths, to_internal_io_path
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.research_paper_producer import (
    CASH_USE_ID,
    MARK_USE_ID,
    PaperCashEvidence,
    PaperMarketEvidence,
    VerifiedPaperContext,
    VerifiedResearchCandidate,
    research_candidate_identity_sha256,
)
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
    file_sha256,
)


TAIPEI = ZoneInfo("Asia/Taipei")
EVIDENCE_BINDING_SCHEMA = "research-paper-evidence-binding.v1"
EVIDENCE_SOURCE_SCHEMA = "research-paper-source-records.v1"
USE_ACCEPTANCE_SCHEMA = "research-paper-source-use-acceptance.v1"
CALENDAR_SOURCE_SCHEMA = "research-paper-official-calendar.v1"
CALENDAR_USE_ID = "paper_policy_cooldown_calendar.v1"
PROVIDER_ID = "external-sha-bound-research-paper-evidence.v1"
_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_TWD_CAPITAL = Decimal("500000")


@dataclass(frozen=True, slots=True)
class _PreviewScope:
    candidate_identity_sha256: str
    event_date: str
    account_namespace: str
    binding_sha256: str
    confirmed_at: str


class ResearchPaperEvidenceBindingError(ValueError):
    """外部來源、用途接受或帳戶 prestate 無法精確核驗。"""


class ResearchPaperEvidenceBindingReader:
    """使用外部固定 SHA 的契約與實際原件建立可信 typed context。

    ``expected_binding_sha256`` 必須由呼叫端的受信設定或明確使用者選擇
    傳入；contract 內沒有自我授權的 ``qualified`` 欄位。所有 source 與
    use-acceptance 檔案均以 contract 內 SHA 讀回原始 bytes 並獨立驗 hash。
    """

    def __init__(
        self,
        binding_path: str | Path,
        expected_binding_sha256: str,
        timeline_service: object,
        account_service: StrategyPaperAccountService,
        personal_paths: PersonalDataPaths,
        protected_roots: tuple[str | Path, ...] = (),
    ) -> None:
        self.timeline_service = timeline_service
        self.account_service = account_service
        self.personal_paths = personal_paths
        self.binding_path = Path(binding_path)
        if not self.binding_path.is_absolute():
            raise ValueError("binding_path must be absolute")
        self.binding_path = Path(os.path.abspath(self.binding_path))
        self.evidence_root = self.binding_path.parent
        roots = tuple(Path(os.path.abspath(item)) for item in protected_roots)
        self.protected_roots = roots
        if any(_paths_overlap(self.binding_path, root) for root in roots):
            raise ValueError("evidence binding cannot be inside a protected data root")
        _require_sha256(expected_binding_sha256, "expected_binding_sha256")
        self.expected_binding_sha256 = expected_binding_sha256

    def preview(self, entry: ResearchTimelineEntry) -> VerifiedPaperContext:
        """在確認前建立供 UI 審閱的新唯讀 context。"""
        binding_doc, _ = self._read_json(
            self.binding_path,
            expected_sha256=self.expected_binding_sha256,
            root=self.evidence_root,
        )
        _require_exact_keys(
            binding_doc,
            {
                "schema_version", "candidate_identity_sha256", "event_date", "currency",
                "account_namespace", "binding_sha256", "account_manifest_sha256",
                "cash_source", "market_sources", "calendar_source",
            },
            "evidence binding",
        )
        event_date = binding_doc.get("event_date")
        account_namespace = binding_doc.get("account_namespace")
        binding_sha256 = binding_doc.get("binding_sha256")
        if not isinstance(event_date, str):
            raise ResearchPaperEvidenceBindingError("evidence binding event_date must be text")
        if not isinstance(account_namespace, str) or not account_namespace.strip():
            raise ResearchPaperEvidenceBindingError("evidence binding account_namespace must be text")
        _canonical_date(event_date, "evidence binding event_date")
        binding_sha256 = _require_sha256(binding_sha256, "evidence binding binding_sha256")
        preview_time = datetime.now(timezone.utc).isoformat()
        intent = _PreviewScope(
            candidate_identity_sha256=research_candidate_identity_sha256(entry),
            event_date=event_date,
            account_namespace=account_namespace,
            binding_sha256=binding_sha256,
            confirmed_at=preview_time,
        )
        return self._load_context(entry, intent)

    def verify(
        self,
        entry: ResearchTimelineEntry,
        intent: Any,
    ) -> VerifiedPaperContext:
        """重讀已保存候選與精確帳戶，並重新核驗全部證據。"""

        return self._load_context(entry, intent)

    def _load_context(self, entry: ResearchTimelineEntry, intent: Any) -> VerifiedPaperContext:
        if type(entry) is not ResearchTimelineEntry:
            raise ResearchPaperEvidenceBindingError("exact saved research entry is required")
        recheck = getattr(self.timeline_service, "read_evidence_baseline", None)
        if not callable(recheck):
            raise ResearchPaperEvidenceBindingError("ResearchTimelineService baseline reader is unavailable")
        try:
            verified_reference, _source_state = recheck(entry)
        except Exception as exc:
            raise ResearchPaperEvidenceBindingError("saved research original could not be reverified") from exc
        if verified_reference != entry.reference:
            raise ResearchPaperEvidenceBindingError("saved research original changed")
        recorded_at = _aware_timestamp(entry.recorded_at, "saved research recorded_at")
        confirmed_at = _timestamp(getattr(intent, "confirmed_at", None), "confirmed_at")
        if recorded_at > confirmed_at:
            raise ResearchPaperEvidenceBindingError("saved research was recorded after human confirmation")

        candidate_sha = research_candidate_identity_sha256(entry)
        if getattr(intent, "candidate_identity_sha256", None) != candidate_sha:
            raise ResearchPaperEvidenceBindingError("human confirmation candidate identity mismatch")
        binding_doc, _binding_raw = self._read_json(
            self.binding_path,
            expected_sha256=self.expected_binding_sha256,
            root=self.evidence_root,
        )
        _require_exact_keys(
            binding_doc,
            {
                "schema_version", "candidate_identity_sha256", "event_date", "currency",
                "account_namespace", "binding_sha256", "account_manifest_sha256",
                "cash_source", "market_sources", "calendar_source",
            },
            "evidence binding",
        )
        if (
            binding_doc["schema_version"] != EVIDENCE_BINDING_SCHEMA
            or binding_doc["candidate_identity_sha256"] != candidate_sha
            or binding_doc["event_date"] != intent.event_date
            or binding_doc["currency"] != "TWD"
            or binding_doc["account_namespace"] != intent.account_namespace
            or binding_doc["binding_sha256"] != intent.binding_sha256
        ):
            raise ResearchPaperEvidenceBindingError("evidence binding candidate/account/date scope mismatch")

        selection = self.account_service.select_account(intent.account_namespace)
        if (
            selection.status is not AccountBindingStatus.READY
            or selection.binding is None
            or selection.route is None
        ):
            raise ResearchPaperEvidenceBindingError(
                "exact strategy account selection is unresolved:"
                + ",".join(selection.blockers)
            )
        binding = selection.binding
        if binding.binding_sha256 != intent.binding_sha256:
            raise ResearchPaperEvidenceBindingError("selected account binding hash mismatch")
        if binding.account_namespace != intent.account_namespace:
            raise ResearchPaperEvidenceBindingError("selected account namespace mismatch")

        manifest_path = self.account_service.accounts_root / binding.account_namespace / "account_binding.json"
        manifest_root = self.account_service.personal_paths.personal_root
        manifest_raw = self._read_pinned_bytes(
            manifest_path,
            root=manifest_root,
            expected_sha256=binding_doc["account_manifest_sha256"],
        )
        manifest = _decode_strict_json(manifest_raw, "account binding manifest")
        if not isinstance(manifest, dict) or StrategyPaperAccountBinding.from_manifest(manifest) != binding:
            raise ResearchPaperEvidenceBindingError("account manifest bytes do not match selected binding")

        paths = PersonalPaperStorePaths.from_route(selection.route, portfolio_id=binding.portfolio_id)
        ledger = PaperTradeLedgerRepository(
            paths.cost_ledger_db,
            route=selection.route,
            personal_paths=self.personal_paths,
            portfolio_id=binding.portfolio_id,
            read_only=True,
        )
        snapshots = PaperPortfolioSnapshotRepository(
            paths.state_db,
            route=selection.route,
            personal_paths=self.personal_paths,
            portfolio_id=binding.portfolio_id,
            force_read_only=True,
        )
        seed = _read_exact_cash_seed(
            snapshots,
            binding,
            confirmed_at=intent.confirmed_at,
        )
        current_rowset = ledger.read_rowset_snapshot(portfolio_id=binding.portfolio_id)
        event_date = _canonical_date(intent.event_date, "confirmed event_date")
        if any(
            _canonical_date(item.event_date, "ledger fill event_date") > event_date
            for item in current_rowset.fills
        ) or any(
            _canonical_date(item.event_date, "ledger transition event_date") > event_date
            for item in current_rowset.transitions
        ):
            raise ResearchPaperEvidenceBindingError("ledger contains rows after the confirmed event date")
        operation_id = getattr(intent, "operation_id", None)
        if isinstance(operation_id, str) and operation_id:
            marker = ledger.get_daily_operation(
                operation_id, portfolio_id=binding.portfolio_id
            )
        else:
            marker = None
        if marker is not None:
            if not isinstance(operation_id, str) or not operation_id:
                raise ResearchPaperEvidenceBindingError("confirmed operation identity is invalid")
            try:
                operation_read = ledger.read_exact_daily_operation(
                    operation_id,
                    portfolio_id=binding.portfolio_id,
                    event_date=intent.event_date,
                )
            except Exception as exc:
                raise ResearchPaperEvidenceBindingError(
                    "confirmed Paper operation failed exact ledger readback"
                ) from exc
            if (
                operation_read.marker != marker
                or current_rowset.rowset_hash != marker.rowset_hash_after
                or operation_read.rowset_hash_after != marker.rowset_hash_after
                or operation_read.rowset_hash_before != marker.expected_rowset_hash
            ):
                raise ResearchPaperEvidenceBindingError(
                    "confirmed operation no longer matches the current ledger rowset"
                )
            rowset = PaperTradeLedgerRowsetSnapshot(
                portfolio_id=binding.portfolio_id,
                fills=tuple(item for item in current_rowset.fills if item.event_date < intent.event_date),
                transitions=tuple(
                    item for item in current_rowset.transitions if item.event_date < intent.event_date
                ),
                rowset_hash=marker.expected_rowset_hash,
            )
        else:
            rowset = current_rowset
        cash_amount, positions = _rebuild_prestate(seed, rowset, binding)

        cash_doc, _cash_use_doc, cash_source_hash, cash_acceptance_hash = self._resolve_source_use(
            binding_doc["cash_source"],
            source_kind="cash",
            candidate_sha=candidate_sha,
            binding=binding,
            event_date=intent.event_date,
            confirmed_at=intent.confirmed_at,
        )
        cash_row = _select_record(cash_doc, binding_doc["cash_source"]["record_id"], "cash")
        if cash_row.get("kind") != "cash_balance" or cash_row.get("currency") != "TWD":
            raise ResearchPaperEvidenceBindingError("cash source record type or currency mismatch")
        external_cash = _decimal_text(cash_row.get("amount"), "cash amount", minimum=Decimal("0"))
        if external_cash != cash_amount:
            raise ResearchPaperEvidenceBindingError("external cash amount differs from ledger prestate")
        cash = PaperCashEvidence(
            amount=external_cash,
            currency="TWD",
            source_id=cash_doc["source_id"],
            source_sha256=cash_source_hash,
            use_id=CASH_USE_ID,
            use_acceptance_sha256=cash_acceptance_hash,
            account_namespace=binding.account_namespace,
            binding_sha256=binding.binding_sha256,
            available_at=cash_row["available_at"],
            observed_at=cash_row["observed_at"],
        )

        required_symbols = set(positions) | {entry.stock_code}
        market_sources = binding_doc["market_sources"]
        if not isinstance(market_sources, list):
            raise ResearchPaperEvidenceBindingError("market_sources must be an array")
        refs_by_symbol: dict[str, dict[str, Any]] = {}
        for ref in market_sources:
            if not isinstance(ref, dict) or not isinstance(ref.get("stock_code"), str):
                raise ResearchPaperEvidenceBindingError("market source reference is invalid")
            symbol = ref["stock_code"]
            if symbol in refs_by_symbol:
                raise ResearchPaperEvidenceBindingError("duplicate market source reference:" + symbol)
            refs_by_symbol[symbol] = ref
        if set(refs_by_symbol) != required_symbols:
            raise ResearchPaperEvidenceBindingError("market source references must exactly cover current and candidate positions")

        marks: list[PaperMarketEvidence] = []
        sectors: dict[str, str] = {}
        market_rows: dict[str, dict[str, Any]] = {}
        use_acceptance_hashes: list[str] = [cash_acceptance_hash]
        for symbol in sorted(required_symbols):
            market_doc, acceptance_doc, source_hash, acceptance_hash = self._resolve_source_use(
                refs_by_symbol[symbol],
                source_kind="market",
                candidate_sha=candidate_sha,
                binding=binding,
                event_date=intent.event_date,
                confirmed_at=intent.confirmed_at,
            )
            record = _select_record(market_doc, refs_by_symbol[symbol]["record_id"], "market")
            if (
                record.get("kind") != "market_observation"
                or record.get("stock_code") != symbol
                or record.get("currency") != "TWD"
                or record.get("event_date") != intent.event_date
            ):
                raise ResearchPaperEvidenceBindingError("market source record identity/date/currency mismatch:" + symbol)
            mark_price = _decimal_text(record.get("mark_price"), "mark price", minimum=Decimal("0.01"))
            reference_price = _decimal_text(
                record.get("execution_reference_price"),
                "execution reference price",
                minimum=Decimal("0.01"),
            )
            sector = record.get("sector_id")
            if not isinstance(sector, str) or not sector.strip():
                raise ResearchPaperEvidenceBindingError("market source sector classification is missing:" + symbol)
            sectors[symbol] = sector
            market_rows[symbol] = record
            marks.append(PaperMarketEvidence(
                stock_code=symbol,
                currency="TWD",
                mark_price=mark_price,
                execution_reference_price=reference_price,
                source_id=market_doc["source_id"],
                source_sha256=source_hash,
                use_id=MARK_USE_ID,
                use_acceptance_sha256=acceptance_hash,
                account_namespace=binding.account_namespace,
                binding_sha256=binding.binding_sha256,
                event_date=intent.event_date,
                available_at=record["available_at"],
                observed_at=record["observed_at"],
            ))
            use_acceptance_hashes.append(acceptance_hash)

        calendar_doc, calendar_acceptance, calendar_source_hash, calendar_acceptance_hash = self._resolve_source_use(
            binding_doc["calendar_source"],
            source_kind="calendar",
            candidate_sha=candidate_sha,
            binding=binding,
            event_date=intent.event_date,
            confirmed_at=intent.confirmed_at,
        )
        sessions = _calendar_sessions(
            calendar_doc,
            acceptance=calendar_acceptance,
            source_sha256=calendar_source_hash,
            binding=binding,
            candidate_sha=candidate_sha,
            event_date=intent.event_date,
        )
        if intent.event_date not in sessions:
            raise ResearchPaperEvidenceBindingError("confirmed event date is absent from accepted official calendar")
        cooldown = _cooldown_days(rowset.fills, entry.stock_code, intent.event_date, sessions)
        weekly_turnover = _weekly_turnover(rowset.transitions, intent.event_date)
        policy = PaperPortfolioPolicyConfig()
        return VerifiedPaperContext(
            candidate=_candidate(entry, candidate_sha),
            binding=binding,
            account_manifest_sha256=binding_doc["account_manifest_sha256"],
            policy_use_id=f"{binding.policy_id}@{binding.policy_version}",
            policy_artifact_sha256=binding.policy_sha256,
            cost_use_id=f"{binding.cost_model_id}@{binding.cost_model_version}",
            cost_artifact_sha256=binding.cost_model_sha256,
            cost_commission_bp_per_side=policy.commission_bp_per_side,
            cost_slippage_bp_per_side=policy.slippage_bp_per_side,
            cost_sell_tax_bp=policy.sell_tax_bp,
            cost_minimum_fee=Decimal("20.00"),
            slippage_model_id="fixed_bps",
            slippage_model_version="v1",
            currency="TWD",
            policy=policy,
            cash=cash,
            marks=tuple(marks),
            positions=positions,
            sector_by_symbol=sectors,
            weekly_turnover_used_bp=weekly_turnover,
            trading_days_since_last_trade=cooldown,
            ledger_rowset_hash=rowset.rowset_hash,
            provider_id=PROVIDER_ID,
        )

    def _resolve_source_use(
        self,
        reference: object,
        *,
        source_kind: str,
        candidate_sha: str,
        binding: StrategyPaperAccountBinding,
        event_date: str,
        confirmed_at: str,
    ) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        if not isinstance(reference, dict):
            raise ResearchPaperEvidenceBindingError(f"{source_kind} source reference must be an object")
        reference_fields = {
            "path", "sha256", "record_id", "acceptance_path", "acceptance_sha256", "acceptance_id"
        }
        if source_kind == "market":
            reference_fields.add("stock_code")
        _require_exact_keys(
            reference,
            reference_fields,
            f"{source_kind} source reference",
        )
        if source_kind == "market" and (
            not isinstance(reference["stock_code"], str)
            or len(reference["stock_code"]) != 4
            or not reference["stock_code"].isdigit()
        ):
            raise ResearchPaperEvidenceBindingError("market source reference stock_code is invalid")
        raw = self._read_pinned_bytes(
            self._safe_relative_path(reference["path"]),
            root=self.evidence_root,
            expected_sha256=reference["sha256"],
        )
        source_hash = file_sha256(raw)
        source_doc = _decode_canonical_json(raw, f"{source_kind} source")
        if source_kind == "calendar":
            _require_exact_keys(
                source_doc,
                {"schema_version", "source_id", "coverage_start", "coverage_end", "sessions"},
                "official calendar source",
            )
            if source_doc["schema_version"] != CALENDAR_SOURCE_SCHEMA:
                raise ResearchPaperEvidenceBindingError("official calendar source schema mismatch")
            if reference["record_id"] != "official-sessions":
                raise ResearchPaperEvidenceBindingError("official calendar record identity mismatch")
        else:
            _require_exact_keys(source_doc, {"schema_version", "source_id", "records"}, f"{source_kind} source")
            if (
                source_doc["schema_version"] != EVIDENCE_SOURCE_SCHEMA
                or not isinstance(source_doc["source_id"], str)
                or not source_doc["source_id"].strip()
                or not isinstance(source_doc["records"], list)
            ):
                raise ResearchPaperEvidenceBindingError(f"{source_kind} source document is invalid")
        acceptance_raw = self._read_pinned_bytes(
            self._safe_relative_path(reference["acceptance_path"]),
            root=self.evidence_root,
            expected_sha256=reference["acceptance_sha256"],
        )
        acceptance_hash = file_sha256(acceptance_raw)
        acceptance = _decode_canonical_json(acceptance_raw, f"{source_kind} use acceptance")
        _require_exact_keys(
            acceptance,
            {
                "schema_version", "acceptance_id", "accepted_by", "accepted_at",
                "account_namespace", "binding_sha256", "candidate_identity_sha256",
                "event_date", "currency", "accepted_uses",
            },
            f"{source_kind} use acceptance",
        )
        accepted_at = _timestamp(acceptance["accepted_at"], "use acceptance accepted_at")
        if accepted_at > _timestamp(confirmed_at, "confirmed_at"):
            raise ResearchPaperEvidenceBindingError("source use acceptance was created after confirmation")
        if (
            acceptance["schema_version"] != USE_ACCEPTANCE_SCHEMA
            or acceptance["acceptance_id"] != reference["acceptance_id"]
            or not isinstance(acceptance["accepted_by"], str)
            or not acceptance["accepted_by"].strip()
            or acceptance["account_namespace"] != binding.account_namespace
            or acceptance["binding_sha256"] != binding.binding_sha256
            or acceptance["candidate_identity_sha256"] != candidate_sha
            or acceptance["event_date"] != event_date
            or acceptance["currency"] != "TWD"
        ):
            raise ResearchPaperEvidenceBindingError(f"{source_kind} use acceptance scope mismatch")
        uses = acceptance["accepted_uses"]
        if not isinstance(uses, list):
            raise ResearchPaperEvidenceBindingError("accepted_uses must be an array")
        expected = _expected_acceptance_use(source_kind, source_hash, reference["record_id"])
        if not any(item == expected for item in uses):
            raise ResearchPaperEvidenceBindingError(f"{source_kind} source use was not explicitly accepted")
        return source_doc, acceptance, source_hash, acceptance_hash

    def _safe_relative_path(self, value: object) -> Path:
        relative = _relative_path(value)
        return self.evidence_root.joinpath(*relative.parts)

    def _read_json(
        self,
        path: Path,
        *,
        expected_sha256: str,
        root: Path,
    ) -> tuple[dict[str, Any], bytes]:
        raw = self._read_pinned_bytes(path, root=root, expected_sha256=expected_sha256)
        document = _decode_canonical_json(raw, "evidence binding")
        if not isinstance(document, dict):
            raise ResearchPaperEvidenceBindingError("evidence binding must be an object")
        return document, raw

    @staticmethod
    def _read_pinned_bytes(path: Path, *, root: Path, expected_sha256: str) -> bytes:
        _require_sha256(expected_sha256, "pinned file sha256")
        root_abs = Path(os.path.abspath(root))
        path_abs = Path(os.path.abspath(path))
        try:
            relative = path_abs.relative_to(root_abs)
        except ValueError as exc:
            raise ResearchPaperEvidenceBindingError("pinned source path escaped its root") from exc
        if not relative.parts:
            raise ResearchPaperEvidenceBindingError("pinned source path is empty")
        current = root_abs
        for index, part in enumerate(relative.parts):
            current = current / part
            try:
                info = os.stat(to_internal_io_path(current), follow_symlinks=False)
            except OSError as exc:
                raise ResearchPaperEvidenceBindingError("pinned source path is unavailable") from exc
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ResearchPaperEvidenceBindingError("pinned source path contains a link or reparse point")
            final = index == len(relative.parts) - 1
            if final and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ResearchPaperEvidenceBindingError("pinned source must be a single-link regular file")
            if not final and not stat.S_ISDIR(info.st_mode):
                raise ResearchPaperEvidenceBindingError("pinned source parent is not a directory")
        file_path = to_internal_io_path(path_abs)
        before = os.stat(file_path, follow_symlinks=False)
        if before.st_size > _MAX_DOCUMENT_BYTES:
            raise ResearchPaperEvidenceBindingError("pinned source exceeds the size limit")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(file_path, flags)
        try:
            opened = os.fstat(descriptor)
            signature = _file_signature(before)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or _file_signature(opened) != signature:
                raise ResearchPaperEvidenceBindingError("pinned source changed before read")
            chunks: list[bytes] = []
            total = 0
            while total <= _MAX_DOCUMENT_BYTES:
                chunk = os.read(descriptor, min(65_536, _MAX_DOCUMENT_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            if total > _MAX_DOCUMENT_BYTES:
                raise ResearchPaperEvidenceBindingError("pinned source exceeds the size limit")
            after_fd = os.fstat(descriptor)
            after_path = os.stat(file_path, follow_symlinks=False)
            if _file_signature(after_fd) != signature or _file_signature(after_path) != signature:
                raise ResearchPaperEvidenceBindingError("pinned source changed during read")
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
        if file_sha256(raw) != expected_sha256:
            raise ResearchPaperEvidenceBindingError("pinned source SHA-256 mismatch")
        return raw


def _read_exact_cash_seed(
    repository: PaperPortfolioSnapshotRepository,
    binding: StrategyPaperAccountBinding,
    *,
    confirmed_at: str,
) -> PaperPortfolioSnapshot:
    if not repository.read_only or repository.route is None:
        raise ResearchPaperEvidenceBindingError("cash seed reader must be route-bound and read-only")
    snapshots = repository.list_for_portfolio(binding.portfolio_id)
    seeds: list[tuple[PaperPortfolioSnapshot, PaperPortfolioSnapshotReceipt]] = []
    for snapshot in snapshots:
        receipt = repository.get_receipt(snapshot.snapshot_id)
        if receipt is not None and receipt.receipt_kind == "account_cash_seed":
            seeds.append((snapshot, receipt))
    if len(seeds) != 1:
        raise ResearchPaperEvidenceBindingError("exactly one bound account cash seed receipt is required")
    snapshot, receipt = seeds[0]
    receipt.validate_for_snapshot(snapshot, expected_account_namespace=binding.account_namespace)
    seed_created_at = _timestamp(receipt.seed_created_at, "account cash seed created_at")
    if seed_created_at > _timestamp(confirmed_at, "confirmed_at"):
        raise ResearchPaperEvidenceBindingError("account cash seed was created after human confirmation")
    if (
        receipt.schema_version != PAPER_ACCOUNT_CASH_SEED_RECEIPT_SCHEMA_VERSION
        or receipt.binding_sha256 != binding.binding_sha256
        or receipt.account_namespace != binding.account_namespace
        or receipt.initial_capital != "500000"
        or receipt.max_positions != 8
        or snapshot.portfolio_id != binding.portfolio_id
        or snapshot.cash != _TWD_CAPITAL
        or snapshot.total_value != _TWD_CAPITAL
        or snapshot.positions
    ):
        raise ResearchPaperEvidenceBindingError("cash seed receipt does not match exact 500000 TWD account binding")
    return snapshot


def _rebuild_prestate(
    seed: PaperPortfolioSnapshot,
    rowset: PaperTradeLedgerRowsetSnapshot,
    binding: StrategyPaperAccountBinding,
) -> tuple[Decimal, dict[str, int]]:
    fills_by_id = {item.fill_id: item for item in rowset.fills}
    if len(fills_by_id) != len(rowset.fills):
        raise ResearchPaperEvidenceBindingError("ledger contains duplicate fill identities")
    if not rowset.transitions:
        if rowset.fills:
            raise ResearchPaperEvidenceBindingError("ledger fills without transitions cannot establish cash state")
        return seed.cash, {}
    transitioned_ids: list[str] = []
    cash = seed.cash
    positions: dict[str, int] = {}
    transition_dates: set[str] = set()
    with localcontext(Context(prec=60)):
        for transition in sorted(rowset.transitions, key=lambda item: (item.event_date, item.transition_id)):
            if transition.event_date in transition_dates:
                raise ResearchPaperEvidenceBindingError("ledger has more than one transition on one date")
            transition_dates.add(transition.event_date)
            if transition.event_date < seed.decision_date:
                raise ResearchPaperEvidenceBindingError("ledger transition predates the exact cash seed")
            if transition.pre_cash != cash or dict(transition.pre_positions) != positions:
                raise ResearchPaperEvidenceBindingError("ledger transition chain has a prestate discontinuity")
            transition_fills: list[PaperTradeFill] = []
            for fill_id in transition.fill_ids:
                fill = fills_by_id.get(fill_id)
                if fill is None or fill_id in transitioned_ids:
                    raise ResearchPaperEvidenceBindingError("transition fill reference is missing or duplicated")
                if fill.event_date != transition.event_date or fill.portfolio_id != binding.portfolio_id:
                    raise ResearchPaperEvidenceBindingError("transition fill date/account mismatch")
                transitioned_ids.append(fill_id)
                transition_fills.append(fill)
            next_positions = dict(positions)
            next_cash = cash
            for fill in transition_fills:
                if fill.filled_quantity == 0:
                    continue
                previous = next_positions.get(fill.stock_code, 0)
                next_quantity = (
                    previous + fill.filled_quantity
                    if fill.side == "buy"
                    else previous - fill.filled_quantity
                )
                if next_quantity < 0:
                    raise ResearchPaperEvidenceBindingError("ledger sell exceeds reconstructed position")
                if next_quantity:
                    next_positions[fill.stock_code] = next_quantity
                else:
                    next_positions.pop(fill.stock_code, None)
                settlement = fill.gross_amount + fill.commission + fill.tax
                next_cash += -settlement if fill.side == "buy" else fill.gross_amount - fill.commission - fill.tax
            next_cash = next_cash.quantize(Decimal("0.01"))
            if next_cash != transition.post_cash or next_positions != dict(transition.post_positions):
                raise ResearchPaperEvidenceBindingError("ledger transition poststate does not reconcile to fills")
            _validate_transition_nav(transition)
            cash = next_cash
            positions = next_positions
    if set(transitioned_ids) != set(fills_by_id):
        raise ResearchPaperEvidenceBindingError("ledger contains fills outside its transitions")
    return cash, positions


def _validate_transition_nav(transition: PaperTradeTransition) -> None:
    with localcontext(Context(prec=60)):
        if transition.common_nav != transition.pre_total_value:
            raise ResearchPaperEvidenceBindingError("transition common NAV differs from prestate NAV")
        for position_map, cash_value, total_value in (
            (transition.pre_positions, transition.pre_cash, transition.pre_total_value),
            (transition.post_positions, transition.post_cash, transition.post_total_value),
        ):
            if any(symbol not in transition.common_prices for symbol, quantity in position_map.items() if quantity > 0):
                raise ResearchPaperEvidenceBindingError("transition common prices omit a held symbol")
            market_value = sum(
                (transition.common_prices[symbol] * Decimal(quantity) for symbol, quantity in position_map.items() if quantity > 0),
                Decimal("0"),
            )
            if (cash_value + market_value).quantize(Decimal("0.01")) != total_value:
                raise ResearchPaperEvidenceBindingError("transition cash/positions do not reconcile to NAV")


def _select_record(document: Mapping[str, Any], record_id: object, label: str) -> dict[str, Any]:
    records = document.get("records")
    if not isinstance(records, list) or not isinstance(record_id, str) or not record_id:
        raise ResearchPaperEvidenceBindingError(f"{label} source record reference is invalid")
    matches = [item for item in records if isinstance(item, dict) and item.get("record_id") == record_id]
    if len(matches) != 1:
        raise ResearchPaperEvidenceBindingError(f"{label} source record is absent or ambiguous")
    return matches[0]


def _expected_acceptance_use(source_kind: str, source_sha256: str, record_id: object) -> dict[str, Any]:
    fields = {
        "cash": ["amount", "available_at", "currency", "observed_at"],
        "market": ["available_at", "currency", "event_date", "execution_reference_price", "mark_price", "observed_at", "sector_id"],
        "calendar": ["sessions"],
    }.get(source_kind)
    use_id = {
        "cash": CASH_USE_ID,
        "market": MARK_USE_ID,
        "calendar": CALENDAR_USE_ID,
    }.get(source_kind)
    if fields is None or use_id is None or not isinstance(record_id, str) or not record_id:
        raise ResearchPaperEvidenceBindingError("unsupported evidence source use")
    return {
        "source_sha256": source_sha256,
        "record_id": record_id,
        "use_id": use_id,
        "fields": fields,
    }


def _calendar_sessions(
    document: Mapping[str, Any],
    *,
    acceptance: Mapping[str, Any],
    source_sha256: str,
    binding: StrategyPaperAccountBinding,
    candidate_sha: str,
    event_date: str,
) -> tuple[str, ...]:
    _require_exact_keys(document, {"schema_version", "source_id", "coverage_start", "coverage_end", "sessions"}, "official calendar source")
    if document["schema_version"] != CALENDAR_SOURCE_SCHEMA:
        raise ResearchPaperEvidenceBindingError("official calendar source schema mismatch")
    sessions = document["sessions"]
    if not isinstance(sessions, list) or not sessions or any(not isinstance(item, str) for item in sessions):
        raise ResearchPaperEvidenceBindingError("official calendar sessions are invalid")
    parsed = tuple(_canonical_date(item, "calendar session") for item in sessions)
    if tuple(sorted(set(parsed))) != parsed:
        raise ResearchPaperEvidenceBindingError("official calendar sessions must be sorted and unique")
    coverage_start = _canonical_date(document["coverage_start"], "calendar coverage start")
    coverage_end = _canonical_date(document["coverage_end"], "calendar coverage end")
    if not parsed or parsed[0] < coverage_start or parsed[-1] > coverage_end:
        raise ResearchPaperEvidenceBindingError("calendar sessions fall outside declared coverage")
    use = _expected_acceptance_use("calendar", source_sha256, "official-sessions")
    if use not in acceptance.get("accepted_uses", []):
        raise ResearchPaperEvidenceBindingError("official calendar use was not accepted")
    return tuple(item.isoformat() for item in parsed)


def _cooldown_days(
    fills: tuple[PaperTradeFill, ...],
    stock_code: str,
    event_date: str,
    sessions: tuple[str, ...],
) -> int:
    dates = [
        item.event_date for item in fills
        if item.stock_code == stock_code and item.filled_quantity > 0 and item.event_date < event_date
    ]
    if not dates:
        return 10_000
    last = max(dates)
    if last not in sessions or event_date not in sessions:
        raise ResearchPaperEvidenceBindingError("official calendar does not cover the candidate cooldown window")
    return sum(1 for item in sessions if last < item < event_date)


def _weekly_turnover(transitions: tuple[PaperTradeTransition, ...], event_date: str) -> int:
    end = _canonical_date(event_date, "event_date")
    start = end - timedelta(days=7)
    total = 0
    for transition in transitions:
        transition_date = _canonical_date(transition.event_date, "transition event_date")
        if not start <= transition_date < end:
            continue
        before_weights, before_cash = _transition_weights(
            transition.pre_positions, transition.common_prices, transition.common_nav
        )
        after_weights, after_cash = _transition_weights(
            transition.post_positions, transition.common_prices, transition.common_nav
        )
        symbols = tuple(sorted(set(before_weights) | set(after_weights)))
        gross_l1 = sum(abs(after_weights.get(code, 0) - before_weights.get(code, 0)) for code in symbols)
        gross_l1 += abs(after_cash - before_cash)
        if gross_l1 % 2:
            raise ResearchPaperEvidenceBindingError("transition canonical turnover has an odd weight delta")
        total += gross_l1 // 2
    return total


def _transition_weights(
    positions: Mapping[str, int],
    prices: Mapping[str, Decimal],
    nav: Decimal,
) -> tuple[dict[str, int], int]:
    with localcontext(Context(prec=28, rounding=ROUND_HALF_UP)):
        return _transition_weights_decimal(positions, prices, nav)


def _transition_weights_decimal(
    positions: Mapping[str, int],
    prices: Mapping[str, Decimal],
    nav: Decimal,
) -> tuple[dict[str, int], int]:
    if nav <= 0:
        raise ResearchPaperEvidenceBindingError("transition common NAV must be positive")
    amounts = {
        symbol: prices[symbol] * Decimal(quantity)
        for symbol, quantity in positions.items()
        if quantity > 0
    }
    if any(symbol not in prices for symbol, quantity in positions.items() if quantity > 0):
        raise ResearchPaperEvidenceBindingError("transition common prices omit a position")
    cash_amount = nav - sum(amounts.values(), Decimal("0"))
    if cash_amount < 0:
        raise ResearchPaperEvidenceBindingError("transition common cash is negative")
    amounts["\x00cash"] = cash_amount
    floors: dict[str, int] = {}
    remainders: dict[str, Decimal] = {}
    for symbol, amount in amounts.items():
        exact = amount * Decimal(10_000) / nav
        floor = int(exact.to_integral_value(rounding=ROUND_DOWN))
        floors[symbol] = floor
        remainders[symbol] = exact - Decimal(floor)
    remaining = 10_000 - sum(floors.values())
    for symbol in sorted(amounts, key=lambda item: (-remainders[item], item))[:remaining]:
        floors[symbol] += 1
    return ({key: value for key, value in floors.items() if key != "\x00cash" and value > 0}, floors["\x00cash"])


def _candidate(entry: ResearchTimelineEntry, identity_sha256: str) -> VerifiedResearchCandidate:
    reference = entry.reference
    revision = getattr(reference, "revision_id", None)
    if not isinstance(revision, str) or not revision:
        revision = ""
    identity = getattr(reference, "decision_identity", None)
    snapshot = getattr(reference, "snapshot", None)
    decision_date = (
        getattr(reference, "research_date", "")
        or getattr(identity, "decision_date", "")
        or getattr(getattr(snapshot, "identity", None), "decision_date", "")
        or getattr(reference, "data_date", "")
        or entry.data_date
    )
    if not decision_date:
        raise ResearchPaperEvidenceBindingError("saved research decision date is unavailable")
    _canonical_date(decision_date, "saved research decision date")
    source_projection = _canonical_json(_canonical_typed_value(reference)).encode("utf-8")
    return VerifiedResearchCandidate(
        identity_sha256=identity_sha256,
        result_id=entry.result_id,
        record_id=entry.record_id,
        revision_id=revision,
        stock_code=entry.stock_code,
        decision_date=decision_date,
        source_identity=entry.source_identity,
        source_sha256="sha256:" + sha256(source_projection).hexdigest(),
        provider_id=PROVIDER_ID,
    )


def _canonical_typed_value(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _canonical_typed_value(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    if isinstance(value, Mapping):
        return {str(key): _canonical_typed_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_canonical_typed_value(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ResearchPaperEvidenceBindingError("saved research Decimal is non-finite")
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float):
        raise ResearchPaperEvidenceBindingError("saved research float is not canonical evidence")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ResearchPaperEvidenceBindingError("unsupported saved research value")


def _relative_path(value: object) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or ":" in value
    ):
        raise ValueError("evidence paths must be relative POSIX paths")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("evidence path contains an unsafe component")
    return path


def _decode_strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ResearchPaperEvidenceBindingError(f"{label} is not valid strict JSON") from exc
    return value


def _decode_canonical_json(raw: bytes, label: str) -> Any:
    value = _decode_strict_json(raw, label)
    if _canonical_json(value).encode("utf-8") != raw:
        raise ResearchPaperEvidenceBindingError(f"{label} bytes are not canonical JSON")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_float(_value: str) -> Any:
    raise ValueError("JSON floating point values are forbidden")


def _reject_json_constant(_value: str) -> Any:
    raise ValueError("non-standard JSON constants are forbidden")


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ResearchPaperEvidenceBindingError(f"{label} must be an object")
    if set(value) != expected:
        raise ResearchPaperEvidenceBindingError(f"{label} fields mismatch")


def _require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise ResearchPaperEvidenceBindingError(f"{label} must be canonical SHA-256 text")
    return value


def _decimal_text(value: object, label: str, *, minimum: Decimal) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ResearchPaperEvidenceBindingError(f"{label} must be Decimal text")
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise ResearchPaperEvidenceBindingError(f"{label} must be Decimal text") from exc
    if not parsed.is_finite() or parsed < minimum or str(parsed) != value:
        raise ResearchPaperEvidenceBindingError(f"{label} must be finite canonical Decimal text")
    return parsed


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ResearchPaperEvidenceBindingError(f"{label} must be canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResearchPaperEvidenceBindingError(f"{label} must be canonical UTC text") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchPaperEvidenceBindingError(f"{label} must be timezone-aware")
    normalized = parsed.astimezone(timezone.utc)
    if normalized.isoformat() != value:
        raise ResearchPaperEvidenceBindingError(f"{label} must use canonical UTC form")
    return normalized


def _aware_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ResearchPaperEvidenceBindingError(f"{label} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchPaperEvidenceBindingError(
            f"{label} must be a timezone-aware timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchPaperEvidenceBindingError(f"{label} must be a timezone-aware timestamp")
    return parsed.astimezone(timezone.utc)


def _canonical_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ResearchPaperEvidenceBindingError(f"{label} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ResearchPaperEvidenceBindingError(f"{label} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ResearchPaperEvidenceBindingError(f"{label} must be YYYY-MM-DD")
    return parsed


def _file_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        try:
            right.relative_to(left)
            return True
        except ValueError:
            return False


__all__ = [
    "CALENDAR_SOURCE_SCHEMA",
    "CALENDAR_USE_ID",
    "EVIDENCE_BINDING_SCHEMA",
    "EVIDENCE_SOURCE_SCHEMA",
    "PROVIDER_ID",
    "ResearchPaperEvidenceBindingError",
    "ResearchPaperEvidenceBindingReader",
    "USE_ACCEPTANCE_SCHEMA",
]
