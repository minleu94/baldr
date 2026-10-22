# V2 月營收與研究 Paper 增量整合決策

日期：2026-10-21（America/Los_Angeles）。本決策依 V2 補完授權界定工程介面；正式來源用途接受、帳戶資金政策及發布授權另行成立。基線為 `12e7f620`，驗證狀態見 [V2 驗收](../06_qa/BALDR_V2_PRODUCT_ACCEPTANCE_20261020.md)。

## 月營收來源

現有 MOPS static snapshot 的 source／parser／schema 身份不變。TWSE `t187ap05_L` 與 TPEx `mopsfin_t187ap05_O` 是兩個具名 OpenData endpoint，不能改名成 MOPS HTML。新 profile 必須逐市場固定 endpoint、parser、schema、原始 bytes／SHA、期間及單位；共用 cohort 只允許精確列出的雙市場組合，不一般化為任意異質來源混用。

優先延伸既有 TWSE OpenAPI preparation 及原 daily publisher／reader。來源金額以 Decimal 保留原值；只有經核驗、與該 endpoint／欄位相符的官方單位證據才可換算 TWD。缺單位證據、缺欄、重複 identity、非有限值、未完成 HTTP body 或不一致期間一律拒絕。批次覆蓋只描述該份 response，不宣稱全部掛牌公司完整。

`出表日期` 與 `資料年月` 不是逐列公告時鐘。無逐列 timestamp 時，current-only availability 採成功完整批次完成時間向上取整的 `daily-hour.v1`；不得回填成當月較早可用或歷史 PIT。一次來源用途接受與每日批次品質分開：候選下載、解析、provenance 與 SHA 可先準備；外部可信設定必須由有權接受者固定。Worker 不生成核准事實或將下載成功解讀為接受。

政府資料集 [18420](https://data.gov.tw/dataset/18420) 與 [56510](https://data.gov.tw/dataset/56510) 列出相應欄位、免費及政府資料開放授權第1版。實際 API 及授權鏈仍須綁本次原件；顯名與衍生處理說明保留。官方申報簡報可作單位證據候選，不能只因同屬月營收便假設 JSON 欄位的單位映射已成立。

## 研究 Paper Producer

使用既有 `PaperTradeFill`、`PaperTradeTransition` 與 `PaperTradeLedgerRepository`，不建立平行帳本、不修改 scheduled T+1 producer 的金融語意。新 application orchestration 接受明確人工確認的 immutable intent，先重核原研究 identity，再核帳戶／策略／政策／成本版本、貨幣、同日合格 mark 及現金來源。

研究 reference price 不作成交價或 mark；benchmark 不作現金；既有策略 500000 空倉 seed 不作通用本金。沒有受信核驗 provider、正式帳戶政策或合法輸入時，保持 fail-closed。第一個可實作切片只接受明示 TWD、整數股與 Decimal 金額，不自建 Owner 帳戶或推導未知本金／日期。

原策略帳戶 binding 目前固定初始本金 500000、最多八檔，這是既有帳戶契約的限制，不是新研究模擬的預設資金。Producer 僅能消費已明確選取且核驗的該型帳戶；其他本金／帳戶形式須另有版本化政策及 reader，不能直接修改 seed。既有 daily operation 每帳戶每日唯一性亦保留，不將不同人工意圖偽裝成同一冪等重試。

持久化採同一原 SQLite 帳本的既有原子 operation／CAS，重複確認須讀回同 identity，改動 intent 或 prestate 不能誤作成功。完整研究／來源／政策指紋須可從保存事件重核，不只存在於畫面記憶體。不能使用先核 rowset、再無條件 append 的競爭窗口。

Fill、transition 與 operation marker 在同一交易提交；不另寫獨立 snapshot DB，避免半套持倉。後續 NAV／snapshot 仍依既有合法投影流程，不因 producer 成功宣稱績效或 Forward 自然成熟。任何失敗不得留下部分 fill／transition；不觸發 broker、不授 auto rebalance。

## 驗證與發布邊界

隔離 fixtures 驗程式契約，不當正式來源接受。五旅程各自列 Code／Contract、自動 Main GUI、金融來源、Native、Owner UAT。首頁用真實當下日期；過時來源只接受過時拒絕，不注入時鐘冒稱當日正向流程。既有 QA164 原整輪 FAIL 保留。

Native `USER_STOPPED_ESCAPE`、`OWNER_UAT_NOT_PERFORMED` 維持。Source 驗證不外推固定 `eefd2163ad95` EXE；所有可安全完成工程收斂後才集中建置一份候選，且不替換正式入口。
