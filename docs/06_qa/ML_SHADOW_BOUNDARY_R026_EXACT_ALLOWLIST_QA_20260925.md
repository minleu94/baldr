# ML shadow boundary R026 精確匯入允許清單 QA（2026-09-25）

## Current addendum：C3 兩個 R026 provenance edges（2026-09-25）

C3 relevant-suite route 為 **2443 passed／4 failed／5 skipped／35 warnings**，執行 650.48 秒；471 個 source fingerprints 前後 unchanged。log `<USER_HOME>\AppData\Local\Temp\c3r_f7acc5\pytest.log` SHA-256 `194C7460A1AD7DD2AD6D030FFB077352FCAA884E40AC5E485987DFBC10BC3168`。C3 guard 掃描 584 個檔案，看到 13 個 diagnostic occurrences：原有 Restated/allocation 11 個，以及兩個 R026 preparation／receipt 語意所需的新 exact imports：

- `app_module/recommendation/prepared_runtime_preparation.py` → `ml_module.recommendation_inference_provenance:RecommendationProvenanceError`，用於維持 preparation source-contract 缺檔的既有例外語意。
- `app_module/recommendation_service.py` → `ml_module.recommendation_inference_provenance:verify_inference_provenance`，用於維持 receipt 前既有 provenance 驗證。

這兩項不是既存 baseline。`MLShadowBoundaryGuard` 只在各自 source path 的 allowlist 加入對應 symbol；正例驗證兩個精確邊，負例驗證 preparation 不可借用 service-only verifier，且 wildcard import、整個 module import、service 未列 symbol 仍被拒絕。修改後直接掃描仍是 584 個檔案，diagnostics 回到原有 **11 occurrences／10 distinct**；上節表格中的 11 個具名 Restated/allocation owners 均未更動。

fresh isolated TEMP focused route 執行 `tests/test_ml_shadow_dependency_boundary.py`、`tests/test_ml_shadow_boundary_cli.py`、`tests/test_r030_architecture_guards.py`、`tests/test_r030_extensibility_acceptance.py`：**30 passed／2 failed**。兩個失敗僅為 repository-wide guard 與 CLI 對原有 11 個 diagnostics 的既有 aggregate assertion；所有精確 allowlist 正／負 fixture 及兩個 R030 files 通過。log `<USER_HOME>\AppData\Local\Temp\msx_4ebc28\f.log` SHA-256 `CA68D74B90B070A4F05343F1B5F8320F5860AC0B62C172C8A48AE8EF7A850FB6`。

本輪 frozen source SHA-256：`ml_module/shadow_boundary_guard.py` `1E5E4AF198A9FC2FEC0AAF1A35786701F94734B245C98212A9349D75D594A4A9`；test SHA-256：`tests/test_ml_shadow_dependency_boundary.py` `3C0408DD7C810E6F9AD183CD36370AA278FEE2063391E571D3589C688FC9B59F`。`mypy ml_module\shadow_boundary_guard.py` 為 1 source file／0 issues；`py_compile` 對 guard 與 test 通過；`git diff --check` 通過。原有 11 項 baseline 仍需由具名 Restated/allocation owners 收口；本 addendum 不把兩個新 allowlisted edges 稱為 baseline，也不擴成模組層級允許。

## 結果與範圍

本次只把已審查的 R026 app→ML leaf imports，以及既有 R012/R015/R016 inference readback edges 加入 `MLShadowBoundaryGuard` 的精確 `module:symbol` 清單與合成正／負例。沒有使用模組層級 broad allowlist，也沒有調整 repository-wide assertion。

合成 fixture 的 12 個正／負例測試全數通過；repository-wide guard 測試仍因既有 Restated/allocation imports 回報 11 個 diagnostic occurrences（10 個 distinct diagnostics）而失敗。這些殘留維持明確 baseline，不能將本次結果寫成整個 guard 已通過。未修改 Restated/allocation source，也沒有以放寬 assertion 來消除殘留。

R026 精確允許範圍涵蓋 prepared input/source contract、historical custody/preparation、model resolution、calibration/inference provenance，以及 inference projection receipt 的已驗 readback caller。每個允許的 symbol 有正例；同一 leaf module 的未列 symbol 仍須由負例拒絕。`prepared_runtime_preparation` 對 `data_module` 的兩個 imports 不屬於此 guard 的 app→ML allowlist；沒有因此擴大 `data_module` 規則。

## 再現命令與執行收據

工作目錄：`C:\Projects\PythonProjects\technical_analysis`

新建隔離根目錄：`<USER_HOME>\AppData\Local\Temp\mlshadow3_5aa7f4a3`

