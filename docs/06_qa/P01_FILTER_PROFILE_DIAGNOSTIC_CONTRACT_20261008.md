# P01 篩選效能診斷與選股解析改動（完整效能驗收尚待）

固定1,000檔P01基線的篩選／selection／首頁p95為5.1925273秒，四類暖操作未達300毫秒；原完整矩陣保持失敗，詳[基線QA](BALDR_SYNTHETIC_UNIVERSE_1000_READBACK_20261008.md)。本輪只補診斷工具，不更改產品、母體、來源核驗、原樣本或期限。

新工具在 `output/qa/p01_filter_select_profile_diagnostic_20261008_a/profile_filter_select_2897.py`，凍結SHA256 `734220e9363ed538bd7384a1fde7f4b8291fbad886a5308c10cb06993f5a6568`。只載固定2897 archive、controller38b4、helperc63及已pin recovery report／原合成store；不混工作樹F17或MA新功能、不重跑producer。原暖排程仍保留五類各30次，只對五種原篩選條件各第一次呼叫加cProfile。整份輸出都是診斷，不重算300毫秒接受結果。

中央獨立自測exit0，新收據 `output/qa/p01_profile_root_selftest_bfd563af/selftest_result.json`。自測只將輸出收據路徑改為全新QA目錄，工具檔案SHA前後一致；沒有產製器、reader、SQL、網路或實際OS child。七個模擬launch audit包含精確命令、漂移與token重用拒絕；五個合成profile事件核實case／AND-OR與工具身分，錯標籤反例拒絕。此證據不是實際child manifest讀回或原1,000檔來源的profiling通過。

中央審查後補入工具自身device／file-id／size／mtime／ctime／SHA，保存於manifest並列入parent寫入保護；worker安裝profile hook前核同次manifest與自身，事件逐筆帶身分，parent核五筆及前後一致。這些實際程序路徑仍待真診斷證明。單一profiled-call wall與整個record wrapper wall分欄；函式cumtime有巢狀關係，不得加總或相減冒充完整階段耗時。

下一步執行一次固定來源診斷，保留所有失敗、Job清理與source／DB／store前後核驗，再以真函式呼叫次數及成本選定性能修改。未量到之前，`Plan.to_dict`、JSON解碼、child讀取或全母體篩選只是候選瓶頸，不把靜態推論寫成已知主因。正式全市場、Native、真人與完整P00–P14／M1–M3仍未接受。

## 真診斷首次讀回（歸屬核對尚待）

固定harness真執行已終態exit0，`C:/t/p01_bycz00e0` 保存 `passed_diagnostic_only`，五種既定篩選各一筆profile。新版唯讀抽取器首次exit1：manifest、來源pins、profile結構、清理、parent write guard與runtime denials檢查為true，但 counts與worker身分交叉檢查false；正在核實真artifact欄位位置，不刪除這次拒絕、不重跑profile。原300ms接受矩陣保持失敗。

根代理直接有界讀取原events：AND match30檔的call wall為19.5315291秒，`read_selection_page` cumtime18.9667921秒，`_materialize_page`18.5588176秒；`_read_session_child_artifact`26次18.4643828秒，snapshot `from_json`416次16.4684633秒。AND unknown2檔的call wall1.6320011秒，只讀1份child／16份snapshot；`_state_metadata`5次cumtime0.9094589秒。其餘call wall為AND no_match3.8416484秒、OR match_unknown20.2208145秒、AND two_match5.2559268秒。這些是含cProfile成本的單筆呼叫；巢狀cumtime不可相加、不是p95、不代表目前工作樹／F17／MA整合速度。

據此下一項效能設計優先審查頁面跨child的重複解析與metadata驗證。任何解析proof重用須綁定exact內容及reader-issued不可變物件，保留每操作fresh來源與檔案完整性檢查、tamper拒絕、有界記憶體、來源分隔與取消；尚未套用此類產品改動。

