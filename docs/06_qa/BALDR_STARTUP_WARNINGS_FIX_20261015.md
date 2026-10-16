# 主視窗啟動與 Qt 清理警告修復（2026-10-15）

## 範圍與基線

使用者回報正常主入口在建立推薦頁時出現 `QWidget::setTabOrder: 'first' and 'second' must be in the same window`，另要求修正先前 main.py 分析中確有必要的項目。基線 `dev` / `f9b4e7d1214967f86d9ae90b1e462bde11b73f3f`；由 root 依序履行 Execution、Tech Lead、Testing / QA、Data Audit 與 Documentation，沒有新建 subagent。

本次不改已驗證 cohort 的拒絕規則，不移除來源守衛，不寫正式資料或來源憑證，不改私人帳、排程、模型、交易或固定試用 EXE。開工後其他 owner 的 `scripts/document_control.py`、Feature Map 與其測試變更保留。

## 原因與修正

| 問題 | 證據與修正 |
|---|---|
| 推薦頁跨視窗 TabOrder | 歷史選取與歷史操作的兩個 host 尚未掛入同一 group 就設定 TabOrder；先把 row 掛入 group，再設定原來的選取 → 讀取 → 回退順序。新增 Qt message-handler 回歸在原程式重現相同訊息。 |
| 可視列 helper 的 signal disconnect | 舊程式依弱 wrapper／signal 名稱重新尋找 callable，Qt 已清理連線或 wrapper 重建時會警告。改保存 `QMetaObject.Connection`，只斷開自己建立的連線；重複清理和其他接收者保留仍有測試。未用 warning filter 掩蓋產品警告。 |
| pandas pct_change FutureWarning | close 已在既有邊界完成 ffill/bfill；明示 `fill_method=None`，避免依賴 pandas 已棄用的隱式 pad。未新增計算、裸 float 或填補政策。原按決策日截斷與 source_data_date 守衛保持；既有 future-row／無有效 close 測試納入回歸。 |
| 主入口工具相容性與匯入 | 移除 UTF-8 BOM 與未使用的 QStatusBar、BatchBacktestService、WatchlistService 匯入。保留有策略註冊副作用的 `decision_module.strategies`。未重寫 MainWindow 或任意縮窄 Qt／身分保護例外。 |
| 公司名冊來源提示 | 唯讀確認正式 `meta_data/companies.csv` 存在，`companies.csv.source.json` 不存在；loader 正確保持 unknown/current-classification-only。這是缺來源憑證，不是視窗建立異常。沒有編造 provenance 或把提示改成成功；手冊補入判讀與恢復路徑。 |

## 驗證

本機 root：`output/tasks/main-startup-fix-20261015-01a14335/`。所有 Python 驗證使用 workspace mutex、8GiB committed memory／12 程序／kill-on-close 與 PID／handle 閉鎖收據；每組結束才啟動下一組。

| 驗證 | 結果 |
|---|---|
| 修正前兩項回歸 | 1 failed / 1 passed；TabOrder 斷言精確重現使用者訊息，清理保留其他接收者案例原先已通過。原輸出 `regression-before.stdout.txt` 保留。 |
| 受改 Python py_compile | PASS |
| 首輪受影響回歸 | 115 passed / 1 failed；唯一失敗是舊歷史列測試仍按左設定欄判定，而控制項已位於右結果欄。載入固定基線 f9b4e7d 的 module bytes，在隔離子程序重跑同樣失敗；沒有修改 checkout 或放寬產品行為。 |
| 歷史列測試修正 | 最後 2 passed，無 warning。保留窄／寬、幾何、鍵盤與可見性斷言，改按真實右結果欄施壓，新增祖先關係與另一欄寬度的反向斷言。舊測試另把 sibling 當 mapTo 目標，混到全域座標；改用共同祖先 group，對齊門檻仍小於 12px。暫時嘗試的 size policy 修改已撤回，產品版面不因此改動。 |
| `scripts/qa_validate_update_tab.py` | 25 PASS / 0 FAIL / 4 保護 SKIP。首次沙箱造成 21 PASS / 3 FAIL / 4 SKIP（fixture 的 data root resolve 拒訪）原件保留；正常系統暫存環境重驗通過，沒有降低門檻。 |
| 八個 roots mypy | PASS，1043 source files；保留兩項 annotation-unchecked 提示，既有 UI ignore_errors 設定不證 UI 強型別。 |
| 真 MainWindow H20 隔離旅程 | 13 passed，55.04 秒；沒有先前 31 個 pandas／Qt RuntimeWarning。以 FutureWarning／RuntimeWarning 當錯誤，另核 stdout／stderr 沒有 TabOrder、Failed to disconnect 或 Qt callback override 錯誤。合成來源／offscreen，含下鑽、返回、取消及關閉；不授 Native／EXE 或正式模型資格。 |
| 文件 Coverage／連結 | PASS，12 features／5 份本次正文，errors=[]；任務同步與風險紀錄完整。初次只缺目前工具要求的 gate 名稱／category=qa 欄位，已補上實際證據後通過，沒有改產品或放寬驗證。 |

首輪 115 PASS 的其他程式與最終產品 patch 相同；只重驗修正過的歷史測試檔，不重跑未受影響案例。各組原始輸出均保留，沒有把中途失敗覆寫為通過。

最終旅程收據 `single_owned_qa_b5a397314cf2465092d010e58ab6a4ff/receipt.json` SHA256 `c038ed12964238be513ac176bf5fd3b800e31776df5e1aa19e903ffcb28bad74`；共同防線 `single_owned_qa_a96981a6a6434943b4a4675d6fc5271e/receipt.json` SHA256 `70bac614834ae070733c94fec46a8da85685420321cf99ff333045b0f44e6f58`；歷史列最後 `single_owned_qa_55d6f2daa736446083290029f489389f/receipt.json` SHA256 `c8dc8f58eccdab6d9c24f94a7a716d1129166d4bef0c5a785e820db49098eba1`。均為三個 PID 陣列空、process／Job handles 關閉、mutex 釋放，沒有 forced cleanup。

文件終驗收據 `single_owned_qa_07eb5af628024e9ba9d419715778eaef/receipt.json` SHA256 `e9a82f5035bb4895595acfec9af2007cdf0831e96333f3566546abb1700dcc8d`；同樣自然閉鎖。之後只回填本表結果／收據，不改連結或產品來源。

## 交付界線

本頁只接受本次啟動、鍵盤、model 清理及相容性變更；不能外推完整產品或 G0–G4 通過。公司名冊來源缺件保留，真正來源憑證需沿既有取得流程處理。固定 `ec5c95733608` 試用包仍保持原樣；未重建或發布 EXE。
