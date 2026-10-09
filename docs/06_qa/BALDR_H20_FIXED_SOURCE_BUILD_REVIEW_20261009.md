# H20 固定來源封套建置審查

本輪完成純程式來源封套，不授予 Main 旅程、原始 H20、EXE、效能或真人接受。固定 base 為 `396c08e8f16c0d6e0ec2807e15aee387e56ca60e`，採原先已核對的九個 overlay，沒有納入目前工作樹的營收整合或其他 chat 變更。

成功封套為 `output/qa/h20src09/snapshots/s3`，包含 `source/`、`source_bundle.zip`、`source_manifest.json` 與 `BUILD_INFO.json`。共 4,161 檔、77,229,228 bytes，22 個必要來源 pins 均符合，Main SHA 為 `813fa8c4c2349cc295e590a2ec867e5ac01d76b84b1c8a6363027f0a8c70f5c9`。

- Source manifest SHA：`36099516489dadb243f3177ec6be4f641e10709edad6792139ee4f12ede08fc9`。
- ZIP SHA：`25d98adafa4898879f784e18b8cadf0e02e58748e5f4555a61deee61754b536b`。
- Builder SHA：`2da2edca440cdad3fffd1e39e1dd009a389147357637544c080dafab1a822f25`。
- 建置收據：`output/qa/h20src09/root_source_build_receipt.json`。
- 獨立驗證收據：`output/qa/h20src09/root_post_build_verify_1791510781880073800.json`。

Root 第二次獨立讀回全部 ZIP 與來源樹，核對每檔大小／SHA、精確檔名集合、無重複 archive member 與全部 22 pins，驗證通過。沒有 `launch_inputs.json`，`approved_for_launch=false`；三項接受欄位仍為 pending。建置與驗證未啟動 Main、未開 SQLite、未開原始來源 groups。

原 `9698340c28cbbfd369585c9212f1632846c2c7b16addc8b674c5e0eb2fc177b2` builder 保持不變。新的 QA builder 只有明示 `source_only=True` 才能在 launch template 為 null 時建來源；預設模式仍拒絕缺啟動輸入，pending 建置決定也拒絕。此分離避免將來源準備誤當啟動批准。

保留的失敗包括深層輸出位置觸發 Windows 長路徑，以及 `h20src09/snapshots/s1` 的 overlay base SHA 不符。後者直接比較 Git blob 與 archive bytes，確認 `core.autocrlf=true` 將 LF 轉成 CRLF；使用匯出命令的 `-c core.autocrlf=false -c core.eol=lf` 後，原始 Git blob SHA 完全符合，沒有改全域設定或預期 pins。`archive_eol_probe.json` 與 `base_pin_diagnosis.json` 保留。

`snapshots/s2` 則在清冊階段遇到 `.cmd` 的 Windows `lstat`／`fstat` permission bits 差異。新 QA helper 只在路徑與 handle 交叉比較時以相同檔案類型取代 permission bits；device、file ID、大小、時間、連結數與 attributes 保持精確，外層完整 `lstat` 起訖核對也不變。實際 `.cmd` 正例及其他八種身分欄位／檔案類型變更拒絕檢查通過。`native_identity_diagnosis.json` 與 s2 失敗日誌保留。

接續工作為以固定來源執行真正 Main 的 H20 列表、2382 下鑽、返回、收藏及 typed fresh reopen，保存分段耗時與完整程序清理。合成旅程不能代替原始 10 檔／684 bp 保存版本；原始來源啟動仍需獨立 launch 環境、來源及 runtime 路由驗收。
