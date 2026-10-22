"""以外部 SHA 錨定的月營收逐批用途資格唯讀解析器。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
from typing import Mapping

from data_module.monthly_revenue_use_policy import MonthlyRevenueQualificationEvidence
from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OPENAPI_MONTHLY_REVENUE_DATASET_IDS,
    OPENAPI_MONTHLY_REVENUE_PARSER_VERSION,
    OPENAPI_MONTHLY_REVENUE_SOURCE_IDS,
    OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION,
    MAX_OPENAPI_UNIT_PROOF_ARTIFACT_BYTES,
    OpenApiMonthlyRevenueBatch,
    OpenApiMonthlyRevenueError,
    OpenApiMonthlyRevenueUnitProof,
    prepare_openapi_monthly_revenue_batch,
    read_openapi_unit_proof_artifact,
)
from data_module.source_acceptance_decision_registry import (
    SourceAcceptanceDecisionRevision,
    parse_source_acceptance_decision_revision,
    validate_source_acceptance_decision_revision,
)


MONTHLY_REVENUE_QUALIFICATION_BINDING_SCHEMA_V2 = (
    "monthly-revenue-qualification-binding.v2"
)
MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_SCHEMA_V1 = (
    "monthly-revenue-qualification-evidence.v1"
)
MONTHLY_REVENUE_QUALIFICATION_BINDING_MAX_BYTES = 2 * 1024 * 1024
MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_MAX_BYTES = 9 * 1024 * 1024
MONTHLY_REVENUE_QUALIFICATION_TOTAL_DOCUMENT_MAX_BYTES = 24 * 1024 * 1024
MONTHLY_REVENUE_QUALIFICATION_SUPPORTING_DOCUMENT_MAX_COUNT = 8
MONTHLY_REVENUE_QUALIFICATION_ISSUED_EVIDENCE_MAX_COUNT = 128
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESEARCH_SHADOW_USES = (
    "comparison",
    "current_research",
    "factor_research",
    "historical_research",
    "portfolio_research",
    "screening",
    "sector_theme",
)
_CAPTURED_AVAILABILITY_BASIS = "captured_complete_batch_available_hour"


class MonthlyRevenueQualificationBindingError(ValueError):
    """資格 binding 或其受 SHA 固定的原件無法通過唯讀核驗。"""


@dataclass(frozen=True, slots=True)
class _Document:
    evidence_id: str
    kind: str
    relative_path: str
    sha256: str
    payload: Mapping[str, object] | None
    raw_bytes: bytes


@dataclass(frozen=True, slots=True)
class _LoadedBinding:
    root: Path
    binding_sha256: str
    binding: Mapping[str, object]
    decision: SourceAcceptanceDecisionRevision
    documents: tuple[_Document, ...]
    supporting_documents: tuple[_SupportingDocument, ...]
    unit_proof: OpenApiMonthlyRevenueUnitProof | None


@dataclass(frozen=True, slots=True)
class _SupportingDocument:
    evidence_id: str
    kind: str
    url: str
    relative_path: str
    sha256: str
    raw_bytes: bytes


@dataclass(frozen=True, slots=True)
class _IssuedEvidence:
    evidence: MonthlyRevenueQualificationEvidence
    batch_fingerprint: str
    binding_sha256: str


class PinnedMonthlyRevenueQualificationResolver:
    """每次核驗都重讀外部固定的 binding 與全部引用原件。"""

    def __init__(self, binding_path: Path | str, expected_sha256: str) -> None:
        self._binding_path = Path(binding_path).expanduser()
        self._expected_sha256 = _require_sha256(
            expected_sha256, "binding_expected_sha256_invalid"
        )
        self._issued: dict[int, _IssuedEvidence] = {}

    def evidence_for_batch(
        self,
        batch: OpenApiMonthlyRevenueBatch,
    ) -> MonthlyRevenueQualificationEvidence:
        """為與固定來源及 raw bytes 完全相符的 batch 發行唯讀 evidence。"""

        loaded = self._load_binding()
        self._verify_batch(loaded, batch)
        if any(
            document.kind == "quality"
            and document.payload is not None
            and document.payload.get("row_count") != len(batch.rows)
            for document in loaded.documents
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_quality_row_count_mismatch"
            )
        evidence = _project_evidence(loaded)
        fingerprint = _batch_identity_fingerprint(loaded.binding)
        self._issued[id(evidence)] = _IssuedEvidence(
            evidence=evidence,
            batch_fingerprint=fingerprint,
            binding_sha256=loaded.binding_sha256,
        )
        while len(self._issued) > MONTHLY_REVENUE_QUALIFICATION_ISSUED_EVIDENCE_MAX_COUNT:
            del self._issued[next(iter(self._issued))]
        return evidence

    def verify(
        self,
        evidence: MonthlyRevenueQualificationEvidence,
        cutoff_at: datetime,
    ) -> bool:
        """只接受本 resolver 發行的同一 evidence，並於每次呼叫重讀原件。"""

        if type(evidence) is not MonthlyRevenueQualificationEvidence:
            return False
        issued = self._issued.get(id(evidence))
        if issued is None or issued.evidence is not evidence:
            return False
        try:
            cutoff = _parse_aware_datetime(cutoff_at, "cutoff_at")
            loaded = self._load_binding()
            fresh_evidence = _project_evidence(loaded)
            decision_at = _parse_iso_datetime(
                loaded.decision.decided_at, "decision_decided_at"
            )
            if (
                loaded.binding_sha256 != issued.binding_sha256
                or _batch_identity_fingerprint(loaded.binding)
                != issued.batch_fingerprint
                or fresh_evidence != evidence
                or decision_at > cutoff
                or evidence.available_at > cutoff
            ):
                return False
            return True
        except Exception:
            return False

    def _load_binding(self) -> _LoadedBinding:
        payload, root = _read_absolute_regular_file(
            self._binding_path,
            MONTHLY_REVENUE_QUALIFICATION_BINDING_MAX_BYTES,
            error_prefix="binding",
        )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != self._expected_sha256:
            raise MonthlyRevenueQualificationBindingError(
                "binding_external_sha256_mismatch"
            )
        decoded = _decode_canonical_json(payload, "binding")
        if type(decoded) is not dict or set(decoded) != {
            "schema_version",
            "source_id",
            "market",
            "endpoint_url",
            "parser_version",
            "source_schema_version",
            "raw_batch_sha256",
            "captured_at",
            "successful_batch_completed_at",
            "available_at",
            "availability_basis",
            "official_announcement_at",
            "official_revision_id",
            "decision",
            "documents",
            "supporting_documents",
        }:
            raise MonthlyRevenueQualificationBindingError(
                "binding_schema_fields_invalid"
            )
        binding: dict[str, object] = decoded
        if binding["schema_version"] != MONTHLY_REVENUE_QUALIFICATION_BINDING_SCHEMA_V2:
            raise MonthlyRevenueQualificationBindingError(
                "binding_schema_version_unsupported"
            )
        market = binding["market"]
        if type(market) is not str or market not in OPENAPI_MONTHLY_REVENUE_ENDPOINTS:
            raise MonthlyRevenueQualificationBindingError("binding_market_invalid")
        source_id = _require_text(binding["source_id"], "binding_source_id_invalid")
        endpoint = _require_text(binding["endpoint_url"], "binding_endpoint_invalid")
        if (
            source_id != OPENAPI_MONTHLY_REVENUE_SOURCE_IDS[market]
            or endpoint != OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_source_profile_mismatch"
            )
        if (
            binding["parser_version"] != OPENAPI_MONTHLY_REVENUE_PARSER_VERSION
            or binding["source_schema_version"]
            != OPENAPI_MONTHLY_REVENUE_SOURCE_SCHEMA_VERSION
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_parser_profile_mismatch"
            )
        _require_sha256(binding["raw_batch_sha256"], "binding_raw_batch_sha256_invalid")
        captured_at = _parse_iso_datetime(binding["captured_at"], "binding_captured_at")
        completed_at = _parse_iso_datetime(
            binding["successful_batch_completed_at"],
            "binding_successful_batch_completed_at",
        )
        available_at = _parse_iso_datetime(binding["available_at"], "binding_available_at")
        if captured_at > completed_at or completed_at > available_at:
            raise MonthlyRevenueQualificationBindingError("binding_clock_order_invalid")
        if binding["availability_basis"] != _CAPTURED_AVAILABILITY_BASIS:
            raise MonthlyRevenueQualificationBindingError(
                "binding_availability_basis_invalid"
            )
        if binding["official_announcement_at"] is not None or binding["official_revision_id"] is not None:
            raise MonthlyRevenueQualificationBindingError(
                "binding_must_not_claim_official_pit"
            )

        decision_payload = binding["decision"]
        if type(decision_payload) is not dict:
            raise MonthlyRevenueQualificationBindingError("binding_decision_invalid")
        try:
            decision = parse_source_acceptance_decision_revision(decision_payload)
            validate_source_acceptance_decision_revision(decision)
        except (TypeError, ValueError) as exc:
            raise MonthlyRevenueQualificationBindingError(
                "binding_decision_rejected"
            ) from exc
        if decision.source_id != source_id:
            raise MonthlyRevenueQualificationBindingError(
                "binding_decision_source_mismatch"
            )

        documents_raw = binding["documents"]
        if type(documents_raw) is not list or not documents_raw:
            raise MonthlyRevenueQualificationBindingError(
                "binding_documents_invalid"
            )
        documents: list[_Document] = []
        total_document_bytes = 0
        seen_ids: set[str] = set()
        seen_kinds: set[tuple[str, str]] = set()
        for item in documents_raw:
            document, document_bytes = _read_document(root, item)
            total_document_bytes += len(document_bytes)
            if total_document_bytes > MONTHLY_REVENUE_QUALIFICATION_TOTAL_DOCUMENT_MAX_BYTES:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_document_total_bytes_exceeded"
                )
            if document.evidence_id in seen_ids:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_document_id_duplicate"
                )
            seen_ids.add(document.evidence_id)
            kind_key = (document.kind, document.evidence_id)
            if kind_key in seen_kinds:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_document_duplicate"
                )
            seen_kinds.add(kind_key)
            documents.append(document)

        supporting_documents_raw = binding["supporting_documents"]
        if (
            type(supporting_documents_raw) is not list
            or not supporting_documents_raw
            or len(supporting_documents_raw)
            > MONTHLY_REVENUE_QUALIFICATION_SUPPORTING_DOCUMENT_MAX_COUNT
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_supporting_documents_invalid"
            )
        supporting_documents: list[_SupportingDocument] = []
        supporting_ids: set[str] = set()
        supporting_kinds: set[str] = set()
        for item in supporting_documents_raw:
            support, support_bytes = _read_supporting_document(root, item)
            total_document_bytes += len(support_bytes)
            if total_document_bytes > MONTHLY_REVENUE_QUALIFICATION_TOTAL_DOCUMENT_MAX_BYTES:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_document_total_bytes_exceeded"
                )
            if support.evidence_id in supporting_ids:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_supporting_document_id_duplicate"
                )
            if support.evidence_id in seen_ids:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_document_id_duplicate"
                )
            if support.kind in supporting_kinds and support.kind in {
                "official_dataset", "official_license", "official_schema", "raw_capture"
            }:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_supporting_document_kind_duplicate"
                )
            supporting_ids.add(support.evidence_id)
            supporting_kinds.add(support.kind)
            supporting_documents.append(support)
        _validate_supporting_document_set(
            supporting_documents,
            market=market,
            endpoint=endpoint,
            raw_batch_sha256=binding["raw_batch_sha256"],
        )

        _validate_document_sets(decision, documents)
        for document in documents:
            if document.kind != "unit":
                _validate_qualification_document(document, binding, decision)
        unit_docs = tuple(item for item in documents if item.kind == "unit")
        if len(unit_docs) > 1:
            raise MonthlyRevenueQualificationBindingError(
                "binding_unit_proof_ambiguous"
            )
        unit_proof: OpenApiMonthlyRevenueUnitProof | None = None
        if unit_docs:
            unit_doc = unit_docs[0]
            if unit_doc.payload is not None:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_unit_proof_document_shape_invalid"
                )
            proof_sha256 = _require_sha256(
                unit_doc.evidence_id, "binding_unit_proof_id_invalid"
            )
            proof_path = _resolve_relative_path(root, unit_doc.relative_path)
            try:
                unit_proof = read_openapi_unit_proof_artifact(
                    proof_path,
                    expected_proof_sha256=proof_sha256,
                )
            except (OpenApiMonthlyRevenueError, OSError, ValueError) as exc:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_unit_proof_rejected"
                ) from exc
            if unit_proof.to_artifact_bytes() != unit_doc.raw_bytes:
                raise MonthlyRevenueQualificationBindingError(
                    "binding_unit_proof_artifact_bytes_changed"
                )
            if (
                unit_proof.market != market
                or unit_proof.source_id != source_id
                or unit_proof.endpoint_url != endpoint
            ):
                raise MonthlyRevenueQualificationBindingError(
                    "binding_unit_proof_source_mismatch"
                )
        return _LoadedBinding(
            root=root,
            binding_sha256=digest,
            binding=binding,
            decision=decision,
            documents=tuple(documents),
            supporting_documents=tuple(supporting_documents),
            unit_proof=unit_proof,
        )

    def _verify_batch(
        self,
        loaded: _LoadedBinding,
        batch: OpenApiMonthlyRevenueBatch,
    ) -> None:
        if type(batch) is not OpenApiMonthlyRevenueBatch:
            raise MonthlyRevenueQualificationBindingError("batch_type_invalid")
        capture = batch.capture
        if capture.body_completed_at is None:
            raise MonthlyRevenueQualificationBindingError("batch_capture_clock_missing")
        market = loaded.binding["market"]
        source_id = loaded.binding["source_id"]
        endpoint = loaded.binding["endpoint_url"]
        if (
            capture.market != market
            or capture.source_id != source_id
            or capture.requested_url != endpoint
            or capture.response_url != endpoint
            or capture.response_status != 200
            or capture.raw_response_sha256 != loaded.binding["raw_batch_sha256"]
            or _datetime_text(capture.body_completed_at)
            != loaded.binding["captured_at"]
            or _datetime_text(batch.successful_batch_completed_at)
            != loaded.binding["successful_batch_completed_at"]
            or _datetime_text(batch.available_hour) != loaded.binding["available_at"]
        ):
            raise MonthlyRevenueQualificationBindingError("batch_binding_identity_mismatch")
        raw_capture_documents = tuple(
            document
            for document in loaded.supporting_documents
            if document.kind == "raw_capture"
        )
        if (
            len(raw_capture_documents) != 1
            or raw_capture_documents[0].raw_bytes != capture.raw_response_bytes
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_raw_capture_bytes_do_not_match_batch"
            )
        try:
            capture.verify_transport()
            rebuilt = prepare_openapi_monthly_revenue_batch(
                capture=capture,
                successful_batch_completed_at=batch.successful_batch_completed_at,
                unit_proof=loaded.unit_proof,
                trusted_unit_proof_sha256=(
                    loaded.unit_proof.proof_sha256
                    if loaded.unit_proof is not None
                    else None
                ),
            )
        except (OpenApiMonthlyRevenueError, TypeError, ValueError) as exc:
            raise MonthlyRevenueQualificationBindingError(
                "batch_reparse_or_profile_rejected"
            ) from exc
        if (
            (batch.unit_proof_sha256 is None) != (loaded.unit_proof is None)
            or (
                loaded.unit_proof is not None
                and batch.unit_proof_sha256 != loaded.unit_proof.proof_sha256
            )
            or _canonical_json_bytes(rebuilt.to_dict())
            != _canonical_json_bytes(batch.to_dict())
        ):
            raise MonthlyRevenueQualificationBindingError(
                "batch_normalized_identity_mismatch"
            )


def _read_document(root: Path, value: object) -> tuple[_Document, bytes]:
    if type(value) is not dict or set(value) != {"id", "kind", "path", "sha256"}:
        raise MonthlyRevenueQualificationBindingError("binding_document_schema_invalid")
    evidence_id = _require_text(value["id"], "binding_document_id_invalid")
    kind = _require_text(value["kind"], "binding_document_kind_invalid")
    if kind not in {"license", "quality", "pit", "unit"}:
        raise MonthlyRevenueQualificationBindingError("binding_document_kind_unsupported")
    relative_path = _require_text(value["path"], "binding_document_path_invalid")
    digest = _require_sha256(value["sha256"], "binding_document_sha256_invalid")
    path = _resolve_relative_path(root, relative_path)
    payload, _ = _read_absolute_regular_file(
        path,
        MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_MAX_BYTES,
        error_prefix="binding_document",
        expected_root=root,
    )
    if hashlib.sha256(payload).hexdigest() != digest:
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_external_sha256_mismatch"
        )
    parsed: Mapping[str, object] | None = None
    if kind != "unit":
        decoded = _decode_canonical_json(payload, "qualification_document")
        if type(decoded) is not dict:
            raise MonthlyRevenueQualificationBindingError(
                "binding_document_payload_invalid"
            )
        parsed = decoded
    return (
        _Document(
            evidence_id=evidence_id,
            kind=kind,
            relative_path=relative_path,
            sha256=digest,
            payload=parsed,
            raw_bytes=payload,
        ),
        payload,
    )


def _read_supporting_document(
    root: Path, value: object
) -> tuple[_SupportingDocument, bytes]:
    """只確認旁證原件位置與SHA，不解讀法律或品質結論的語義。"""
    if type(value) is not dict or set(value) != {
        "id", "kind", "url", "path", "sha256"
    }:
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_schema_invalid"
        )
    evidence_id = _require_text(
        value["id"], "binding_supporting_document_id_invalid"
    )
    kind = _require_text(
        value["kind"], "binding_supporting_document_kind_invalid"
    )
    if kind not in {
        "official_dataset", "official_license", "official_schema", "quality_qa",
        "raw_capture",
    }:
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_kind_unsupported"
        )
    url = _require_text(value["url"], "binding_supporting_document_url_invalid")
    relative_path = _require_text(
        value["path"], "binding_supporting_document_path_invalid"
    )
    digest = _require_sha256(
        value["sha256"], "binding_supporting_document_sha256_invalid"
    )
    path = _resolve_relative_path(root, relative_path)
    payload, _ = _read_absolute_regular_file(
        path,
        MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_MAX_BYTES,
        error_prefix="binding_supporting_document",
        expected_root=root,
    )
    if hashlib.sha256(payload).hexdigest() != digest:
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_external_sha256_mismatch"
        )
    return (
        _SupportingDocument(
            evidence_id=evidence_id,
            kind=kind,
            url=url,
            relative_path=relative_path,
            sha256=digest,
            raw_bytes=payload,
        ),
        payload,
    )


def _validate_supporting_document_set(
    documents: list[_SupportingDocument],
    *,
    market: str,
    endpoint: str,
    raw_batch_sha256: object,
) -> None:
    by_kind = {document.kind: document for document in documents}
    required = {"official_dataset", "official_license", "raw_capture"}
    if not required.issubset(by_kind):
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_required_reference_missing"
        )
    dataset_id = {
        "twse": OPENAPI_MONTHLY_REVENUE_DATASET_IDS["twse"],
        "tpex": OPENAPI_MONTHLY_REVENUE_DATASET_IDS["tpex"],
    }.get(market)
    swagger_url = {
        "twse": "https://openapi.twse.com.tw/v1/swagger.json",
        "tpex": "https://www.tpex.org.tw/openapi/swagger.json",
    }.get(market)
    if dataset_id is None or swagger_url is None:
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_market_invalid"
        )
    expected_urls = {
        "official_dataset": f"https://data.gov.tw/dataset/{dataset_id}",
        "official_license": "https://data.gov.tw/license",
        "raw_capture": endpoint,
    }
    for kind, expected_url in expected_urls.items():
        if by_kind[kind].url != expected_url:
            raise MonthlyRevenueQualificationBindingError(
                f"binding_supporting_document_{kind}_url_mismatch"
            )
    schema_document = by_kind.get("official_schema")
    if schema_document is not None and schema_document.url != swagger_url:
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_official_schema_url_mismatch"
        )
    quality_documents = tuple(
        document for document in documents if document.kind == "quality_qa"
    )
    if any(
        not document.url.startswith("evidence://")
        or len(document.url) <= len("evidence://")
        or "://" in document.url[len("evidence://"):]
        for document in quality_documents
    ):
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_quality_qa_url_invalid"
        )
    raw_capture = by_kind["raw_capture"]
    expected_raw_sha256 = _require_sha256(
        raw_batch_sha256, "binding_raw_batch_sha256_invalid"
    )
    if raw_capture.sha256 != expected_raw_sha256:
        raise MonthlyRevenueQualificationBindingError(
            "binding_supporting_document_raw_capture_sha256_mismatch"
        )


def _validate_document_sets(
    decision: SourceAcceptanceDecisionRevision,
    documents: list[_Document],
) -> None:
    for kind, referenced in (
        ("license", decision.license_evidence_ids),
        ("quality", decision.quality_evidence_ids),
        ("pit", decision.pit_evidence_ids),
    ):
        found = tuple(sorted(item.evidence_id for item in documents if item.kind == kind))
        if not referenced or found != tuple(sorted(referenced)):
            raise MonthlyRevenueQualificationBindingError(
                f"binding_{kind}_evidence_reference_mismatch"
            )


def _validate_qualification_document(
    document: _Document,
    binding: Mapping[str, object],
    decision: SourceAcceptanceDecisionRevision,
) -> None:
    payload = document.payload
    if payload is None:
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_payload_missing"
        )
    common = {
        "schema_version",
        "evidence_id",
        "kind",
        "source_id",
        "market",
        "endpoint_url",
        "batch_sha256",
        "captured_at",
        "available_at",
        "decision_revision_id",
    }
    extras: dict[str, set[str]] = {
        "license": {"status", "license_scope", "attribution_required"},
        "quality": {
            "status", "row_count", "parser_version", "source_schema_version"
        },
        "pit": {
            "status", "availability_basis", "official_pit_eligible",
            "official_announcement_at", "reason",
        },
    }
    if set(payload) != common | extras[document.kind]:
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_payload_fields_invalid"
        )
    if (
        payload["schema_version"] != MONTHLY_REVENUE_QUALIFICATION_DOCUMENT_SCHEMA_V1
        or payload["evidence_id"] != document.evidence_id
        or payload["kind"] != document.kind
        or payload["source_id"] != binding["source_id"]
        or payload["market"] != binding["market"]
        or payload["endpoint_url"] != binding["endpoint_url"]
        or payload["batch_sha256"] != binding["raw_batch_sha256"]
        or payload["captured_at"] != binding["captured_at"]
        or payload["available_at"] != binding["available_at"]
        or payload["decision_revision_id"] != decision.decision_revision_id
    ):
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_identity_mismatch"
        )
    if document.kind == "license":
        if (
            payload["status"] != "verified"
            or payload["license_scope"] != "research_shadow"
            or payload["attribution_required"] is not True
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_license_evidence_invalid"
            )
    elif document.kind == "quality":
        row_count = payload["row_count"]
        if (
            payload["status"] != "passed"
            or type(row_count) is not int
            or row_count <= 0
            or payload["parser_version"] != binding["parser_version"]
            or payload["source_schema_version"] != binding["source_schema_version"]
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_quality_evidence_invalid"
            )
    elif document.kind == "pit":
        if (
            payload["status"] != "not_established"
            or payload["availability_basis"] != _CAPTURED_AVAILABILITY_BASIS
            or payload["official_pit_eligible"] is not False
            or payload["official_announcement_at"] is not None
            or payload["reason"] != "official_pit_not_established"
        ):
            raise MonthlyRevenueQualificationBindingError(
                "binding_pit_limitation_evidence_invalid"
            )


def _project_evidence(loaded: _LoadedBinding) -> MonthlyRevenueQualificationEvidence:
    decision = loaded.decision
    if (
        decision.status != "limited"
        or decision.allowed_use_cases != ("research_shadow",)
    ):
        raise MonthlyRevenueQualificationBindingError(
            "binding_decision_not_limited_research_shadow"
        )
    licenses = tuple(item for item in loaded.documents if item.kind == "license")
    if not licenses:
        raise MonthlyRevenueQualificationBindingError(
            "binding_license_evidence_missing"
        )
    license_ref = ";".join(
        f"{item.evidence_id}@{item.sha256}" for item in sorted(licenses, key=lambda x: x.evidence_id)
    )
    return MonthlyRevenueQualificationEvidence(
        source_id=str(loaded.binding["source_id"]),
        endpoint_url=str(loaded.binding["endpoint_url"]),
        batch_sha256=str(loaded.binding["raw_batch_sha256"]),
        available_at=_parse_iso_datetime(
            loaded.binding["available_at"], "binding_available_at"
        ),
        license_evidence_ref=license_ref,
        unit_proof_sha256=(
            loaded.unit_proof.proof_sha256 if loaded.unit_proof is not None else None
        ),
        source_accepted_uses=_RESEARCH_SHADOW_USES,
        acceptance_evidence_ref=decision.content_hash,
        official_pit_evidence_ref="",
        downstream_evidence_refs=(),
        source_available_at=None,
        captured_at=_parse_iso_datetime(
            loaded.binding["captured_at"], "binding_captured_at"
        ),
        availability_basis="captured_observation",
    )


def _batch_identity_fingerprint(binding: Mapping[str, object]) -> str:
    fields = (
        "source_id",
        "market",
        "endpoint_url",
        "parser_version",
        "source_schema_version",
        "raw_batch_sha256",
        "captured_at",
        "successful_batch_completed_at",
        "available_at",
        "availability_basis",
    )
    identity = {key: binding[key] for key in fields}
    return hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


def _resolve_relative_path(root: Path, relative_path: str) -> Path:
    if (
        "\\" in relative_path
        or ":" in relative_path
        or PurePosixPath(relative_path).is_absolute()
        or PureWindowsPath(relative_path).is_absolute()
        or PureWindowsPath(relative_path).drive != ""
        or not PurePosixPath(relative_path).parts
        or any(part in {"", ".", ".."} for part in PurePosixPath(relative_path).parts)
    ):
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_path_must_be_safe_relative"
        )
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_missing"
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MonthlyRevenueQualificationBindingError(
            "binding_document_path_escapes_root"
        ) from exc
    _reject_links_and_reparse_points(candidate, include_parents_until=root)
    return candidate


def _read_absolute_regular_file(
    path: Path,
    max_bytes: int,
    *,
    error_prefix: str,
    expected_root: Path | None = None,
) -> tuple[bytes, Path]:
    if not path.is_absolute():
        raise MonthlyRevenueQualificationBindingError(f"{error_prefix}_path_must_be_absolute")
    try:
        _reject_links_and_reparse_points(path)
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > max_bytes
            or before.st_nlink != 1
        ):
            raise MonthlyRevenueQualificationBindingError(
                f"{error_prefix}_file_type_or_size_invalid"
            )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > max_bytes
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise MonthlyRevenueQualificationBindingError(
                    f"{error_prefix}_file_changed_during_open"
                )
            payload = stream.read(max_bytes + 1)
    except MonthlyRevenueQualificationBindingError:
        raise
    except OSError as exc:
        raise MonthlyRevenueQualificationBindingError(
            f"{error_prefix}_unreadable"
        ) from exc
    if len(payload) > max_bytes:
        raise MonthlyRevenueQualificationBindingError(
            f"{error_prefix}_file_type_or_size_invalid"
        )
    root = expected_root if expected_root is not None else path.parent.resolve(strict=True)
    return payload, root


def _reject_links_and_reparse_points(
    path: Path,
    *,
    include_parents_until: Path | None = None,
) -> None:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    current = path
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise MonthlyRevenueQualificationBindingError("binding_path_component_missing") from exc
        attributes = getattr(info, "st_file_attributes", 0)
        if current.is_symlink() or attributes & reparse_flag:
            raise MonthlyRevenueQualificationBindingError("binding_path_link_or_reparse_point")
        if include_parents_until is not None and current == include_parents_until:
            break
        if current.parent == current:
            break
        current = current.parent


def _decode_canonical_json(payload: bytes, label: str) -> object:
    try:
        decoded = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise MonthlyRevenueQualificationBindingError(f"{label}_json_invalid") from exc
    if _canonical_json_bytes(decoded) != payload:
        raise MonthlyRevenueQualificationBindingError(f"{label}_json_not_canonical")
    return decoded


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MonthlyRevenueQualificationBindingError("binding_json_duplicate_key")
        result[key] = value
    return result


def _reject_float(_value: str) -> object:
    raise MonthlyRevenueQualificationBindingError("binding_json_float_not_allowed")


def _reject_constant(_value: str) -> object:
    raise MonthlyRevenueQualificationBindingError("binding_json_constant_not_allowed")


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MonthlyRevenueQualificationBindingError("binding_json_not_serializable") from exc


def _parse_iso_datetime(value: object, label: str) -> datetime:
    if type(value) is not str or not value:
        raise MonthlyRevenueQualificationBindingError(f"{label}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MonthlyRevenueQualificationBindingError(f"{label}_invalid") from exc
    return _parse_aware_datetime(parsed, label)


def _parse_aware_datetime(value: object, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise MonthlyRevenueQualificationBindingError(f"{label}_must_be_aware")
    return value.astimezone(timezone.utc)


def _datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise MonthlyRevenueQualificationBindingError(label)
    return value


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise MonthlyRevenueQualificationBindingError(label)
    return value
