# P08 策略帳戶綁定切片（2026-10-10，未完成 P08）

本切片建立明示策略版本與帳戶路徑的唯讀映射，避免同股、同日的不同策略共用帳本身分。它不建立帳戶、資料庫或成交紀錄，不啟動產製器，也不授予績效資格。

## 已實作的契約

`StrategyPaperAccountService` 接收明示 `personal_paths`、策略版本目錄與契約 artifact 目錄。`select_account(namespace)` 驗證 `account_binding.json` 與 exact strategy/policy/cost/benchmark artifact；`select_exact_version` 要求精確版本，有多個帳戶時回傳 unknown，不能猜最新版本。缺件／不可讀保持 unknown，錯版／雜湊不符／非法路徑具名拒絕。

binding schema 為 `strategy-paper-account-binding.v1`，涵蓋策略版本、來源 run、params/config 雜湊、policy/cost/benchmark ID／版本／檔案雜湊、起始日、資金與持倉上限。canonical binding SHA 決定 `acct-<64位SHA>` namespace 與 portfolio ID。現行資金 `500000`、持倉上限 `8`、單邊佣金 `15bp`、滑價 `10bp`、賣出稅 `30bp` 保持原政策。有限 JSON 數字只在身分序列化邊界處理，未新增金融 float 計算或未來資料依賴。

`paper_account_namespace` 是明示 route 欄位；新帳戶使用 `personal_root/paper_portfolio/accounts/<namespace>/` 隔離 state、成交 ledger、benchmark、baseline、binding 與 status。未指定 namespace 的既有 `paper-main` 路徑保持原樣。檔案讀取有大小上限，雜湊與 JSON 解析使用同一份 bytes；讀取期間變更保持 unknown，沿用既有全路徑 link/reparse 拒絕規則。

## 資格與剩餘工作

帳戶映射 `READY` 只證明上述引用與身分相符，`performance_eligible` 固定 false。既有週報 `build`／`build_latest` 對新 namespace 在讀取資料列與計算前回傳 `not_computable`、`strategy_account_row_provenance_unverified`，report 為空。

尚需實作逐筆 snapshot/fill/benchmark 的策略、版本、政策、成本與可得時鐘收據，受控產製／帳本寫入、自然結果、歷史績效及正常 UI 選擇與新程序閉環。binding 不能代替這些證據，P08／M3 尚未完成；一般使用者目前沒有新的帳戶建立入口。

## 驗證與回滾

root 審閱候選完整新增 service/test 與三份既有差異，核對 preimage/postimage 後套用五檔。正式 new binding、既有 personal route、weekly evidence 及 CLI 回歸：**50 passed、1 skipped／1.62秒、exit0**。skip 是 Windows symlink/reparse 測試無法建立案例，未宣稱通過。四份 app source mypy、五份 Python py_compile、diff check 通過。

QA 封套在 `output/qa/p08_account_binding_20261010/`，patch SHA `776c0e7ba11385220678f3947a76797e00f844cf7b417be581f48faefee5742e`；正常測試暫存在 `C:/t/p08formal1010a`。只使用小型合成 JSON／既有合成週報 fixture，不碰原 D 資料與正式排程。

套用前已在封套的 `root_formal_rollback_01/` 保存三份原 checkout raw bytes 與 `rollback.json`。回滾只限列出的五個 task-owned source/test：既有三檔恢復原 bytes；新兩檔僅在 postimage 未被他人修改時移除。不得整體 reset 或覆寫其他 agent 工作。raw QA 封套不提交 Git。
