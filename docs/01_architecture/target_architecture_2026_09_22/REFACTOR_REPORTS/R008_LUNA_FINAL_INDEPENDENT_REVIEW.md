# R008 Luna Max 最終獨立審查

本報告只判定修正前 frozen snapshot；審查基準包含 `app_module/recommendation/contracts.py` SHA-256 `B5F2B11FF362F470974B89D0B7E5881EEAEE9F1076517F43EAEA94EC50851C83` 與 `decision_module/recommendation/contracts.py` SHA-256 `C4F691881CB96A86EEF58DB91DDFB4D01AD368DE0C6F6F5DB495C27AB6FA7018`。後續 datetime 回修 bytes 不屬於這次審查或結論，須以新 SHA 另行複審。依指定範圍核對 R008 任務規格、FINAL target architecture §5/6、architecture invariants、ML compatibility contract §2、兩份 scope addendum、implementation/numeric rework reports、兩份 Luna parallel audit 與 SOL batch decision；另依 repo 架構文件確認 owner 與匯入邊界。沒有啟動其他 R-task，也沒有修改 production 或測試檔。

## Frozen bytes 與工作樹範圍

以下九個程式／測試檔的審查基準 SHA-256 與修正前 frozen 值一致，包含指定的 app contract、decision contract 與 app contract test。實作報告本身於同一審查基準的 SHA 也一併記錄；先前報告中的 `0FA98...` 是較早內容的 digest，不能拿來比較此基準報告。

| 檔案 | 審查基準 SHA-256 | 核對 |
|---|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` | 符合 |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` | 符合 |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` | 符合 |
| `app_module/recommendation/__init__.py` | `1BF187FF2A083E691C274B9FF2ACF24FC46F2E11286E09BF85E01B0EB15DEACA` | 符合 |
| `app_module/recommendation/contracts.py` | `B5F2B11FF362F470974B89D0B7E5881EEAEE9F1076517F43EAEA94EC50851C83` | 符合指定值 |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` | 符合 |
| `decision_module/recommendation/contracts.py` | `C4F691881CB96A86EEF58DB91DDFB4D01AD368DE0C6F6F5DB495C27AB6FA7018` | 符合指定值 |
| `tests/test_recommendation_contracts.py` | `DDADE06FBD3F82055FBAE0AC165DC6D71ACF030CA27ABBD9000F5AC8FB4CC08E` | 符合指定值 |
| `tests/test_r008_decision_numeric_enum_rework.py` | `56C705E0DB33896B03CBEBF0DDADA4B7FF1C8F5C60F9B6714E8A054CBE0911C0` | 符合 numeric rework report |
| `docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md` | `296A79DC73DBB384B2822592F3970C894D795F60326258122CD08C64B8F410F6` | 記錄審查基準 bytes；報告未提供此版 self-hash |

`git diff HEAD` 中與 R008 相符的 tracked 變更只有 `app_module/__init__.py`、`decision_module/__init__.py` 與 import contract test：兩個 package 以窄 `__getattr__` 保留舊 exports，測試只改為比較 lazy access 前後的載入狀態。這符合 scope addendum 的核准範圍。R008 新增的兩份 contracts、package exports 與專用 tests 是 untracked；我逐檔檢視，而非把它們當作沒有 diff。其餘工作樹 dirty/untracked paths 屬既有工作，沒有併入 R008 審查或改動。`git diff --cached --name-only` 為空。

## 已核對項目

