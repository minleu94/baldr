# 本機 main 使用版 packaging 驗收

## 本機發布結果

使用者要求dev開發／main乾淨易用，父層明示採本機main單一squash commit。最終 `main=a8c81bf534952cdf35d35a57d9e367c0fa10c817`，唯一parent仍是原 `1bedee9aff0be2a375f90eb677911cb029688339`，tree `1477a445dc5b76e0498fcd231e99e3bd6a0ad2a4`。來源dev `809e0884`，dev完整歷史保留；未reset／force／push／public share／visibility變更。初候選a7已durable bundle保全，本聊天僅在未發布leaf補回必要文件，未改原main歷史。main本機可用，不代表完整Git歷史已審可公開再散布。

## dev／main 差異裁決

父層獨立只讀release reviewer固定4e234576／1bedee9a，manifest覆蓋3,895 tracked entries；dev首次設定增量809e0884另核9檔。初候選3,286檔／611排除，精確匯出治理test首11P／2F查明7份導航／治理doc必要；補回且去識別、不改斷言後 **13P／14.18s**。最終受控tree **3,293檔／604排除**：含saved notebook／機器TaskXML、內部規劃／日期化私人啟用收據／歷史流水帳。排除的是使用版tree，dev原檔與驗證bundle仍保全，不清除原始資料。

**1,386 tests／QA support entries全保留**；所有Python blobs與809e0884一致，包括核心程式、腳本、實驗基線、測試与治理runner。review桶不是bug清單，未因目錄名或日期刪必要程式。tests/manual/README.md僅整理開發參考連結，其餘test blobs不變。

74份public docs去識別私人候選／原cycleID／user-home及換掉指向刻意dev-only收據的死鏈；main Snapshot使用當前產品／資料資格說明，完整Manual操作內容保留并加first setup；README短入口、runtime安裝、獨立roots、不自動load_dotenv與資料缺件判讀已同步。新合成CSV只有兩列資料形狀，不是可載入UI demo，無市場/PIT/正式資格。未擅選license，README明示未授予新的公開再散布權。

## Packaging 驗證

- 新建Windows x64／Python3.11 venv，按requirements-runtime及direct constraints完整安裝成功；TA-Lib／fastdtw成功。首次requirements UTF-8 comments被舊pip cp1252解碼拒絕；設 `PYTHONUTF8=1` 原安裝重試成功，已寫入指南，首紅raw保留。`pip check` 顯示 no broken requirements；constraints不是transitive lock，不冒跨平台完全重現。
- 從精確index tree匯出到全新目錄，避免main worktree殘留dev-only檔影響驗證。在該匯出與全新runtime，以獨立空DATA_ROOT／OUTPUT_ROOT、隔離QSettings、禁止provider網路，**offscreen MainWindow完整建立、event loop及close exit0**。未使用私人FA_Data、模型／active pointer／Task，不宣稱Native或自然產品成熟。
- Python AST parse **0 errors**，14項首設／規範入口存在、link **0 missing**；保留全部tests/QA paths。非fixture Python user-home literals **0**、docs私人ID／user-home **0**，tracked DB／SQLite／pkl／joblib／private-key／ipynb格式 **0**，machineTaskXML不在tree。固定tree token候選為Markdown slug誤報；此是tree packaging檢查，非歷史secret全面掃描或公開license驗收。
- 全main相對舊main的cr-at-eol-aware diff-check530行whitespace警告全為既有dev560行警告的subset，**新增0**。未為去警告重排核心source。第一次未加cr-at-eol的巨量警告來自既有CRLF，非產品回歸；raw保留。首次設定CLI audit輸出改成config.output_root，不再依個人home，source compile已通過。

既有四包affected/mandatory結果按原HEAD／scope保留，未冒稱重跑全产品gate。工程功能、個人實際啟用、下一自然排程與自然品質成熟仍分域；自然10pending／0成熟，原Task2026-10-07 12:45UTC仍待實際驗收，不因main發布升credit。

## 收據與恢復

所有raw、manifest、source blobs與驗證JSON在ignored `output/qa/baldr_branch_cleanup_20261007/`。`public_release_manifest.json` 記所有3,293 path／Git blobs；最終AST／入口／privacy重新核零缺件。`public_tree_validation.json`、`clean_install_utf8.log`、`clean_pip_check.log`、`clean_startup.log`、治理首紅與final13P具名證據。最終7份doc與README文字增量不改任何Python，空root啟動驗證仍按初tree／相同code scope記錄。獨立review資料在ignored `output/qa/baldr_release_boundary_review_20261007/`，不提交或分享備份／私人成果。

持久恢復位置為 `C:/Projects/RepositoryBackups/technical_analysis_branch_recovery_20261007`；原all_refs.bundle及extras、release_refs.bundle與main新增611extras ZIP都驗證保留。後續只一主要worktree的實際整理結果另由兩branch恢復收據更新；main checkout未在驗收前刪除。
