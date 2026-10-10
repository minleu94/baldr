# 策略說明文件目錄

> **最後整理**：2026-10-09
> **定位**：本目錄保存給使用者與開發者閱讀的策略說明。策略程式碼、版本註冊與執行邏輯不放在這裡。

## 文件列表

| 文件 | 用途 |
|---|---|
| `momentum_aggressive_v1.md` | 暴衝策略的目的、適用情境與風險說明。 |
| `stable_conservative_v1.md` | 穩健策略的目的、適用情境與風險說明。 |

本目錄只列使用者面向的策略說明，不是 registry 全量清單。`baseline_score_threshold` 雖列於 registry，但其 executor 明確定位為回歸測試基準，因此不作為使用者策略文件列入此表。

## 維護規則

- 新增策略說明時更新本 README；只有主要導航入口或權威邊界改變時，才同步更新 `../00_core/DOCUMENTATION_INDEX.md`。
- 策略實作與唯一 registry 狀態以 `decision_module/strategies/` 為準；舊 `app_module/` strategy imports 僅由 `TMP-STR-01` 薄 facade 暫時相容，退休條件見 [`FINAL_MIGRATION_SEQUENCE.md`](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)。策略語意仍以 [`STRATEGY_DESIGN_SPECIFICATION.md`](../02_features/STRATEGY_DESIGN_SPECIFICATION.md) 為準。
- 策略說明不得宣稱投資績效或保證收益；若提及驗證結果，必須連到對應 QA 或 Research Run evidence。
- Registry `risk_level` 是 metadata 描述，不等同實證風險分數；預期收益、回撤、交易頻率、資金權重與停損／停利必須由固定版本設定及對應研究證據支持，不能由策略名稱推定。

## 更新記錄

- 2026-10-10：將新增策略說明的導覽責任改為更新本領域 README；中央 Index 僅在主要入口或權威邊界變更時同步。
