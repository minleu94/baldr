# PROJECT_SNAPSHOT（目前狀態）

> 更新：2026-10-17（使用者時區）。本頁列目前入口、各流程進度與下一個出口。逐輪身分、原FAIL與收據見[具名QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md)，交付順序沿[原計畫§0.4](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。

## 現在有哪些入口

**指定試用版為日常研究141c（`7134efaa94d6`）**。雙擊[Launch-Baldr.cmd](../../output/trial/Baldr-Daily-Research-141c/Launch-Baldr.cmd)，步驟見[試用指南](../07_guides/TRIAL_VERSION_GUIDE.md)。全新包含自有runtime與原件，首次啟動前放妥完整資料夾；首次設定本機實測約8分34秒，同根後續保存保持。舊139及131保留供回訪，不自動匯入私人資料。EXE SHA `36a5cff62bf3835240c88c00e28d60daf002e8b0438b91e1489b977680fbc4c9`，交付SHA `1c49d736887bc62aa559d3a926523466d7761c4cb21b0edcebafc14b9622d79d`。

116與更早候選保留，不能把其外部檢查當目前版本驗收。三個判讀已在指南更正：0完成配對不等於沒有訊號；公司名錄缺來源憑證仍限制用途資格；118起價格選股雙擊會進主個股頁。一般四股行情與1,951檔同源價格研究仍是不同範圍及日期。

| 使用流程 | 已有成果 | 下一個出口／尚有限制 |
|---|---|---|
| 市場與個股 | 市場狀態、四股價格／技術；三公司五列半年比較，2382新增同表月營收與增減率 | 一般行情截至2026-09-23；月營收最新2026-09，兩者各標日期。缺方向不補造，2382半年財報缺件隔離。 |
| 價格選股與收藏 | 2026-10-16來源：宣告1,989／處理1,951／排除38，可設條件、同源個股、2–5股比較、收藏及重開 | 5筆UNKNOWN；名錄用途與來源clock未接受，不稱正式真N或歷史PIT。 |
| 清單、持倉與情境 | 持倉在四卡下方，唯一精確代號／名稱互補，回個股可重載；初次情境有隔離證據 | 私人帳／真人及真策略Paper同日原件仍待，不以手動成本造NAV。 |
| 回測、保存與比較 | 原單股規則、結果、返回及新程序重開；2–5個同股同窗保存策略可看逐日意圖，附三筆示範 | 研究樣本不等於策略有效。SOP／Baseline FAIL、Walk-forward、成本／來源權威、PIT及完整雙策略績效分別保留。 |
| 推薦結果追蹤 | 134補計畫目標日、實際取價日與缺價原因；5／10／20日受限結果可回訪 | 1538缺價、60日未成熟與P12正式時序／修訂限制保持。 |
| 首次設定與搬移 | 141c固定EXE含139月營收／市場狀態，在原600秒內513.532秒完成本機新位置設定；正常Main／新程序收藏、原研究及金融值一致，保留新手動觀察項目，啟動器正反SHA通過 | 只接受全新包的本機新位置出口。已用state、跨機及私人帳搬移仍待；138與141診斷原FAIL保持。 |

V1維持[原四條流程與驗收出口](../superpowers/plans/baldr_product_completion_plan_20261006.md#03-兩階段交付與v1範圍凍結)，後續增量不擴V1範圍。134已有1280×760保存策略回訪及1500×900新回測保存／新程序的限定原生證據；完整Native、其他DPI及真人接受仍待。

## 目前工程狀態與限制

**139的月營收成果已保留於141c。** [139 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment139-quanta-monthly-sales)綁既存TWSE公司原件與廣達官方月營收，八檔版本保留同表百萬元整數／0.1%披露率。真實台北10/18 04:00後的原正常頁／新程序、股票切換與捲動證據維持；141c另驗新根五列原值、精度及歷史隔離。未改旅程沿原證據，未重跑全部四流程或授完整Native。官方綜合損益表入口302 ASPX錯誤原件保留，停止該入口；半年財報缺件仍隔離，不混表、推算累計或接評分。完整F12、來源／PIT及原計畫其餘列繼續保留。

[138](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment138-first-trial-setup)兩次600秒FAIL及partial原件保留。[140](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment140-archive-byte-reuse)在同一恢復工具限量重用初次SHA已驗原件，保留前後完整實體核對，Source整包首次設定已在原600秒完成；不替換139或授整包可攜資格。135月營收因子的缺月／前史修正只屬後端工程驗證，尚未進指定候選的正式評分。這些局部成果不授完整F12或P14。

[141c](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment141-full-trial-exe)已解除本機固定路徑及漏帶139內容的交付阻礙：v2明選月營收／市場狀態，生成config沿共同契約；48項整合／保護檢查與mypy1069通過，新固定EXE設定、Main26016→32764受改讀回及啟動器正反SHA通過。Windows背景QA保留原斷言／15秒，未攔截關閉；原提前close來源仍未確認，原FAIL完整保留。CMD改用.NET SHA256核同一EXE，不依賴缺失cmdlet。完整包與指南已封存，未授完整跨機、私人owner-migration或Native；下一輪沿原第三至五列可獨立出口續推。

外部缺件各自隔離：TPEx年度日曆授權、TPEx法人API、官方文件／單位／用途、歷史PIT、真N、完整績效、Native／EXE及Paper／forward自然成熟分別判定。MOPS partial／缺EOF及舊月營收／TWSE GET耗盡scope保持，不重抓、不把一處缺件變成全產品新前置。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4未完成項仍在原計畫，不以commit或案例加總計完成率。

[142開發來源](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment142-trial139-feedback)回應139真人回報，先修月營收值被來源長文淹沒、窄頁壓縮及收藏名稱／下鑽混淆。48項定向、Workbench85、validator25／0／4及mypy1069通過；正常Source Main3344已核五列、窄頁、名稱、原來源與保存值；固定EXE出口另驗，指定141c暫不變。共同期限說明仍須核逐期限適用原因；真人D未驗不寫成PASS。原金融值、缺件、精度及可得時間守衛保持。

## 產品與系統入口

- **進度與交付**：[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md#04-依使用流程重排交付2026-10-15)。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 保留；不以 Increment 或測試數量計算完成率。
- **產品方向與來源優先序**：[Product Roadmap](PRODUCT_ROADMAP_POST_REFACTOR.md)；正式 Gate 依賴見[六個月工程路線](ROADMAP_6M_ENGINEERING.md)，不以本輪交付排序改寫 Gate。
- **實際操作**：[APPLICATION_MANUAL](../07_guides/APPLICATION_MANUAL.md)；首次設定看[快速開始](../07_guides/QUICK_START.md)，移機看[首次安裝／移機 Prompt](../07_guides/FIRST_INSTALL_PROMPT.md)。
- **現行與目標架構**：[system_architecture](../01_architecture/system_architecture.md)／[current 分冊](../01_architecture/current/README.md)；[FINAL](../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 是目標設計，不作已實作證據。
- **主程式與資料**：`ui_qt/main.py`，九個頂層工作區；資料位置由 `data_module/config.py` 的 `TWStockConfig` 管理，預設 `DATA_ROOT=D:/Min/Python/Project/FA_Data`，不能以 repo 相對路徑推定正式資料位置。
- **L2 產業鏈與題材萃取對應（獨立模組）**：[`decision_module/industry_theme_map.py`](../../decision_module/industry_theme_map.py) 提供季度／手動之 25 條產業鏈、L2 題材與股票對應三檔建置（未介入既有選股／UI 流程）；規格與檔案欄位見[設計文件](../02_features/INDUSTRY_THEME_MAP_DESIGN.md)，驗證收據見[QA](../06_qa/INDUSTRY_THEME_MAP_STANDALONE_QA_20261016.md)。

## 重要限制

- 正式資料寫入、全量回補、正式 Task／maintainer 變更、push、發布與交易沒有新增授權；私人資產與其他 owner 變更受保護。
- 金融精度、決策當下可得性、來源用途、原 FAIL 與各 Gate 門檻維持；缺值與未知不能補零。
- Historical replay、readiness、dry-run、shadow、Paper、合成資料或測試通過，均不能代替真來源、有效績效、真人接受、自然成熟或 production ML 資格。程式碼／EXE 可啟動也不授上述接受；UI 的既有 mypy ignore 設定不證強型別。
- Root 串行 QA 與資源守衛依[共用規則](../agents/shared_context.md)。本補完 task 已用完新建代理額度 10/10；只在無待寫與無衝突時重用既有 Luna。

[143派工修正](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment143-setup-work-scheduling)只為解除142固定包首次設定600秒FAIL；原核驗與2／4併行上限保持，QA與新候選待驗。未通過前入口仍為141c，142／partial原件不改。
