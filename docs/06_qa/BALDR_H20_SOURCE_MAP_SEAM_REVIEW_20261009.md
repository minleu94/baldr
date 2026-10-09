# H20 固定來源清單環境橋接審查

## 範圍與結論

根 agent 已直接審閱 `synthetic_main_20261009_m` 的 child、controller 與測試紀錄。此變更僅處理 Windows 環境變數單一值長度限制：完整 4,161 檔來源 SHA 清單有 493,808 字元，不適合放入 Win32 環境變數。

候選改由固定 manifest 路徑及 SHA 傳遞，驗證完整來源 inventory、檔案身分、總位元組與 22 個依賴 pins 後，僅對精確 legacy 模組的單一環境 key 提供唯讀值。其餘環境讀寫委派真實環境；沒有截斷清單或更換全域 `os.environ`。旅程結束須還原 loader 與模組 `os`，確認該 key 恰好讀取一次並重核 manifest 身分。

## 已核對的證據

- child SHA-256：`DDEBB4068E7A120EE674F2A0DB590042B20934FC042AA854AAB1C1D205DB60E2`。
- controller SHA-256：`B819400F51FD7134F7DCAE34967A85F0351F0566DA2D198927EBAB54CAF592F5`。
- 實際純測試紀錄：7 passed，1.88 秒；測試檔 mypy 通過。
- 測試涵蓋完整 s3 清單、不可變 map、錯誤 manifest pin、來源漂移、額外檔案、環境長度限制、精確模組橋接與還原。
- 純測試沒有啟動 Main 或連接 SQLite。child 整檔仍有與 preimage 相同的 19 類動態 Main／DTO 型別錯誤，不能宣稱整檔型別檢查通過。

## 下一步與驗收界線

已授權 owner 以固定 controller 執行一次全新隔離合成 Main 旅程，保存啟動 argv、來源起訖、三條 DB 路由、2382 下鑽時間與結果、child terminal，以及 Job 關閉後 owned process 為零的證據。失敗不得覆寫或直接重試。

此審查只批准 QA 橋接與下一次執行，尚未證明 Main 旅程、原始 H20 下鑽效能、EXE 或真人操作驗收完成。

## 路徑前置修正 c 的接受邊界

前次 n 旅程在 Main 前失敗：QA root 指向 repo attempt，而 case 在 C:\t，違反原守衛的嚴格 containment。c 候選保留原守衛，將每次唯一 QA parent 放在 C:\t 的專屬直接子目錄，case／output 位於該子目錄內；控制器在建立目錄前核既有父鏈的 lstat、reparse、canonical path 與穩定身分，不將共用 C:\t 授為可寫範圍。

Root 實讀 c 相對 b controller diff 與 c child 相對 m 的完整差異，並獨立解析 `synthetic_root_preflight_20261008_c/root_runtime_preflight_receipt.json`：24 項 passed、0 skipped、SQLite 0、Main false。負例包括共享根、錯誤 leaf、路徑型 attempt 名稱、既有目標、case 越界、output 混版與實際 junction。此為真 legacy guard 安裝與路徑前置測試，沒有正式原件讀取。

controller SHA `82529c9e658ed0f505d9c3899eb6b759bcba167c3d909df7ddf2f61070b38a9c`、child SHA `cbb92dabf51603634db814cce080f66852d7027bfacd57a66b06c8eb73ca1066` 已重新計算符合。已批准 owner 複製固定 c 到全新 attempt，執行一次合成 Main 旅程；禁止重用 c preflight case，終態仍須另讀回，不將 24 項前置成功當作下鑽／收藏成功。

## c 的實際 Main 嘗試：preparer 契約缺口

唯一 `synthetic_main_c_main_20261008_a` 嘗試 terminal exit 1，Root 直接讀取 `fixture_prepare_stderr.log`：preparer 的 `_make_environment()` 仍預期 case 等於 QA parent，而 controller／child 已採 QA parent 下的 `case` 子目錄，故拋出 `synthetic_case_root_mismatch`。preparer 0.125 秒即停止，Main、child 與 SQLite 未啟動；沒有名單／2382／返回／收藏的時間可報。原快照與失敗封套留存。

