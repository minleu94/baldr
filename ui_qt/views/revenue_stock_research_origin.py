"""營收研究列的短期、唯讀個股研究來源身份。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


def _sha256_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class RevenueStockResearchOrigin:
    """只攜帶已核驗營收結果列的身份，不攜帶行情或營收 facts。"""

    stock_code: str
    source_identity_sha256: str
    recipe_identity_sha256: str
    query_identity_sha256: str
    page_identity_sha256: str
    request_identity_sha256: str
    row_identity_sha256: str
    page_index: int
    origin_sha256: str

    @staticmethod
    def _identity_payload(
        *,
        stock_code: str,
        source_identity_sha256: str,
        recipe_identity_sha256: str,
        query_identity_sha256: str,
        page_identity_sha256: str,
        request_identity_sha256: str,
        row_identity_sha256: str,
        page_index: int,
    ) -> dict[str, object]:
        return {
            "schema": "revenue-stock-research-origin.v1",
            "stock_code": stock_code,
            "source_identity_sha256": source_identity_sha256,
            "recipe_identity_sha256": recipe_identity_sha256,
            "query_identity_sha256": query_identity_sha256,
            "page_identity_sha256": page_identity_sha256,
            "request_identity_sha256": request_identity_sha256,
            "row_identity_sha256": row_identity_sha256,
            "page_index": page_index,
        }

    @classmethod
    def create(
        cls,
        *,
        stock_code: str,
        source_identity_sha256: str,
        recipe_identity_sha256: str,
        query_identity_sha256: str,
        page_identity_sha256: str,
        request_identity_sha256: str,
        row_identity_sha256: str,
        page_index: int,
    ) -> RevenueStockResearchOrigin:
        values = cls._identity_payload(
            stock_code=stock_code,
            source_identity_sha256=source_identity_sha256,
            recipe_identity_sha256=recipe_identity_sha256,
            query_identity_sha256=query_identity_sha256,
            page_identity_sha256=page_identity_sha256,
            request_identity_sha256=request_identity_sha256,
            row_identity_sha256=row_identity_sha256,
            page_index=page_index,
        )
        return cls(
            stock_code=stock_code,
            source_identity_sha256=source_identity_sha256,
            recipe_identity_sha256=recipe_identity_sha256,
            query_identity_sha256=query_identity_sha256,
            page_identity_sha256=page_identity_sha256,
            request_identity_sha256=request_identity_sha256,
            row_identity_sha256=row_identity_sha256,
            page_index=page_index,
            origin_sha256=_sha256_payload(values),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.stock_code, str) or not self.stock_code.strip():
            raise ValueError("revenue_stock_origin_stock_code_invalid")
        if type(self.page_index) is not int or self.page_index < 0:
            raise ValueError("revenue_stock_origin_page_index_invalid")
        for name in (
            "source_identity_sha256",
            "recipe_identity_sha256",
            "query_identity_sha256",
            "page_identity_sha256",
            "request_identity_sha256",
            "row_identity_sha256",
            "origin_sha256",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise ValueError(f"revenue_stock_origin_{name}_invalid")
        expected = _sha256_payload(
            self._identity_payload(
                stock_code=self.stock_code,
                source_identity_sha256=self.source_identity_sha256,
                recipe_identity_sha256=self.recipe_identity_sha256,
                query_identity_sha256=self.query_identity_sha256,
                page_identity_sha256=self.page_identity_sha256,
                request_identity_sha256=self.request_identity_sha256,
                row_identity_sha256=self.row_identity_sha256,
                page_index=self.page_index,
            )
        )
        if expected != self.origin_sha256:
            raise ValueError("revenue_stock_origin_identity_mismatch")


__all__ = ["RevenueStockResearchOrigin"]
