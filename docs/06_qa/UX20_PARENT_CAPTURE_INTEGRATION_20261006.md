# UX20 具名母體多批 capture 整合收據（2026-10-06）

基底 de262862486117da6659707df23625a65a34a38f。本批完成限定多批工程閉環，Stage5／UX20 仍 partial。既有個人儲存／Journal 已程式整合，真實 migration／activation 未進行；舊 personal lane 不重複整合。

## 契約與資料流

`rule_research_parent_capture.py` 沿既有 SQLite query-only source、DailyMarketSnapshotProducer、child capture writer 與 readiness；沒有第二套資料源或寫入框架。單一唯讀 transaction 綁定 DB/schema/main+WAL stat pin、方法 hash、母體原 bytes hash 與 decision cutoff；這是觀測來源 pin，不是 raw custody 或官方 available-at。

parent schema 為 daily-market-research-parent-universe.v1：具名 universe_id/version/as_of_date，method=daily-market-close-ma.v1、scope=bounded_multibatch_research_cohort，完整 included／excluded+reason、population_count、research_only=true、complete_fixed_cohort=true。included 1–256、excluded 0–256，最多16批，每批 included 1–16、excluded≤16；無法合法分批便拒絕，不複製成員湊批。完整僅指明示研究母體。

plan hash 綁定母體／來源／cutoff／方法；batch universe、snapshot、child capture 與 parent receipt 固定對應。缺批、重複成員、混入另一 child、途中來源／方法／母體改變，不能成 complete。每方法 matched+notmatched+unknown+excluded+uncaptured 等於完整分母；未保存成員另列 uncaptured，不借 unknown 補齊。

parent writer 繼承現有原子 writer，只替換 decoder／receipt factory。保留200GiB reserve、256KiB/包、8MiB/128包單 store限制；另加每個母體 snapshot/capture root 64MiB/4096 entries總預算及批次前預留。只接受既有隔離路徑，不啟正式配置；測試 capacity probe 為隔離 fixture，不放寬正式 gate。links/hardlinks/busy/partial fail closed，沒有自動清理。lstat/fstat 不宣稱完整對抗性 Win32 no-follow 或 crash durability。

## 失敗、取消與重試

每批分開回報 production_status／sample_capture_status；producer已發布而 capture拒絕時，manifest/status 保留，不能顯示沒寫任何東西。KeyboardInterrupt 或尚未取得 producer返回時標 interrupted_unknown。取消／來源變更的 parent 可保存 incomplete/cancelled 收據，即使最後一批已 capture 也不能稱母體 complete；envelope receipt.status=complete 僅表示保存包完整，cohort_status另列。

相同 source/母體/方法/cutoff/固定 as_of 重試去重，保留首次 receipt；當前操作的 published/unchanged 不進 semantic identity。若 child原子寫中斷留下 partial，同一 capture store 拒絕重試，使用明示新的隔離 capture root，保留舊partial供審查。新程序只按 exact parent identity、配置與來源 pin 讀回，不開 DB、不挑 latest、不觸 producer。

## 驗證

- 受影響測試86個不同案例 passed；1個既有通用 symlink案例因環境 skip，hardlink拒絕實測通過。最終 parent21 passed（11.61s）；其餘65案例在83 passed/1 skipped集中通過，未把重跑重複計數。
- 實際隔離 query-only producer→兩批 snapshot→child capture/receipt→parent→新程序 readonly readiness，17 included+2 excluded=19，無 uncaptured；固定 as_of duplicate，來源 bytes/mtime不變。不是自然producer／模型訓練證據。
- 取消後重試、第二批失敗、capture拒絕但producer已發布、source/method/universe變更、重hash缺批/重複/混pin、錯cutoff、256+256/16批與總預算、寫入中斷後新root安全重試、最後capture後取消均覆蓋。
- full roots mypy805 sources通過，最後局部修正再targeted4通過；compile5、diffcheck、quant precision/look-ahead通過。未新增金融裸float，未補available-at／outcome label。
- UI本批未改，沿用前批Workbench85／validator25+4環境skip，不重跑。無Native、正式DB/EvidenceDB寫入、WindowsTask、migration、ML重訓、push或刪除。

原始XML與受控readback在 ignored output/qa/ux20_parent_capture_20261006：focused_final.xml（83/1skip）、parent_final.xml（21），controlled_readback.json。Temp fixtures保留，不拷DB。QA原始輸出不提交。

## 剩餘工程與自然依賴

多批 parent 現已完成；仍待工程：固定決策時鐘／cadence／漏日與同日修訂接受規則、正式data-owner留存部署、Outcome H5/10/20與calendar／label／benchmark契約及接線、saved parent母體UI瀏覽。自然／官方依賴是 available-at custody、官方日曆、真正每日收據、後續交易日與成熟outcomes／準確度；不可用自然等待替代工程。

UX21獨立 lane建議只擁有 app_module/rule_research_forward_outcome.py、tests/test_rule_research_forward_outcome.py 及其QA，不碰 shared capture/readiness/CLI/plan。輸入 exact capture/member、decision day、H5/10/20、明示tradingdays、target/benchmark價格點與as_of；重用純OutcomeMaturityService與Decimal/整數bp。終點為immutable pending/ready、horizon end/available date/missing reasons、日期對齊benchmark；缺價／未成熟為null/pending，不填零，不授PIT/ML-fit。尚未建立或實作此lane，由父層派工。

## 文件與回滾

Coverage Pass：QA、Manual、Snapshot、Architecture、Features、UserGuide、Index、Navigation與唯一原計畫同步；產品方向／6M／長期版號未改。git revert本批commit可回復程式／文件；保留隔離收據與partial，無資料搬移或刪除。UTC07:00依既定安排安全暫停工程；未另建automation。
