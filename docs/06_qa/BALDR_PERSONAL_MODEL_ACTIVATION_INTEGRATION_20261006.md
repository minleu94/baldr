# 個人 H20 模型中央接線與真候選核對（2026-10-06）

本次接受原 H20 毛報酬 head 的精確讀取工程，尚未完成每日目前來源啟用。使用者已明示接受有限 BBANDS30 上軌比較與 H20 gross、希望真模型在每日個人研究中實際使用；自然績效成熟度不再作個人使用的工程門檻。原交易、正式 PIT、global promotion 等資格不因此提升。

## Coverage

| 文件 | 優先級 | 範圍 |
|---|---|---|
| 完整 Manual | Must | policy 路徑、preview、參數、結果、安全與排錯 |
| Snapshot | Must | 接受範圍與尚存 daily source 阻塞 |
| 現行 architecture | Must | 原 lineage reader、same-bytes loader、cutoff 分域 |
| Index | Must | 本文件、A02、activation preflight 入口 |
| 唯一原 product experience plan | Must | append-only；保留原文與 Stage／UX／例外 |
| Product／6M／version roadmap | 不修改 | 沒有新增 maturity gate 或競爭路線 |

## 可核交付

A02 原 `7b5f055d506f0f95777edd4dfaae7cd381f3666d` 採入中央 `25530d9d`；只有四新增檔。沿用 worker 固定 commit 64 focused 與 16 adjacent 收據，不累加成完整 App suite。

中央以可信原 fit 收據 `output/qa/pc-fit-v7/fit-v7-fe4e918b1257.receipt.json`，raw SHA256 `f5ca4372ba71ac3c006181ab0dcd4e2a56fdc62ba6529083cb63bbc7987a35b1`，核候選 `rec-cal-3f8b2c276ef316e28de3806d`。三個 scheduled legacy 候選仍缺 lineage，未修改或啟用。

`scripts/qa_prepare_personal_h20_gross_contract.py` 要求 caller 明示原 fit 收據與可信 raw SHA；讀回原 candidate／manifest／lineage 精確 bytes，注入原 `read_recommendation_training_lineage`，輸出 A02 typed contract 與原 blockers。它不讀 model artifact、不 deserialize、不 fit、不保存 policy 或修改 Task。raw hash 與 canonical manifest hash 分別保存，不混用。

中央真候選核對發現兩個 synthetic 未覆蓋缺口，已補：模型 `training_as_of=2026-05-25` 是原 final fold 截點；merged lineage cutoff `2026-06-26` 另以 additive `lineage_training_as_of` 精確綁定，candidate.training_cutoff 同核；晚於決策日拒絕。原 lineage canonical JSON 使用 `ensure_ascii=False`，中文內容不能改成 ASCII escapes 重算 hash。

實際 same-bytes 原 artifact `sha256:8890df64cb66d73af1b34755053d271dad4d38450bdb6e51578681e8684d7310` 載入後，對原 2026-09-28 保存特徵請求重播：2408=`1613 bp`、2454=`1963 bp`、3037=`1086 bp`，逐項等於原 ranking_score_bp。模型／manifest／candidate／lineage／fit 與請求收據 bytes、mtime、size 前後一致。不是新自然預測、不寫回原 capture，不冒稱目前正式 DB 已每日接通。

raw：`output/qa/baldr_real_model_intake_20261006/verified_existing_h20_saved_replay_final.json`；初次 cutoff 與 Unicode 拒絕證據保留。原候選 holdout Brier2730、null2500、落後230bp，after-cost 缺件；這些須揭露，不能用來無限延後已准個人使用。

中央 final A02 68 passed／4.45s（含四個新 cutoff／Unicode cases）；rebuild 工具 4 passed／0.97s；四 sources targeted mypy 0 error。pytest cache 寫入 warning 保留。對 main/config 的既有 mandatory 收據沿用：Workbench85 passed、validator25 pass／4 skip／0 fail、full roots841 sources0 error；此輪 A02 數量不代替將來 A01/A03 union。

## 操作與排錯

`PERSONAL_MODEL_POLICY_PATH` 或 TWStockConfig.personal_model_policy_path 明示絕對路徑；MainWindow explicit policy_config_path 優先，其次 config，最後原 AppConfigLocation 預設。配置欄位不自建 policy、不等於啟用；relative path 在來源 I/O 前拒絕。不要把 FA_Data 或 market DB 當私人 policy 目錄。

```powershell
.\.venv\Scripts\python.exe scripts/qa_prepare_personal_h20_gross_contract.py --fit-receipt <原fit收據絕對路徑> --fit-receipt-sha256 <獨立核准的原rawSHA256>
```

`scripts/scheduled/rebuild_personal_calibration_candidate.py --help` 列出來源、歷史期間、explicit symbols、max decision dates、cost bp、shared heavy-chain lock 與新 output 等必要參數；default preview 只讀，不訓練、不 lock／mkdir／發布。execute 工程保留原 capacity／shared lock／source guard；scratch 僅新 output/temporary，建立失敗也釋放 reservation。這次沒有 execute。

實際正式來源 replay preview 得0樣本：原 revision guard 自2014-01-02拒 historical PIT，diagnostics 原文保留。不得刪 marker、放寬 guard、補造 available-at 或 PIT；也不得把原9月24日 frozen snapshot 當每日目前行情。

可信候選對原 frozen source 的 source-time proposal=`proposal_ready`；對當前正式 DB 則 `training_source_time_training_rows_unbound`。剩下必須完成目前 current-restated observation 與 frozen training source 的明示分域，以及 A03 CLI 的真 lineage reader／contract 接線、自然結果與中央 union。新 gross trainer不是前置需求。

可逆回退：先撤新 policy path override 使用原路徑；原 rule-only／policy CAS 回退契約不變。不要刪原 receipt 假裝未曾推論或重新標記舊模型資格。本次不變更 Task、ACL、交易、真 DB、migration，也未 push／main merge。
