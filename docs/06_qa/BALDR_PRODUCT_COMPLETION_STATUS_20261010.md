# Baldr 補完範圍與下一步（2026-10-10，未完成）

本表是本次產品補完工作的具名 QA 接續索引，完整需求仍以[原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)為準；不取代 Snapshot、Roadmap、架構或 Manual 的 Scoped SSOT。保留 P00–P14、M1–M3、F01–F23 全部範圍，不以已通過的切片重新定義完成。P07 目錄切片提交為 `6407d6e8`；本輪另完成 P08 帳戶綁定基礎與相關回歸，新 EXE 與真人結果尚未取得。

## 工作包：現有基礎與未完成驗收

| 包 | 現有基礎／可核證據 | 還需完成的範圍 |
|---|---|---|
| P00 共用契約 | 多種保存來源、query、method、時鐘與正常 Main 接線已有切片 | 所有包使用一致版本／日期／帳本身分，保存→讀回→返回→新程序總旅程 |
| P01 完整母體與資源 | 固定千檔、完整 DTO／30 組比對有證據 | 最新 Q13 未達 300ms，link 負例未建立；完整 cold/warm、AND/OR、拒絕矩陣、正式 UI 與真 N 仍待 |
| P02 技術條件 | 既有 MA/KD/MACD／具名量比，另有排列、KDJ、BB／ATR 的有限方法 | 跨方法完整規則、同母體正常來源、返回／收藏／新程序與版本等價驗收；原料不等於策略 |
| P03 其他資料域 | 原籌碼、法人、基本面、產業與官方狀態服務；營收有獨立分支 | 各域可得時間、coverage、版本／PIT、保存完整母體與 UI 閉環，缺資料不能補為安全 |
| P04 共享選股體驗 | 部分全域篩選、排序、分頁、比較及收藏已接 | 所有域／條件共同 query、正常產製來源、跨頁狀態保存及重開 |
| P05 個股可讀性 | `65d5f515` H20 來源／完整錯誤修正、`9d5e8cd4` 正常 Main 耐久案例 | 原 2382 同源首次名單／下鑽／報告／返回速度、跨域時效、摘要與用途真人判讀 |
| P06 持倉情境 | 原 Portfolio／Health／研究情境基礎 | 同股多帳本、明示配置情境、保存／新程序與原模型關係；不能直接把毛報酬轉權重 |
| P07 自有策略 | Registry／StrategySpec／限定封存規則卡；`6407d6e8` 有限方法目錄對齊 | 完整策略規則／executor、型態與 VCP 定義、多策略共振、正常 UI 消費者；目錄尚不是策略產品 |
| P08 策略帳本與績效 | 原 `paper-main`、ledger/snapshot、唯讀週報、Registry 歷史比較；明示版本帳戶 binding／分離路徑，50 PASS／1 skip | 逐筆 provenance、受控 writer／ledger／benchmark／績效與正常 UI；新帳戶週報保持不可計算，writer 仍限制 paper-main |
| P09 收藏與追蹤 | 不同來源的 bookmark／restore 切片 | 全域 query/source/origin、各域新程序、錯版／半批／晚到回呼與完整返回 |
| P10 四用途首頁 | 四用途引導卡、九工作區導覽已存在 | 同源日期、市場／模型／持倉／更新完整往返／重開、跨時區與真人理解 |
| P11 自然結果 | 既有 daily journey 與 Forward Performance 部分進度 | 每筆 prediction→entry→outcome→readiness／公平比較接線；未成熟保持 waiting，不用 replay 代自然結果 |
| P12 時效與維運 | 已有 status／scheduled operations 與具名歷史檢查 | 超時／依賴／重試／終態、下一次真自動執行及完整時效 Gate；文件中的 running 不是本輪 live 證據 |
| P13 整體接受 | 多項回歸、Manual 與受限整合測試 | 四用途全產品旅程、程序樹資源、同版 EXE／來源、Native 與 3–5 位非技術真人接受 |
| P14 可攜同版 | 舊候選有各自的同版受限收據 | 目前碼版的新凍結 candidate／Python 等價與完整旅程；保留現有包，不以舊包代表新碼 |

P01 最新證據為 Q13 single-warm：30 組完整 DTO 相等；baseline p95 1,342.431ms、candidate p95 1,400.885ms，都未達原 300ms。這不是乾淨全矩陣或產品保證；較早 Snapshot 的局部時間不覆蓋它。六個負例通過不等於七個通過，link setup 未成功必須保留未驗。

## 條件清單：不能遺失的剩餘工作

