# C3/C4 Manifest 差異核對

> 本文只核對 2026-09-25 的封存 JSON receipt 與 manifest 身分，不代表目前程式碼或 QA 狀態。

| 證據 | HEAD blob OID |
|---|---|
| `docs/06_qa/C3_C4_RELEVANT_SUITE_DRAFT_MANIFEST_20260925.json` | `3ea2891dab5441d62f430e8d7aa6e8b2a919ef5c` |
| `docs/06_qa/C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json` | `b51f084ab39dda46b407330dbdd8a9be2808d5a0` |
| `docs/06_qa/C4_FINAL_UNION_RECEIPT_20260925.json` | `74cc3018370dd1aab43a2fc5ef793fd9326fca56` |

## Route manifest 身分

Receipt 的 `route` 記錄暫存來源 `C:\Users\archi\AppData\Local\Temp\c4r_de0d7b\route.json` 與工作樹路徑 `docs/06_qa/C4_FINAL_RELEVANT_SUITE_MANIFEST_20260925.json` 使用相同 SHA-256 `3E7CF99F6CB2133D5B019B8E99C305FAC1CF386E973210CA49D7490F57358E72`，大小為 142,438 bytes。

封存 C4 manifest blob 為 137,934 bytes、SHA-256 `22737116CC50B84089272CCFBB31A0E3E3F2C19267E41281543A2300D308C5A0`，內容有 4,504 個 LF、沒有 CR。將該 blob 的每個 LF 轉為 CRLF 後，得到 142,438 bytes，SHA-256 也精確等於 receipt 的 route/workspace hash。因此尺寸與 hash 差異由行尾格式解釋，屬同一 JSON 內容的 LF/CRLF 表示差異，不能據此判定 manifest 內容不一致。

## C3→C4 input delta

以 JSON parser 讀取兩份 manifest 的 `tests`、`sources` 陣列，按 `path` 對應並比較 `bytes`、`sha256`：測試皆為 234 個路徑且無增刪，來源皆為 237 個路徑且無增刪；3 個測試與 1 個來源的 metadata 改變。Receipt 的 `c3_to_c4_input_delta` 列出其中兩個測試及該來源，所列 hash 均與兩份 manifest 相符。未列出的第三個測試為 `tests/test_personalization_generation_cli.py`，由 46,051 bytes / `B761BDB9E3B3880C7125B4881AED5F95B695CFA5067069C4A82392A783D7FC1F` 變為 48,881 bytes / `40F209EED4ABD6400AEB361539CD050A57C20D1F528D17C55B53CB3B14AD7F90`。

這是相對於完整 manifest 差異的 **mechanical diff omission; scope/intent unresolved**。該測試在兩份 manifest 都標為 `C2-BASE`，且不在 C4 的 `c2_base_drift` 清單；JSON 未定義 delta 是否僅列 C4 專屬輸入變更，因此不據此判定 receipt 無效。
