# R006 Luna 回修之 SOL 審查

> 本文是 R006 前一輪 `CHANGES_REQUIRED` 審查與回修指示的歷史記錄；後續接受結果見 [R006 SOL 整合驗收](R006_SOL_INTEGRATION_REVIEW.md)。下文命令及修改指示不構成目前派工授權。

## 判定

R006 已把先前過度宣稱改為分層證據，且 15/15 Direct source raw bytes/size/SHA-256 已由 SOL 對目前工作樹獨立核對一致；受控 joblib fixture、歷史 20 欄與 OOC dtype/field order 有新增測試。但 QA 文件仍缺原審查要求的逐項 owner 和 ABI→test 對照，且大段英文敘述及兩處英文程式註解違反 repository 的繁體中文規範。這些均可在 R006 原 scope 修正，不構成 architecture blocker。

## 必須修正的項目

1. `docs/06_qa/REFACTOR_ML_ABI_BASELINE_R006_20260922.md` 的 Direct 15-path 表只有路徑、bytes、SHA；前次 SOL finding 要求每條 path 的 source owner／責任。請補明確 owner 欄或相鄰逐項表；再為 Direct、OOC、SafeShadow、legacy serialized asset 列出 reader／writer authority 與本次只讀範圍。不得把 source 所屬 module 簡稱為已驗證的正式 writer 權限。
2. 同文件缺可直接交 R010/R026/R027 的 `ABI 條款 → 測試／證據` mapping。請將 historical 20 欄、`None→NaN`、imputer/scale、HGB mask、allocation feature order/scale、OOC dtype／mask／row-fold refs、Direct carry/checkpoint/source identity、manifest/library/class path 分別列出來源位置、對應測試或唯讀資產證據、狀態 `source-declared`／`controlled-fixture verified`／`artifact-readback verified`／`unknown`。未獲本次驗證的項目保持 unknown 或 source-declared，不新增超出 scope 的 production 執行或未知模型載入。
3. QA 文件第 45、74、78、87、100、102、108、122、126 行等含完整英文敘述段落，測試檔第 192、235 行有英文註解。`AGENTS.md` 與 `docs/agents/shared_context.md` 要求文件和註解使用繁體中文。請將敘述與註解改為繁體中文，保留必需的英文字面 schema、欄位、hash 和 class path 原值，不改數值內容。
4. `R006_IMPLEMENTATION_REPORT.md` 同步更新本次修正的證據、狀態、精確驗證命令／結果與未決項。報告不得把 `73 passed, 1 failed` 寫成全綠；已知 shadow-boundary 四條 import 仍只記錄，不改 allowlist 或 production。
5. 第二輪讀回發現 QA 資產計數表把 R001 的 `portfolio_ml_direct_numeric_production_v4_v2-source-rebuild-79dccf8b7f0b` 縮成不精確的 `...-source-rebuild`；請用 R001 實際路徑更正，勿將 7 個 manifest 錯歸到不存在的根目錄。另將 OOC row/fold reference `(year_ordinal, local_row_index)` 的證據與 causal fold fixture 分開標示：現有 `test_base_oof_and_meta_use_only_prior_mature_folds` 證明 fold 時序，不直接逐欄斷言 persisted row-ref tuple。若另有精確 test 請引用其斷言，否則該 tuple 僅列 `source-declared`。

允許改動仍只限 R006 專用測試、ML ABI QA 文件與 R006 實作報告。SOL 初查 15-path 表全數 size/hash 相符；無須改 source bytes、正式 artifact、pointer、checkpoint 或外部模型。完成後重跑 R006 新測試、相關 affected focused tests、`py_compile`、格式／diff checks，回報結果。正式 10 檔長跑若 code/test assertions 未變，可引用上輪 `73 passed, 1 known failure`，明確標示未在本次文字修正後重跑；若有任何測試語意改動則重跑對應 affected suites。

REVIEW_STATUS: CHANGES_REQUIRED
