# R008 Luna Max 終版獨立審查（V2）

> 本 `PASS` 限於本文凍結的 R008 source/test bytes。文末 R007 dependency gate 後續另由 [R007 SOL timezone-name acceptance](R007_SOL_TZNAME_ACCEPTANCE.md) 記錄；目前 R007／R008 task disposition 見 [R031 index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)。本文不單獨宣告 Wave 2 release。

本審查為唯讀，僅檢查 root 指定的 R008 凍結 bytes、授權的 lazy-export 支援檔與 R007 dependency。未實作程式碼、未修改測試或其他既有檔案；唯一新增檔案是本報告。

## 凍結範圍與 SHA-256

下列指定的 R008 source/test SHA 在審查開始與 focused suite 結束後均相符：

| 範圍 | 檔案 | SHA-256 |
|---|---|---|
| R008 app | `app_module/recommendation/contracts.py` | `8CEFCC9D00B8E35D38488D8603486BFEFBBCA575AC74DE27C4BD8147D087E9C1` |
| R008 app | `tests/test_recommendation_contracts.py` | `83847793C9C5B78FED6AC12FD0A2ED4E793D76D51FA99656E9E84DBE3B7F0D84` |
| R008 decision | `decision_module/recommendation/contracts.py` | `65BE03D7DC9DC667759D814D10A293333BD4D5FA34E30BC8C4854AB5A4C1C85D` |
| R008 decision | `tests/test_r008_decision_numeric_enum_rework.py` | `74CCE82275B7A18AE7499084730AB278ED33E5FD6B6EA280ADD8A6CB4E4BAC9B` |

相關 package/export 與 import-contract 檔也符合先前建立的凍結值：

| 檔案 | SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |

## 審查結果

R008 contracts 符合 R008 任務規格、FINAL_TARGET_ARCHITECTURE §5–6、INV-03／06–11 與 ML compatibility contract §2：

- Decision owner 保存 `RecommendationItem`、`CandidateAssessment`、`DecisionBatch`；app execution 只持有 `decision`，`items` 與 `assessments` 是唯讀委派 property，沒有重複儲存。
- 深凍結只接受明示 scalar、enum、date、aware datetime、tuple/list、mapping 及 allowlist frozen records。mapping 先複製 backing dict 再遞迴凍結；mapping key 與 scalar 子類均以 exact type 限制；未知 record、循環引用與不支援 payload 會被拒絕。
- aware datetime 的標準 immutable timezone 快速路徑同時要求 exact `timedelta` offset 與 exact `str` timezone name。其他時區會建立固定 offset snapshot，並以 `timedelta` 基底 descriptor 複製天、秒、微秒，避免 timedelta 子類覆寫屬性造成 offset 偏移。直接時鐘與巢狀 evidence／metrics／details 均走凍結路徑。UTC、固定 offset 與 ZoneInfo/DST 的既有語意有回歸測試。
- terminal status、quality、ML availability 與 persistence outcome 分開。completed 必有 `DecisionBatch`、允許零 item；failed/cancelled 不帶 decision 且需要非空原因。ML reason/status 組合、receipt identity/date/stock membership、hash 形狀、重複 receipt/stock 和不相容 reference 均有拒絕測試。空 projection 不會被合成為 receipt。
- canonical 金融數值接受 `Decimal`／exact `int`，拒絕 float；null、整數零、Decimal 零與既有 legacy DTO float 保持區別，原分數精度沒有量化或重算。此任務未改 rule 計算、ML ordered schema/dtype、top-N、normalization 或 artifact loader。
- parent package 的 lazy exports 保留原 `__all__` 名稱與順序、direct/star import、`getattr` 與 17 個 class identity。leaf import 子程序 audit 拒絕非程式檔案 open 與 SQLite connect，並檢查 domain→app 方向及 pandas/matplotlib/service 載入。bare parent import 後尚未觸發的 export 不立即出現在 `module.__dict__`；R008 實作報告已明示此限制，符合任務要求。
- 變更未超出 R008 核准範圍：兩側 contracts、package exports/tests，以及由初始 import 實測支持的兩個 parent lazy export 與其 import-contract oracle。沒有修改 service、DTO、codec、writer、UI、算法或 ML contract internals。

## 獨立驗證

執行 R008/R007 與相鄰 checkpoint focused tests：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_recommendation_contracts.py tests/test_r008_decision_numeric_enum_rework.py tests/test_data_market_contracts.py tests/test_data_module.py tests/test_update_service_import_contract.py tests/test_recommendation_execution_state_characterization.py tests/test_recommendation_execution_coordinator.py -q -o addopts= -p no:cacheprovider
```

結果：**85 passed in 6.67s**。另以唯讀腳本交叉建立含有 `days` 覆寫的 `timedelta` 子類及帶 mutable attributes 的 `str` 子類 timezone name，分別封存 app 直接欄位、app nested metrics、decision evidence、data availability 與 market cutoff 共七個時鐘；修改原 payload 後，各 sealed datetime 仍保有 exact builtin offset/name、ISO、timestamp 與 fold：**PASS**。`git diff --check` 對 R008 的三個 tracked import-support 檔通過。

## R007 dependency gate 限制

目前工作樹的 `data_module/contracts/market.py` SHA 為 `0DE0A4832E900A0250991B03F2A315A17459DD88A2C31AA6458A629EA853638A`，其測試 SHA 為 `E98E905515C4B9BE6D4EFD420D44A16AD3ED6FFE1D128A68E850340D4F0C4E4B`。現有 R007 SOL acceptance 與 Luna independent review 記錄的程式 SHA 是 `6BE9FA87D9B3E49F75603CAD6F3263E27EEFE5942D2566902B7169FD752C3D84`，不是目前 dependency SHA；因此那份 R007 PASS 不能直接代表目前 bytes 已獨立審查。此次合併 suite 與 alias probe 對目前 R007 bytes 通過，靜態檢查也未發現時區 alias 缺口；但 R007 最新 SHA 仍須走自己的終版 gate。這是 checkpoint 依賴條件，不是 R008 code finding。

R008 凍結範圍未發現需修正事項。此結論只代表上述 R008 bytes 的獨立 code review 通過；R007 最新 bytes 完成獨立 gate 之前，不宣告 Wave 2 完成或可釋放後續 wave。

REVIEW_STATUS: PASS
