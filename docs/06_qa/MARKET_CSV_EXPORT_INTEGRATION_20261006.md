# 明示市場CSV consumer／CLI dev整合（2026-10-06）

> 本頁的「UX23 未採納」只記錄市場 CSV 包結束時的父層安排；後續 [UX23 scoped registry 整合](UX23_REGISTRY_INTEGRATION_20261006.md) 已記錄 lane 採納與有界驗收。兩份收據對 24UX pending／partial 的統計基準未調和，不能把下文 `0pending` 推成 UX23 當時已接受，也不能把 UX23 切片接受推成整體 gate 完成。

review兩個lane commits f0e1d8e62727a305ee7ff74c3b42e363fecce1db → 8d0a6090b13bc52ce49a216daf1af29133648104，dev依序採納ac0cc19b→ffa6e537；最小修正另commit。既有viewport UI包609dfb4a獨立交付，這包不改sharedUI/config或正式資料。

## 實用範圍

既有明示MarketOnlyExportPlan→Windows handle pins→CSV hash／bytes核驗→全新隔離目標→不可覆寫canonical完成收據。獨立 scripts/export_market_csv.py 預設只讀preview，不建立目標，不默存接受hash；caller保存核對後的preview，再明示--execute與--accepted-preview。來源三root／精確明列file set／identity／size／hash重驗，不把新版本當作先前接受版本；目標可另指定新位置供取消後重試。

禁止glob／整包FA_Data；排除personal／legacy output／未列檔／SQLite及sidecar名稱、magic或NULbinary偽裝CSV。readonly source handle與已建輸出全程持有sharing鎖，目錄祖先pin，不降級未鎖定copy。輸出hash／source identity／同來源最終hash與目標allowlist最後再驗，成功才發布完成收據。取消130／blocked2，partial或pending留證據，重試另新目標；不清理、不上傳或分享。沒有真市場包、真personal內容、正式Task／migration或root啟用。只能在caller可鎖定的Windows filesystem使用。

## review阻礙與修正

短路徑lane測試pass不足：review在較長路徑重現API成功卻生成 market-csv-export.v1.jsonsts。原FileName buffer沒有尾NUL，可能把額外記憶體字元當檔名；修正為UTF-16原bytes加尾NUL，長度欄仍不含結尾。規格參考[Microsoft FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info)，以fixture實際改名驗證，不以API返回值猜成功。發布後另核exact canonical path是否存在、pending不再存在、原handle／路徑identity與receipt bytes hash；錯名或沒有發布即具名export_receipt_publication_mismatch，不回報completed。

新10案例：8種UTF-16路徑長度／surrogate目標、成功API但no-op／錯名不能當完成。既有不可覆寫競爭receipt、source revision/hash、hardlink/junction、streaming取消／pending取消／publication IO、來源bytes與dev/ino/size/mtime/ctime不變保留。

## 驗收

- 去重192passed：consumer62／CLI26／既有personal paths104，使用新短ignored fixture .t/csv_owner_final_20261006，沒有刪除重用舊basetemp。
- 深路徑僅consumer／CLI88passed（與上列重複不加分母），證明長路徑rename修正。初次192合成深root，CSV／CLI全過、3個既有COW fixture因普通open路徑超260失敗；保留full.txt，不改COW／私人migration或重開gate。短fixture全套192通過。
- targeted mypy3modules、完整mypy821檔、4個CSV Python檔compile、quant／diff通過。無UI修改，沿上一包mandatoryWorkbench85／validator25+4skip，不宣稱重跑UI或Native。
- 獨立fixture preview→明示accepted preview→execute成功，canonical receipt bytes hash與來源stat不變；raw synthetic_cli_evidence/accepted-preview.json、execution-result.json、new-package/market-csv-export.v1.json、evidence.json。這只是假資料，不代表真匯出／分享授權或CSV每欄語意合格。

raw output/qa/market_csv_export_integration_20261006；所有fixture／原始驗證輸出ignored不stage。原計畫prefix保留只追加，其他owner三檔不改；父層DOCUMENTATION_INDEX UX審查入口及PRODUCT_UX_SIMPLIFICATION_AUDIT草稿保持原樣、不stage。

## 限制與進度

市場CSV隔離consumer／CLI有限工程閉環完成，UX08資料分離／全體UX仍partial，9stage1done8partial0pending、24UX2done22partial0pending不增加done。真來源／授權與語意核對、實際分享、市場DB表／view／trigger／sidecar契約、大清單handle容量、正式啟用尚未驗收。不能以白名單／hash證明私人欄位不存在或來源license；不讀artifact模型、不接正式Task。UX23只讀lane收到未在本輪採納，等待父層安排。

回滾只revert此修正／文件包及兩採納commit；保留原資料與partial，不能為回滾清理輸出或他人草稿。
