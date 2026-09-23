# 2026-09-22 價格修訂候選資料與重訓 Gate

> 結論：E 隔離資料復原與 868 列來源 custody 已完成；本輪不能安全產生成熟 fit rows，故未開始訓練。此結果只適用於 2026-09-22 這次資料修訂與已核查的訓練入口。

## 事件與隔離復原

5/20 的價格修訂 receipt 有 868 個股票列，修訂值於 2026-09-22 才取得；`available_at=null`、`historical_decision_time_available=false`。其後 9/22 technical publication 的 `updated_stocks` 包含 0050，且增量 writer 會對 120 個交易日 lookback 刪除後重寫 technical rows。0050 在 2026-05-20 至 2026-09-22 有 88 個交易列，落在該區間。現存 technical 值與 repair plan 不一致，price row 則仍符合 final price receipt。獨立固定鍵抽查與 tracked full-window verifier 證實 E snapshot 需要按 sealed plan 復原；這不是價格修訂回退證據。

E run01 保留 publication 後的原貌，SHA-256 為 `899e8d0eac9390c4863d21dd24996106720bc4f6e3f66f8ff6321987465b6b84`。在 run02 的隔離 SQLite 複本內，recovery 只更新 technical repair plan 涵蓋的 75,442 個 affected rows，其他 5,186,211 列的 digest 保持不變；price table、正式 DB 和模型均未寫入。run02 復原後 SQLite SHA-256 為 `38ab1d1dfd201285ed6d8e3bce477b06f021bf6a08397ba369648d67dcbc35c`。tracked 全窗口 readback 驗證 1,277,135 個 after cells、2,117,755 個 untouched cells，皆零 mismatch；SQLite `quick_check` 通過。verifier evidence SHA-256 為 `1e3fc58f984e89126ed6d8e3bce477b06f021bf6a08397ba369648d67dcbc35c`。Recovery receipt body hash 為 `ed9b17b284e1f5c88fe88328ae58606c4a008385026f4410a3090bd18b7786d2`；receipt 檔案 SHA-256 為 `0cb77390e483f427e52005cfbf768b02811fc2463c1fbcdf54eb6c2362a5c767`。

**不得把 E run02 DB 複製覆蓋正式 D SQLite。** 這次流程沒有 D 寫入 API／路徑，只有唯讀抽查。D 當時 WAL 非空（19,969,672 bytes），main-file hash 不等於完整 SQLite logical snapshot，因此本 QA 不宣稱 D 在整段期間未變，也不宣稱正式 D 已持續修好。9/22 writer 的重覆覆寫防護涉及 `app_module/update_service.py`，該檔屬 R028 重構專責；本任務不修改它。正式 source acceptance 與 writer 協調仍是後續阻礙。

## 候選來源 artifact 邊界

隔離 artifact 位於：

`E:\codex_ml_price_rebuild_20260922_luna\artifacts\revision_20260922_run02\research_source_dataset\runs\7e2f19cc5a00f20ba5b3890a`

封存副本：`D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna`。此處 transfer receipt SHA-256 為 `c0e0cb823d172c052db201351d7db0dc3d170f6b436003d37d4815ce28015fe4`；26 檔、11,326,481,197 bytes 已逐檔 hash/readback。原始 E 路徑只保留作 provenance。Dataset ID 為 `research_shadow_daily_price_revision_recovered_source_20260922`；manifest SHA-256 為 `f9a19b704fab86d0701091073d74353dec51dd1a8d3902fc46a6fb24ec1ba772`，rows SHA-256 為 `506f464d92ead313c4fc0d15eaa4eb490b553e86e084701f7d4e93c34e796fb4`。868 列中 865 列有完整 OHLC，3 列（1538、2321、5906）缺 OHLC，明列 `missing_ohlc_excluded_from_fit`，未補值或靜默剔除。0050、1256、1477 抽樣均為 `late_obtained`、`historical_available_at=null`。manifest 記錄 `feature_contract_status=not_assessed`、`labels_materialized=false`、`label_maturity_status=not_materialized`、`model_training_input_compatible=false`；因此這是修訂來源證據，不是訓練 rows。

## 既有訓練入口與 bounded 動態拒絕

