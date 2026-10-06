# H20C01 完整已保存母體研究列表

固定共同 base：`d222ba0dbd3e87991ba5404fec29470646af2c68`。唯一 dispatch：`output/plans/baldr_parallel_remaining_dispatch_20261007.md`。獨立分支 `lane/baldr-h20c01-research-20261007`，工作樹 `output/worktrees/baldr-h20c01-research`。

本包完成唯讀 readmodel 與實際消費它的獨立 Qt widget；未接 main／推薦工作區。模型日常研究的原保存輸出可依 gross 排序及 exact 下鑽返回，但中央 mount 尚未完成，不能宣稱全模型選股流程或全市場預測完成。效果未成熟不是本包工程阻擋；不變更正式／PIT／交易資格。

## Ownership 與回滾

只新增下列五檔，既有 producer、capture、outcome、推薦服務、main、config、shared DTO、Manual 與原 plan 全部唯讀：

| 檔案 | 類型 | 用途 | 回滾方式／風險 |
| --- | --- | --- | --- |
| `app_module/recommendation/personal_h20_research_cohort.py` | 新增 | 原 manifest 唯讀母體與排序 | 撤回本包 commit；中央接 consumer 後須同步撤回引用 |
| `ui_qt/widgets/personal_h20_research_widget.py` | 新增 | typed cohort consumer 與 exact selection | 同上；沒有預測資料寫入 |
| `tests/test_personal_h20_research_cohort.py` | 新增 | 原 public reader／時序／pins | 同上；只合成 QA |
| `tests/test_ui_qt_personal_h20_research_widget.py` | 新增 | offscreen 列表／返回 | 同上；只合成 QA |
| `docs/06_qa/BALDR_H20_RESEARCH_COHORT_20261007.md` | 新增 | 有限驗收與中央素材 | 同上；原資料無遺失風險 |

回滾步驟：先核中央 consumer 與未提交變更，再以 `git revert <本包完整commit>` 撤回本包；重跑其 focused tests。未執行回滾、清理或整合 dev/main。

## Frozen API

三個 `@dataclass(frozen=True, slots=True)` 沿 dispatch，沒有 additive 欄位：

```python
PersonalH20ResearchRow(
    symbol: str, status: Literal["available", "unknown"], reason: str,
    gross_return_bp: int | None, decision_date: str,
    source_date: str | None, feature_as_of_date: str | None,
    sample_id: str, prediction_id: str, capture_path: str, capture_sha256: str,
)
PersonalH20ResearchCohort(
    manifest_path: str, manifest_sha256: str, candidate_id: str,
    contract_hash: str, cycle_id: str, decision_date: str,
    symbols: tuple[str, ...], rows: tuple[PersonalH20ResearchRow, ...],
)
PersonalH20ResearchSelection(
    manifest_sha256: str, candidate_id: str, contract_hash: str, cycle_id: str,
    symbol: str, sample_id: str, prediction_id: str, capture_sha256: str,
)
read_personal_h20_research_cohort(
    manifest_path: str | Path, *, root: str | Path, expected_sha256: str,
    prediction_reader: Callable[..., Mapping[str, Any]],
) -> PersonalH20ResearchCohort
sort_personal_h20_research_rows(
    cohort: PersonalH20ResearchCohort, *, descending: bool = True,
) -> tuple[PersonalH20ResearchRow, ...]
PersonalH20ResearchWidget(parent: QWidget | None = None)
widget.set_cohort(cohort: PersonalH20ResearchCohort) -> None
widget.restore_selection(selection: PersonalH20ResearchSelection) -> bool
widget.researchRequested = Signal(object)  # 傳原 exact selection
```

`prediction_reader` 的 frozen call 為 `prediction_reader(pin["path"], root=store, expected_sha256=pin["raw_sha256"])`。中央 composition 必須注入原 `read_personal_current_observed_h20_capture`，並綁定既有可信 `source_verifier`／`contract_verifier`；不能換成直接 JSON reader 或重推論。API 零新增 ML imports。

## 原保存鏈與安全界線

