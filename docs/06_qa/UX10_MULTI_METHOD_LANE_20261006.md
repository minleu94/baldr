# UX10 多方法共同符合：獨立 lane 限定交接

日期：2026-10-06。原 lane handoff 狀態為 **readmodel 切片完成、整項 UX10 partial，待主 owner 審查**；後續 dev consumer 整合另記於下方「2026-10-06 dev consumer 整合收據」，應以該段判讀有限接線結果。該收據仍將整項 UX10 列為 partial。

## 所有權、基線與回滾

- 實際基線 HEAD：`a205275db9986f23253797b83363d20090e3db1b`。
- 分支：`lane/ux10-multi-method-20261006`。
- worktree：`C:/Projects/PythonProjects/technical_analysis_multi_method_lane`，建立前不存在；未複製 DB、raw 或用戶資料。
- 整合 owner：主 thread `01a10b0e-ccab-779b-b409-3591c1e74041`；本 lane 僅持有下面三個新增檔案。

| 檔案 | 類型／用途 | 回滾 | 風險 |
|---|---|---|---|
| `app_module/multi_method_research_consensus.py` | 新增純 readmodel 與 pinned 唯讀 adapter | 不採用本 lane 提交；整合後由 owner 反向該限定提交 | 現有 consumer 沒有呼叫 |
| `tests/test_multi_method_research_consensus.py` | 新增專屬契約／fixture adapter 測試 | 隨限定提交撤回 | 不含正式資料 |
| `docs/06_qa/UX10_MULTI_METHOD_LANE_20261006.md` | 新增此限定收據 | 隨限定提交撤回 | 無全域狀態更新 |

不修改共享 dev、COW/config、shared DTO、consumer、Manual、全域 plan/chart 或 shared state。依使用者 exclusive-files 限制，task intake／handoff 記錄集中在本文件；不覆寫其他 lane 狀態。未 push、合併 dev、reset、clean、安裝依賴、永久清理或建立排程。

## 原計畫與接受範圍

已核對原檔 `C:/Projects/PythonProjects/technical_analysis/output/plans/baldr_product_experience_plan_20261004.md` 的 §8.2、§8.6–8.7、UX10 工作包與 §11 依賴。2026-10-06 交接時所讀原檔 SHA256：`cb5eb67c9d6591c22729104fa1c8485077232a8c2214ebf4bc5a0d77cb085f59`。原檔為主 owner 可更新的本機計畫，不提交其副本。

原計畫要求同決策範圍已保存方法結果、股票去重、方法版本／家族／日期／各自理由；相近策略不能當獨立支持，不同日期不能混成今日交集；不足資格不可計入 eligible，命中數不得直接提高分數或獲利機率。本切片接受範圍為既有 MA 方法的 **current-observed research**；不是正式推薦資格。

沿 UX18 方法／特徵契約與 UX19 已驗證快照；母體身份沿 UX20 已存在契約。UX09 lifecycle 另有交易日曆／連續歷史契約，此模組只呈現本次三態，沒有產生 exit/reentry 或寫入歷史。

已讀 repo AGENTS、Agent README/shared context/Git exclusions/skills registry、Execution／QA／Documentation、Team／Quant guard、Snapshot／Roadmap Hub／Product／6M、Current／Target architecture 與 Manual 入口。graphify 技能檢查既有 `graphify-out/graph.json`，這些 daily-market／lifecycle 節點未涵蓋，故回到原始碼核對，不重建圖譜。UI 設計技能經適用性檢查：本批沒有 UI，不建立設計系統。

## 現有來源契約的核對

- `daily_market_method_contract.py` 只有 `daily_market.close_above_ma20` 與 `daily_market.close_above_ma60`，版本均 `1.0.0`，同家族 `close_vs_moving_average`。
- `daily_market_feature_snapshot.py` 保存方法參數、決策日、三態／relation、eligibility／unknown reason 與輸入指紋；投影既有值，不重算 MA。
- `daily_market_research_screener.py` 的 evaluator 核對方法 metadata，`eligible + match/no_match` 才轉成 selected/not_selected；未知、缺 metadata／條件或錯日期維持 unknown。
- `daily_market_snapshot_repository.py` 驗證固定 manifest、artifact、方法契約、母體與 optional universe 原檔；不需要 DB 或 producer。`complete_declared_cohort` 和 `partial_research` 分開。
- `original_stock_ranking.py` 保存排名和 native engine eligible 輸出，沒有本輪批准的研究入選 predicate；不作第三方法或 eligible 計數。
- `research_membership_lifecycle*.py` 以方法／母體 identity、修訂、日曆、availability 與歷史缺件判斷；本切片不以 unknown 冒充 false/exit。

## API 與輸出

優先入口：

```python
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.multi_method_research_consensus import read_daily_market_consensus

model = read_daily_market_consensus(
    DailyMarketSnapshotRepository(snapshot_root),
    manifest_sha256=pinned_manifest_sha256,
    cohort_id=cohort_id,
    decision_date=decision_date,  # date
    as_of=as_of,                # timezone-aware datetime
)
payload = model.to_dict()
```

