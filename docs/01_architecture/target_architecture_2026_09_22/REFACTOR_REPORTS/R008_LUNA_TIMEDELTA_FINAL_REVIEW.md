> **時點／狀態導覽（2026-10-11）**：本文的 finding 與 `REVIEW_STATUS` 是該次獨立審查的歷史結果，不等同 R008 整體現行 disposition。本文提出的 timezone-name alias finding，後續 app／decision 凍結修正及最終 scoped 驗收見 [app freeze report](R008_APP_DATETIME_FREEZE_REPORT.md)、[decision freeze report](R008_DECISION_DATETIME_FREEZE_REPORT.md) 與 [SOL final acceptance](R008_SOL_FINAL_ACCEPTANCE.md)。[R031 task index](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md) 將 R008 列為 `ACCEPTED_WITH_TYPED_CONTRACT_SCOPE`；[R031 final closeout](../../../06_qa/R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 未列 R008 專項，因此保留本文原始判讀與限制，並按上述具名驗收核對該 finding。

# R008 Luna Max timedelta 深凍結最終獨立審查

REVIEW_STATUS: CHANGES_REQUIRED

本次依 root 提供的終版清單審查 R008 兩側 contract/test 與 R007 dependency。R008 四個受審 SHA 在合併 focused tests 前後均吻合；R007 contract、test 與 erratum report 也與其凍結清單一致。

| 範圍 | 檔案 | SHA-256 |
|---|---|---|
| R008 app | `app_module/recommendation/contracts.py` | `1C30155F42B7F482DAAF7C8F46D7AB8EEB41569CAC0EC19F2392D484BCBF7AB3` |
| R008 app | `tests/test_recommendation_contracts.py` | `A726246D6B62B88032247164A8E93259722CB247F35F572D30540C9B306D64BF` |
| R008 decision | `decision_module/recommendation/contracts.py` | `C866E76A0F857AC4E619566BE02BB1B9DAE45F5ECC60C10BDDBC9F8EF7C9AABD` |
| R008 decision | `tests/test_r008_decision_numeric_enum_rework.py` | `FFF83A8F7E1E4646F8A74776109C4956A83655F76B64833733073B003F6ECC5F` |
| R007 dependency | `data_module/contracts/market.py` | `6BE9FA87D9B3E49F75603CAD6F3263E27EEFE5942D2566902B7169FD752C3D84` |
| R007 dependency | `tests/test_data_market_contracts.py` | `878113E6E7A92FC966FEA90D6A981613F8FCFBE80F3E051E5BCA73AF9FCC30B6` |
| R007 dependency | `REFACTOR_REPORTS/R007_DATETIME_FREEZE_ERRATUM_REPORT.md` | `F51C781CBDEA9DD88FB0137CFA44149F22A34DCDE038DD17D7DE935E03CA6243` |

## Finding

### R008-LUNA-TIMEDELTA-01（P1）：exact `timezone` 可保留 caller-owned mutable `str` 子類名稱

offset 為 exact builtin `timedelta` 時，app 與 decision 將 exact `datetime.timezone` 視為可直接沿用的 immutable tzinfo。R007 helper 也對 exact `datetime`、`timezone`／`ZoneInfo` 與 exact `timedelta` 採相同快路徑。可是 Python `timezone(offset, name)` 可保留 caller 提供的 `str` 子類物件；其文字值雖不可變，子類仍可帶 mutable attributes，`tzname()` 會把同一物件暴露出來。

唯讀最小 PoC：

```python
from datetime import date, datetime, timedelta, timezone
from app_module.recommendation.contracts import Context
from data_module.contracts.market import Availability, AvailabilityStatus, MarketSlice
from decision_module.recommendation.contracts import NegativeEvidence

class CallerName(str):
    def __new__(cls, value):
        obj = super().__new__(cls, value)
        obj.payload = []
        return obj

name = CallerName("named-zone")
zone = timezone(timedelta(hours=5), name)
source = datetime(2026, 9, 22, 12, 0, tzinfo=zone)
app_time = Context(decision_at=source).decision_at
decision_time = NegativeEvidence("clock", "clock", observed_at=source).observed_at
availability_time = Availability(AvailabilityStatus.KNOWN, available_at=source).available_at
cutoff_time = MarketSlice(date(2026, 9, 22), cutoff_at=source).cutoff_at

assert zone.tzname(None) is name
assert all(value.tzname() is name for value in
           (app_time, decision_time, availability_time, cutoff_time))
name.payload.append("caller mutation")
assert app_time.tzname().payload == ["caller mutation"]
```

在實際重現中，app `Context`、decision `NegativeEvidence`、R007 `Availability.available_at` 與 `MarketSlice.cutoff_at` 的 `tzname()` 均回傳 caller 的同一 `CallerName` 實例；修改其 payload 後，封存時鐘可讀到該變更。這是可觀察的 caller-owned mutable alias，違反 INV-08。app 與 decision 的 `timedelta` 子類 offset 複製已使用 builtin descriptors，相關 property-override PoC 通過；本 finding 是另一個藏在 exact `timezone` 物件內的名稱別名。

需讓 fast path 同時保證 timezone name 為 exact builtin `str`，或在封存時重建 exact `timezone` 與 exact `str` 名稱；R007、app、decision 三個 owner 都須涵蓋此反例。現有 R007 frozen dependency bytes 因此不足以支持 no-alias gate，應先修正並取得新的 R007 SHA／獨立複審，再供 R008 最終 gate 使用。

## 已通過但不消除此 finding 的驗證

合併執行 R008 recommendation、decision numeric/enum、R007 market contract、parent import、execution state 與 coordinator focused suite，結果 **77 passed in 6.96s**。另外獨立重現兩種 `timedelta` subclass offset：自訂 tzinfo 回傳 offset，以及 `timezone(MutableDelta, "explicit-zone-name")`；覆寫 `days` property 的 subclass 也正確以 builtin descriptor 複製。直接欄位與巢狀 mapping/record 的 offset、ISO、timestamp、fold 與 explicit timezone name 均保持穩定。

合併 suite 也覆蓋先前 typed contract findings：completed/failed/cancelled terminal 組合、ML availability 與 receipt binding、一致性檢查、basis-point exact-int/range，以及 leaf import 無 I/O 與 import 邊界。這些測試通過，但不涵蓋 timezone name subclass alias。

本次只新增此報告，沒有修改 production/tests；沒有 stage、commit 或 push，並保留既有 dirty changes。