執行前將 `PROFILE=test`、`DATA_ROOT`、`OUTPUT_ROOT` 指向該隔離根目錄下新建的合成資料目錄，並將 `TEMP`、`TMP` 指向隔離根目錄；pytest basetemp 為隔離根目錄下的 `p`，Python bytecode cache 為隔離根目錄下的 `pycache`。完整 pytest 命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ml_shadow_dependency_boundary.py -q -rs -o addopts= -p no:cacheprovider --basetemp <USER_HOME>\AppData\Local\Temp\mlshadow3_5aa7f4a3\p --tb=short
```

結果：`1 failed, 12 passed in 3.17s`。失敗項目是 `test_repository_respects_ml_shadow_dependency_boundary`，其唯一失敗原因為下表列出的既有 11 個 occurrences；12 個 fixture 正／負例全部通過。pytest console log 位於 `<USER_HOME>\AppData\Local\Temp\mlshadow3_5aa7f4a3\pytest.log`，SHA-256：`908A3F16439A61C242F28D1B97378655FDDEF83206D81D6D2212C6674D5D05B0`。

靜態檢查亦已完成：

- `mypy ml_module\shadow_boundary_guard.py --cache-dir <隔離 TEMP cache>`：成功，1 source file，0 errors。
- `py_compile ml_module\shadow_boundary_guard.py tests\test_ml_shadow_dependency_boundary.py`：成功；`PYTHONPYCACHEPREFIX` 指向隔離根目錄。
- `git diff --check -- ml_module/shadow_boundary_guard.py tests/test_ml_shadow_dependency_boundary.py`：成功，無 whitespace errors。
- 直接執行 `MLShadowBoundaryGuard(Path.cwd()).inspect()`：檢視 583 files，11 occurrences，10 distinct diagnostics。

## 已保留的 repository-wide baseline

| Guard 診斷 | 精確 import site | 具名責任範圍 |
|---|---|---|
| `ml_imports_production_path` | `ml_module/restated_h5_training_runner.py:1285`、`:2022` → `app_module.allocation_release_adapter`（兩個 occurrences） | Restated H5 training runner 與 allocation release adapter 的反向依賴；依 R030 architecture-boundary owner 收口。 |
| `production_imports_ml_module` | `app_module/allocation_release_adapter.py:38` → `RestatedResearchInputBinding` | Allocation release adapter／Restated research input contract owner。 |
| `production_imports_ml_module` | `app_module/bounded_restated_shadow_service.py:19` → `require_compatible_market_sources` | Bounded Restated shadow service／market-source contract owner。 |
| `production_imports_ml_module` | `app_module/ml_allocation_inference_service.py:1676` → 私有 `_ConstantProbabilityModel` | ML allocation inference/release 與 Restated research contract owner。 |
| `production_imports_ml_module` | `app_module/ml_allocation_inference_service.py:1677` → 私有 `_ConstantRegressionModel` | ML allocation inference/release 與 Restated research contract owner。 |
| `production_imports_ml_module` | `app_module/ml_allocation_inference_service.py:42` → `RESTATED_RESEARCH_PROFILE` | ML allocation inference/release 與 Restated research contract owner。 |
| `production_imports_ml_module` | `app_module/ml_allocation_inference_service.py:43` → `RestatedResearchInputBinding` | ML allocation inference/release 與 Restated research contract owner。 |
| `production_imports_ml_module` | `app_module/ml_allocation_inference_service.py:588` → `require_compatible_market_sources` | ML allocation inference/release 與 Restated market-source contract owner。 |
| `production_imports_ml_module` | `app_module/ml_allocation_inference_service.py:44` → `research_rows_hash` | ML allocation inference/release 與 Restated research contract owner。 |
| `production_imports_ml_module` | `app_module/restated_allocation_shadow_service.py:14` → `require_compatible_market_sources` | Restated allocation shadow service／market-source contract owner。 |

這是 ML shadow guard 的 Restated/allocation baseline，不等同 R030 文件所稱既有四項 Direct boundary violations；兩組須各自分帳。R030 尚未完成時依 R030 task 保留具名 owner，不能為求綠燈擴成整個 `ml_module` allowlist。

另外，R030 preflight 曾指出 `data_module/company_registry.py:11` 與 `data_module/tpex_daily_price_backfill.py:17` 對 `FactorDiagnostic` 的反向 import，以及 `decision_module/industry_mapper.py` 的 `DBManager` I/O。它們不是上述 11 個 shadow guard diagnostics，須依 R030 authority 另行追蹤。

## Bytes custody

| 檔案 | bytes | SHA-256 |
|---|---:|---|
| `ml_module/shadow_boundary_guard.py` | 14,800 | `48074B1F4F5A73737530A409F18E5BFCC91D6A70F2A0750F2813ADA5EA7B1D05` |
| `tests/test_ml_shadow_dependency_boundary.py` | 13,205 | `550C09EE88A75F86751F92B893823630C64D4066FE1CA707DB2D286BF71600CE` |
| pytest log | 683 | `908A3F16439A61C242F28D1B97378655FDDEF83206D81D6D2212C6674D5D05B0` |