這說明前次純路徑 preflight 未覆蓋真正 preparer 的完整契約，24 項通過不能推論三支腳本能串行執行。已分派新 d 候選修正 preparer，要求真正 standalone 產生完整合成 fixture，再沿該 fixture 核驗 manifest、DB 路由與原 guard；核所有三支腳本的固定路徑相依後才交 Root 審查。尚未批准新的 Main 嘗試。

## d 獨立行情 fixture 與 e 首次終態

Root 發現原合成 preparer 以 H20 SQLite bytes 建行情庫後，要求改為獨立建 schema／資料。d preparer SHA `4bb1747fa9526e70163289e1e82862c7da6b630e6c3dd52affcd559ce4b767ed` 現以字串價格與整數股數建立獨立行情 DB；Root 已實讀建表／寫入程式與唯讀讀回的 2382 三個日期。原 standalone wrapper 因呼叫錯 QA 模組而失敗，preparer 子程序本身 exit 0，該失敗收據保留。

唯讀 postflight 收據 SHA `a7dcd113b56d0f34fc9f6ba0607b19d41a2251acbe0e8fdcb34f7e1c3e57ef0c`，14 checks 通過，4161 檔／22 dependency pins 不變，Main false。這僅支持新具名 Main attempt 的前置條件，不證原十股／684 bp。

批准後的新 `synthetic_main_full_20261009_e` 已 terminal exit 1；fixture preparer exit 0，child 在 dual verifier 讀取 `H20_CANONICAL_SOURCE_FILE_SHAS` 時失敗，尚未進 Main／SQLite。舊 seam 只提供 legacy verifier 的單 key 讀取，漏接 dual verifier 本身的同 key；不是產品行情讀取或下鑽失敗。

新 `source_map_seam_candidate_20261009_a/synthetic_main_child_candidate.py` SHA `35fac99dfbbe3980da5727079e3508809956f93ad61c4f249a25e2e09329d3c1` 改為兩個精確 pinned 模組共用同份已核 map，各限一次讀取，finally 各自還原原 os 及 loader；主例外不被 cleanup 訊息掩蓋。Root 實讀 seam 與 selftest，要求補完整成功 terminal／streams／起訖 pins 封套，不能只依工具輸出批准下一次 Main。selftest 暫清 legacy MODULES 僅核讀取／還原 callsite，不等於完整 legacy inventory；真正 Main 不得清空 MODULES。尚未批准該新候選 Main。

## 新 seam 成功封套與正確版本重配

Root 實讀 `source_map_seam_selftest_20261009_f/terminal_receipt.json` 與完整 stdout：native child exit 0、15 outer checks／10 callsite assertions true，stderr 空；收據 SHA `38f7c96c67abcd96d3a352d230e393bcbcba4e7da1bf3fc5dd2c4e5b8287c60e`。4161 檔 map、22 pins、候選與兩 fixed verifier 前後一致。只接受來源映射 seam 前置範圍，未改 selftest 的 MODULES 限制；b–e 外層 runner 自身前置失敗留存，不算 Main 嘗試成功。

授權後的 n attempt 誤配舊 m controller／preparer；Root 比對 owner 報出的 SHA 即指出版本選取錯誤。該次已 terminal，舊 preparer 建成合成 fixture，但 child 因缺少 H20_SYNTHETIC_QA_ROOT 在 Main 前失敗；Job 清空。此結果不能證 d 的獨立行情 fixture 或新 Main 旅程；錯版 fixture 保留，不續跑。

已要求 o 只從明示 d 路徑複製 controller `82529c9e658ed0f505d9c3899eb6b759bcba167c3d909df7ddf2f61070b38a9c`、獨立行情 preparer `4bb1747fa9526e70163289e1e82862c7da6b630e6c3dd52affcd559ce4b767ed`，搭配新 child `35fac99dfbbe3980da5727079e3508809956f93ad61c4f249a25e2e09329d3c1`；不修改 controller／dual／legacy／guard。Root 再次直接計算 o 三個目的檔 SHA 全符。只批准這個全新隔離合成 Main 組合的一次執行，終態仍待讀回；原十股、684 bp 與真人 EXE 尚未驗。
