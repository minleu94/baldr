"""Quick 執行同輪 TWSE／TPEx 行情來源收據的有界索引。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Mapping

from data_module.ml_research_output_boundary import (
    _read_bounded_regular_file_no_follow,
    _reject_json_constant,
    _unique_json_object,
)


BUNDLE_SCHEMA = "daily-price-source-bundle.v1"
LOCATOR_SCHEMA = "daily-price-source-bundle-locator.v1"
MAX_BUNDLE_BYTES = 512 * 1024
MAX_LOCATOR_BYTES = 16 * 1024
MAX_PUBLICATION_BYTES = 32 * 1024 * 1024
_SHA_RE = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_RUN_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,160}\Z")
_SOURCE_FAMILIES = {
    "twse.mi_index.daily_price": "twse-daily-price-sqlite-publication.v1",
    "tpex.daily_close_quotes": "tpex-daily-price-sqlite-publication.v1",
}
_PUBLICATION_DIRECTORIES = {
    "twse.mi_index.daily_price": "twse_daily_price_sqlite_publication",
    "tpex.daily_close_quotes": "tpex_daily_price_sqlite_publication",
}
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class DailyPriceSourceBundleError(ValueError):
    """Quick 行情來源 bundle 不符合固定 schema 或檔案邊界。"""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_json(raw: bytes) -> object:
    return json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )


def _aware_utc(value: object) -> str:
    if not isinstance(value, str):
        raise DailyPriceSourceBundleError("completed_at_invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DailyPriceSourceBundleError("completed_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DailyPriceSourceBundleError("completed_at_timezone_missing")
    return parsed.astimezone(timezone.utc).isoformat()


def _run_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not _RUN_ID_RE.fullmatch(value)
        or value in {".", ".."}
    ):
        raise DailyPriceSourceBundleError("quick_run_id_invalid")
    return value


def _root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise DailyPriceSourceBundleError("root_must_be_absolute")
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DailyPriceSourceBundleError("root_unavailable") from exc


def _reject_reparse_components(path: Path, root: Path) -> None:
    """拒絕授權根以下的連結元件，根本身以呼叫端解析後路徑為準。"""
    absolute = path.absolute()
    try:
        absolute.relative_to(root)
    except ValueError as exc:
        raise DailyPriceSourceBundleError("path_outside_root") from exc
    current = absolute
    while current != root:
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise DailyPriceSourceBundleError("path_component_unavailable") from exc
        if current.is_symlink() or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT:
            raise DailyPriceSourceBundleError("path_reparse_component")
        current = current.parent


def _ensure_plain_directory_tree(path: Path, root: Path) -> None:
    """逐層建立並檢查目錄，避免 mkdir(parents=True) 穿越連結。"""
    absolute = path.absolute()
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise DailyPriceSourceBundleError("path_outside_root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise DailyPriceSourceBundleError("directory_create_failed") from exc
            try:
                metadata = current.lstat()
            except OSError as exc:
                raise DailyPriceSourceBundleError("path_component_unavailable") from exc
        except OSError as exc:
            raise DailyPriceSourceBundleError("path_component_unavailable") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or current.is_symlink()
            or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
        ):
            raise DailyPriceSourceBundleError("path_reparse_component")


def _relative_file(root: Path, value: object, maximum: int) -> tuple[str, bytes]:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
    ):
        raise DailyPriceSourceBundleError("relative_path_invalid")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise DailyPriceSourceBundleError("relative_path_invalid")
    candidate = root.joinpath(*pure.parts)
    _reject_reparse_components(candidate, root)
    try:
        raw = _read_bounded_regular_file_no_follow(candidate, maximum_bytes=maximum)
    except Exception as exc:
        raise DailyPriceSourceBundleError("file_read_failed") from exc
    return pure.as_posix(), raw


def _database_identity(data_root: Path, database_path: str | Path) -> tuple[str, dict[str, int]]:
    supplied = Path(database_path).expanduser()
    if not supplied.is_absolute():
        raise DailyPriceSourceBundleError("database_path_must_be_absolute")
    database = supplied.absolute()
    try:
        relative = database.relative_to(data_root)
    except ValueError as exc:
        raise DailyPriceSourceBundleError("database_path_outside_data_root") from exc
    _reject_reparse_components(database, data_root)
    try:
        metadata = database.lstat()
    except OSError as exc:
        raise DailyPriceSourceBundleError("database_unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise DailyPriceSourceBundleError("database_identity_invalid")
    return (
        PurePosixPath(*relative.parts).as_posix(),
        {"device": int(metadata.st_dev), "inode": int(metadata.st_ino)},
    )


def _normalize_publication_descriptors(
    descriptors: Mapping[str, object],
) -> list[dict[str, object]]:
    if not isinstance(descriptors, Mapping):
        raise DailyPriceSourceBundleError("descriptors_invalid")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for source_id, descriptor in descriptors.items():
        if source_id not in _SOURCE_FAMILIES or source_id in seen:
            raise DailyPriceSourceBundleError("source_family_unknown_or_duplicate")
        if not isinstance(descriptor, Mapping):
            raise DailyPriceSourceBundleError("publication_descriptor_invalid")
        schema = _SOURCE_FAMILIES[source_id]
        if (
            descriptor.get("status") != "captured"
            or descriptor.get("schema_version") != schema
        ):
            raise DailyPriceSourceBundleError("publication_descriptor_not_captured")
        relative = descriptor.get("relative_path")
        path = PurePosixPath(relative) if isinstance(relative, str) else None
        digest = descriptor.get("sha256")
        rows = descriptor.get("row_count")
        if (
            path is None
            or path.is_absolute()
            or "\\" in str(relative)
            or any(part in {"", ".", ".."} for part in path.parts)
            or not isinstance(digest, str)
            or not _SHA_RE.fullmatch(digest)
            or isinstance(rows, bool)
            or not isinstance(rows, int)
            or rows < 1
        ):
            raise DailyPriceSourceBundleError("publication_descriptor_identity_invalid")
        digest_hex = digest.removeprefix("sha256:")
        expected_path = PurePosixPath(
            "scheduled", _PUBLICATION_DIRECTORIES[source_id], digest_hex[:2],
            f"{digest_hex}.json",
        )
        if path != expected_path or path.as_posix() != relative:
            raise DailyPriceSourceBundleError("publication_descriptor_path_mismatch")
        seen.add(source_id)
        normalized.append(
            {
                "source_id": source_id,
                "schema_version": schema,
                "relative_path": path.as_posix(),
                "sha256": digest,
                "row_count": rows,
            }
        )
    if not normalized:
        raise DailyPriceSourceBundleError("publication_descriptors_missing")
    return sorted(normalized, key=lambda item: str(item["source_id"]))


def _write_atomic_locator(path: Path, raw: bytes, root: Path) -> None:
    if len(raw) > MAX_LOCATOR_BYTES:
        raise DailyPriceSourceBundleError("locator_exceeds_size_limit")
    _ensure_plain_directory_tree(path.parent, root)
    if path.exists() or path.is_symlink():
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise DailyPriceSourceBundleError("locator_unavailable") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
        ):
            raise DailyPriceSourceBundleError("locator_identity_invalid")
    temporary = path.with_name(f".{os.getpid()}.{os.urandom(8).hex()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _reject_reparse_components(path.parent, root)
        os.replace(temporary, path)
        observed = _read_bounded_regular_file_no_follow(path, maximum_bytes=MAX_LOCATOR_BYTES)
        if observed != raw:
            raise DailyPriceSourceBundleError("locator_readback_mismatch")
    except DailyPriceSourceBundleError:
        raise
    except OSError as exc:
        raise DailyPriceSourceBundleError("locator_publish_failed") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def publish_daily_price_source_bundle(
    *,
    output_root: str | Path,
    data_root: str | Path,
    database_path: str | Path,
    quick_run_id: str,
    completed_at: str,
    quick_status: str,
    descriptors: Mapping[str, object],
) -> dict[str, object]:
    """以 Quick 本輪實際 captured publication descriptor 建立唯讀 bundle。"""
    output = _root(output_root)
    data = _root(data_root)
    run_id = _run_id(quick_run_id)
    completed = _aware_utc(completed_at)
    if quick_status not in {"passed", "passed_with_warnings", "failed"}:
        raise DailyPriceSourceBundleError("quick_status_invalid")
    database_relative, database_identity = _database_identity(data, database_path)
    publications = _normalize_publication_descriptors(descriptors)
    for publication in publications:
        _, publication_raw = _relative_file(
            output, publication["relative_path"], MAX_PUBLICATION_BYTES
        )
        publication_payload = _strict_json(
            publication_raw[:-1] if publication_raw.endswith(b"\n") else publication_raw
        )
        if (
            type(publication_payload) is not dict
            or _canonical(publication_payload) + b"\n" != publication_raw
        ):
            raise DailyPriceSourceBundleError("publication_json_invalid")
        publication_body = {
            key: value
            for key, value in publication_payload.items()
            if key != "content_sha256"
        }
        source_id = str(publication["source_id"])
        if (
            _sha(publication_raw) != publication["sha256"]
            or publication_payload.get("schema_version") != publication["schema_version"]
            or publication_payload.get("source_id") != source_id
            or publication_payload.get("database_relative_path") != database_relative
            or publication_payload.get("content_sha256") != _sha(_canonical(publication_body))
            or not isinstance(publication_payload.get("rows"), list)
            or len(publication_payload["rows"]) != publication["row_count"]
        ):
            raise DailyPriceSourceBundleError("publication_descriptor_pin_mismatch")
        if source_id == "tpex.daily_close_quotes" and any(
            publication_payload.get(field) is not False
            for field in (
                "formal_source_contract_eligible", "pit_eligible", "training_eligible"
            )
        ):
            raise DailyPriceSourceBundleError("publication_qualification_invalid")
    body: dict[str, object] = {
        "schema_version": BUNDLE_SCHEMA,
        "quick_run_id": run_id,
        "quick_status": quick_status,
        "natural_success": False,
        "quick_execution_passed": quick_status in {"passed", "passed_with_warnings"},
        "completed_at": completed,
        "database_relative_path": database_relative,
        "database_identity": database_identity,
        "publications": publications,
        "formal_source_contract_eligible": False,
        "pit_eligible": False,
        "training_eligible": False,
    }
    payload = _canonical(body) + b"\n"
    if len(payload) > MAX_BUNDLE_BYTES:
        raise DailyPriceSourceBundleError("bundle_exceeds_size_limit")
    digest = _sha(payload)
    relative_path = PurePosixPath(
        "scheduled", "daily_price_source_bundles", "runs", run_id,
        f"{digest.removeprefix('sha256:')}.json",
    ).as_posix()
    target = output.joinpath(*PurePosixPath(relative_path).parts)
    _ensure_plain_directory_tree(target.parent, output)
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        existing = _read_bounded_regular_file_no_follow(
            target, maximum_bytes=MAX_BUNDLE_BYTES
        )
        if existing != payload:
            raise DailyPriceSourceBundleError("immutable_bundle_conflict")
    except OSError as exc:
        raise DailyPriceSourceBundleError("bundle_create_failed") from exc
    observed = _read_bounded_regular_file_no_follow(target, maximum_bytes=MAX_BUNDLE_BYTES)
    if observed != payload:
        raise DailyPriceSourceBundleError("bundle_readback_mismatch")
    locator_body = {
        "schema_version": LOCATOR_SCHEMA,
        "quick_run_id": run_id,
        "relative_path": relative_path,
        "sha256": digest,
    }
    locator_payload = _canonical(
        {**locator_body, "content_sha256": _sha(_canonical(locator_body))}
    ) + b"\n"
    _write_atomic_locator(
        output / "scheduled" / "daily_price_source_bundles" / "latest.json",
        locator_payload,
        output,
    )
    return {
        "status": "captured",
        "schema_version": BUNDLE_SCHEMA,
        "quick_run_id": run_id,
        "reference": {"relative_path": relative_path, "sha256": digest},
    }


def load_daily_price_source_bundle(
    *,
    output_root: str | Path,
    data_root: str | Path,
    database_path: str | Path,
    descriptor: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """依外部 descriptor 或最新 locator 指向的精確 bundle 讀回。"""
    try:
        output = _root(output_root)
        data = _root(data_root)
        database_relative, database_identity = _database_identity(data, database_path)
        if descriptor is None:
            locator_path = output / "scheduled" / "daily_price_source_bundles" / "latest.json"
            _reject_reparse_components(locator_path, output)
            locator_raw = _read_bounded_regular_file_no_follow(
                locator_path, maximum_bytes=MAX_LOCATOR_BYTES
            )
            locator = _strict_json(locator_raw)
            if type(locator) is not dict or set(locator) != {
                "schema_version", "quick_run_id", "relative_path", "sha256", "content_sha256"
            } or _canonical(locator) + b"\n" != locator_raw:
                raise DailyPriceSourceBundleError("locator_schema_invalid")
            locator_body = {key: value for key, value in locator.items() if key != "content_sha256"}
            if (
                locator.get("schema_version") != LOCATOR_SCHEMA
                or locator.get("content_sha256") != _sha(_canonical(locator_body))
            ):
                raise DailyPriceSourceBundleError("locator_hash_invalid")
            selected: Mapping[str, object] = {
                "status": "captured",
                "schema_version": BUNDLE_SCHEMA,
                "quick_run_id": locator.get("quick_run_id"),
                "reference": {
                    "relative_path": locator.get("relative_path"),
                    "sha256": locator.get("sha256"),
                },
            }
        else:
            selected = descriptor
        if (
            selected.get("status") != "captured"
            or selected.get("schema_version") != BUNDLE_SCHEMA
        ):
            raise DailyPriceSourceBundleError("bundle_descriptor_unavailable")
        run_id = _run_id(selected.get("quick_run_id"))
        reference = selected.get("reference")
        if type(reference) is not dict or set(reference) != {"relative_path", "sha256"}:
            raise DailyPriceSourceBundleError("bundle_reference_invalid")
        expected_path = (
            PurePosixPath("scheduled", "daily_price_source_bundles", "runs", run_id)
        )
        relative = reference.get("relative_path")
        if not isinstance(relative, str) or "\\" in relative or ":" in relative:
            raise DailyPriceSourceBundleError("bundle_relative_path_invalid")
        supplied = PurePosixPath(relative)
        digest = reference.get("sha256")
        if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
            raise DailyPriceSourceBundleError("bundle_sha_invalid")
        if (
            supplied.parent != expected_path
            or supplied.name != f"{digest.removeprefix('sha256:')}.json"
            or supplied.as_posix() != relative
        ):
            raise DailyPriceSourceBundleError("bundle_path_run_identity_mismatch")
        relative, raw = _relative_file(output, relative, MAX_BUNDLE_BYTES)
        if _sha(raw) != digest:
            raise DailyPriceSourceBundleError("bundle_sha_mismatch")
        payload = _strict_json(raw[:-1] if raw.endswith(b"\n") else raw)
        if type(payload) is not dict or _canonical(payload) + b"\n" != raw:
            raise DailyPriceSourceBundleError("bundle_json_not_canonical")
        if set(payload) != {
            "schema_version", "quick_run_id", "quick_status", "natural_success",
            "quick_execution_passed",
            "completed_at", "database_relative_path", "database_identity",
            "publications", "formal_source_contract_eligible", "pit_eligible",
            "training_eligible",
        }:
            raise DailyPriceSourceBundleError("bundle_schema_invalid")
        if (
            payload.get("schema_version") != BUNDLE_SCHEMA
            or payload.get("quick_run_id") != run_id
            or payload.get("quick_status") not in {"passed", "passed_with_warnings", "failed"}
            or payload.get("natural_success") is not False
            or payload.get("quick_execution_passed") is not (
                payload.get("quick_status") in {"passed", "passed_with_warnings"}
            )
            or _aware_utc(payload.get("completed_at")) != payload.get("completed_at")
            or payload.get("database_relative_path") != database_relative
            or payload.get("formal_source_contract_eligible") is not False
            or payload.get("pit_eligible") is not False
            or payload.get("training_eligible") is not False
        ):
            raise DailyPriceSourceBundleError("bundle_identity_or_scope_mismatch")
        stored_db_identity = payload.get("database_identity")
        if (
            type(stored_db_identity) is not dict
            or set(stored_db_identity) != {"device", "inode"}
            or any(
                isinstance(stored_db_identity.get(field), bool)
                or not isinstance(stored_db_identity.get(field), int)
                for field in ("device", "inode")
            )
            or stored_db_identity != database_identity
        ):
            raise DailyPriceSourceBundleError("bundle_database_identity_mismatch")
        publications = payload.get("publications")
        if type(publications) is not list or not publications:
            raise DailyPriceSourceBundleError("bundle_publications_invalid")
        source_ids: list[str] = []
        descriptors_by_source: dict[str, dict[str, object]] = {}
        for publication in publications:
            if type(publication) is not dict or set(publication) != {
                "source_id", "schema_version", "relative_path", "sha256", "row_count"
            }:
                raise DailyPriceSourceBundleError("bundle_publication_schema_invalid")
            source_id = publication.get("source_id")
            if source_id not in _SOURCE_FAMILIES or publication.get("schema_version") != _SOURCE_FAMILIES[source_id]:
                raise DailyPriceSourceBundleError("bundle_publication_family_invalid")
            source_ids.append(str(source_id))
            publication_path = publication.get("relative_path")
            publication_relative, publication_raw = _relative_file(
                output, publication_path, MAX_PUBLICATION_BYTES
            )
            publication_payload = _strict_json(
                publication_raw[:-1]
                if publication_raw.endswith(b"\n")
                else publication_raw
            )
            if (
                type(publication_payload) is not dict
                or _canonical(publication_payload) + b"\n" != publication_raw
            ):
                raise DailyPriceSourceBundleError("publication_json_invalid")
            publication_body = {
                key: value
                for key, value in publication_payload.items()
                if key != "content_sha256"
            }
            source_id = str(source_id)
            publication_digest = publication.get("sha256")
            if not isinstance(publication_digest, str) or not _SHA_RE.fullmatch(publication_digest):
                raise DailyPriceSourceBundleError("bundle_publication_sha_invalid")
            publication_digest_hex = publication_digest.removeprefix("sha256:")
            expected_publication_path = PurePosixPath(
                "scheduled",
                _PUBLICATION_DIRECTORIES[source_id],
                publication_digest_hex[:2],
                f"{publication_digest_hex}.json",
            ).as_posix()
            if publication_path != expected_publication_path:
                raise DailyPriceSourceBundleError("bundle_publication_path_mismatch")
            if (
                _sha(publication_raw) != publication.get("sha256")
                or isinstance(publication.get("row_count"), bool)
                or not isinstance(publication.get("row_count"), int)
                or publication["row_count"] < 1
                or publication_payload.get("schema_version")
                != _SOURCE_FAMILIES[source_id]
                or publication_payload.get("source_id") != source_id
                or publication_payload.get("database_relative_path")
                != database_relative
                or publication_payload.get("content_sha256")
                != _sha(_canonical(publication_body))
                or not isinstance(publication_payload.get("rows"), list)
                or len(publication_payload["rows"]) != publication["row_count"]
            ):
                raise DailyPriceSourceBundleError("bundle_publication_pin_invalid")
            if source_id == "tpex.daily_close_quotes" and any(
                publication_payload.get(field) is not False
                for field in (
                    "formal_source_contract_eligible", "pit_eligible", "training_eligible"
                )
            ):
                raise DailyPriceSourceBundleError("bundle_publication_qualification_invalid")
            descriptors_by_source[source_id] = {
                "status": "captured",
                "schema_version": _SOURCE_FAMILIES[source_id],
                "relative_path": publication_relative,
                "sha256": publication["sha256"],
                "row_count": publication["row_count"],
            }
        if len(source_ids) != len(set(source_ids)):
            raise DailyPriceSourceBundleError("bundle_source_family_duplicate")
        final_database_relative, final_database_identity = _database_identity(
            data, database_path
        )
        if (
            final_database_relative != database_relative
            or final_database_identity != database_identity
        ):
            raise DailyPriceSourceBundleError("database_identity_changed_during_bundle_read")
        return {
            "status": "captured",
            "schema_version": BUNDLE_SCHEMA,
            "reference": {"relative_path": relative, "sha256": digest},
            "descriptors": descriptors_by_source,
            "bundle": payload,
            "source_use_accepted": False,
            "source_published_at": None,
            "available_at": None,
            "pit_eligible": False,
            "training_eligible": False,
        }
    except Exception as exc:
        return {
            "status": "unknown",
            "reason_code": (
                str(exc) if isinstance(exc, DailyPriceSourceBundleError)
                else f"bundle_read_failed:{type(exc).__name__}"
            ),
            "source_use_accepted": False,
            "source_published_at": None,
            "available_at": None,
            "pit_eligible": False,
            "training_eligible": False,
        }


__all__ = [
    "BUNDLE_SCHEMA",
    "DailyPriceSourceBundleError",
    "load_daily_price_source_bundle",
    "publish_daily_price_source_bundle",
]
