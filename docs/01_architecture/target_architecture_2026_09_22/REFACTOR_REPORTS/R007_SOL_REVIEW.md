# R007 SOL Review

## 結論

R007 在一次 `CHANGES_REQUIRED` 修正後通過。初版正確揭露 parent `data_module/__init__.py` eager imports 會破壞 leaf contract 的無 I/O import；SOL 判定這是可在既定架構內處理的窄 implementation conflict，允許 R007 獨占將原四個 public exports 改為 lazy exports。第二次 review 發現局部型別推斷造成兩個 mypy errors；worker 只加入 `value: object`，未改 runtime 行為。

## Scope 與架構核對

- 新增 `data_module/contracts/market.py` 與窄 `contracts/__init__.py`；無 provider migration、I/O、codec、ML schema 或 consumer wiring。
- `SourceObservation`、`MarketSlice`、availability、unit 與 source refs 為 frozen/slotted typed leaf records；沒有 `Any`、DataFrame、live connection 或 latest pointer。
- market fact 數值只允許有限 `Decimal` 或具名非浮點 scalar；沒有新增裸 `float` 核心計算。
- missing row、`value=None`、unknown availability 與 numeric zero 有分離測試；date-only availability 不補造 clock。
- `data_module/__init__.py` 只延遲原四個 exports，保留名稱、順序、`__all__`、class identity、direct/star import 與 ordinary submodule import。
- Import subprocess audit 證明 canonical contracts import 不載入 data loader/processor、yfinance、app/domain/ML/Qt，且不開 SQLite 或非程式檔。

符合 INV-02、INV-03、INV-04、INV-05、INV-08；未接 consumer，沒有提前開始 R018/R021/R023/R024/R010。

## SOL 驗證

```text
.\.venv\Scripts\python.exe -m pytest tests\test_data_market_contracts.py tests\test_data_module.py -q -o addopts= -p no:cacheprovider
```

結果：`13 passed in 0.57s`。

```text
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases data_module\__init__.py data_module\contracts\market.py data_module\contracts\__init__.py
```

結果：`Success: no issues found in 3 source files`。Changed Python `py_compile` 與 `git diff --check` 亦通過；diff-check 只有既有 LF/CRLF warning。

## Frozen review scope

- `data_module/__init__.py` — `D05D5275D2A4453FC4CF86B8F2D99FE611AEC98F610C58A8D63BA289A8825537`
- `data_module/contracts/__init__.py` — `C36C0AAB8805F98B9FCEABCF48BABDF68587704D0AB261CE1E2A9580E2860FE6`
- `data_module/contracts/market.py` — `A7C13F660268AB26AC20E6B2815B640863F3500911A8354B2B75F703BEBEA48A`
- `tests/test_data_market_contracts.py` — `CAC3C9D8D6C9366568A23C03BB5916B9A6CD0A1D5E514C3F80DEA13AF4AF10DB`
- `REFACTOR_REPORTS/R007_IMPLEMENTATION_REPORT.md` — `34D06DADD84FAF5441E278CBE21BC8A88370E863679798BDDB82BC8F6F5A492C`

`bare import data_module` 後直接檢查 module `__dict__` 的可見時點會改變；報告已明示此必要限制，`dir()` 與正式 public import paths 保持相容。沒有證據顯示這會阻擋下游；後續 wave 若新增依賴，仍須走 contract import guards。

REVIEW_STATUS: PASS
