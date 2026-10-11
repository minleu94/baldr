# R008 Luna 平行契約審查

> 本檔是 2026-09-22 的獨立契約 audit，不是 Gemini 正式 verdict；所列 `CHANGES_REQUIRED` findings 對應當時 SHA。後續 task-level bounded disposition 見 [R031 R008 row](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)，原 findings 保留作歷史審查證據。

審查日期：2026-09-22。此文件是獨立唯讀契約審查，不是 Gemini 正式 `REVIEW_STATUS`，也不代表 Wave 3 放行。

## 版本基準

依 `REFACTOR_REPORTS/R008_SOL_REWORK_REVIEW.md` 核對九個完整 SHA-256；九檔均與 SOL 列出的目前版本完全相符。舊 Gemini 審查的 `C12670CD…` 與 `2975AC35…` 不屬於本次受審版本。

| 檔案 | 目前 SHA-256 |
|---|---|
| `app_module/__init__.py` | `5B309F7DEE902B3205A5299824C058F90CA81B3564563B2656367B286DC5C3F0` |
| `decision_module/__init__.py` | `617CDBE9C95F04A0D5EBF06B44273C0BCA9873E2032FFEDC4BDD07D233EC9F39` |
| `tests/test_update_service_import_contract.py` | `6FE79B65574E67B787D7A885C03239AD058C5F0C2B0E446300B971CB6DDB0CF0` |
| `app_module/recommendation/__init__.py` | `6C72A5C327D8F9C1CE9E087E274A510243B1F336D8F71DA1E64DCC0D937882E3` |
| `app_module/recommendation/contracts.py` | `EDEED3DDD91478EC78878820A52310CA6B46E2DD8B1BABD69449FF1018AA7487` |
| `decision_module/recommendation/__init__.py` | `27BCF39C6CFF326EC8503C041A5676A062B6C96AC7016B4892720C63779A695C` |
| `decision_module/recommendation/contracts.py` | `BEF137F7D55696C3B18CB6FCAD6F035147BF2BBD1A5B43536A6CF319126725CB` |
| `tests/test_recommendation_contracts.py` | `54BC720194C31050A83BE6B7788C4A5502E3886F02D8ECC9BAD80DBA67CA9BDA` |
| `REFACTOR_REPORTS/R008_IMPLEMENTATION_REPORT.md` | `0FA98AF3EDA595A4E10C21FB19DF176D0561490EB79E4AC53305EB5DCA21AD68` |

## 發現

### R008-LUNA-01：failed/cancelled execution 可完全沒有原因

位置：`app_module/recommendation/contracts.py:403`、`415–426`；測試反例在 `tests/test_recommendation_contracts.py:301–304`。

FINAL_TARGET_ARCHITECTURE §5.2 明定 failed/cancelled 各有明示狀態與原因。現在 `failure_reason` 只在非 `None` 時檢查型別，沒有要求 failed/cancelled 提供原因；`events` 也可為空，預設 quality 為 unknown。因此以下輸入成功建構，結果沒有任何原因或診斷：

```python
RecommendationExecution(
    result_id="rec_00000000-0000-0000-0000-000000000001",
    request=Request(),
    context=Context(),
    status=ExecutionStatus.FAILED,
)
```

最小修正：對 `FAILED`、`CANCELLED` 強制要求非空白 `failure_reason`；若契約選擇允許以事件取代該欄，則須強制至少存在一個帶非空原因的診斷事件，並同步固定其語意。現有測試應把無原因案例改為拒絕，並保留有明確原因的失敗與取消案例。

### R008-LUNA-02：ML reference 沒有契約化的 receipt／execution 綁定

位置：`app_module/recommendation/contracts.py:147–178`、`399–402`、`442–459`；目前測試只在 `tests/test_recommendation_contracts.py:397–403` 驗證兩種 reference 都非空。

FINAL_ML_COMPATIBILITY_CONTRACT §2 要求單次 execution 綁定 `result_id`、精確候選集合與 symbol、decision time/date、cutoff/mode；保存實際輸入身份與 hash，並封存精確 receipt 的 ID/hash/candidate/date/cost lane。現在 projection 與 receipt 都只能用通用 `VersionReference(kind, reference_id, version)` 表示；`version` 可省略，且沒有欄位或驗證能保證 reference 是不可變/內容定址的 receipt，或把 receipt 綁到本 execution 的候選、日期與成本 lane。execution 驗證只檢查 reference kind 及 `AVAILABLE` 兩組 tuple 非空。

可重現反例：以 `status=COMPLETED`、`decision=DecisionBatch()`、`ml_availability=MLAvailability(AVAILABLE)` 建立 execution，再傳入 `VersionReference(ML_PROJECTION, "projection-unbound")` 與 `VersionReference(ML_RECEIPT, "receipt-unbound")`。目前會接受零候選 execution 與這兩個任意 ID 的組合；引用物沒有 hash、候選、日期或成本欄位可供 contract 核對。零候選本身可合法完成；問題是目前 shape 無法證明掛上的 receipt 是這次零候選 execution 的 immutable receipt。