`read_daily_market_consensus` 只載入指定 manifest，不追 latest、不讀 DB、不啟動 producer 或排名、不讀個人資料。optional universe 綁定仍由既有 repository 核對來源檔，來源修訂會拒絕。

`adapt_daily_market_snapshot(snapshot, as_of=...)` 承接既有 Verified DTO，重核 canonical manifest／identity、逐股 artifact hash 與 captured 方法契約，防止取得 verified DTO 後可變內層被修改。

`build_multi_method_consensus(sources)` 為純函式，接收此 lane 自有 frozen DTO。這是可信來源 adapter 的契約邊界：有格式正確的 hash 不代表核驗過真實檔案，因此 consumer 應用上述 repository 入口；不得把任意外部字典包裝成正式證據。

來源保留 snapshot ID／manifest hash、cohort ID／hash、決策日／cutoff／published clock、完整 universe JSON／hash（含版本與 source hash）、declared codes／excluded reasons／population、completeness、方法 ID／家族／版本／參數／contracts hash、逐股 data date／artifact／stock snapshot／input hash／relation／三態／理由、來源 refs。舊 declared cohort 沒有 universe version 時明示 legacy scope，不造版本或 population，後者維持 None。

每股只一列，stock code 穩定排序，方法 ID 穩定排序；不按命中數排名。`selected_method_count` 是研究符合的方法數；`selected_family_count` 為符合的去重家族數。兩個 MA 都符合仍是 **2 方法、1 家族**，不是兩份獨立策略或兩份股價樣本。`all_methods_state` 為已提供方法的 Kleene AND；未提供的第二方法不被捏造。方法缺某股票觀測時補該股票 unknown，保留分母。

`family_states` 為同家族方法 OR 的描述，沒有策略或統計獨立主張。現有合格契約只一個家族，所有 `multi_family_state` 必為 unknown，理由明示缺第二個既有家族。此欄位不宣稱完成跨家族交集。

`method_counts` 每項為 `(method_id, selected, not_selected, unknown)`，三數總和等於 `denominator`。`denominator` 是 included declared cohort，excluded 清單與原始 `population_count` 分開保留。沒有 universe 時 population 不猜為全市場。

partial 快照保留 source 原觀測與缺件原因，但所有 eligible 投影降 unknown、selected 計數為 0。AND 中已知 not_selected 可以使交集 not_selected；unknown 原列仍是 unknown，不解讀為負樣本或退出。

## 修訂、上限與安全

- 同方法同來源重播、完全相同同股重複，canonical 去重；來源 revision 或同股狀態衝突直接拒絕，不任取 latest。
- 跨方法必須同 snapshot pin／clock／日期／cohort／universe／完整分母／contracts hash／source refs；即使不同日期有相同股票也拒絕。同股 artifact／data date／input hash 不同也拒絕。
- 未登記方法、混方法版本、缺 hash／source refs、明示未來 data date 或發布晚於 as_of 都拒絕；missing 觀測與 artifact 維持 unknown。
- 最多 8 個 source（含重播）、16 included 股票、每 source 32 個觀測（含同股重複）、included＋excluded 最多 32 股票；universe JSON 32KiB、refs JSON 64KiB。超界拒絕，不截斷、分批或偷偷縮分母。
- 不新增金融計算、交易、ML、外部源、推薦／排名算法；以整數計數。新模組 AST 掃描裸 float literal 0、float call 0。
- Look-ahead 自查：只讀指定決策日期已保存觀察；data date 不晚於決策日，cutoff/publication 不晚於 as_of，不借 live 或其他日期結果。不推證官方 availability／PIT；輸出 `research_only=True`、`historical_pit_eligible=False`，保留來源可得性未證明 warning。工程測試不授 Formal credit。

## 驗證結果

使用原 repo 既有 `.venv/Scripts/python.exe`，工作目錄為專屬 worktree；無新依賴。測試以現有 `_snapshot_payload`／`_publish` fixture helper 建小型合成 artifact，再由現有 repository 唯讀讀回；helper 為隔離 fixture 寫檔，不呼叫正式 producer。

| 驗證 | 結果 |
|---|---|
| 專屬 `tests/test_multi_method_research_consensus.py` | 45 passed |
| 加上既有 feature snapshot／method contract／snapshot repository | 共 81 passed（45 新＋36 既有） |
| `mypy --follow-imports=silent app_module/multi_method_research_consensus.py` | 1 source file clean |
| `py_compile` 新模組與專屬測試 | pass |
| `scripts/quant_guard_linter.py` | pass；白名單靜態工具，新模組另有 AST 無 float 自查 |
| `git diff --check` | pass |

