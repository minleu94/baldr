# 最終架構不變條件

> 設計定案，尚未實作。唯一決策來源：[FINAL_TARGET_ARCHITECTURE](FINAL_TARGET_ARCHITECTURE.md)。以下 18 條是目標系統與後續實作 prompt 的強制規則；現況尚未全部符合。過渡違規只能以 [遷移退休帳](FINAL_MIGRATION_SEQUENCE.md) 的具名 owner／退出條件列管，不允許整包永久豁免。

| ID | 必須遵守 | 驗證方式 |
|---|---|---|
| INV-01 | 原始資料、歷史 artifact、模型與 checkpoint 不因重構改 bytes、ID 或 hash。 | 唯讀基線／hash inventory；寫入只用隔離 root。 |
| INV-02 | data 擁有來源解碼；analysis 擁有技術公式；domain 擁有 factor 語意、策略與規則；app 擁有用例；UI 只呈現。 | 變更 owner 表與 import／call-site 審查。 |
| INV-03 | domain 不依賴 app、Qt、concrete DB/HTTP/file reader、ML trainer 或 scripts；純 leaf contracts 不觸發 I/O。 | 精確 module DAG、無 I/O 的 domain fixture、import smoke。 |
| INV-04 | factor 語意轉譯與公式留同一 domain owner；vendor 欄名／來源 fallback 留 data；app 不複製兩者。 | 同標準輸入跨來源等價、factor unit/missing 測試。 |
| INV-05 | 訊號、特徵、母體、標準化與 benchmark 只用 decision-time 可得資料；unknown availability 不當已知。 | cutoff／PIT／未來資料注入反例。 |
| INV-06 | 新金融核心計算使用 Decimal 或具單位整數；不得在重構中偷改原 precision、rounding、tie-break 或 ML matrix ABI。 | 獨立數值 oracle、精確比較；具名 legacy 例外退休帳。 |
| INV-07 | 每次執行回傳同一完整 execution；result_id 在 ML receipt 前建立；runtime／portfolio／replay ID 只以 reference 連結。 | A/B 交錯、ID conflict、parent/receipt 對照。 |
| INV-08 | worker 返回前遞迴封存所有結果；frozen dataclass＋tuple＋複製後 MappingProxyType，不保留 mutable alias。 | 原輸入與回傳值兩側的巢狀 mutation 測試。 |
| INV-09 | completed/failed/cancelled、quality、ML availability、保存 outcome 分開；零候選可為 completed。 | 零列、取消、部分失敗與 last-good UI 案例。 |
| INV-10 | save／query／UI 不讀 service.last_*、不補算 regime、score 或 ML；真正業務 prior state 必須明示保留。 | 執行後來源變更再保存、regime 多日／cooldown 測試。 |
| INV-11 | canonical typed contract 是唯一新欄位 schema；codec 自動涵蓋支援型別，未知 schema/type 必須拒絕，禁止無型別核心擴充字典。 | 全欄位 roundtrip、null/0、缺 optional、未知 revision 拒絕。 |
| INV-12 | 新保存採 create-only；同 ID/hash 冪等、異 hash 拒絕；metadata 不進 execution hash；SQLite index 可重建。 | 並行保存、中斷後補索引、改名不改 payload hash。 |
| INV-13 | 歷史顯示只讀原結果；歷史重算建立新 result_id 並保留 parent/版本；兩模式 policy 差異不得被共用 engine 偷改。 | 無 live lookup readback、日期/母體/策略差異 fixtures。 |
| INV-14 | ML prepare 明示固定資料／模型版本；build/infer 不暗讀 live source。初輪 frozen reads 僅依列管例外維持，不能假稱已隔離。 | 來源更新 barrier、exact candidate/date/cost/receipt 驗證。 |
| INV-15 | 舊 ML ordered schema、dtype、scale、mask、row/fold refs、transform、source identity、class path 與 safety gate 不自動演進。 | [ML 契約](FINAL_ML_COMPATIBILITY_CONTRACT.md) 的相容正反例；新 feature 明示 opt-in 新版本。 |
| INV-16 | composition 建立並管理資源；runtime 只排程／治理；UI/CLI 呼叫相同用例。 | 單一實例／生命週期、取消與重試、入口測試。 |
| INV-17 | 過渡 runtime 機制必有 ID、owner、caller、刪除條件；新舊不留雙引擎。永久歷史 decoder／artifact ABI 支援分帳。 | 全 caller inventory、動態/serialized 依賴、退休帳逐項驗收。 |
| INV-18 | 設計完成、測試通過、工程完成與 formal/promoted/production 權限分開；不可用重構通過替代產品 Gate。 | 驗收記錄、權限拒絕測試、Scoped SSOT 核對。 |

每個實作切片至少指出受影響 INV、對應證據與仍存在的具名例外；未驗證項目明記未執行。新介面不能再產生 `last_*` 依賴，即使舊 caller 尚在遷移也一樣。
