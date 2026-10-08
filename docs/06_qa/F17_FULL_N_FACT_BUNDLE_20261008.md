# 完整母體官方處置事實保存 QA

## 範圍與契約

新增獨立 sidecar，固定技術 v4 store 的 generation／plan／receipt 與市場歸屬、官方處置 exact source pins，逐列保存完整 declared 母體。包含納入與排除列、原排除原因、來源品質與公告／處置／觀察日期；不修改原技術 store 或原資料。

writer 使用明示 ResearchCaptureWriteScope，輸出不得與 DB、技術 store／parents、市場或處置來源重疊。每256列一分片，列16KiB、分片4MiB、manifest8MiB、bundle64MiB上限；超限拒絕，不截斷後宣稱完整。create-only發布核物件身份／SHA，解除本任務 candidate hardlink後立即核單連結；manifest final gate 與取消互斥，不覆寫同身份衝突內容。

reader 必須先核完整 manifest／分片／技術來源／兩個 source readers，再發 immutable verified state。逐列 projection 和 counts 從 exact來源重新推導並比對；projection complete 不等於官方覆蓋完整。來源截點沿原技術決策 cutoff，較晚 CMS／處置資料不能回補舊來源。

所有結果為 current_only、historical_pit_eligible=false、official_available_at未知；未有正面名冊／處置證據時保留 unknown，不補安全證明。此葉片尚未接正常更新、查詢條件、比較／收藏或UI，不代表完整F17已交付。

## 中央驗證

凍結 module SHA `bae21a6c964abacb226a474cc5736aafd0c4bc9b413dce208f0aab18cc8d1435`；test SHA `bbfceb2dafe423146014f4654511a4cc4daa1a25d9cf871aba4d1bfec398d6ab`。中央起訖核對相同，獨立合成整檔 terminal0：**22 passed／1 skipped，199.93秒**，log為 ignored `output/qa/f17_bundle_root_20261008_a.log`。

驗證使用真 public producer 一次產製257納入＋1排除、兩個 actual exact source readers；258列完整 counts、兩分片、current-only／partial來源、原件inventory不變、不同程序讀回、late cutoff、bytes及重新簽章語義竄改、取消 barrier、五類來源root重疊、DB parent scope、錯plan／receipt／source pins、真列／manifest／shard／count界限、hardlink與callback失敗、既有manifest衝突均涵蓋。合成市場名冊及處置資料不是原市場的完整覆蓋證據。

唯一skip是建立reparse symbolic link時WinError1314（此環境無所需privilege）；hardlink是獨立通過的測試，不能把skip寫成通過。兩檔targeted mypy及py_compile通過。

## 歷史與未完成

初次sandbox strict-realpath拒絕、原生long-path inventory失敗、舊4case與單連結強化後4case均保留在ignored QA，未覆寫。舊順序容許暫時nlink2核驗再cleanup；新順序是提前滿足單連結契約，不能誤記成已證舊程式必失敗。

正常更新後保存、完整F08–F19條件、full-N global filter／排序、比較／收藏來源身份、新程序及候選UI仍待接線與驗收。未觸發正式Task，未開原SQLite，未修改原資料。回滾先審依賴，再僅移除本次兩個新葉片及相應文檔；保留其他聊天dirty、原來源與失敗QA。
