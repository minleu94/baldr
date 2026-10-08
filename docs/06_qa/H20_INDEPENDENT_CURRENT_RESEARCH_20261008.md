# H20 原研究保留與獨立目前行情入口

## 行為

H20 保存名單／收藏的個股報告，在原估計已核驗可用時顯示「查看目前個股行情與資料（獨立研究）」。按下後另開非模態個股報告，標題及可見說明明示目前來源；context 不攜帶原 H20 的決策日、capture、模型、result_id 或來源 pins。原工作區的 H20 數值、來源、選取與返回身分保持。關閉獨立視窗後繼續原研究，不再複製原私人 SQLite。

未知／不可核驗的 H20 停用此入口；開窗前重核原 context、來源、程序內 cohort seal 與設定。設定已變更不開窗；主程式關閉時取消並等待獨立報告 worker。相同原研究重複點擊會聚焦既有視窗，不重複開啟。

H20 原報告的價格／技術／歷史缺件改為明示「未綁定同版本」，避免誤導成資料庫不存在或單靠更新就能修復。沒有放寬保存來源 guard、補入目前行情、調整策略門檻或產生模型估計。另一份 ML 與 H20 的目標區隔沿用 `3ae0ba82`。

## 中央審核與驗證

Root 完整兩份變更 UI 測試：session 78647 **exit 0，65 passed／24.88 秒**。真 Main 合成旅程核原估計 1234 bp、一次 cohort 讀回、獨立目前價格資料、乾淨 context、關閉回原報告、過期設定拒絕及關閉等待；service 反例核 H20 不消費另一份目前價格。合成估計不是原 2382 的 +684 bp，不宣稱真人來源通過。

Root Workbench **85 passed／3.59 秒**；validator **25 passed／0 failed／4 protected skips**；全 roots mypy **902 檔無錯誤**；五檔 py_compile 與 scoped diff-check 通過。既有 pandas pct_change FutureWarning 與 Qt destroyed callback disconnect RuntimeWarning 保留。

前次 root 完整測試先有 65 setup errors：新 basetemp 父目錄未建立，未執行產品案例。另一次 workspace 深路徑為 **58 passed／7 failed**，包含合成 SQLite backup unable to open database file 與既有 2.5 秒鍵盤讀回等待。兩次工具輸出與隔離產物保留；同兩份測試改用已核不存在的短根 `C:/t/h20p05_root_8f921` 全通過，沒有增加逾時或跳過案例。葉片 C:/t 定向六項也通過；整份舊 test 檔的額外 mypy 有既有測試 typing 問題，沒有把它當全 roots production mypy 的通過證據。

凍結 SHA256：

- main：`4b3efe293baf605be2e35b25c658c0f8c426e5e47fb339bae02518f776d1c2ce`。
- report view：`b5de0618fc5810ebdd324b194933dae480ffc0627844f6457358d14654d82f4d`。
- service：`2e900a997d3febeff79934004afe10e8f8811bfc2b7c3fc3342ff258a3720a25`。
- report tests：`6663ffe7d53e48fd317368966a1b4e92b035d66cf80860c3c9d80105ab4ffaf9`。
- Main journey tests：`ee2041a3994a105f752ed8ec112ff1ac5d6b2155e18d887dadde8702cb7722a3`。

前像：`output/qa/h20_current_dialog_p05_c3132d9bf85d4782a68b33e81f7d90e3`；root 深路徑失敗：`output/qa/h20_current_dialog_root_full_20261008_b`；validator 前像：`output/qa/h20_current_dialog_validator_preimage_20261008_a`。這些 raw output 不提交 Git。

## 操作與未完成項目

推薦分析→個人模型選股研究→可研究的 2382→研究選取股票→上方「查看目前個股行情與資料（獨立研究）」。核新視窗標題、來源日期與目前資料；按返回／關閉後核原 H20 預測、日期、來源與 2382 選取。未知時按鈕停用且保留原因，不操作模型回退或正式排程。

目前為已核來源版補件，新固定候選打包與同版比較仍待；已交 `421bc973a891` 不含此入口。原 H20 同版圖表、原資料保護與真人速度／完整資料脈絡仍待，不授完整 P05、Native 或補完計畫完成。