| ID | 保留的範圍與限制 |
|---|---|
| F01–F05 | MA5/20、KD、MACD 交叉與 5／20 日量比的各自版本；F02 四均線排列不是坡度或交叉；KDJ 另有明示方法，不能改名當型態辨識。完整來源／母體與交互旅程仍逐項驗。 |
| F06 | BB30 bandwidth／ATR14-SMA 是已保存原料；收斂窗口／門檻、多段 VCP、pivot／突破／失效仍需定版與因果驗證。 |
| F07 | Decimal 價格區間／排序已有旅程切片；正常來源、EXE／守衛收尾及真人接受不能省。高中低命名須有明示數值。 |
| F08–F09 | 分點與三大法人分開；原期間、coverage、連續官方開市日、缺日與 available_at 必須保存核驗。 |
| F10–F11 | 權證標的／掛牌／到期關係；基本面具名成長指標、前期／期間／修訂與 PIT，未知不可當不符合。 |
| F12 | 營收 reader/query/view/bookmark 切片存在；T38 正常轉場與自然收尾通過，收藏前精確 resolver message 為 `unexpected_private_sqlite_uri`。這是 QA 守門拒絕，不能據此推論正式 marker 損壞；未到 fresh child。正在追精確 URI／callsite，不放寬 SQL 守門。 |
| F13–F15 | 產業同期分類／母體與相對強度；族群核心的透明定義；成交額代理與真淨新資金分開，不能冒稱來源不存在的流入。 |
| F16–F18 | 注意／處置當下 reader 與完整事件／可得時鐘分開；處置預警須有公開規則版本與累積史料，未知不是安全。 |
| F19–F21 | 各域資料日／風險三態、全域多欄穩定排序、完整已選母體分母與清除／復原；已選 cohort 不冒稱全市場。 |
| F22–F23 | 真正版本化多策略共振與技術／籌碼／基本面三域共振；方法數不當策略數，一域未知不標成立。 |

## 里程碑與當前分工

M1 有歷史固定候選切片，但現在碼版的 EXE／Native 真人未完成；M2 有多個保存／完整已選母體／新程序切片，但條件、資源矩陣、原來源與真人未閉合；M3 策略獨立帳本與歷史績效工作流未完成。

- root：審查正式差異、執行驗證、保存進度；不覆寫其他文件整理工作。
- F12 葉片：T38 已執行一次，正常轉場與 launcher→native PID 鏈核對通過；收藏前 QA SQLite 拒絕仍未解，下一候選先交 root 審核。
- 原 2382 葉片：C 候選已執行一次，H20 頁籤位於可點擊範圍外而自然收尾，未選到 2382、未取得下鑽速度；來源指紋不變。子程序 exit code 未取得，外層 exit0 不能代表成功。D 候選正在修正真實頁籤箭頭操作與 exit code 讀取，尚待 root 審查及執行。E 槽私人副本／狀態、D 原來源唯讀；見[四段計時方案](BALDR_H20_2382_TIMING_PLAN_20261010.md)及 root follow-up 的 C 終態。
- P08 Luna max：明示 binding／帳戶路徑切片取得 50 PASS／1 skip；成本 reader 修正另取得 38 PASS／1 skip、真 SQLite 成本邊界 1 PASS，歷史 basis／ledger-window 未知時不計算收益。逐 snapshot 證據 writer 與策略 UI 尚未完成。見[P08 契約與限制](BALDR_P08_ACCOUNT_BINDING_SLICE_20261010.md)。

真人目前可做[合成來源六步驗收](BALDR_COMPOSITE_HUMAN_CHECK_20261010.md)：窄窗、完整文字、返回、比較、收藏即時重開及關閉後重開。它使用 1000／1256，不替代原 2382／H20、真實推薦或整體四用途接受。

恢復後 root 已審讀 P08 receipt 候選全部差異：原子寫入、歷史缺件維持 unknown 的設計有合成測試證據，但種子持倉數值一致性仍需補負例，尚未套用正式來源。推薦理由窄窗與鍵盤捲動聚焦測試取得 3 PASS／native exit0；七份人驗入口 UI 指紋再次相符，仍沒有真人結果。T39 月營收精確鎖核驗候選與 H20 D 候選由兩個葉片平行準備，root 審查後才執行。

H20 D 後續實測：root 完整審查 C→D 差異及 launcher，五份核心 hash 與唯讀 preflight 30＋17 pins 相符，執行一次取得 child PID 35724／exit1，未逾時、未由 launcher 終止。真頁籤箭頭點擊三次成功；原名單 10 列可研究、0 列未知、2382 唯一。Main 啟動至列表就緒 35.422 秒，頁籤揭露與點擊至就緒 30.891 秒；這是一次固定來源觀測，不是 p95。隨後因「2382 列未在真實表格 viewport 內」停止，未取得下鑽／報告／返回時間。原來源 metadata 前後相同；內層收據 `E:/t/h20p2382d/output/qa/h20_2382_timing_receipt.json` SHA-256 為 `a3ae7d65fa99e6bbff3730885d4b68f794cf4050bae3a1aff99fb777b8633636`。下一 sibling 補有界真實表格捲動，不覆寫 D 收據，也不以程式直接選取冒稱真實操作。

詳細成功／失敗與 scope 證據保留於[root follow-up](BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md)。本表沒有宣稱 live Task、原自然結果、正式模型品質或全產品完成。

P08 receipt v2 已經 root 審核並整合，正式 import 路徑取得 55 PASS／native exit0、mypy／語法檢查通過。此基礎僅有 unknown 與合成 seed_reference 的原子保存／讀回；未接真實 seed、daily writer 或週報資格，P08／M3 仍未完成。契約、驗證及回滾見[快照紀錄切片](BALDR_P08_SNAPSHOT_RECEIPT_SLICE_20261010.md)。

H20 viewport 的純合成 root 探針：正式 RecommendationView 嵌入同 PersonalH20ResearchWidget／panel constraints，960×700、680×500、460×600 都取得 table 高192、viewport 高147，scrollToItem 後第八列可見，native exit0；未重現 D 停點。這不包含 Main 原來源、真 manifest 文字或 worker；E sibling 必須記錄真實初末幾何及 ancestor 裁切，待幾何穩定再以原生捲動操作，不能以此探針宣稱原下鑽成功。
