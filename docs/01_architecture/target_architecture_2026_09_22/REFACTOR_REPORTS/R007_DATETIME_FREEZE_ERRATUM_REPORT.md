# R007 aware datetime 深凍結依賴勘誤報告

> 本頁的 PASS 只涵蓋 2026-09-22 aware datetime 深凍結勘誤；後續 timezone-name 別名修正見 [R007 SOL 驗收](R007_SOL_TZNAME_ACCEPTANCE.md)，整體波次狀態依 [R031 任務索引](../../../06_qa/R031_TASK_REPORT_INDEX_DRAFT_20260925.md)判讀。

日期：2026-09-22
狀態：`PASS`

## 問題與修正

R007 的 frozen records 直接保留 aware `datetime` 中呼叫者提供的 `tzinfo`。自訂 `tzinfo` 若在建構後改變 offset，既有 `Availability.available_at` 與 `MarketSlice.cutoff_at` 的時間解讀也會改變。datetime subclass 也能覆寫 `utcoffset()` 並掛載可變 slot；即使其 `tzinfo` 是 `timezone.utc`，原樣保留仍會讓 sealed offset 改變。`utcoffset()` 亦可能回傳帶 mutable payload 的 `timedelta` subclass；即使 wrapper 是 exact `datetime.timezone`，timezone 仍會保留並暴露該 offset 物件。另有 `MeasureUnit`、`Availability`、`SourceRef` 或 `SourceObservation` subclass 可帶 mutable payload，若被 nested contract 以 `isinstance` 接受，外部仍能改變 sealed graph。nonblank string 欄位也透過 `isinstance(str)` 接受帶 mutable payload 的 str subclass。`Availability.status` 的 `isinstance` 還會接受以 `__class__` property 偽裝成 enum 的 caller object。這些都違反 INV-08。

新增同一個 aware datetime 封存 helper，並套用於 `Availability.available_at` 和 `MarketSlice.cutoff_at`。只有 exact builtin `datetime`、時區精確型別為 `datetime.timezone` 或 `ZoneInfo`、且當刻 offset 是 exact builtin `timedelta` 時才原樣保留，以維持固定時區 identity、ZoneInfo 名稱與 DST 規則。其他輸入（包括 datetime subclass，即使攜帶可信時區）都複製成 builtin `datetime`；只在建構當刻呼叫一次 `utcoffset()`，並以固定 `timezone(offset)` 封存。若 offset 是 `timedelta` subclass，使用 builtin `days`／`seconds`／`microseconds` 描述器建立 exact builtin `timedelta`，不使用浮點換算。複製 datetime 時也透過 builtin 欄位描述器讀取底層 year/month/day/time/microseconds/fold，避免 subclass 覆寫屬性或 `replace()` 留下別名。結果保留當刻 wall-clock、microseconds、fold、offset、ISO 字串與 timestamp，不做時區轉換或 PIT／availability 重解釋。`SourceObservation.availability.available_at` 由同一 `Availability` 建構路徑封存。

`SourceObservation` 僅接受 exact `MeasureUnit`、`Availability`、`SourceRef`；`MarketSlice` 僅接受 exact `SourceObservation` 與 `SourceRef`。帶額外 mutable slot 的 subclass 在進入巢狀 sealed graph 前會被拒絕。

`_require_nonblank()` 改用 exact `str`，因此 `MeasureUnit.code`、`SourceRef.source_id`／`snapshot_id`、`SourceObservation.subject_id`／`fact_id` 不再保存帶外部 mutable payload 的 str subclass；原字串內容沒有轉換或重解釋。

`Availability.status` 改用 exact `AvailabilityStatus`，拒絕以 `__class__` property 偽裝 enum 型別並帶 mutable payload 的 caller object。

自訂 `tzinfo` 的 `tzname()` 不屬固定 offset snapshot 的保留範圍；ZoneInfo 和標準 `timezone` 的既有名稱語意保持不變。此處不新增 I/O、來源解讀、wire codec 或 consumer wiring。

## 驗證

- 新增 mutable `tzinfo` alias 回歸測試：offset 從 `+02:00` 改為 `+09:00` 後，直接 availability、巢狀 observation availability 與 market cutoff 均保留建構當刻的 offset、wall-clock、microseconds、fold、ISO 與 timestamp。
- 新增 datetime subclass alias 測試：即使 subclass 使用 `timezone.utc`，其動態 `utcoffset()` 與覆寫的 year/fold 屬性也不會留在封存值；輸出為 builtin `datetime` 並保留底層時鐘欄位與封存當刻 ISO/timestamp。
- 新增 mutable `timedelta` subclass 測試：涵蓋 datetime subclass 動態 offset 與包在 exact `timezone` 內的 offset subclass；sealed datetime 的 offset 是 builtin `timedelta`，原 payload mutation 不會穿透。
- 新增帶 mutable payload slot 的 nested record subclass 拒絕測試，涵蓋 unit、availability、source ref 與 observation。
- 新增帶 mutable payload 的 str subclass 拒絕測試，涵蓋所有 nonblank contract 欄位，並確認 observation graph 建構前拒絕 alias。
- 新增 `__class__` 偽裝型 status payload 測試，確認 Availability 建構時以 exact enum type 拒絕。
- 新增 ZoneInfo DST fold 測試，確認原 datetime／ZoneInfo identity、offset、名稱、fold、ISO 與 timestamp 維持不變。
- R007 與相鄰 R008 focused tests：`62 passed`。
- mypy：`Success: no issues found in 5 source files`。
- py_compile：market contract、R007 tests 與相鄰 R008 contracts 均 exit 0。

執行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_data_market_contracts.py tests\test_data_module.py tests\test_recommendation_contracts.py tests\test_r008_decision_numeric_enum_rework.py -q -o addopts= -p no:cacheprovider
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases data_module\__init__.py data_module\contracts\market.py data_module\contracts\__init__.py app_module\recommendation\contracts.py decision_module\recommendation\contracts.py
.\.venv\Scripts\python.exe -m py_compile data_module\contracts\market.py tests\test_data_market_contracts.py app_module\recommendation\contracts.py decision_module\recommendation\contracts.py
```

## SHA-256

| 檔案 | 修改前 | 修改後 |
|---|---|---|
| `data_module/contracts/market.py` | `A7C13F660268AB26AC20E6B2815B640863F3500911A8354B2B75F703BEBEA48A` | `6BE9FA87D9B3E49F75603CAD6F3263E27EEFE5942D2566902B7169FD752C3D84` |
| `tests/test_data_market_contracts.py` | `CAC3C9D8D6C9366568A23C03BB5916B9A6CD0A1D5E514C3F80DEA13AF4AF10DB` | `878113E6E7A92FC966FEA90D6A981613F8FCFBE80F3E051E5BCA73AF9FCC30B6` |

## 範圍與回復方式

本勘誤只修改 `data_module/contracts/market.py`、`tests/test_data_market_contracts.py`，並新增本報告。未修改 `data_module/__init__.py`、R008 contracts、provider、其他 R-task 或既有 dirty files；未 stage、commit 或 push。

兩個程式檔在本勘誤開始前已是未追蹤 R007 工作檔，不能用 `git checkout HEAD` 還原。若要撤回本勘誤，僅恢復 datetime／offset helper、status 與 nonblank validation、nested exact-class validation 和本次新增 regression tests 至上表的修改前 SHA；保留 R007 其餘內容與其他 R-task 變更。
