# UX20 MA 完整控制組 capture 主線限定整合（2026-10-06）

基線 c5e216c30ee342ed21117ba6790227db9276ea88；lane 4bcc842 以 4764a240 cherry-pick。唯一主線 owner 接線；一位 Luna Max 唯讀審查，沒有新增寫入代理。保留 lane／worktree，不 push。

## 交付及回滾

新增 rule_research_sample_readiness、專用整合測試及本 QA；修改 lane capture validator／測試、隔離 produce_daily_market_research_snapshot CLI、既有 DailyMarketResearchView 及下列文件。回滾依反序 git revert 本批整合 commit、4764a240；先核對 owner/status。回滾移除入口，不刪 QA capture／正式 DB／私人資料。

Coverage Pass：Must 為本 QA、Manual、Snapshot、Architecture、功能說明、User Guide、Index、Navigation 與唯一原 plan 的追加收據。產品方向／6M／長期 Roadmap 與既有正式 data-owner pipeline 不變，不另建推進計畫。沒有缺少需使用者回答的參數。

## 審查與接線

lane 已有兩條固定 MA observation 的完整 matched/notmatched/unknown/excluded 列，單批 included 1–16、represented 至多32，整數分母，不新增公式或績效。排除保存理由、missing artifact 留 unknown；部分 artifact 不能當完整成功。rank 沒有入選 predicate，selected_count=0、selection_status=unknown；沒有混入 Paper／持倉／私人收藏。

Luna 審查指出三個必要缺口，主線已補：讀回逐方法 code 集合必須恰等於 captured universe 的 included＋excluded（legacy 對 declared codes）；排除狀態／理由及 population 必須一致；逐列方法版本對 contract；保存時鐘含時區且 cutoff≤published≤as_of≤observed。六個 rehash 竄改回歸含換股、版本、invalid/reversed clock、population、排除理由。這些是內部語意核對，不證明真實時鐘／PIT；兩個方法仍是同一 MA 家族。

隔離 CLI 明示 --capture-root 與 --capture-as-of 成對，無 flag 保持原 producer 流程。首次明示 observed-now 時，producer 發布後記錄本次觀測 as_of；結果回傳固定值，重跑須沿用該值才去重。反覆 observed-now 是新觀測身份，不是假重複／同次自然決策。同日來源修訂新身份，舊包不覆寫。先檢查 1–16 不重複 symbols、capture 根及來源互不包含，才開 readonly SQLite；超過16立即拒絕，不截斷／自動分批。

成功 producer pin→capture_pinned（三次來源重核）→atomic capture＋receipt→writer.read→再讀同 manifest/cohort/date/as_of→read_saved_rule_sample_readiness。readiness 的 saved_verified 僅表示本包 bytes／來源 pin 一致。readiness 不補 source_available_at、交易日曆、成熟 outcomes 或 label；training/formal/PIT/natural 全 false。snapshot pin 綁已保存 artifacts，不代表原 SQLite 現況或官方 raw custody。

MA 頁在既有快照接受後顯示當期完整聲明單批及兩方法分母，只有 DTO 純投影，明示「尚未保存樣本」。來源清除時同步清空；工程身份在 tooltip。UI 不啟動 writer／producer／新背景任務，未新增持久化配置。

writer 只接受 repo output/qa 或 Temp 的子目錄；容量 reserve200GiB、單包256KiB、留存8MiB/128包不放寬。低容量會拒絕，不要求正式C/D root可寫。partial／busy／不一致 receipt fail closed 且保留，僅移除自己的 transient lock；不永久清理。既有 lstat/fstat 守衛不是惡意同步替換的完整 Windows no-follow 證明，不宣稱斷電 durability。

## 驗證

- 最終 focused suite：146 passed／1 skipped，5.79s；包括 lane及既有repository/consensus/universe/UI，新增4個實際接線案例＋6個語意拒絕案例，不把重跑加總。
- 實際小型合成 SQLite，既有 query-only source／MA producer→capture／receipt→readonly readiness；來源 SHA bytes／mtime 不變。重跑 duplicate、同日 source revision 保留兩包、wrong as_of拒絕、17股在 source open 前拒絕、純 UI投影及清除通過。未讀正式行情 DB。
- Workbench85；validator25／0fail／4既有skip；full roots mypy804。語意補強後 targeted mypy3、compile6、diffcheck通過；quant precision/look-ahead通過，人工核對只讀保存輸入，不以 outcome 補時鐘，沒有裸 float。
- focused 唯一skip是一般 symlink建立權限，hardlink拒絕實測通過；唯一warning為 sandbox pytest cache不可寫。初次新測試容量fixture鍵名／qtbot未安裝、補強時completeness拼錯均修正，失敗不當通過證據。
- raw收據 output/qa/ux20_sample_integration_20261006/focused.xml；小型隔離來源與capture留Temp，不拷大型DB。所有Native／WindowsTask／正式EvidenceDB／重訓／全市場收集未執行。

## 原 UX20 終點與剩餘

本包完成「單批完整控制組→capture/receipt→readonly readiness」有限工程終點；Stage5／UX20改 partial，不能整項done或ML-ready。兩組必須分開：

| 可現在繼續寫完的工程（未等自然日） | 需自然日／正式來源的證據 |
|---|---|
| >16股有界多批manifest、完整parentbinding、缺batch拒絕；本包選擇原允許的≤16＋大母體明示拒絕 | 正式來源可證 available-at及官方交易日曆資格 |
| 正式capture owner／固定決策時點／漏日及同日修訂接受契約、保留容量治理、部署配置；不由本包替data-owner啟用 | 按該契約實際逐日採集的來源／失敗／修訂收據 |
| Outcome H5/10/20 producer/readiness與calendar政策接線、未知／不足／修訂拒絕及saved receipt瀏覽；尚無自然label consumer，不可標done | 足夠後續交易日、符合政策的成熟outcome與樣本量／準確度 |

上述工程是後續可安排有限包，不歸為自然成熟等待。本包不擴大16股上限或部署；UTC07:00暫停期限不變。

個人儲存／Journal 程式先前已整合（含 6d9a4316、18224c33、0a58d9f2）；尚未正式 migration／activation。不是未整合程式，也不重新採用舊25c3b326 lane。其他 owner 三檔／未知 root paper_event_source_capture.py 不讀不動。

補充：CLI capture失敗仍返回原producer manifest/status，另標sample_capture_status=rejected，避免把已發布快照誤說成全部未寫。容量不足的追加實際fixture案例1pass、CLI targeted mypy1及compile2通過；不重複加總146。正式reserve不放寬。

## 2026-10-11 後續收據核對

本文只完成單批、最多 16 股的整合，並把大母體合法分批列為後續工程。`UX20_PARENT_CAPTURE_INTEGRATION_20261006.md` 後續記錄有界多批 parent capture、批次身份與完整母體分母核對，`UX20_PARENT_RECEIPT_UI_20261006.md` 記錄相應的唯讀保存收據瀏覽。原單批上限是此交付當時的範圍，不能代表現有流程仍完全沒有多批工程；後續交付仍受有界 capture 規則約束，UX20／Stage5 仍 partial，正式來源時點及自然成熟證據仍缺。