- manifest 為原 `personal-h20-daily-manifest.v1` 的 raw pin，exact `root/h20_daily_receipts/<raw64hex>.json`；沿原 no-follow handle reader，最大 64 KiB，另核 plain／single-link、duplicate JSON keys、原 false 資格與同讀回 stat。
- `symbols` 必須是排序唯一完整分母，1–50 股；captures 不缺列、不重複身分，必須在 exact `root/h20_predictions`。manifest 自身 pin／scope 失配整份拒絕。
- 所有 row 逐次呼原 public prediction reader，各保存 capture 原 raw pin、sample／prediction 身分不變；reader 拒絕或缺件保留 `unknown` row 和原 pins，gross／source／feature 未知不補值。取消 `InterruptedError` 直接傳出，不交部分 cohort。
- 已讀回的 capture 模型、contract、cycle、decision、symbol、sample／prediction 失配拒絕整份母體；原 product projector 再核 aware clock、feature < decision、source <= decision。底層 public reader 持續核模型 version／來源／fit／lineage／cutoff／觀測時鐘，不用新快照更新舊預測。
- gross 原 `int` bp 排序，未知永遠後置，同值 symbol 升冪，升降序都不以 probability 推導 gross。無 float、重算、預測副本、新 canonical ID 或自然樣本重計。
- widget 使用 typed cohort 展示完整列表、日期、exact trace 及原因；未知不可啟動研究。selection 保留完整 frozen identity，刷新必須明示 exact restore；跨 cohort／model／cycle／hash／sample／prediction 或關閉回呼拒絕。
- widget 的 `set_cohort` 是同步 API，沒有自行啟 background reader。中央背景 worker **必須在呼此 API 前核對 generation、當前 manifest request 與 closing**；本包只驗 widget 舊 item／selection 和 close 回呼，不能宣稱已驗中央晚到 worker。不新增未凍結 token 參數。

Look-ahead 自查：僅讀原決策時已保存的 H20 output；排序 universe 固定為當份 manifest；沒有跨日標準化、未來價格、benchmark、交易或停損停利計算。保存日期與可得性均沿原 public reader，未取得的新 clock 不填回原樣本。

## focused 驗收與原失敗保留

所有執行使用主 checkout `.venv/Scripts/python.exe`、本包工作樹 cwd，`QT_QPA_PLATFORM=offscreen`、`PYTHONUTF8=1`。合成 fixture 放 package 外 Windows Temp；原 guard／ACL 不修改。

```powershell
python -m pytest tests/test_personal_h20_research_cohort.py tests/test_ui_qt_personal_h20_research_widget.py -q -o addopts= --basetemp C:/Users/archi/AppData/Local/Temp/baldr_h20c01_20261007_final --junitxml=output/qa/h20c01/focused-final.xml
python -m mypy --follow-imports=silent app_module/recommendation/personal_h20_research_cohort.py ui_qt/widgets/personal_h20_research_widget.py
python -m py_compile app_module/recommendation/personal_h20_research_cohort.py ui_qt/widgets/personal_h20_research_widget.py tests/test_personal_h20_research_cohort.py tests/test_ui_qt_personal_h20_research_widget.py
python scripts/quant_guard_linter.py
```

最終本包單次 **43 passed／7.95s**，無 skip。targeted mypy **2 source files、0 errors**；4 Python files compile 通過；quant precision／lookahead guard exit 0；`git diff --check` 通過。

初跑 sandbox 因 Windows ancestor no-follow handles 權限拒絕而 41 failed；相同 scope 授權後 38 passed／3 failed，三個失敗都在原 capture fixture 的 `source_changed_during_read`，未到本包 assertion。三個原 node 原樣重跑 **3 passed／1.60s**，未改 capture 或 verifier。補兩個本包取消／same-bytes-stat mutation 測試後，完整 43 最終一次綠。初跑、retry 與 delta raw／JUnit 全保留，數量不累加。

raw／JUnit 位於本包工作樹 `output/qa/h20c01/`，不提交：

