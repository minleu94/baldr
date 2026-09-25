# C1 R017 Option 2 Replay Bridge Readiness

## 狀態

- `OPTION2_SYNTHETIC_READINESS_PASS`
- SOL：`ACCEPTED_U5B_R017_OPTION2_SYNTHETIC_READINESS_ONLY`
- 獨立 Luna Max review：`ACCEPTED`，無 P1/P2
- C1：`REOPENED_CHANGES_REQUIRED`
- Wave 6：`BLOCKED`
- R017 production bridge、正式 annotation owner 與 TMP-REC-04 退場：留待 R020。

本報告只記錄 C1 U5b/R017 option 2 的隔離 readiness 測試。它不實作 R017 production bridge、不建立 canonical artifact、不啟動 Wave 6，也不代表 C1、formal ML 或 production readiness 通過。

## 驗證範圍與結果

新增 `tests/test_c1_replay_bridge_readiness.py` 與合成 fixture `tests/fixtures/c1_replay_bridge/r017_stored_annotation_snapshot.json`。Raw UTF-8 fixture bytes 為 2,563 bytes，SHA-256：`sha256:bea89c9d6e11e024a9a8481550e7161d1dc068b2e44a8db9038a130319215e3d`。Fixture 僅包含人工合成的兩列與固定時鐘／reference。

1. 測試 provider 注入 legacy recommendations，並經 `RecommendationReplayService.run_snapshot()` 取得外層 `RecommendationSnapshotDTO`。`RecommendationPortfolioBacktestResultDTO.to_dict()`／`from_dict()` roundtrip 後，snapshot date、候選順序、float score 型別和值、availability date/time、source refs 及 `stored_annotation` 都與輸入逐值相同。Annotation 固定為 `probability_bp=8123`、`model_version=historical-model-v1`、`source=stored-result`。
2. 測試在記憶體中建立 synthetic `RecommendationExecution`：row 僅用現有 `RecommendationItem` 的 `stock_code`、`stock_name`、`rule_score`、`indicator_score`、`reason_text`；Request/Context 保存 replay date、policy ref、decision/created/available clocks 與 source/data refs。child 中沒有 `stored_annotation`、ML projection/receipt refs 或 related parent refs；`RecommendationItem` 不接受 `stored_annotation`，`RecommendationExecution` 不接受 `parent_result_id`。隔離 `tmp_path` 保持空白，測試沒有呼叫 codec 或 persistence。
3. 負例透過 exact synthetic child-vs-pinned-fixture oracle 覆核 candidate 欄位、列順序、數值與其餘具名 row fields；annotation 與推測 parent ID 另由現有 typed constructor 拒絕。此 oracle 僅驗 synthetic child 相對固定 fixture 的一致性，不宣稱 production R017 bridge 會拒絕這些變異。

就此 option 2 樣本，現有 contract 可表達明確的 row、date、availability clock、source/data refs 與 policy ref，因此沒有需交 SOL 裁決的新增 owner blocker。`stored_annotation` 無對應 typed owner；Ruling 已選擇讓它只在 legacy outer dict 原樣透傳，不得投影成 ML 欄。`RecommendationDataFrameProvider` 的 production rows 沒有此 annotation 或 parent source；若 R020 前出現正式來源，須另指定 typed owner。此測試不聲稱 typed child 能保存任意 row-level availability/ref 擴充，也不將測試注入值視為 production source。

R005 characterization golden 未修改；其原有 annotation passthrough test 作為基線執行。測試僅用 synthetic DataFrame 和 `tmp_path`，沒有存取或寫入正式 `DATA_ROOT`。

## 初版驗證命令

```text
.\.venv\Scripts\python.exe -m py_compile tests\test_c1_replay_bridge_readiness.py
```

結果：通過。

```text
.\.venv\Scripts\python.exe -m pytest tests\test_c1_replay_bridge_readiness.py -q -o addopts=
```

結果：`6 passed`。

```text
.\.venv\Scripts\python.exe -m pytest tests\test_recommendation_replay_characterization.py -q -o addopts=
```

結果：`13 passed`。

初次兩檔合併重跑結果：`19 passed`。manifest 補強後的新結果見下節。沒有 stage 或 commit。

## Fixture manifest 與原始 bytes readback 補強