抽取器欄位錯配已修正：parent wrapper沒有完整bootstrap/source hash欄位，worker建立時間與launcher資料在resource summary與獨立bootstrap檔；新版按真schema綁定各檔，不放寬缺件。舊版拒絕封套與preimage已保留。新版extractor SHA256 `ca901d28f479c65c514b94e0187dd6678d6f12bfcc87a979596b39b8d358f130`；根代理獨立重讀exit0，`output/qa/p01_profile_root_readback_bycz00e0_20261008/extraction.json` 為 `profile_diagnostic_verified`，十項來源／身分／counts／清理／guard檢查全true、profile五筆。worker PID10108、launcher32728、Job關閉且無剩餘owned程序，sampler6445筆、peak working set161423360 bytes。這授診斷證據接受，仍不授300ms／p95或整體產品接受。

頁面materializer本來已依artifact分組，26／27次讀取是不同child；僅同operation重複引用解碼cache不足以改善此瓶頸。下一輪須評估有界session content-addressed proof重用或已核母體下的選股解碼路徑，每operation仍完整fresh檔案bytes／SHA／來源binding核驗；未量測前不宣稱改善比例。

## 選股解析改動的第一批證據

共享後端改動已在隔離257股真 writer 來源完成跨段 targeted 測試：1 passed／129.31秒。所選57列跨 segment；測試觀察到65份 batch artifact bytes 仍完整 fresh 讀取／SHA核驗，只對57個所選 snapshot 執行解碼；結果與 strict query page DTO 相同。同 mtime 的未選 sibling 內容遭修改仍拒絕，讀檔中取消不發布頁。首次測試選頁導致整個 child 全選、找不到未選 sibling 的 StopIteration 保留為測試假設失敗，不計為產品通過。

中央靜態審查另外要求公開 canonical source payload、query identity 及原 `index_bytes` 完全相容；proof bytes 只加入私有 combined 64MiB 預算，不能改舊收藏來源身分。跨版本固定3d reader保存→新reader新程序重開、原完整回歸及凍結提交仍待完成。以上解碼次數證據不證明300ms或新p95：原1,000股完整矩陣四類失敗保持有效，需完成這次改動與相容審核後再量測。

固定3d跨版本證據現已補齊兩種收藏：一般P01測試1 passed／14.40秒，價格F07測試1 passed／11.10秒。中央直接讀取價格測試原log、`price-cross-version-compatibility-receipt.json` 與source SHA收據：舊模組由固定3d archive載入，新PID價格reader由工作樹載入；完整source／query／result／page／bookmark JSON一致，`price_index_bytes=9173`，主選S0001仍在S0002/S0001比較籃。此處只授這份17股真Store下的格式／來源相容，真Main／257股／效能／EXE仍分別驗證。

中央獨立 repository proof 回歸1 passed／2.27秒：batch GC後selected fresh讀回、clone拒絕、未選sibling同mtime改動拒絕與取消都通過。產品兩檔維持repository SHA `85a8ce21806a902d64f46d2bfb013ac9e06ab8a9324902453a077606750cf9fa`、query SHA `22ba48aa2ba2d52f37d187410c6b8bfe1633b2a2ef3e807b4cbac032328ab471`；跨版價格測試新增後read_session test SHA `de496a5d8d534b30bd7c2f35b59693b07f0d35312f484eb5e5e0528d4c1e4627`。未重跑1,000矩陣，也未以相容證據宣稱效能達標。

## 2026-10-11 後續矩陣狀態核對

本文所列 10/08 原診斷與其固定來源結果仍是歷史證據；後續 session-metadata 與 proof-gated 收據使用不同 runtime/source pins，不能混成同一組 p95。`BALDR_P01_PROOF_GATED_REHYDRATION_20261009.md` 記錄 page flip 220.0639 ms、global sort 248.2336 ms 通過、filter 677.9689 ms 未通過；目前 `PRODUCT_UX_QA_INDEX.md` 所列 85bc 六角色矩陣則為翻頁 196.205 ms、排序 191.8186 ms、篩選 523.902 ms，冷啟動至首頁 20.0319 秒。這些是隔離候選矩陣，篩選仍高於 300 ms，且不代表完整 Main／EXE／真人驗收。
