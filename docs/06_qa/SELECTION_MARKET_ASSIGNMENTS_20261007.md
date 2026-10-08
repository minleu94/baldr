# 選股現況市場歸屬來源：中央審核

本葉片提供 `CurrentMarketAssignmentReader.from_pointer()`、`from_exact()` 與 `get()`，使用既有 CMS 保存的上市、上櫃與興櫃三份官方名錄原件。保存 pin 綁定 snapshot、manifest、三份 raw SHA／大小／擷取時間、來源日期、schema 與截止時間；exact 重開不追讀已推進的 pointer。不以股票代號推測市場，也不採用 snapshot 最後寫入的 market 值。

三份名錄都完整、非空且有已核 aware 擷取時間，才可依唯一正向成員證據指派上市或上櫃。缺件、空名錄、同源重複、跨市場衝突與興櫃均不可授已知市場；缺擷取時間及來源 schema／原件／時間越界則明示拒絕。非名錄來源的 CMS partial_failure 保留於 pin，不阻止這三份各自完整的名錄判定。終止正向證據必須與同批 raw 原件相符；未驗終止狀態明示 not_verified，不能推導安全證書。

中央審核發現初版缺擷取時間仍可判 ready、零列仍可排除市場衝突，已要求補正並新增具體回歸。最後定向測試 12 passed（1.17 秒），收據 `output/qa/market_assignment_root_20261007_b.xml`；兩檔 mypy 通過。第一次 sandbox 執行因 Windows strict resolve 權限限制而 11 failed／1 skipped，原收據保留；另開唯一隔離合成目錄原樣驗證，沒有放寬路徑或硬連結檢查。

既有 TWSE 封存原件唯讀核對 1095 列、row count 與 SHA 一致；同次兩份 TPEx 名錄擷取失敗。因此三源完整成功目前只由合成 CMS fixture 證明，不宣稱正式來源完整或最新。來源註記維持 current_only、official_available_at=None、historical_pit_eligible=False；不能作歷史回測條件。

尚未接 full-N 保存 fact bundle、全母體 query 篩選、正常更新入口或 UI 條件。本葉片不構成 F08–F19、P03 或完整產品驗收，後續需將市場來源 pin 與處置來源 pin、相同完整母體 plan／receipt 綁定後再驗。