新增 `tests/fixtures/c1_replay_bridge/fixture_manifest.json`，固定 `fixture_id`、相對檔名、原始 UTF-8 bytes 長度及 SHA-256（manifest 為 1,524 bytes，SHA-256 `sha256:836f67e51e770d160cfd60efda16bbacee160db4ea0def523ce15bf29150ee0a`）。格式明記為無 canonical execution envelope 的 legacy replay snapshot JSON，`schema_version` 與 `schema_revision` 為 `null`。Manifest 另固定合成 child/policy/data/source/profile opaque IDs、as-of/decision/created/available clocks，並明示 fixture-only annotation injection、production annotation source unknown、parent ID/source unknown、非 canonical ML artifact。

測試先從 manifest 載入 expected byte length/hash，驗證原始 fixture bytes 後才 decode JSON；metadata 也與 fixture 中的 opaque IDs、clocks、synthetic source refs 和 unknown flags 交叉核對。Outer DTO 測試把 `to_dict()` 結果序列化成 UTF-8 JSON bytes，再 `from_dict()` readback，逐值比較 annotation、候選順序、數值型別、availability 與 source refs；roundtrip/readback 後再次讀取原 fixture 並斷言 bytes、長度和 SHA-256 均不變。這個 pinned SHA 只固定合成測試輸入，不是 production legacy artifact 的 trusted historical hash。

另新增具名 `_assert_child_matches_pinned_fixture_oracle`，同時由正例與負例呼叫。Oracle 逐欄比對 child result ID/status、Request policy/date/limits、Context policy/data/source refs 與時鐘、row 數量及順序、每列 stock code/name、Decimal `rule_score`／`indicator_score`、`reason_text`，並確認沒有未列入 fixture 的 parent/ML references。六種負例（stock code、順序、stock name、rule score、indicator score、reason text）均以 `pytest.raises(AssertionError, match="differs from pinned fixture")` 證明此 synthetic oracle 明確拒絕差異。這只驗 synthetic child 對 pinned fixture 的一致性，不是 production R017 bridge rejection；真 bridge 留待 C1 後 R017 task。Typed child 仍只保存已知 row/date/policy/source 欄位，不增加 annotation 或 parent source；沒有寫 canonical artifact。

本次補強後驗證：

| 命令 | 結果 |
|---|---|
| `\.venv\Scripts\python.exe -m pytest tests\test_c1_replay_bridge_readiness.py tests\test_recommendation_replay_characterization.py -q -o addopts=` | **22 passed**（R017 9、R005 13） |
| `\.venv\Scripts\python.exe -m py_compile tests\test_c1_replay_bridge_readiness.py` | **通過** |

兩項命令使用 `\.venv\Scripts\python.exe` 執行；未啟動 scheduler、正式資料或 live ML。未 stage 或 commit。

## SOL 接受範圍

SOL 僅接受 U5b/R017 option 2 的 synthetic readiness；獨立 Luna Max review 無 P1/P2。此接受不包含 R017 production bridge、不賦予正式 annotation typed owner，也不退役 TMP-REC-04。C1 仍為 `REOPENED_CHANGES_REQUIRED`，Wave 6 仍為 `BLOCKED`；後續正式 annotation owner 與 TMP 退場由 R020 負責。

## 回滾清單

| 新增檔案 | 回滾方式 | 回滾風險 |
|---|---|---|
| `tests/test_c1_replay_bridge_readiness.py` | 以 `Remove-Item -LiteralPath tests/test_c1_replay_bridge_readiness.py` 移除 | 無；只移除此切片新增測試 |
| `tests/fixtures/c1_replay_bridge/r017_stored_annotation_snapshot.json` | 以 `Remove-Item -LiteralPath tests/fixtures/c1_replay_bridge/r017_stored_annotation_snapshot.json` 移除 | 無；只移除此切片新增 fixture |
| `tests/fixtures/c1_replay_bridge/fixture_manifest.json` | 以 `Remove-Item -LiteralPath tests/fixtures/c1_replay_bridge/fixture_manifest.json` 移除 | 無；只移除此切片新增 fixture manifest |
| 本報告 | 以 `Remove-Item -LiteralPath docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/C1_REPLAY_BRIDGE_READINESS_REPORT.md` 移除 | 無；只移除此切片新增報告 |
