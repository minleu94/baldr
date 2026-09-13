"""共用 promotion authority family contract。

Allocation promotion 與 recommendation calibration adapter 使用同一個
machine-authority family 以便追蹤，但 scope 與能力仍分離：只有既有
allocation authority 可以簽署 allocation custody bundle；recommendation
adapter 只發布 shadow pointer/receipt，永遠不授權 order。
"""

from __future__ import annotations

from typing import Any


AUTHORITY_FAMILY = "baldr-ml-promotion-authority-daily"
ALLOCATION_SCOPE = "allocation_promotion"
RECOMMENDATION_SCOPE = "recommendation_calibration_adapter"


def authority_family_contract() -> dict[str, Any]:
    return {
        "authority_family": AUTHORITY_FAMILY,
        "allocation_scope": ALLOCATION_SCOPE,
        "recommendation_scope": RECOMMENDATION_SCOPE,
        "recommendation_formal_order_allowed": False,
        "recommendation_signing_key": "none",
        "allocation_signing_owner": "scripts.run_ml_promotion_authority",
    }
