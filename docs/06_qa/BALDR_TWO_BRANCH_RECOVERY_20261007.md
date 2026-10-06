# dev／main 分支整理與可恢復收據

## 最終一個 worktree（先前42個原地保留區段為歷史時點）

使用者直接要求全部完成後只留一worktree（Sentinel_154bb8a336948191b98de7817897aa3e）。本機main packaging驗收與持久新增備份完成後，**42個其他checkout均使用普通 `git worktree remove` 移除**，未用force／prune。最終list只有 `C:/Projects/PythonProjects/technical_analysis`、checkout dev；refs/heads只有dev／main，remote refs未刪未push。

移除前逐exact Gitroot核HEAD／clean／每檔SHA及reparse boundary；ignored／untracked原檔以LiteralPath搬到持久 `loose_extras/worktree_XX`，原ZIP仍保留，再核無未備份extras才移除可由Git重建的tracked checkout。primary ignored／正式FA_Data／私人資料／ACL／Task均未動。

market-csv-export遇14個synthetic parent junction，守衛即停。metadata證明全部targets在同worktree內；先以新Temp probe驗Native Move-Item只搬link物件／target不動，再保存metadata與原junction物件，未followtarget或刪外部資料。原ZIP裡透過alias投影的檔案列保留；實體檔另逐SHA保存。這14份link metadata補充原只檢file-lstat的manifest，不能以原links空陣列冒稱沒有parent reparse。還原時先重建實體內容，再按metadata核target後重建junction，不在備份中跟隨已移除原路徑的link。

新main發布工作區604extras另存 `main_release_final_extras.zip`／manifest；原a7候選611extras與原all_refs bundle仍保留，最終main a8與dev809e另有final_main_refs.bundle。普通remove恢復段（最後10個）的卷可用空間觀測增加 **737,497,088 bytes（約703 MiB）**；這不是前32個加總或全程獨佔净值，沒有假報完整釋放量。收據：ignored `retirement_result.json`／`resume_space_before.json`／兩輪raw／reparse metadata。

## 結果

本機 `refs/heads` 已只剩 **dev／main**。40個lane分支名稱已在逐一驗證持久備份、clean與exact HEAD後，以原地detached checkout及expected-old-SHA CAS ref移除完成。**42個worktree目錄全部保留**，無永久刪除、無force prune、無main reset、無push／公開分享／visibility變更。primary ignored／正式FA_Data私人資料未搬移、未刪除。

dev工程基線 `4e234576d8722c07b2124203a5bda301d081ba47`；main仍 `1bedee9aff0be2a375f90eb677911cb029688339`。舊lane如果繼續工作須重新指派ownership，不能在已釋放的detached checkout擅自寫入中央dev。

## 持久備份

位置：`C:/Projects/RepositoryBackups/technical_analysis_branch_recovery_20261007`。此為本機私人恢復資料，**不得stage、commit、上傳或分享**。Temp staging副本亦保留，持久副本已独立驗證，不依Temp存續。

- `all_refs.bundle` SHA256：`5b8d25805f3f5f4fa3cbdbc470d2f096734ae56d5379b767285e77b96da9defd`。包含complete history、全部71正常refs以及各worktree HEAD，共113 bundle refs。
- `manifest.json` SHA256：`e34d4fa75c9862a231252a8a7d41729f0041e517dddce93277d0e3f1df4f1fb7`。記錄42HEAD、原路徑、原refs、各非primary extras的SHA／size／mtime與archive SHA。
- 41個非primary ZIP，共18,771個ignored／untracked檔，1,693,769,067原始bytes；Temp與持久副本都逐檔重讀SHA通過。primary目錄仍在原地，不在刪除範圍，其ignored資料也未移除。
- 從持久bundle重建 `restore_verify.git` mirror，`git fsck --full` exit0、71refs逐SHA一致、42HEAD都可讀。完整收據在ignored `output/qa/baldr_branch_cleanup_20261007/durable_backup_receipt.json`；備份目錄另有 `verification_receipt.json`、`RESTORE.md` 與只新增不覆寫的extras還原script。

## 唯一舊patch與停寫證據

`git cherry` 顯示44c3bd17非等價，但其五個完整檔案（personal_store_selection、config、test、QA、Manual）blob與已採入中央5441e1c7完全一致。差異来自原parent／Manual patch上下文，沒有漏掉runtime/test/doc成果；原44c3bd17仍完整保存在bundle。detached `fef56b934262502e9dc354bd6d97820b9cf53f1d` 亦可由bundle恢復。

BBP01原thread初查active，中央先跳過；父層取得最新turn completed、停止全部工程／測試／代理及釋放ownership後才最後處理。未以全機無writer作保證，也未為查程序改ACL。每個worktree fresh clean、HEAD／extras檔名／SHA核對後detach；CAS刪ref後再核extras SHA／mtime與clean。原檔全保留，未以cleanup為由刪測試或QA。

## 還原方式與發布後續

先驗上列SHA及manifest，再以 `git fetch <backup>/all_refs.bundle refs/heads/<原名>:refs/heads/<原名>` 恢復缺失branch，對原SHA；若同名branch已存在且分歧，停止而不覆寫。原checkout可直接以該branch重新checkout。另可在新目錄clone mirror，再以原HEAD建立detached worktree；extras script只向缺失檔寫入並核SHA／mtime，links僅保存metadata、需人工核對後重建，不跟隨到外部私人資料。

main用途與發布邊界由父層独立只讀審查；2097檔大型差異不直接快轉。下一步先完善README／安裝／首次設定／合成示例、核無private或憑證後，選可逆本機發布commit保留原main parent及dev完整歷史；不擴成遠端授權。產品自然排程與品質成熟仍採原中央QA分域，不因branch整理獲新資格。
