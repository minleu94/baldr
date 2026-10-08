# c611 固定候選：建置及同版驗證

候選來源固定為 c611ed515ca06ae3c2a8d6b8fa56552c5f7c811b，版本 2026.10.06+c611ed515ca0；不納入工作樹其他聊天的 dirty 變更，也不因後續文件提交改稱新版。包含正常保存研究讀取根、H20 收藏保存／重開、個人收藏本地排隊及基本面副本配置；F17 僅是來源 reader，尚未接完整選股。

新候選在 dist/candidate_c611ed515ca0_1cc2db97/baldr/baldr.exe，53,122,929 bytes，SHA256 d37bed44f21be2a1bde646a54c53097cb3f5a2898693e31efa9fd205b8c5e2ef。source archive SHA256 4336ff7be5ddb8581e3e205ede6397ecfae7321b4a02145f19e6171baa9653bb，依賴鎖 b1a3bb4bd03246c025f09bca3658104aff6c676983c878f46d118cec992df743，建置完成於 2026-10-08 02:06:52.986117 UTC。中央逐值核 source metadata／BUILD_INFO／candidate receipt、archive 與 exe hashes；原 exe SHA ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e 不變。

BUILD_INFO 保持 immutable built_not_validated，驗證收據另存，不覆寫建置收據。中央建置核對 output/qa/c611_candidate_build_root_20261007_a.json 不授同版、原 Main H20 或 Native 資格。

| 驗收範圍 | 目前證據 | 邊界 |
|---|---|---|
| 固定版本／archive／exe／依賴／原 exe 保留 | 中央一致，build terminal exit 0 | 未簽章、不替換原 exe |
| 既有同版隔離回歸 | output/qa/baldr_same_version_c611ed515ca0_60600e21/same_version_receipt.json，passed_isolated_fixture，terminal exit 0 | 四用途／收藏與重開／worker取消／配置／呈現 H20 是既有合成 probe；不代替真保存母體或原私人來源 |
| Python launcher、直接 Qt、-m 與 exe 共用設定／版本 | 上述收據逐值一致，invalid DATA_ROOT 拒絕 | resource_root／frozen形態／screenshot路徑為明示必要差異 |
| 257+1正常 Main 同一 sealed store/query/bookmark | 新精確 controller/probe 尚未通過；origin 前置要求、合成 seed path 與 Windows strict resolve 測試環境失敗各自保留 | 不用 browser root override，不以兩模式各自產製相似版本代替；尚未授固定exe完整旅程資格 |
| 原十股→2382真 Main 載入／雙擊／返回耗時 | guard preflight通過；首個真 Main attempt在隔離OUTPUT的portfolio目錄初始化受guard阻擋，未到H20讀取 | source/archive inventory不變；下一attempt預建app-local目錄並明示區分原source只讀與隔離runtime DB寫入，不推導Native或p95 |
| 真人閱讀／速度／完整四用途／實際市場資源 | 未驗 | 未發新真人啟動檔，完整 P00–P14/M3仍開放 |

同版驗證首次 attempt 9b8cc079 在印中文狀態時因宿主 cp1252 失敗，未執行案例；原 failed receipt 保留。改設 PYTHONUTF8=1／PYTHONIOENCODING=utf-8 後另開 60600e21 全部通過，不重建、不覆寫候選，也不刪除原失敗。這是驗證工具宿主編碼問題，不是候選程式的中文 UI 失敗。

H20 Main 首次完整 attempt `output/qa/h20_main_canonical_design_20261007_a/attempts/20261008T022030Z_27782a316737/controller_receipt.json` terminal exit 1、18.234秒；未到名單或2382，下鑽速度仍沒有新量測。下一輪只允唯一QA case的明示app-local runtime SQLite，原H20 snapshot必須mode=ro／query_only，正式market DB與任何原來源寫入仍拒絕。不能把runtime必要DDL計數冒稱所有SQLite零寫入。

後續本地 `1e0e28ae` 市場歸屬來源提交不在此固定候選，不重建或修改c611的BUILD_INFO；其中央12項與892檔mypy資格另見市場歸屬QA，也未接完整篩選UI。
