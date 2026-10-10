# baldr Windows 可攜版

可攜版包含 `baldr.exe` 與 `_internal`。**必須保存整個 baldr 資料夾**，不可只複製 exe。Windows x64 不需 IDE、全域 Python 或虛擬環境；雙擊 `baldr.exe` 開啟既有九工作區。舊交付日期版號為 `2026.10.06`；首波候選是 `2026.10.06+4b40788bea9e`，以完整來源commit區分，不是產品成熟度版號。

## 首次啟動與既有使用者

本機現有交付位置：`C:/Projects/PythonProjects/technical_analysis/dist/baldr/baldr.exe`。exe 大小 **52,301,884 bytes**；SHA256：`ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e`，與實際檔案及 `output/packaging/active_delivery.json` 相符。這是原日期／啟動畫面交付，尚未包含補完首波。建置依賴 PyInstaller 6.16.0／Python 3.11.9／Qt 6.10；支援 Windows 10 1809 以上 x64／Windows 11，依 [Qt 平台文件](https://doc.qt.io/qt-6.10/supported-platforms.html)。舊驗收不延伸為本輪candidate驗收。

首波候選另放 `dist/candidate_4b40788bea9e_dd7335f7/baldr/baldr.exe`；固定來源 `4b40788bea9e74b5d5207d3d81b1e1c80394b7d6`，52,413,416 bytes，SHA256 `6015311ff93286fa045ff04ed2a82284f812ed009cd48db79db435a2ef344410`。Python比較使用 `output/packaging/build_4b40788bea9e_dd7335f7/source` 的同commit快照，不使用當前dev。精確依賴及同一隔離JSON下的四用途、shadow模型／新PID、收藏保存／重開、H20呈現、日期／異常／取消／spawn比對通過；詳見[首波QA](../06_qa/BALDR_COMPLETION_FIRST_WAVE_20261006.md)。`BUILD_INFO.json`保留建置事實，`VALIDATION_INFO.json`連結獨立驗證收據；固定發布身分不等於已替換現有交付或Native接受。以下原交付歷史驗收與新candidate的具名結果分開判讀。

已驗隔離 offscreen 啟動、空資料設定提示、九工作區、Unicode／空格工作目錄、synthetic 模型安全載入與新程序重開、multiprocessing、保存重開、Worker 取消與重新執行，以及 CLI／scheduler 未配置 preflight。Native 真人操作、真實私人模型、正式 Task 自然 run、其他 Windows 機器尚未由本包驗證；不以 fixture 改寫原資格。

四用途以合成來源／空報價 fixture 驗證畫面與安全未知狀態；推薦 legacy SQLite runs 的 canonical 保存結果重開，在本環境受既有 no-follow handles root／ancestor guard 阻擋，不能列為通過。此限制沿原 audit 保留，沒有放寬 guard；Watchlist 保存重開不等同推薦保存重開。

此機真 config 的 FA_Data/output 組合也已驗真正 launcher 建立九工作區並正常關閉；測試禁止真根寫入與 provider 網路，鎖檔／研究庫寫 handle 被 guard 拒絕，範圍只授唯讀保護下的啟動。ML registry 必須與市場根分離；原錯置於 OUTPUT_ROOT 的打包版本會被安全邊界拒絕，已修正且失敗歷史保留。

首次未明示設定時使用 `%LOCALAPPDATA%\baldr\market` 與 `output` 空根，顯示設定提示。空來源保持 missing／unknown，不帶行情、私人持倉或模型。設定檔位於 `%LOCALAPPDATA%\baldr\config.json`；可用 `BALDR_CONFIG` 指定另一個絕對路徑。設定檔不是 `.env`，程式不自動讀 `.env`。同名環境變數優先於 JSON。

```json
{
  "DATA_ROOT": "D:/My Baldr/market",
  "OUTPUT_ROOT": "D:/My Baldr/results"
}
```

1. 關閉程式並等待背景工作安全收尾。
2. 在上述檔案填自己的絕對路徑；roots 必須在程式包外且可寫。設定後重開。
3. 既有使用者沿原啟動器／設定填相同 DATA_ROOT、OUTPUT_ROOT。不要因為換 exe 建立或搬移資料。
4. 私人選擇沿原契約填 `PERSONAL_DATA_ROOT`／`PERSONAL_WATCHLIST_SOURCE`、`PERSONAL_JOURNAL_ROOT`／`PERSONAL_JOURNAL_MODE`、`PERSONAL_STORE_ROOT`／`PERSONAL_STORE_MODE`；單設拒絕，不改市場 writer。
5. 已接受個人模型填原 `PERSONAL_MODEL_POLICY_PATH`，指向原可信 policy；指定路徑不自動訓練／啟用。原 manifest、same-bytes、identity、source、cutoff 核驗仍適用。
6. 在數據更新確認行情日期與缺件；看盤勢／持倉健康／選股研究／個股研究仍按 [完整手冊](APPLICATION_MANUAL.md) 操作。

Runtime 狀態位於 `OUTPUT_ROOT/application_state`；ML研究registry的repository root預設為 `%LOCALAPPDATA%/baldr/research_state`，依既有研究庫契約再解析其 `output/ml_research_storage.json`／`output/ml_research`。兩者是不同位置，研究根與市場根隔離。新使用者保持空研究狀態；原模型artifact、真帳與FA_Data均不在程式包。

新版 Python 與 candidate 的技術分析日誌均寫入 `OUTPUT_ROOT/application_state/logs/technical_calculation.log`，不依工作目錄。資源位置仍有必要差異：Python 固定來源快照的 `ui_qt/`，exe 的 `_internal/ui_qt/`；主視窗版本提示列與 `--launch-info` 明示實體路徑。資料、runtime與研究保存根不因此改變。

## 子程序與排程

### exe 與 source 入口的資料優先序

補完新版Python入口為 `python baldr_launcher.py`；`python ui_qt/main.py` 與 `python -m ui_qt.main` 在服務／Qt匯入前轉入同一launcher。設定統一為同名環境變數 → `BALDR_CONFIG` 或 `%LOCALAPPDATA%/baldr/config.json` → LOCALAPPDATA空行情／輸出根；不自動讀 `.env`。解析完成才交由TWStockConfig與原服務初始化。這是新版原碼行為；上述原交付exe仍維持其已交付功能，新candidate另行驗收，不能以dirty Python冒稱它已修復。

既有使用者沿已建立的JSON與原資料根重開。新版主視窗底部顯示版本與開發／發布狀態；提示中列完整來源commit、設定、行情、輸出、runtime、研究與資源路徑。`--launch-info`可讀回同一解析值；日期相同但commit不同即不同建置。開發版含未提交變更會明示；無Git／無合法metadata顯示版本未核實。

若需讀原已保存ML registry，維護者可在JSON／環境明示 `RESEARCH_STATE_ROOT` 為原registry的repository root（其中有原 `output/ml_research_storage.json`／`output/ml_research`），兩種入口使用同一值。此值須絕對路徑、與DATA_ROOT隔離且位於程式包外；不自動搬移、啟用或訓練模型。日常選來源仍使用既有來源選單，不要求輸入hash。獨立執行舊排程腳本仍沿其原TWStockConfig契約；正式Task不因GUI入口更新而換入口。

H20 原 hook 使用 DATA_ROOT 下 `personal/recommendation_h20/activation.json`（或原 PERSONAL_H20_ACTIVATION_CONFIG 環境 override）。對齊 DATA_ROOT 會讀回原已選 activation，沒有重新 enable／fit；它與另一個 PERSONAL_MODEL_POLICY_PATH policy namespace 不相同。不要將某個 activation JSON 填成另一個 policy，也不要因換 exe 新建私人 store。

可攜入口支援 `baldr.exe scripts/scheduled/<原腳本>.py <原參數>` 與 `baldr.exe -m <模組> <原參數>`。相對腳本以程式包資源根解析，不依目前工作目錄；參數、dry-run／preflight／execute gate 仍以原腳本為準。例：`baldr.exe scripts/scheduled/run_daily_data_update_quick.py --help` 只列說明。

原正式 Task 不會自動改為 exe，也不會註冊或手動觸發。日常排程若要換入口，需另外確認完整 action、環境與身份，不以本輪隔離驗證代替原 Task 自然 run。取消與關閉沿原合作式收尾；重開保留外部設定與保存結果。

## 排錯、安全與建置

- 未簽章；簽章與 SmartScreen 信譽未知。不得繞過 Windows 警告或降低防護。本包不是已簽章安裝程式。
- 首次無字或缺資料：確認整個資料夾存在、設定為 UTF-8 JSON 且 root 為絕對路徑；中文字型沿 Windows 原字型，未複製 Windows 字型。
- 沒有 console 的日誌在 `%LOCALAPPDATA%/baldr/stdout.log`／`stderr.log`，主 App crash diagnostics 沿原資料根機制。資料根／來源拒絕時核對提示，不改 hash／no-follow／ACL。
- 合法 `passed_with_warnings` 表示更新完成但有警告；最後成功時間、來源資料日期、新鮮度與警告分開判讀。failed／unknown／invalid／stale 不假成功。
- 任意深層 OUTPUT_ROOT 的既有 Windows 長路徑限制仍適用；本輪測 Unicode／空格，未保證所有大於 260 字元的保存路徑。
- 維護者在固定依賴環境執行 `.\.venv\Scripts\python.exe packaging/build_windows.py --commit <完整40字元已驗證commit>`。以 `packaging/windows-dependencies.lock.json` 精確核對Python、CPU與所有distribution；不符即拒絕，不自行安裝／升級。Git archive輸出固定commit快照，再從該快照spec建置；不混dirty工作樹，也不新增worktree。輸出到獨立 `dist/candidate_<commit>_<job>/baldr`，保存版本、commit、依賴鎖／資源SHA與候選receipt，狀態先為built_not_validated。現有 `dist/baldr` 與active_delivery不被自動替換。
- 同版比較必須使用candidate receipt的source_directory、同一依賴鎖、同一隔離JSON與測試資料，分別跑Python與exe；四用途、模型讀回、保存／返回／新PID、日期、錯誤與取消、資源和子程序都需核對。通過工程比較仍不等於Native真人、真私人模型或正式Task自然run通過。
- 執行 `.\.venv\Scripts\python.exe packaging/verify_same_version.py --receipt <candidate資料夾/BUILD_INFO.json>`，先核對exe／archive SHA、來源逐檔bytes與精確依賴，再用該固定來源的probe跑兩種形態。新收據與兩組raw log留在 `output/qa/baldr_same_version_<commit>_<job>`；失敗收據保留，不能直接覆寫成通過。推薦synthetic呈現和canonical讀回限制分列，H20呈現fixture不替代原capture資格。
- 建置器限定venv／系統PATH與空userbase，避免外部Poppler ICU遮蔽Windows系統ICU；spec統一已安裝Qt wheel附帶C++ runtime。只收正式程式、必要資源與依賴，不收QA、experiments、FA_Data、私人模型或 `.env`。

替換版本前保留舊可攜資料夾；回滾時改用舊 exe＋整個舊資料夾。資料與設定不刪除，不清 cache、不重建 DB；程式回滾不代表資料 schema 遷移回滾。


## 啟動載入畫面與圖示

雙擊 exe 後，在 Qt 可建立視窗時顯示原 loading_view.png 背景、目前工作與進度條。套件匯入使用不定進度；14 個實際初始化階段完成後推進，主視窗顯示後才完成。進度代表介面初始化，不代表市場資料新鮮度或排程成功。可按 Esc／Alt+F4 關閉載入窗；程式在安全階段邊界取消，等待既有 worker 合作式退出，不會顯示半成品主視窗。單一同步初始化呼叫期間仍須等該呼叫返回；不宣稱能強制中斷。缺圖時保留深色底與可讀進度。

exe、應用程式與主視窗使用原 app_icon.png；Windows AppUserModelID 在建立視窗前設定為 Baldr.TechnicalAnalysis，不修改 registry。既有釘選或 Windows 圖示快取可能仍顯示舊圖，未自動更動使用者釘選。初始化失敗會關閉載入窗，顯示既有錯誤／log 位置；offscreen 測試不顯示阻塞對話框。
