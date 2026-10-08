# F17 單次完整來源核驗中央審查

## 行為與界線

原 F17 factory 先完整核驗 bundle 的技術 parent 圖，再用 P01 open 重讀同圖。現在沿同一 StoreReader callback 收集已核驗 parent；所有 bundle manifest／shard／source／coverage 檢查完成、取消檢查通過後，才發布固定 P01 session。未傳 typed builder 的 BundleReader API 維持原行為；沒有跨操作快取、跳過核驗或使用 latest 補值。

builder 核對完整 callback 順序、同來源 context、cohort／count／clock／method、plan／receipt hashes、索引上限與固定 root。builder 單次使用，重建／重綁拒絕；取消在來源路徑工作前即生效。金融計算及決策日期條件未修改，沒有新增裸 float 或未來資料。

## 中央證據

root session 60588 exit 0：既有 P01 read_session 全檔、F17 query_reader 全檔、builder 完整 callback 與早期取消兩案例合併 **46 passed／466.87 秒**；全新合成 basetemp `C:/t/f17_root_single_graph_20261008_b`。前一 collection 指定錯誤 test 名稱，0 案例執行，原輸出保留，不當成產品失敗或通過。

涵蓋完整排序／分頁、Decimal 與未知尾序、完整分母、選取證據／來源變動拒絕、新程序讀回，以及一次 StoreReader／每個 parent 一次的實際讀取計數與雙讀 oracle parity。取消在 session 構造後仍不發行，manifest bytes 漂移不發行。root full-roots mypy 903 檔通過；六個修改 Python 檔 py_compile 與 diff check 通過。

固定三份 source SHA256：query `50d604b45add31afeedb21a058ec55bf89ef04d4b60dc0186a0d105195d72b05`；bundle `8251087995636762aa55bbab74923ba2d762aea6bc95b11a286acbc7bc1ee47a`；reader `5f20e40a11814889ef76d0a0155fe3958d077a282cea190daf63a92508dfec43`。

## 未授予

這是來源版接線接受，尚無新固定 EXE、Native 同來源比較或效能實測；不能由移除同圖重讀推論特定加速比例，也不能套用至 H20／2382 的 20 秒。正常資料更新至保存 F17 的閉環、官方 available_at／歷史 PIT、實際全市場母體與完整 F01–F23 仍待。原 stage 143.357 秒／121.005 秒取消與全部失敗封套保留。回滾前像：`output/qa/f17_single_graph_20261008_a/preimage/SHA256.txt`。
