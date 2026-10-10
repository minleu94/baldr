# P08 快照來源紀錄切片（2026-10-10，P08 尚未完成）

本切片為策略帳戶後續逐筆來源核驗建立保存契約，不新增帳戶建立入口、不執行每日產製器，也不解除週報的成本基礎或來源未知阻擋。完整範圍仍見[補完進度](BALDR_PRODUCT_COMPLETION_STATUS_20261010.md)。

## 保存與讀回契約

`PaperPortfolioSnapshotRepository.append(snapshot, receipt=None)` 保留原呼叫方式；提供紀錄時，snapshot、positions 與 companion table 的紀錄在同一 transaction 保存，任一步失敗全部回滾。重複 snapshot 不覆寫。`get_receipt(snapshot_id)` 核對 canonical JSON 雜湊、snapshot 身分、帳戶 namespace 及資料列 metadata。舊列或舊 schema 缺紀錄回傳 `None`，意義仍是 unknown；唯讀路徑不建立新表、不回填舊列。

本切片的 frozen DTO 使用 `paper-portfolio-snapshot-receipt.v1`，上限 16 KiB，拒絕重複 JSON key 或額外欄位；當時只有 `unknown` 與明示 `synthetic:` 的 `seed_reference`。後者核對 500000 初始資金、最多 8 個持倉、binding hash 導出的 namespace、持倉雜湊與現金／市值總和，並沿既有 daily runner 的分位量化及整數基點截斷核對每列市值／權重。金額欄位拒絕非有限 Decimal 或負數。後續前向現金開戶另加入相容的 v2 `account_cash_seed`，契約與正式驗證見[開戶切片](BALDR_P08_CASH_SEED_SLICE_20261010.md)；daily／績效資格仍未完成。

`seed_reference` 只是合成來源引用；雜湊不是簽章，也沒有驗證真實 seed artifact、PIT、成本、benchmark 或來源 run 的完整性。沒有 net／績效資格欄位。真實種子、每日 `[S,D)` fills 與 prior snapshot 的來源鏈、受控 writer、weekly consumer 及正常 UI 仍須實作，不能用這項基礎契約替代 P08／M3。

## Root 審查與正式路徑驗證

Root 已完整讀取原候選、持倉一致性修訂及 v2 測試增量，核對正式 preimage、candidate postimage、patch SHA 與 AST。隔離 overlay 整合取得 55 PASS；套用後在正式 import 路徑另取得 **55 PASS／5.52 秒、native exit0**，涵蓋 receipt 30 項及五份既有 snapshot repository、daily runner、weekly report、weekly evidence、inspect CLI 測試。單檔 mypy、兩檔 py_compile 與 diff check 通過。

測試包含原子回滾、重複不覆寫、legacy append、唯讀舊 schema 缺表且 DB bytes/schema 不變、JSON／metadata 篡改、錯帳戶、重複 JSON key、超限內容、非有限金額及市值／權重不一致。Decimal context 比對確認候選沿用既有 runner 的 rounding／precision，沒有增加裸 float 或新的報酬計算。此切片不選價格、不讀真 fills，也不產生策略決策；look-ahead 與收益資格仍需由後續真實來源鏈另驗。

候選：`output/qa/p08_snapshot_receipt_20261010_consistency_v2/`；完整 patch SHA-256 `1bb971eddadbdd76c74463aba92917c8b1fff0a5a6fca00a24f5f33458f08188`。正式套用後僅移除新測試檔末尾的多餘空白行；測試內容不變。正式測試暫存位於該封套的 `root_formal_test_01`。沒有執行正式／私人／D 市場資料庫或排程，Windows junction/reparse 專項未設置，不能宣稱通過。

## 回滾清單

| 路徑 | 變更 | 回滾方式與限制 |
|---|---|---|
| `app_module/paper_portfolio_snapshot_repository.py` | 紀錄 DTO、原子 companion table 與讀回、有限金額核對 | 原 raw bytes 保存於候選的 `root_formal_rollback_01`；只有確認沒有他人後續修改後才恢復本任務差異。 |
| `tests/test_paper_portfolio_snapshot_receipt.py` | 新增合成測試 | 確認 task-owned 且無後續他人修改後，才移除新測試。 |
| 本 QA 文件與補完進度 | 說明契約及驗證界線 | 只回退本次文件差異，不覆寫其他 agent 整理結果。 |

回滾不包含資料庫、原始資料或已保存紀錄的刪除。程式碼回退後，既有 companion table 保留；舊 reader 不因此取得績效資格。不得整體 reset。QA 原始封套及 rollback bytes 都維持 ignored，不提交。
