# R001 replay 清冊勘誤之 SOL 重審

## 判定

R001 先前已通過 SOL inventory 驗收。本輪 integration 查出 replay service/provider 的 source path 與頂層回傳型別混淆，並在第一輪勘誤後發現 TMP-REC-02/03/04 將現行 legacy API 誤寫成已建立的 canonical adapter。Luna 只在 R001 基線清冊與實作報告內修正；SOL 根據目前 source、R011/R012/R017/R020 規格及實際檔案重審後，R001 的勘誤予以 PASS。這不代表 Wave 1 checkpoint 或 R003/R005/R006 正式 Gemini review 已完成。

## 實際 source／架構核對

- `app_module/recommendation_replay_service.py:13, 17–25, 51–57` 定義 `RecommendationReplayService.run_snapshot() -> RecommendationSnapshotDTO`，只在 DTO 的 `recommendations` 欄位承載 provider 的 `List[Dict[str, Any]]`；DTO 定義在 `app_module/recommendation_portfolio_dtos.py:10–16`。
- `app_module/recommendation_dataframe_provider.py:13, 21, 80` 定義 provider `__call__() -> List[Dict[str, Any]]`，依既有 replay/portfolio policy 做 score/filter/sort。portfolio service 將 provider 注入 replay wrapper，Qt backtest view 建立該 provider；`historical_evidence_replay.py` 和 `recommendation_market_data_provider.py` 不是這兩個 class 的定義處。
- `R011.md:36`、`R012.md:37`、`R017.md:37` 分別列明 TMP-REC-02、03、04 尚待建立；`R020.md:35` 移除 TMP-REC-04。清冊現已區分目前 active 的舊 list API、保存呼叫形狀、replay provider，與尚未建立的 canonical façade／adapter／bridge。R005/R017/R020 路由及 replay mode-specific policy 未變。

## 實際檔案、驗證與範圍

- `docs/06_qa/REFACTOR_BASELINE_R001_20260922.md`：SHA-256 `93E4DDDC29BACCD9483EB6B35D83E5078C77B2A318508A82B452CD40EF028867`。
- `REFACTOR_REPORTS/R001_IMPLEMENTATION_REPORT.md`：SHA-256 `4F2CF0BF3B2FB4FDE390568E8676D8BF047AA568C9BD9B7B88E78C95C8FF54C3`。
- SOL 直接讀清冊第 132–133、165–167 行及報告 §10，逐項對照實際 source、DTO、caller 與 authoritative task/sequence。兩份文件 UTF-8、LF/final LF、無 trailing whitespace；`git diff --check` exit 0，僅有既有 tracked dirty files 的 LF/CRLF warning。沒有 Python、正式資料、artifact、模型、Git index 或其他 R-task 改動；這次為文件勘誤，沒有重跑 production tests。
- R005 的兩份正式受審檔案 SHA 仍為 `F572128AFC270E7C865EF6533B5DEBFA2B1608AEFADDD946E473E547F4D35A21` 和 `14BE9F9E0E5F796E3E59A2AF3FB12A6D030EF38AC14113BE97D4FDD2C75DAF1F`；R005 實作報告中提及的 R001 source-path mismatch 是勘誤前的歷史觀察，已由此文件收口，不需改動凍結的 Gemini review packet。

R001_STATUS_AFTER_ERRATUM: PASS