最小修正：讓這些欄位使用既有且具明確不可變性／內容身份與 execution binding 保證的 projection/receipt reference；若既有型別沒有該保證，則只加最小 immutable reference snapshot，明示 receipt identity/hash、result/candidate binding、decision date/cutoff 及 cost lane，並驗證它與 execution 相符。不要複製 ML feature/model schema。測試需包含零候選正確綁定、跨 `result_id`/候選/日期/cost lane 錯配拒絕，以及未知狀態保留 refs 但不冒稱 available。

### R008-LUNA-03：Request.options 是未限定鍵與值語意的擴充字典

位置：`app_module/recommendation/contracts.py:244–266`。

`Request.options` 的型別是 `Mapping[str, object]`，實際驗證只限制遞迴值必須落在通用封存白名單；沒有允許鍵、鍵對應值型別或 options schema/version。以下未註冊選項會被接受並封存：

```python
Request(options={"unregistered_option": {"value": Decimal("3.5")}})
```

這讓新的核心 request 語意可以透過任意 mapping key 加入，而不更新唯一 canonical typed schema，與 FINAL_ARCHITECTURE_INVARIANTS INV-11 的「禁止無型別核心擴充字典」不一致。深凍結只能避免 mutation，不能使其成為受版本管理的欄位契約。

最小修正：將正式支援的 request 設定改成具名 frozen options contract（或由 caller 傳入既有 immutable config reference，options 只保留固定且明示欄位）；若需保留 mapping，必須有明確鍵白名單與各鍵型別/range 驗證，未知鍵拒絕。測試增加未知鍵拒絕與每個支援選項的型別案例。

### R008-LUNA-04：百分位 bp 與 universe count 接受不可能的負值

位置：`decision_module/recommendation/contracts.py:184–187`、`195–198`。

`RecommendationItem.__post_init__` 僅確認 `score_percentile_bp` 與 `eligible_universe_size` 是 `int`，未檢查其領域範圍。這個輸入目前成功建構：

```python
RecommendationItem("2330", score_percentile_bp=-1, eligible_universe_size=-2)
```

`score_percentile_bp` 表示百分位基點，負百分位不成立；universe size 是數量，負值亦不成立。FINAL_TARGET_ARCHITECTURE §5.3 要求數值具明確單位且不能把 bp 當任意分數；僅驗證 Python 型別不足以維持欄位語意。

最小修正：拒絕 `score_percentile_bp` 不在 `0..10000` 的值，並拒絕負的 `eligible_universe_size`。不量化或轉換既有 Decimal/int score，也不變更其精度或排序行為。

## 已通過項目與驗證邊界

- Decision 與 app records 使用 frozen dataclass；tuple/list 會轉 tuple；mapping 會複製 backing dict 後包成 `MappingProxyType`；巢狀值及循環輸入有白名單拒絕測試。MappingProxy backing-copy 測試通過。
- 金融分數與 factor value 僅接受 Decimal/int/None，明確拒絕裸 float；percentile bp 欄位使用 int。此判斷不代表上述負值 range 缺陷已解決。
- `completed` 要求 `DecisionBatch`，空 items 可完成；`failed`/`cancelled` 禁止發布 decision。terminal cause 的缺口見 R008-LUNA-01。
- ML status 獨立於 terminal/quality；`NOT_REQUESTED` 禁止 refs，`AVAILABLE` 要求 projection 與 receipt refs，`UNKNOWN` 可保留 refs 但不會被改判為 available，`UNAVAILABLE`/`BLOCKED` 要求 typed reason。zero-item completion 與 explicit reasons 有測試；ref binding 缺口見 R008-LUNA-02。
- schema version 與 revision 在 application contract 宣告，revision 固定為 1；SaveReceipt 驗證 schema/version 欄位。RecommendationExecution.items/assessments 是委派 property，不是第二份 dataclass storage。
- recommendation package exports 與 parent package lazy exports 保留 `__all__`、direct/star import、`getattr` 和檢查到的 class identity；裸 parent import 後尚未讀取的 exports 不在 `module.__dict__`，實作報告已明示這項載入時序差異。兩個 contract-import subprocess 測試檢查非程式檔案 open、SQLite connect 與 domain→app 方向限制。
- 唯讀驗證：`PYTHONDONTWRITEBYTECODE=1 .\.venv\Scripts\python.exe -B -m pytest tests/test_recommendation_contracts.py tests/test_update_service_import_contract.py -q -o addopts= -p no:cacheprovider`，結果 `15 passed`。另以不寫檔的 Python probe 確認上述四項反例均可建構。
- 審查未修改 production、測試或既有檔案；只新增本報告。未 stage、commit、push，未啟動其他 R-task，也不據此釋出 Wave 3。

AUDIT_STATUS: CHANGES_REQUIRED