| 產物 | SHA-256 |
| --- | --- |
| `focused-final.raw.txt` | `976bad1c9019ded5cf819f028738490ab4ca41b1c3290548be0bd47b0033f5cd` |
| `focused-final.xml` | `4b8ff7f67f71e94c40cadcdd436ea4851b9f6c8cbdad7f3da73c6b35cc5458de` |
| `focused.raw.txt` | `cc8f04f643e904739c5e2df6db7aec7c201fa76d3d1396eb27f9172d1149761f` |
| `focused.xml` | `e94784711d65f4d7a61b3b9fed7bc55b4e645d19116e09babe4fc0a22e3803f6` |
| `focused-retry.raw.txt` | `b7ddcbf7da6017b4f9053586ec87d31fc6855cf51d90fd072a3238b1e76cba2b` |
| `focused-retry.xml` | `b1377665d250952642c3c4a6d0ce3169fd8eac6aa2a69afef06edfe737f0c013` |
| `focused-delta.raw.txt` | `e6d9a560c6d8212041abcdb736059b369c800d99f8b5196a9c2411bae93a9d83` |
| `focused-delta.xml` | `72a959a1e8f40d641b22f8fae388c2d79879587bd6d226ad7c3327bbc180f378` |
| `mypy-final.raw.txt` | `0c37c4158c91ef55c724ba017bf6465f26018199badb08e3ff13f98acdf056c2` |
| `compile.raw.txt` | `b5d51295cb643989a05c341a1d43ffc7443a9a77d5bd16824b27c9705efb69bd` |
| `quant.raw.txt` | `87be6a99ac7beb04aa3fa6497b13b81b3bf6d4371887b667e6dc8c2a99681e3a` |

測試覆蓋原 writer/public reader→cohort→widget→exact click→兩次刷新→same cohort restore→新程序原 bytes 重讀／exact restore。1與50上限、missing/tamper/source unavailable unknown、排序同值與升降序、manifest scope/raw／capture identity／模型／cycle／date／clock／future feature/source、duplicate JSON／budget／hardlink、取消與stat mutation負例均含。未驗 foreground Native／真人使用或真資料自然成熟。

## 中央剩餘接線與 Manual 精確素材

中央保留 main、推薦工作區與返回路由。建議接線：在 existing product reference／activation 驗證後取得 exact manifest path/raw SHA 與 personal root，經既有 source／contract verifier 綁定的 public reader 呼 `read_personal_h20_research_cohort`；背景工作結果先核目前 request/generation/closing，再送 `widget.set_cohort(cohort)`。不自行挑 latest、glob、舊 cohort 或 fallback JSON。

接 `researchRequested(selection)` 時保存原 frozen selection 與原 manifest path，從當前已核 cohort exact 找原 row／capture，沿中央 existing research context router 下鑽。不得只以 symbol 取代 sample/prediction/capture hash。返回或新程序啟動先重讀同 manifest pin，通過後 `restore_selection(selection)`；false 必須清除返回選取並提示來源／cohort 已變更。新增 DTO 欄位或 router 改動由中央裁決，不屬本包。

Manual 待中央同步的可見入口與文案：

1. 進入中央接線後的「個人 H20 研究列表」，明確讀取原保存 manifest；顯示本份保存母體股數、決策日、模型、cycle、contract 與 raw pin。
2. 選「預測毛報酬由高到低」或「由低到高」。數值為原 H20 absolute/no-cost `int bp`，未知在末尾，同值按股票排序；不能當勝率／機率或原推薦分數。
3. 選取可核原預測的股票，再按「研究選取股票」或雙擊該列。下鑽使用完整 selection；返回只還原同一 manifest/model/cycle/sample/prediction/capture hash，不借其他股票或 cohort。
4. 來源／capture 缺件保留未知與原因；manifest pin／scope 不符整份拒絕。排錯先核原 raw pin、原 store、來源／模型 verifiers、日期／時鐘及 no-follow 權限，不放寬 guard、不補未知。
5. 完整范围僅此 manifest，未冒稱全市場。H20 gross 未扣成本，不是勝率；效果未成熟、成本後有效性未證明；高預測不代表值得買，不授自動交易。此包不重推論、不覆寫保存預測、不重計自然樣本。

中央完成 UI union 時才執行 Workbench→Update validator→full-roots mypy mandatory；本包依 dispatch 未重跑全倉 gate。新兩個 test 檔的 inventory/registry 同步由中央完成；本包沒有修改共用 registry。無 Task／ACL／真 DB write／資料搬移／push／main merge／清理／交易。
