# dev／main 兩用途整理與可恢復發布準備

## 已核盤點

使用者直接真人同意本機dev採入BBP01，並要求最終只留dev開發／main乾淨供別人使用。此輪先完成四包工程與穩定驗收，不將localdev批准擴大為遠端發布。本文件是整理清單，尚未執行branch刪除、worktree移除、main更新或push。

2026-10-07 唯讀時點 dev `5eefe3317e01f92f8dca1ce343e2df46a070d396`；main 與 origin/main、origin/dev 均為 `1bedee9a`（本機 remote refs，未 fetch，非遠端即時聲明）。origin 為 `https://github.com/minleu94/technical_analysis.git`。dev 比 main 多 509 commits、2,097 檔差異、760,211 新增／23,062 刪除行；不能僅憑這次 61P 宣稱整個差異都已發布驗收。

42個local branches、42個worktrees；其中主dev因本輪新增test/inventory當時dirty，其餘41個tracked/untracked status clean。clean不代表ignored內容可丟棄：盤點另外保存每個worktree的ignored目錄項，包含QA raw、Temp與模型試驗產物。原始完整盤點 `output/qa/baldr_central_resume_20261007/branch_audit.json`（ignored，不stage）。未更改git global safe.directory；sandbox讀外部既有worktree遭dubious ownership後，原使用者升權只讀完成。

`git cherry dev <branch>`逐分支比對：唯一非等價舊patch為 `lane/baldr-b09-personal-portfolio-20261006` 的 `44c3bd17de11acab7fde5fa36984b1ed48b2d706`，涉及personal_store_selection、config、Manual、test、QA。該branch尖端 `0c149aae` 及其其他patch已有等價成果；這不表示44c3bd17可直接補採，dev後續實作可能已用不同方式取代，必須先語義核對並保存。另有既有managed detached worktree `fef56b934262502e9dc354bd6d97820b9cf53f1d`，不可當作多餘branch而直接刪除。

## 可恢復順序

1. 凍結各lane owner、記錄所有refs／HEAD／status及ignored內容的保留位置；對未整合44c3bd17與detached基線單獨核差異。此輪不重開lane或共編。
2. 在repo外或ignored保全目錄建立含全部refs的Git bundle並驗證可讀、記錄SHA；bundle不能保全ignored檔，必要QA raw與任何唯一資料另做明確檔案清單／雜湊保全。不得搬移或刪除正式FA_Data。
3. 確認每個worktree唯一commit與必要ignored資料都可恢復後，managed worktree使用Codex archive_worktree保留snapshot；非managed者需逐絕對路徑核所有權與保全位置，再由單一PowerShell原生LiteralPath流程處理，不強制刪除、不跨shell拼刪除命令。
4. 只有已歸檔、不再checkout、commit可由bundle恢復的lane refs才可刪除，保持dev與main。不可用強制branch delete抹掉未知差異；兩branch目標不等於只保存兩段成果。
5. main在本機發布前先保存原main可恢復commit於已驗證bundle，建立審閱差異清單與使用者公開用途入口。保持必要test／Manual／架構／QA文件；UI採PySide6既有入口，研究／實際啟用／自然品質成熟分域。
6. 優先以經整理的dev commit讓main可逆fast-forward；若需剔除tracked發布不應有檔案，先做明確本機整理commit及影響驗證，不resetmain、不改歷史。失敗可依bundle恢復refs及原檔，不刪任何原始資料。

## 發布包邊界與剩餘核對

tracked敏感路徑形狀初篩只命中 `.env.example`；此為檔名初篩，不是內容憑證掃描或完整發布合格證。正式私人 `FA_Data/personal`、真持倉、預測、個人設定、憑證、SQLite與測試Temp不得進main包。`output/**`、graphify-out、shared_state、cache本來ignored，此輪未stage；原Git歷史是否含應排除內容需在實際發布前另外核對，不宣稱歷史已清理。

四包工程驗收／新原保存名單唯讀證據詳見 [中央QA](BALDR_CENTRAL_COHORT_NATURAL_BBUI_INTEGRATION_20261007.md)。下一原Task 2026-10-07 12:45UTC仍待父層唯讀驗收，自然10pending／0成熟；尚未push、公開分享或改repo visibility。兩branch整理剩餘阻塞為唯一舊patch語義核對、必要ignored保全及main巨大差異發布審閱，而非BBP01批准（已解除）。