測試覆蓋固定 pin 避開 latest、讀前後檔案 hash 不變、原檔 revision 拒絕、完整分母與來源缺件、explicit universe／排除理由／原檔修訂、同股／同 run 去重、同家族雙命中只一個家族、日期／cohort／方法版本／hash／逐股 data date 不可比、unknown 不作負樣本、partial 全部 unknown、發布晚於 as_of 與容量上限。這些是 service oracle／contract tests；未跑前景 Native、UI、正式 DB、排程、真實個人資料或真人驗收。

## 主 owner 最小整合建議與剩餘工作

1. 主 owner 審查後自行 cherry-pick 本地限定 commit；不得將此報告視為已整合 dev。
2. 在既有已驗證每日結果讀取處呼叫 `adapt_daily_market_snapshot(verified, as_of=明示觀測時點)`＋`build_multi_method_consensus(...)`，或者採用固定 manifest repository 入口；以既有 callback pin 防 stale。不改 shared DTO 也能將此 lane model 用於唯讀呈現。
3. 顯示「MA 研究方法符合度」、方法版本／family／理由與完整分母；跨家族欄保 unknown。原排名只作另外的旁證欄位，不加入 sources 或 count。
4. consumer 接線與使用者流程改變時，由主 owner 同步 Manual／Snapshot／架構／索引與全域計畫，另跑 UI 強制檢查。本 lane 沒有 consumer 接線，這些共享文檔依 exclusive-files 指令未改。

硬依賴缺件：目前沒有第二個不同家族且具完整 selected/not_selected/unknown predicate 的批准方法結果，所以 **真正跨家族共同入選仍 pending**。新方法不得由此 lane 補算法或捏造資格；須先補 UX16/18/19 的來源、固定方法契約、分母、snapshot 與接受證據。UI 列表／跨頁帶入、生命週期視圖連動、真人驗收與正式資料範圍亦仍 pending。整項 UX10 不標 full done。

2026-10-06：完成有限 readmodel／fixture adapter 包，停止本 lane 的新增範圍，交主 owner 審查。


## 2026-10-06 dev consumer 整合收據（最新，限定工程）

immutable lane `340eac2f5729fade53190967d11d2d637a4c85bf` 基於 `a205275db9986f23253797b83363d20090e3db1b`；dev 核驗為 personal 整合 `1fbe83a5189390859c0ab69d73068995a1adb86c`、工作樹乾淨後，cherry-pick 為 `1ad0d53db71eef1ab69fef26b23be637c0e40e28`。三個 cherry 檔案的 disk Git blob、dev commit blob 與原 lane blob 全相同；根層完整審查 readmodel／adapter／契約及基線差異。

每日 view 在唯一 _accept_snapshot 接受點，使用同一 VerifiedDailyMarketSnapshot 與 Asia/Taipei aware current-observed 時鐘，經 adapter 重核後投影一次；篩選／排序僅呈現，不啟producer、live DB 或新方法。候選首屏短行列2方法／1家族、MA20/60各三態分母；選取股票短行列符合方法／家族數與跨家族未知。各方法state／版本／family／原因、逐股data date／artifact／stock snapshot／input hash與manifest／cohort／contracts pins保留tooltip。2MA共同符合不當兩個獨立策略；原排名不計方法數、不調分數或勝率。

partial 全部unknown保分母；舊DTO／captured contract缺件／新來源不相容時清前次model並具名理由，原每日研究結果可讀。clear同步清model／error／observed clock。只一個合格MA家族，所以跨家族共同入選全部unknown，缺第二合格家族仍pending。current-observed研究不賦歷史PIT／官方availability／Formal credit；整項UX10維持partial，其他family由父層另行安排，不在本批發明。

| 根層驗證 | 結果 |
|---|---|
| readmodel＋feature／method contract／snapshot repository | 81 passed（45新＋36既有） |
| 既有UX04/05每日view＋main routing | 8 passed |
| 新增consumer focused UI | 6 passed，0.91s；含同家族／partial／legacy／錯契約去舊／clear／hash不變 |
| 本批受影響案例合計 | 95 passed；重跑相同案例不累加 |
| UI強制Workbench | 85 passed，另列 |
| validator | 25 passed／4 skipped／0 failed |
| mypy指定全部source roots | 798 source files clean |
| compile | 4 Python檔通過 |
| 精度／未來函數guard、diff check | pass |

首輪新fixture只改MA60condition而未同步feature，repository以snapshot_condition_value_mismatch拒絕；已改用既有DailyMarketFeatureSnapshotService自合成價格／technical DTO完整投影，未放寬任何guard。consumer型別／literal newline替換已修，最終來源compile通過。正向合成pinned artifact UI前後SHA256全相同，不當自然資料／投資效果證據。

raw收據：output/qa/ux10_consumer_integration_20261006（ignored）。原計畫只追加本批結果、stage5/6/7最小exclusive backend提案，以及父層轉交personal inventory／Journal排他界線，未覆蓋先前接受內容。Manual／UI docs／Snapshot／current architecture／index／navigation同步。新Native／真人、第二合格family、生命週期consumer跨頁聯動仍pending。沒有正式DB／personal配置寫入、遷移、訓練、清理或push；Journal與Portfolio相關排他檔未改。
