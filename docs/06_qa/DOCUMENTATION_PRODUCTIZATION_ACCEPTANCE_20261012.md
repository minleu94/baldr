# 文件產品化與角色交付驗收

> 任務 `documentation-productization-20261012`；基線 `b834f6116dff8316d45dae7c704f260738896325`。本收據驗證文件閱讀、角色路由、同步工具與移機計畫。產品 Gate、真安裝、原生平台隱式 discovery 與自然排程仍各自驗收。

需求見[整合計畫](../superpowers/plans/documentation_productization_plan_20261012.md)，原件及去向見[處置入口](../09_archive/documentation_productization_20261012/README.md)，同步要求見[工作流程](../00_core/PRODUCT_CHANGE_WORKFLOW.md)與[功能關聯](../00_core/FEATURE_DOCUMENT_MAP.json)。

## 成果與審查

- 根入口改為用途、日常旅程與開始方式；現況、產品方向、工程順序和目標設計按各自權威查找。
- 現行架構與操作各分三冊。獨立靜態審查找出並補回取消能力／8 future、Paper partial-finalize、Health exact receipt、來源／writer／保存時鐘、Scenario 估值與版本、H20 cutoff、Personal store／CAS、retention 邊界。日期化測試數字保留原件。
- 六角色共用規則與唯一路由；原生 Skill 是薄入口。兩個前測請求分別選 UI 實作與唯讀資料審計，閱讀與修改範圍分開；角色卡不等於獨立 Agent 已被啟動。
- 首次安裝流程涵蓋 fresh／owner-migration 及 plan-only／configure／restore-and-enable；21 Windows Task 與兩個文件化 Codex heartbeat分開盤點。舊 CMD Direct 05:30 與現行 PS1／checker 10:00 衝突已在入口標示，舊 CMD 不作移機路徑；此次未修 scheduler runtime。
- 只移除本任務建立且未使用的預備原件副本。正式資料、舊任務 singleton、其他聊天的 QA／Snapshot 增量保持原所有權。

## 實際驗證

| 檢查 | 結果與證據範圍 |
|---|---|
| 維護工具行為 | 51 PASS；`tests/test_document_control.py` 與 `tests/test_auto_state_task_json.py`，涵蓋路由、漏同步／Gate、越界／owner、唯讀預設／原子更新、清冊重複／缺件／hash／時區／原停用與通知／模型保留、有效行號片段。最終收據 `output/doc_productization/validation/behavior06/receipt.json`。 |
| Python 語法 | 四個本次 Python 檔 `py_compile` 通過，收據 `validation/final_compile02/receipt.json`。 |
| 型態 | `mypy scripts/document_control.py scripts/auto_state_sync.py` 通過，收據 `validation/tool_types02/receipt.json`。 |
| 原生 Skill 格式 | skill-creator `quick_validate.py` 通過；收據 `validation/native_skill/receipt.json`。 |
| 公開清冊與 CLI | 7 項核對通過：兩個 Schema、route、init／重跑拒絕、A/B 規劃草稿及隔離 fresh bootstrap CLI；計畫讀到現行 21-task catalog、`mutations=[]`。收據 `validation/schema_cli03/receipt.json`，兩草稿仍 planning、未執行產品修改。 |
| 正文與入站連結 | 145 個待提交路徑、1578 個 Markdown 來源與 11 組功能關聯核對；本次正文／入站錯誤為零。工作樹全庫掃描另有 50 個既有／本機證據引用問題；乾淨提交鏡像未提供本機 raw output，另列 224 個既有／本機引用問題，不宣稱全庫皆有效。收據 `validation/staged_delivery02/receipt.json` 與 `staged_delivery.json`。 |
| 原件與提交範圍 | 57 份原件 Git blob 的 SHA／bytes 全部相符，現行 87 份來源／封存支援頁指紋相符；精確 staged 路徑與測過的工具 bytes 相符，其他 owner QA 不在提交中。清冊自身列為 self-reference，封存支援頁均已列入處置及指紋核對。 |

上述 Python 執行由 root 序列處理，啟動前 RAM 超過 8 GiB；全 Job 8 GiB／12 程序上限讀回相符，child suspended-before-assignment，正常 terminal／Job member 0／handles 關閉／鎖釋放，無 forced cleanup。原始 log／JSON 留 ignored `output/doc_productization/`，不提交。

## 失敗保留與修正

初輪 pytest 的保留參數名及改名漏項、四個型態錯誤、尚未生成映射／相容錨點與前測 coverage 漏項均保留原失敗收據，修正後重驗。前測也促成收斂過廣的文件匹配，唯讀 B 的 read files 不再當 changed scope。封存原件的 CRLF／尾空白觸發 staged 空白檢查後，只對 exact-byte originals 設保全例外；現行正文仍檢查。沒有放寬產品門檻或把未跑項目寫成已通過。

## 接受界線

本次沒有修改產品 UI／金融計算，未跑完整產品 UI／Main／EXE／資料庫驗收；未搬資料、註冊、啟用、觸發排程或更新 Graphify。Skill 格式與明示閱讀前測不能證明新主機的隱式 discovery 或 Antigravity 執行。移機時依[Runbook](../07_guides/MACHINE_BOOTSTRAP_RUNBOOK.md)取得具體來源與讀回證據；設定完成與自然 run／consumer 接受分開。
