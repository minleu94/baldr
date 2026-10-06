# UX08 可操作 viewport 整合（2026-10-06）

基線96ebcb33177f75e3f64c92b60330347b5301331c，純controller lane e52b27dd91f63982e28329f71ab966b887e994c0 審閱後以 cd33ddd6 採納，再接既有個股原生圖。UX08整項／stage4仍partial，沒有增加done。

## 可使用結果

價格／技術頁新增放大、縮小、往較早、往較新、重設全部；範圍旁明示可見日期與可見／完整筆數，下方價格及MA精確表保持全量。「完整來源範圍」與可見圖表分開，不改來源artifact。每次操作切核對後原DTO，恢復同源MA線；價格或MA缺值留None並斷線。hover與paint共用可見原日期槽，缺價格也可查看該日缺值，不壓縮缺口到其他日期，不插入休市日曆或補價格。

完整stock/source/version/cutoff/context同身份重讀可保留可見日期交集；已核驗保存content hash或已核驗完整價格／技術列hash作版本，未知版本／source或任一身份變更重設全部。取消重讀保留已載入範圍，重試同版本保留；stale report與已淘汰控制callback不改新圖。跨股票／來源清頁與拒絕投影清除viewport。範圍只在此view生命期，重開新的保存來源view從全量開始，同版artifact仍相同；不新增個人保存偏好或DB。

空資料停用按鈕，單槽不能再放大，邊界平移與反覆點擊clamp；初始化或操作重畫失敗保留全量精確表，後者停用控制並明示。所有範圍計算整數，畫圖沿既有隔離Decimal邊界，不改推薦／策略／PIT。

## 驗收

相關controller與真widget/UI/保存導航/投影回歸115 passed；其中新產品整合11個案例。Workbench85passed，update validator25passed/4skip，完整mypy820檔，5個變動Python compile、quant／diffcheck通過。擴充V5回歸63passed/2failed，兩項既有斷言（日期vs資料日、缺件summary期待值得看）以96ebcb33原UI檔重現，保留baseline證據，不修改無關首版結論。

raw命令／輸出：`output/qa/ux08_viewport_integration_20261006/`，含 all_related／metadata_final／v5_baseline／workbench／update_validator／mypy／quant，offscreen_readback與viewport_offscreen.png。真widget按鈕操作後可見10/20筆，精確表20列；系統字體僅在offscreen fixture載msjh.ttc，不改產品。沒有前景Native／真人、正式Task、migration、trueDB寫入或push，offscreen不當真人接受。其他owner三檔保持不變；父層另加的DOCUMENTATION_INDEX產品UX審查入口保留，不stage其hunk。

## 下一依賴與真實進度

viewport有限可操作工程完成，UX08仍partial：更多指標／markers、舊保存補建、圖商選型、Native／真人未完。9stage1done8partial0pending、24UX2done22partial0pending不變。Manual／Snapshot／架構／導航／index／coverage／routing同步，原計畫原文234727bytes只追加。

CSV consumer／CLI另包；review發現長路徑收據改名瑕疵，需先最小修正與fixture驗證，不能只以短路徑pass採納。UX23 readonly d9efbc6da62cfc19fa1f70edbf5e811bb021f814僅收到待父層安排，不在本包採納。回滾只revert本UI包與controller採納commit，保留他人及原資料／raw證據，不reset、cleanup。