以 E run02 snapshot 作為 `check_daily_price_source_revision` 的 `database_path`，並**顯式傳入**正式 D 來源的 repair receipt 目錄 `D:\Min\Python\Project\FA_Data\output\scheduled\daily_price_repair_receipts\20260520\historical_price_spike_20260921`。E snapshot 自身不含自動搜尋路徑下的正式 receipt；這項傳入是明示的來源修訂 gate，不代表 E DB 有正式 receipt。2026-09-22 cutoff 對 0050、1256、1477 都回報 `DailyPriceSourceRevisionError`，錯誤指出 2026-05-20 修訂 receipt 仍阻擋該 PIT prefix。receipt 的 pending marker 不能單純刪除或略過；需由 revision-aware prospective acceptance 另行證明新的決策時間、來源版本、affected coverage、特徵與標籤依賴，不可回填舊 `available_at`。

動態結果保存在 `E:\codex_ml_price_rebuild_20260922_luna\artifacts\revision_20260922_run02\evidence\revision_training_gate_probe.json`，檔案 SHA-256 為 `c54224d68bec7f5e137e599144059becf339b4383475c778e9e1819f9e12c088`，exit code 0（probe 成功捕捉預期拒絕）。它綁定 E snapshot SHA `38ab1d…898771`、price pending SHA `f60fe67d82930280f3ce76d8a0a3e0dd4b0f28e00fa48900e86f0fa1bf8b19b7`、final price receipt SHA `a157a401b21f3eaac8ae82fd21859161f37acc277fcd3d26a0614ccb6a6d280f`、dataset manifest/rows hash 與 gate/validator/CLI 的程式 SHA。probe 只讀 receipt JSON、dataset 檔與 E snapshot bytes；沒有執行 fit、載入或反序列化模型，也沒有 SQLite 寫入。

訓練入口的契約與結果：

- `scripts/build_ml_pit_year_shards.py` 經 `PITYearShardExporter.build` 呼叫相同修訂 gate；本次 cutoff 在 5/20 之後會 fail closed。
- `scripts/build_portfolio_ml_ooc_from_raw.py` 與 `scripts/train_ml_allocation_out_of_core.py` 是 Raw PIT → OOC 的正式鏈。OOC loader 要求 store 完整、`formal_source_only=true`、`research_shadow_included=false`，且逐列 PIT/T-1 契約已重驗；它不能把本 custody artifact 當 input。
- `scripts/train_ml_research_shadow_challenger.py` 呼叫 `validate_research_training_publication`，只接受註冊的 research union manifest identity 及其完整 shards。對本 artifact manifest/rows 的 bounded 呼叫回 `ValueError: unsupported research union manifest schema`。即使通過，它仍要求特定的 formal/shadow raw、base training shards 與成熟 horizon labels；本 artifact 不符合資料形狀或身份。

故目前 frozen-source chain 不能在不碰 15 條 frozen ML source、也不補造歷史 availability 的條件下，從本次修訂資料產生安全可訓練 rows。既有兩個修復前模型保持 quarantine：derived h5 SHA `aa152ebb8e8d7913a6a2274a0526620d8b8ce151a5f667d8de446df9724c895c`、bounded operational SHA `92668aa574967990fa560aef8a48e595296eb22f3fef2a4264cff08210d78b6d`。改用舊訓練產物不會使它變成 corrected-source 模型。

## 可以平行做與重訓前置

可與大型重構平行進行的工作限於：E 隔離工作樹中的 receipt/source custody、revision-aware research QA、測試、文件，以及不改 frozen source contract 的設計審查。這些工作不得清除 pending、改正式 gate、寫 D SQLite、替換既有 shadow/production 模型或授予正式 PIT／OOS credit。

安全重訓至少需要一條明確接受 revision lineage 的新候選建置路徑：以新 identity 重建受影響的 price/technical rolling 依賴窗口；保留實際 observed/available time 與 late-obtained 標記；逐列核對 feature schema、順序、dtype、缺值政策；再依既有 label registry 建立完整 horizon labels，只有在 horizon 自然到期且 availability 可驗後才納入 fit。2026-09-22 之後的新 prospective rows 仍須等待 label horizon 成熟。完成後只能先寫至新的 research/shadow candidate output，並以獨立 OOS/功能評估作候選；正式 PIT、promotion 與 production 旗標仍保持 false，直到既有 owner gate 明確通過。

E 的 run01/run02 artifacts 已移轉至 D 上述 `research_only/non_release` 目錄；transfer receipt 保留每檔原路徑、目的相對路徑、size 與 SHA-256，並標示內嵌 E 絕對路徑仍是 provenance。移轉沒有改寫原 receipts 或 manifests。原 E 任務根目錄 `E:\codex_ml_price_rebuild_20260922_luna` 已依使用者明確授權清除；D archive 與 `codex/luna-price-revision-research-20260922` task branch 保留。

## 2026-09-23 prospective research acceptance preview