- `completed` 必須包含 `DecisionBatch`，空 `items` 仍可完成；`failed`／`cancelled` 不可帶 decision，且必須有非空白 `failure_reason`。`Request` 只有具名日期與 typed version refs，沒有泛用 `options`。
- Decision 與 app freeze helper 對 Enum 採 exact-type allowlist；任意 caller-defined Enum 及其 mutable payload 會被拒絕。`score_percentile_bp` 限於 `0..10000`，`eligible_universe_size` 為 exact int 且不可小於零。
- `MLAvailability` 明確區分 not-requested、unknown、available、unavailable、blocked，後兩者需 typed reason。`MLReceiptBinding` 要求 ML_RECEIPT reference、小寫 SHA-256 格式、result ID、date、非空 candidate ID、非空且不重複的 stock-code tuple；Execution 會核對 result ID、已知 context date、DecisionBatch 股票集合與重複 receipt ID。測試涵蓋錯 hash、空值及 result/date/stock mismatch。實際 receipt bytes/body 與 PreparedMLInput 的一致性明確留給 R010/R026；此處沒有宣稱端到端 ML 驗證。
- 零列 completed 的測試使用空 receipt refs 和 `UNKNOWN` availability，未合成現有 writer 不會發布的空 projection receipt。`items`／`assessments` 是委派 properties，不是第二份 storage。
- 17 個舊 app/decision exports 的測試逐項對照來源 class object，涵蓋 `getattr`、direct import、star import 與 `is` identity。bare parent import 後 exports 尚未進入 `__dict__` 的時序差異，已在實作報告揭露且由 scope addendum 允許。
- 子程序 import audit 與 focused tests 驗證 leaf contract import 不讀非程式檔、不連 SQLite，並維持 domain→app 依賴方向。新 numeric contract 使用 Decimal/int，不改既有 scoring、precision、rounding、tie-break、legacy DTO、ML ordered ABI 或 production consumer。
- 自行執行 R008/相依 focused suite：`61 passed in 5.38s`。命令使用 `PYTHONDONTWRITEBYTECODE=1`、`-B` 與 `-p no:cacheprovider`，沒有建立測試快取。

## Finding

### R008-LUNA-FINAL-01（P1）：可變自訂 `tzinfo` 讓封存後的時間值改變

`datetime` 被當成封存白名單中的不可變 scalar，但 `datetime` 的 `tzinfo` 可以是呼叫者持有的可變 `tzinfo` 子類。`app_module/recommendation/contracts.py` 的 `_freeze_value` 在 55–59 行只驗證 offset 後原樣回傳 datetime；`Context.__post_init__`（285–287 行）、`ExecutionEvent.__post_init__`（224–228 行）及 `SaveReceipt.__post_init__`（564–569 行）也只檢查 aware，沒有複製或替換 timezone。Decision 端 `_freeze_value`（42–45 行）同樣回傳原物件；`NegativeEvidence` 對 `observed_at` 呼叫 freeze helper，但沒有保存其回傳值。

最小重現使用正常建構的 caller-owned timezone，而不是對 sealed dataclass 呼叫 `object.__setattr__`，也不是修改可信 Enum singleton：

```python
from datetime import datetime, timedelta, tzinfo
from app_module.recommendation.contracts import Context

class MutableTimezone(tzinfo):
    def __init__(self):
        self.offset = timedelta(0)
    def utcoffset(self, dt):
        return self.offset
    def dst(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return "MutableTimezone"

tz = MutableTimezone()
value = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
sealed = Context(decision_at=value)
before = sealed.decision_at.utcoffset()
tz.offset = timedelta(hours=9)
after = sealed.decision_at.utcoffset()
print(sealed.decision_at is value, before, after)
```

實際輸出：`True 0:00:00 9:00:00`。呼叫端只改了自己仍持有的 timezone，sealed `decision_at` 的時間語意已改變；同一漏洞適用於 event/save timestamps 與 decision `observed_at`，也適用於巢狀 mapping 裡的 datetime。這直接違反 INV-08 的 no-mutable-alias 保證，會令決策時間或保存時間在建構後漂移。

最小修正是在封存時把時間轉成不保留呼叫端 tzinfo 的 immutable snapshot（例如以建構當下 offset 建立固定 offset timezone），或拒絕無法證明不可變的 tzinfo；所有直接 datetime 欄位都必須寫回 snapshot，`NegativeEvidence` 也必須保存 freeze helper 的回傳值。增加測試：建立 contract 後改動原 tzinfo，確認 `Context.decision_at`、`ExecutionEvent.occurred_at`、`SaveReceipt.persisted_at`、`NegativeEvidence.observed_at` 及巢狀 datetime 的語意不變，或明確拒絕該輸入。

Enum 威脅模型裁定：自訂 Enum caller input 已由 exact allowlist 拒絕。對契約自有 Enum singleton 事後 monkeypatch `_value_` 或掛上新屬性屬於全域修改受信任程式物件；它不構成此次所見的 caller-owned input alias，也不另列 finding。

REVIEW_STATUS: CHANGES_REQUIRED
