# 重構風險登錄表

> Risk owner 是負責產生證據與停止條件的 task，不代表可自行變更架構。任何風險觸發 rollback／blocker時，先保留差異，再由 program manager決定下一task。

| ID | 風險／觸發訊號 | 影響 tasks | 預防與偵測 | 停止／回滾條件 | Owner |
|---|---|---|---|---|---|
| RK-01 | 推薦計算、filter、ranking、order語意漂移 | R002,R011,R018,R019,R020 | 固定輸入golden/手算、同mode exact parity、stable sort/tie-break | 任一未核准差異即停止該slice | R002基線；各實作task |
| RK-02 | Decimal quantum、legacy float、null/zero或rounding改變 | R002,R008,R009,R019,R029 | Decimal字串、不經float中轉；TMP-NUM-01；極值/unknown tests | bytes/value/order差異未解釋即rollback | R002/R009/R019 |
| RK-03 | execution仍依賴共享last_*，A/B run互相污染 | R003,R011,R013-R015,R029 | A→B→save A、invocation capture、nested mutation、repo search | execution無法獨立重讀或跨run混合 | R003/R011 |
| RK-04 | schema-driven codec漏欄、舊reader截斷新revision | R009,R012,R030 | fields-based codec、revision dispatch、unknown reject、all-field test | 新artifact可被少欄reader回存或hash不穩 | R009 |
| RK-05 | JSON artifact／SQLite index不一致或舊replace覆寫 | R004,R012,R014,R015 | exclusive create、same-hash idempotency、orphan recovery、index rebuild | 同ID異hash可覆寫或失敗後重算 | R012 |
| RK-06 | 歷史artifact／DTO／中文keys無法讀 | R004,R009,R012,R016,R029 | 永久decoder、old bytes fixtures、先驗hash | unknown bytes遭修改/刪除或read view重寫原檔 | R009/R012 |
| RK-07 | replay被「共用」後偷偷採interactive政策 | R005,R017,R020 | 各mode獨立oracle、versioned policy、future-row/date tests | replay score/candidate/lookback差異未核准 | R020 |
| RK-08 | temporary dual architecture永久存在 | R001,R011,R017,R025,R029 | 每個TMP有creator/remover/caller/exit；Wave 9搜尋 | 無deletion owner、兩engine都可寫正式結果 | R001/R029 |
| RK-09 | dependency cycle或廣泛re-export在import時觸發I/O | R007-R010,R021-R025,R030 | leaf import smoke、module DAG、窄re-export支援期 | 新data↔decision/app cycle或import side effect | R030；各boundary task |
| RK-10 | factor source解碼與domain語意分離後值／quality漂移 | R023,R024,R019 | 同標準facts→原FactorRecord、unit/date/missing tests | factor值/diagnostic/source custody差異 | R023/R024 |
| RK-11 | Regime I/O抽離消失confirmation/cooldown或保存時重查 | R022,R012,R013 | 多日/same-day/historical tests、execution-time snapshot | state transition或run A保存結果改變 | R022 |
| RK-12 | Strategy relocation產生雙registry、import break或不同signal | R025,R029 | ID/meta/signal exact tests、caller inventory、TMP-STR-01 | registry可分歧、UI直接讀private registry未遷移 | R025 |
| RK-13 | UI顯示／保存不是同一execution，stale callback覆蓋 | R003,R013,R031 | request correlation、last-good、cancel/save tests | cancelled/old run顯示或保存成新run | R013 |
| RK-14 | Scheduled clock/calendar/candidate publication順序改變 | R014 | wrapper/calendar custody tests、save-before-forward assertion | clock/source custody或side-effect順序改變 | R014 |
| RK-15 | Personalization result/receipt/ACK identity不一致 | R015,R026 | exact readback、candidate/model hash、CAS/retry tests | ACK掩蓋save、retry重算或降級舊personal result | R015 |
| RK-16 | ML feature order/dtype/scale/mask/transform失效 | R006,R010,R026,R030 | ABI inventory、loader/feature tests、new feature opt-in | 舊model input或prediction parity改變 | R006/R026 |
| RK-17 | ML provider在infer中暗讀更新中的DB造成race | R010,R026 | PreparedMLInput、update barrier、snapshot/source identity | 無法證明cutoff/version一致時拒絕projection | R026 |
| RK-18 | Direct source bytes/path或runtime constants使checkpoint identity失效 | R006,R027,R028 | 15-path inventory、stable/runtime分層、resume正反例 | 任一hash/timing/bytes差異→AB-ML-01 | R027 |
| RK-19 | joblib/pickle qualified class path被當無caller刪除 | R001,R006,R025,R029 | artifact inventory＋load fixture，不只rg imports | 支援artifact仍引用舊path | R006/R029 |
| RK-20 | 大型central files的多人diff互相覆寫 | R011,R012,R018,R019,R026,R029 | execution waves、exclusive owner、small merge order | active tasks碰相同central region | Program manager |
| RK-21 | Data contract抽取需要正式資料重寫 | R007,R023,R024 | additive contract/adapters、tmp fixtures、no data migration | task要求修改/回填正式data才能通過 | Boundary task owner |
| RK-22 | Architecture guard靠廣泛allowlist變綠 | R030,R031 | bad-fixture positive/negative tests、exact symbol baseline | 新allowlist未列owner/expiry或掩蓋4項既有違規 | R030 |
| RK-23 | 「full regression」範圍過大導致無法定位，或過小漏跨流 | R012,R020,R029,R031 | C1-C4分層checkpoints、focused first/full relevant later | checkpoint缺category或只跑單元測試 | R031 |
| RK-24 | 工程完成被誤報為formal/production/promotion | 全部，尤其R031 | INV-18、Scoped SSOT與closeout措辭審查 | 文件或UI宣稱未獲准權限 | R031 |
| RK-25 | 未知外部/dynamic caller使facade刪除成migration dead end | R001,R014,R025,R029 | string/scheduler/script/plugin inventory、支援期決議 | caller不是repo可遷移且無deprecation決議 | R001/R029；必要時ARCHITECTURE_BLOCKER |
| RK-26 | 既有 opaque result_id 直接作檔名造成路徑逃逸、保留名稱或大小寫碰撞 | R008,R009,R012,R016 | 保留 exact identity；R012 writer採安全檔名映射、target containment／symlink 檢查與 readback exact ID；隔離fixture測 traversal／separator／Windows保留名／case collision | 任一 ID 可寫出預期 artifact root、同名不同 ID 碰撞或讀回身份不符即停止保存切片 | R012；R008 僅維持 typed ID／binding |

## 風險 review 節點

- **C1/R012**：RK-01–06、15–17、26。
- **C2/R020**：RK-01–08、13–17。
- **R027 decision gate**：RK-18；失敗即 `AB-ML-01`。
- **C3/R029**：全部temporary／serialized／external caller風險。
- **C4/R031**：所有open risks必須標 `CLOSED`、`ACCEPTED WITH OWNER` 或 `BLOCKED`，禁止空白。

## 不以本計畫處理的風險

- 投資策略有效性、自然時間證據、正式資料來源接受、ML promotion、broker execution權限仍由既有產品／工程Gate管理。
- 未經另案授權，不進行正式資料修復、回填、全市場ML重建、scheduler實跑或模型切換。
- 發現既有產品bug時另建behavior-change task；除FINAL已明確要求的execution-time snapshot/create-only一致性修正外，不混入結構task。
