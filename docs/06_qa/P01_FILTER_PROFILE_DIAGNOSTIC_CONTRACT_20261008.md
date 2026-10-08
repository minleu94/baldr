# P01 篩選效能診斷工具（實際歸因尚待）

固定1,000檔P01基線的篩選／selection／首頁p95為5.1925273秒，四類暖操作未達300毫秒；原完整矩陣保持失敗，詳[基線QA](BALDR_SYNTHETIC_UNIVERSE_1000_READBACK_20261008.md)。本輪只補診斷工具，不更改產品、母體、來源核驗、原樣本或期限。

新工具在 `output/qa/p01_filter_select_profile_diagnostic_20261008_a/profile_filter_select_2897.py`，凍結SHA256 `734220e9363ed538bd7384a1fde7f4b8291fbad886a5308c10cb06993f5a6568`。只載固定2897 archive、controller38b4、helperc63及已pin recovery report／原合成store；不混工作樹F17或MA新功能、不重跑producer。原暖排程仍保留五類各30次，只對五種原篩選條件各第一次呼叫加cProfile。整份輸出都是診斷，不重算300毫秒接受結果。

中央獨立自測exit0，新收據 `output/qa/p01_profile_root_selftest_bfd563af/selftest_result.json`。自測只將輸出收據路徑改為全新QA目錄，工具檔案SHA前後一致；沒有產製器、reader、SQL、網路或實際OS child。七個模擬launch audit包含精確命令、漂移與token重用拒絕；五個合成profile事件核實case／AND-OR與工具身分，錯標籤反例拒絕。此證據不是實際child manifest讀回或原1,000檔來源的profiling通過。

中央審查後補入工具自身device／file-id／size／mtime／ctime／SHA，保存於manifest並列入parent寫入保護；worker安裝profile hook前核同次manifest與自身，事件逐筆帶身分，parent核五筆及前後一致。這些實際程序路徑仍待真診斷證明。單一profiled-call wall與整個record wrapper wall分欄；函式cumtime有巢狀關係，不得加總或相減冒充完整階段耗時。

下一步執行一次固定來源診斷，保留所有失敗、Job清理與source／DB／store前後核驗，再以真函式呼叫次數及成本選定性能修改。未量到之前，`Plan.to_dict`、JSON解碼、child讀取或全母體篩選只是候選瓶頸，不把靜態推論寫成已知主因。正式全市場、Native、真人與完整P00–P14／M1–M3仍未接受。
