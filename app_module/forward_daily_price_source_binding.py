"""把同次 Forward fetched rows 綁至明確 publication，來源資格另外判定。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence


PRICE_PROJECTION_COLUMNS = (
    "日期", "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
    "開盤價", "最高價", "最低價", "收盤價", "漲跌", "漲跌價差",
    "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
)
PRICE_DIRECTION_COLUMNS = ("漲跌", "漲跌(+/-)", "涨跌")


def has_full_price_projection(columns: Sequence[str]) -> bool:
    return (
        set(PRICE_PROJECTION_COLUMNS).difference({"漲跌"}).issubset(columns)
        and any(column in columns for column in PRICE_DIRECTION_COLUMNS)
    )


def unknown_price_source_binding(reason: str) -> dict[str, Any]:
    return {
        "status": "unknown", "reason_code": reason,
        "source_use_accepted": False, "source_published_at": None,
        "available_at": None, "pit_eligible": False, "training_eligible": False,
    }


class ForwardDailyPriceSourceBinder:
    """只核已固定來源的完整列；不另開 DB、不依相同收盤價搜尋來源。"""

    def __init__(
        self, *, output_root: Path, data_root: Path, database_path: Path,
        bundle: Mapping[str, Any],
        revision_ledger: Any | None = None,
        qualification_policy: Any | None = None,
        qualification_resolver: Any | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.data_root = Path(data_root)
        self.database_path = Path(database_path)
        self.bundle = deepcopy(dict(bundle))
        self.revision_ledger = revision_ledger
        self.qualification_policy = qualification_policy
        self.qualification_resolver = qualification_resolver
        self._verified_source_cache: dict[tuple[object, ...], object] = {}

    def bind_rows(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        qualification_policy: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        active_policy = (
            qualification_policy
            if qualification_policy is not None
            else self.qualification_policy
        )
        if self.bundle.get("status") != "captured":
            return tuple(unknown_price_source_binding("source_bundle_unavailable") for _ in rows)
        descriptors = self.bundle.get("descriptors")
        if not isinstance(descriptors, Mapping):
            return tuple(unknown_price_source_binding("source_bundle_descriptors_invalid") for _ in rows)
        if not self._database_identity_matches():
            return tuple(unknown_price_source_binding("source_bundle_database_identity_changed") for _ in rows)
        from data_module.twse_daily_price_publication import (
            verify_fetched_daily_price_rows as verify_twse,
        )
        from data_module.tpex_daily_price_publication import (
            verify_fetched_daily_price_rows as verify_tpex,
        )

        candidates: list[list[dict[str, Any]]] = [[] for _ in rows]
        reasons: list[dict[str, str]] = [{} for _ in rows]
        for source_id, verifier in (
            ("twse.mi_index.daily_price", verify_twse),
            ("tpex.daily_close_quotes", verify_tpex),
        ):
            descriptor_list: list[Mapping[str, Any]] = []
            primary_descriptor = descriptors.get(source_id)
            if isinstance(primary_descriptor, Mapping):
                descriptor_list.append(primary_descriptor)
            if self.revision_ledger is not None:
                pub_map = getattr(
                    self.revision_ledger, "_publication_descriptors_by_date", {}
                )
                for (sid, _dkey), extra_descs in sorted(pub_map.items()):
                    if sid != source_id:
                        continue
                    for extra in extra_descs:
                        if isinstance(extra, Mapping) and all(
                            extra.get("sha256") != d.get("sha256")
                            for d in descriptor_list
                        ):
                            descriptor_list.append(extra)
            for descriptor in descriptor_list:
                try:
                    verified = verifier(
                        output_root=self.output_root, data_root=self.data_root,
                        database_path=self.database_path, descriptor=descriptor,
                        fetched_rows=rows,
                        verified_source_cache=self._verified_source_cache,
                    )
                    if len(verified) != len(rows):
                        raise ValueError("source_verifier_row_count_mismatch")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    for row_reasons in reasons:
                        row_reasons[source_id] = f"source_verifier_failed:{type(exc).__name__}"
                    continue
                for index, result in enumerate(verified):
                    if not isinstance(result, Mapping):
                        reasons[index][source_id] = "source_verifier_result_invalid"
                        continue
                    if result.get("status") != "source_identity_bound":
                        if source_id not in reasons[index]:
                            reasons[index][source_id] = str(result.get("reason_code") or "source_row_not_bound")[:240]
                        continue
                    if (
                        result.get("source_id") != source_id
                        or result.get("source_published_at") is not None
                        or result.get("available_at") is not None
                        or result.get("source_use_accepted") is not False
                        or result.get("pit_eligible") is not False
                        or result.get("training_eligible") is not False
                    ):
                        reasons[index][source_id] = "source_verifier_qualification_contract_invalid"
                        continue
                    if not any(
                        existing.get("source_id") == source_id
                        and existing.get("publication_sha256") == result.get("publication_sha256")
                        for existing in candidates[index]
                    ):
                        candidates[index].append(dict(result))
        results = []
        if not self._database_identity_matches():
            return tuple(unknown_price_source_binding("source_bundle_database_identity_changed") for _ in rows)
        ledger = self.revision_ledger
        if active_policy is not None and self.qualification_resolver is None:
            return tuple(
                unknown_price_source_binding("qualification_trust_root_missing")
                for _ in rows
            )
        if active_policy is not None and ledger is None:
            from data_module.daily_price_qualification_binding import (
                DailyPriceRevisionLedger,
            )

            ledger = DailyPriceRevisionLedger(
                output_root=self.output_root, data_root=self.data_root
            )
            for source_id, desc in descriptors.items():
                if isinstance(desc, Mapping) and isinstance(desc.get("relative_path"), str):
                    ledger.register_publication(
                        source_id=source_id,
                        relative_path=str(desc["relative_path"]),
                        expected_sha256=(
                            str(desc["sha256"]) if isinstance(desc.get("sha256"), str) else None
                        ),
                    )
        for index, matches in enumerate(candidates):
            if len(matches) > 1:
                distinct_sources = {item.get("source_id") for item in matches}
                if len(distinct_sources) == 1:
                    selected_source_id = next(iter(distinct_sources))
                    same_full_row = len(
                        {
                            (
                                item.get("source_date"),
                                item.get("stock_code"),
                                item.get("parser_id"),
                                item.get("projection_row_sha256"),
                                item.get("sqlite_projection_row_sha256"),
                            )
                            for item in matches
                        }
                    ) == 1
                    primary_descriptor = (
                        descriptors.get(selected_source_id)
                        if isinstance(selected_source_id, str) else None
                    )
                    if same_full_row and isinstance(primary_descriptor, Mapping):
                        primary_path = primary_descriptor.get("relative_path")
                        primary_sha = primary_descriptor.get("sha256")
                        selected = [
                            item
                            for item in matches
                            if item.get("publication_relative_path") == primary_path
                            and item.get("publication_sha256") == primary_sha
                        ]
                        if len(selected) == 1:
                            candidates[index] = matches = selected

            if len(matches) == 1:
                result = matches[0]
                result["source_bundle_reference"] = deepcopy(self.bundle.get("reference"))
                if active_policy is not None and ledger is not None:
                    from data_module.daily_price_qualification_binding import (
                        evaluate_bound_daily_price_row_qualification,
                    )

                    result = evaluate_bound_daily_price_row_qualification(
                        bound_row=result,
                        revision_ledger=ledger,
                        policy=active_policy,
                    )
                    from data_module.daily_price_qualification_binding import (
                        verify_qualified_binding_payload,
                    )

                    if result.get("source_use_accepted") is True and not verify_qualified_binding_payload(
                        result,
                        resolver=self.qualification_resolver,
                        policy=active_policy,
                        revision_ledger=ledger,
                    ):
                        result = unknown_price_source_binding(
                            "qualification_revalidation_failed"
                        )
            else:
                reason_code = "ambiguous_source_identity" if matches else "no_verified_source_identity"
                if len(matches) > 1:
                    distinct_sources = {m.get("source_id") for m in matches}
                    if len(distinct_sources) > 1:
                        reason_code = "dual_source_ambiguity"
                    else:
                        reason_code = "same_key_revision_conflict"
                result = unknown_price_source_binding(reason_code)
                if reasons[index]:
                    result["source_reasons"] = reasons[index]
            results.append(result)
        return tuple(results)

    def _database_identity_matches(self) -> bool:
        body = self.bundle.get("bundle")
        expected = body.get("database_identity") if isinstance(body, Mapping) else None
        if not isinstance(expected, Mapping):
            return False
        try:
            info = self.database_path.lstat()
            return (
                stat.S_ISREG(info.st_mode)
                and not self.database_path.is_symlink()
                and not (getattr(info, "st_file_attributes", 0) & 0x400)
                and self.database_path.resolve(strict=True).is_relative_to(self.data_root.resolve(strict=True))
                and expected == {"device": info.st_dev, "inode": info.st_ino}
            )
        except (OSError, ValueError, RuntimeError):
            return False


__all__ = ["ForwardDailyPriceSourceBinder", "PRICE_PROJECTION_COLUMNS", "unknown_price_source_binding"]
