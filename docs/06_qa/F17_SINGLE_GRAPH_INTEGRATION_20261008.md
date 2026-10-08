# F17 單次完整來源核驗中央審查

## 行為與界線

原 F17 factory 先完整核驗 bundle 的技術 parent 圖，再用 P01 open 重讀同圖。現在沿同一 StoreReader callback 收集已核驗 parent；所有 bundle manifest／shard／source／coverage 檢查完成、取消檢查通過後，才發布固定 P01 session。未傳 typed builder 的 BundleReader API 維持原行為；沒有跨操作快取、跳過核驗或使用 latest 補值。

builder 核對完整 callback 順序、同來源 context、cohort／count／clock／method、plan／receipt hashes、索引上限與固定 root。builder 單次使用，重建／重綁拒絕；取消在來源路徑工作前即生效。金融計算及決策日期條件未修改，沒有新增裸 float 或未來資料。

## 中央證據

root session 60588 exit 0：既有 P01 read_session 全檔、F17 query_reader 全檔、builder 完整 callback 與早期取消兩案例合併 **46 passed／466.87 秒**；全新合成 basetemp `C:/t/f17_root_single_graph_20261008_b`。前一 collection 指定錯誤 test 名稱，0 案例執行，原輸出保留，不當成產品失敗或通過。

涵蓋完整排序／分頁、Decimal 與未知尾序、完整分母、選取證據／來源變動拒絕、新程序讀回，以及一次 StoreReader／每個 parent 一次的實際讀取計數與雙讀 oracle parity。取消在 session 構造後仍不發行，manifest bytes 漂移不發行。root full-roots mypy 903 檔通過；六個修改 Python 檔 py_compile 與 diff check 通過。

固定三份 source SHA256：query `50d604b45add31afeedb21a058ec55bf89ef04d4b60dc0186a0d105195d72b05`；bundle `8251087995636762aa55bbab74923ba2d762aea6bc95b11a286acbc7bc1ee47a`；reader `5f20e40a11814889ef76d0a0155fe3958d077a282cea190daf63a92508dfec43`。

## 未授予

這是來源版接線接受；固定 EXE 與一般隔離比較已完成，但 F17 同來源 Native 旅程仍失敗，見下方補記。不能由移除同圖重讀推論特定加速比例，也不能套用至 H20／2382 的 20 秒。正常資料更新至保存 F17 的閉環、官方 available_at／歷史 PIT、實際全市場母體與完整 F01–F23 仍待。原 stage 143.357 秒／121.005 秒取消與全部失敗封套保留。回滾前像：`output/qa/f17_single_graph_20261008_a/preimage/SHA256.txt`。

## 固定 EXE 與同來源旅程補記

固定 330b98f416f7 EXE 已建置：`dist/candidate_330b98f416f7_afa55c15/baldr/baldr.exe`，SHA256 `08fe63362d61ecf6c49e54c659c1d37d21aaee5490eab9b62ede985bb5bdf8a4`；source archive SHA256 `7853244fc33dfff25bac45b75f5bef52f2a5a82eef2b0db6f3794cf4f509693e`。一般隔離同版比較通過（root session60033，`output/qa/baldr_same_version_330b98f416f7_9c8f0282/same_version_receipt.json`）；這不能替代 F17 真保存來源的新程序旅程。

root另建全新 QA控制器目錄 `output/qa/f17_native_same_source_330b98f4_20261008_a`，由原9d契約複製、精確更新固定來源／EXE pins，保留合成 fixture／query pins及300秒總期限。stage hook改記同圖 builder構造，沒有假造第二次open事件；純logger契約8項通過，plan-only與verify-ready皆通過且未啟動來源API。

實際 root session51855 terminal exit1，`attempt_66716c84f243` 為 failed_preserved_attempt，controller280.719秒。source Main catalog／exact-open成功，bundle exact134.3359489秒（含builder1.1668109秒）、select0.5349204秒、外層open137.085592秒；execute100.9564537秒、首個page26.0443581秒。下一頁以 technical_official_query_reader_v1_cancelled 結束，source receipt報全域翻頁1到deadline；frozen child未啟動。

此證據證明同圖重讀已消除且開啟完成，但揭露全母體query／分頁仍昂貴；不授Native／跨程序收藏／效能／真人接受，也不以延長期限或減少母體判通過。後續需定位execute／page實際成本，保持每份來源pins、完整分母及來源變動拒絕。

## 後續靜態成本追查（未作耗時歸因）

唯讀追查確認 F17 每列的 membership／technical filter／sort key／counts 路徑會反覆呼叫 fact.to_dict 並重新 strict JSON decode；底層 P01 execute 分頁及最終頁面 materialization 也會重新完整驗證涉及的 child artifact。plan.to_dict 與 metadata accessor 另有重複解析路徑。這些是實際呼叫關係，尚無 profiler 證據可判定其耗時占比；不能直接用它們解釋上述100.956秒或26.044秒。

下一次受控量測須分開 open／execute／page，記錄各解析、rule語義重播、SHA與artifact read的呼叫數、CPU及累積時間。任何優化均須保持完整來源核驗、child變動拒絕、完整母體、取消與原query／page身份；不以跨操作快取或省略核驗換取通過。1000檔矩陣仍執行時暫停 profiler 與其他重測。