late-obtained 修訂歷史可另行評估是否作為「未來 research/shadow 預測」的訓練例；本 preview 沒有政策性地宣稱此路徑永遠禁止。它與 5/20 當時 PIT 是不同主張：修訂資料的歷史 `available_at` 仍為 null，故 `historical_pit_eligible=false`，不得把更正後的值當作當時已知。未來候選仍須完整重建所選模型的 feature dependency，並對每列／每個 horizon 分別證明交易日序列的 `horizon_end_date` 及來源提供的 `label.available_at <= training_as_of`。日期經過只能協助推得 horizon end，不能替代 label availability 證據。

以權威 v2 source run `7e2f19cc5a00f20ba5b3890a` 執行 preview；其 manifest SHA-256 為 `f9a19b704fab86d0701091073d74353dec51dd1a8d3902fc46a6fb24ec1ba772`、rows SHA-256 為 `506f464d92ead313c4fc0d15eaa4eb490b553e86e084701f7d4e93c34e796fb4`。Preview command 為：

```powershell
$TrainingAsOf = [DateTimeOffset]::UtcNow.ToString('o')
.\.venv\Scripts\python.exe scripts\preview_ml_daily_price_revision_acceptance.py `
  --archive-root 'D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna' `
  --training-as-of $TrainingAsOf
```

本次 `training_as_of=2026-09-23T01:08:04.2782728+00:00`，exit `0`；狀態是 `preview_complete_candidate_not_accepted`，不是重訓，也沒有建立訓練 rows。868 列中 865 列 OHLC 完整，1538、2321、5906 三列缺 OHLC，仍保留明確排除狀態。每列標示 `late_obtained=true`、歷史與 exact source `available_at=null`，另列 custody observation；這個 observation 只證明封存 artifact 在該時間已存在，不充當權威 source availability。

本次 preview 對 D archive 的 transfer receipt SHA-256 `c0e0cb823d172c052db201351d7db0dc3d170f6b436003d37d4815ce28015fe4` 驗證通過。它檢查全部 26 項 inventory 的存在與 size，並重新計算 12 個選定來源檔的 content hash，包含 run02 SQLite snapshot、v2 manifest/rows、price/technical receipts、recovery receipt/diff/row hashes、tracked verifier 與既有 negative gate probe；**沒有重新計算全部 26 個封存檔案的 content hash**。正式 gate probe 沿用封存證據，0050／1256／1477 仍是 `DailyPriceSourceRevisionError`；research union validator 仍以 `ValueError: unsupported research union manifest schema` 拒絕該 custody schema。Preview 本身不呼叫該正式 gate。

本次沒有 feature registry/model family 綁定、全訓練期間 corrected rolling-feature 依賴重建證據、特徵名稱／順序／dtype／缺值契約比對，也沒有 materialized horizon labels 或來源 `available_at` 證據。輸出將 horizon end 與 label availability 分開留為 pending，因此 `future_research_candidate_accepted=false`、`model_training_input_compatible=false`。所有 formal/OOS/PIT/promotion flags 保持 false、`production_alpha_bp=0`；未載入模型、未 fit、未寫 DB。

重現輸出原始位置為隔離 worktree ignored QA 路徑 `output/qa/revision_aware_acceptance_preview/runs/ed46d5a9c542218ed1f62c85/acceptance_preview.json`，SHA-256 `ab84f636914f650bb7b9f5e69bfa4eabb990311041b002d54b3369cee78f0875`。為在移除暫存 worktree 後保留唯一真實 preview，create-only 副本位於 `C:\Projects\PythonProjects\technical_analysis\output\qa\revision_aware_acceptance_preview_archive\acceptance_preview.json`；逐檔 readback SHA 相同。副本 transfer receipt SHA-256 為 `80f344a0f10c3461076a7a7889838038fa9dd5626ca1053dbc3905f2c419be0b`。這些輸出仍是 ignored QA artifact，不提交 Git。R027 仍只負責隔離驗證；R028 負責 technical writer/orchestration 遷移，不承接此 revision-aware acceptance 或訓練資料／fit。

原始 worktree output 路徑只在該 linked worktree 存在時有效；永久 preview 副本與 transfer receipt 位於主 repo ignored archive。保留的 D archive/run01/run02 receipts 與此 preview 都是 research-only/non-release，不是模型重訓結果。

focused synthetic tests：`python -B -m pytest -q -o addopts= -p no:cacheprovider tests/test_ml_daily_price_revision_acceptance_preview.py`，`4 passed`。測試涵蓋 late-obtained／label pending positive summary、錯誤 transfer hash 拒絕、捏造 historical `available_at` 拒絕及輸出不得覆寫。
