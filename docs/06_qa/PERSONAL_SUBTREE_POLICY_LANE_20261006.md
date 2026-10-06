# Personal subtree 政策變更 lane

2026-10-06；使用者改指定 FA_Data 內獨立資料夾，父層選定 `DATA_ROOT/personal`。本節取代前兩份 lane QA 的「personal 必須在 DATA_ROOT 外」政策與 LOCALAPPDATA 首選提案；外部 custom root 仍可明示相容，但不是現在的預設接線建議。

lane：`C:/Projects/PythonProjects/technical_analysis_personal_store_lane`；branch `lane/personal-store-separation-20261005`；本包基準 `5115a12772397960ebad783396425ea34457d950`。開始及提交前 dev `6d9a4316a9fb6cb8d63559ff9b7e8a183b2be938` 的 personal_data_paths 與 lane 同版，涉及 guard tests 無共享 dirty ownership；未 merge/rebase 主線。

## 限定變更

- `app_module/personal_data_paths.py`：只放寬精確的 `market_root/personal`；其他 ancestor、相同 root、任意市場子目錄、sqlite/raw/output 與 legacy output 重疊仍拒絕。`personal/notes` 不能取代精確 subtree root。原 link／reparse／hardlink／Windows alias 守衛保留。
- 市場 CSV whitelist 額外明確拒絕頂層 personal（含 Windows case alias），manifest 再核對來源不落個人 subtree；舊 output／watchlist JSON、notes、任意 SQLite/DB/sidecar 不在市場白名單。
- 同 module 的 COW source path 守衛補拒絕 personal subtree，避免內置 personal 被 market-root containment 誤當 legacy source；沒有改 COW converter、activation、capacity、rollback 或服務控制邏輯。
- `tests/test_personal_data_paths.py` 新增新政策允許／拒絕與 synthetic JSON／SQLite v1/v2 pipeline fixtures；`tests/test_personal_journal_storage.py` 將 fixture 改為市場內精確 personal，來源不變斷言核對 personal 外的市場檔與 legacy output。
- `tests/test_personal_watchlist_cow_activation.py` 只改一個舊 negative fixture 的 root：`market/personal` → `market/output/personal`。原測試拒絕現在使用者已准許的 root，需同步新政策，不更動 activation 實作或其餘測試。

未改 global config、UI main、Journey、Manual、plan、Portfolio／Ledger／Paper，未建立正式 D:/personal、未讀搬真 journal/watchlist/帳本/持倉。沒有正式 migration、activate、export、分享、push 或 dev cherry-pick；未新增代理。

## 位置與主 owner 接線建議

正式 root 選擇：`config.data_root / 'personal'`，目前預設 DATA_ROOT 對應 `D:/Min/Python/Project/FA_Data/personal`。位置決定不是轉換或啟用批准；resolver 缺 explicit root／PERSONAL_DATA_ROOT 仍拒絕，不自動配置或建立資料夾。

| 用途 | 指定 root 下路徑 |
|---|---|
| 獨立收藏 DB | `watchlists/watchlists.v3.sqlite` |
| marker／lock／receipt | `watchlists/watchlists.v3.sqlite.cow-active.json`、其 `.lock`、`watchlists.v3.sqlite.cow-conversion.v1.json` |
| 原 JSON bytes 備份 | `backups/watchlists/source.<source-path-sha256>.json` |
| rollback audit marker | `activation_backups/watchlists/rollback.<activation-id>.json` |
| notes JSONL／sibling lock | `research_notes/journal_entries.jsonl`、`research_notes/.journal_entries.jsonl.lock` |
| notes backup／audit 保留路徑 | `backups/research_notes/`、`research_notes/audit/`（未有 producer） |
| 帳本域保留 root | `ledgers/`（原 owner，未接手） |

市場 DB 仍是 `DATA_ROOT/sqlite/twstock.db`，與 personal 收藏 DB 分檔。實際 source、target、備份、停寫、校驗、writer 切換與回復方案仍需 migration 的具體批准。原 JSON／journal 不自動移動或合併。

main 的最小調整是將選擇 personal 模式時顯示／傳入的 candidate root 改為 `config.data_root / 'personal'`，並使用既有 resolver：

```python
paths = resolve_personal_data_paths(
    config.data_root, personal_root=config.data_root / 'personal',
    legacy_output_root=config.output_root, environ={},
)
notes = resolve_personal_journal_paths(
    config.data_root, personal_root=config.data_root / 'personal',
    legacy_output_root=config.output_root,
)
```

上述只解析路徑，不代表叫用 convert／activate。不要為 notes 套用 watchlist source 配對而建立 watchlist；兩個 store 使用同一 root 下各自契約。外部 custom root 可明示覆寫，但不再暗推 LOCALAPPDATA 為預設。不能全域把 OUTPUT_ROOT 改 personal 或把個人 tables 加進市場 twstock.db。

## 分享邊界

**FA_Data 整包現在包含私人 personal subtree，不能直接 zip／複製整包分享。** 使用固定市場 whitelist export 的 caller，才可排除 personal 與既有 output。即便 personal CSV 掃入來源清單，也必須拒絕整次 manifest，不靜默當市場檔。把 personal CSV hardlink／junction 映射到允許樹仍拒絕。

此功能只建市場 CSV metadata manifest，沒有真正複製或打包，不解析 CSV 的個人內容／license，不是 handle-based 併發安全 copy。市場 SQLite 表分享尚無 table/view/trigger/sidecar 契約；Evidence／Desk／DecisionQuality 可能 fallback twstock.db 的 custody 風險仍留主 owner 另行盤點，不在本包宣稱清除。

## 本次重新驗證

**232 passed、2 skipped，38.68s**；不是沿用舊政策測試結論。104 路徑／export／新內置 COW synthetic cases、27 內置 Journal cases、19 external COW activation、11 external converter、71 legacy COW/CLI/governance。兩個 skip 僅為 Windows 無權建立普通 directory symlink；JSON／SQLite 真 junction、internal root/cross-subtree junction、hardlink、Windows alias 負例實際通過。

新內置 JSON／SQLite v1/v2：convert ready → activate → service load/save 新 revision → rollback；來源 bytes/mtime 不變，target 新 bytes 保留，marker/receipt/JSON backup 皆在 personal，沒有建立 twstock.db 或來源 activation marker。Journal 全套 fixture 現使用 DATA_ROOT/personal，包括跨新process16 append、CAS單勝、readonly無來源鎖／mkdir、取消、未知type、ACK／tombstone。未知／未設定 root 仍不默默初始化；外部 custom root 回歸同次通過。

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_personal_data_paths.py tests/test_personal_journal_storage.py tests/test_personal_watchlist_cow_activation.py tests/test_personal_watchlist_cow_conversion.py tests/test_watchlist_sqlite_cow.py tests/test_watchlist_json_cow.py tests/test_watchlist_cow_activation.py tests/test_watchlist_json_cow_activation.py tests/test_watchlist_sqlite_cow_cli.py tests/test_watchlist_cow_storage_governance.py -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/ta_personal_subtree_final_1006_b
```

personal_data_paths／personal_journal_paths targeted mypy（follow-imports=skip、專屬 Temp cache）通過；四個本包 Python 檔 py_compile、git diff --check 通過。本包未修改 UI，不聲稱 Journey／UI gate 或全部回歸已驗收；前 Journal 包記錄的兩個 baseline 跨域失敗不在本次 root-only scope 重新診斷。

整合只採本限定提交，主 owner 同步預設候選位置、Manual 分享邊界與各 caller；本 lane 不 stage 主線。回滾此包會恢復外部-only root 契約，因此已正式使用內置 personal 之後，不能只 revert 程式就恢復 legacy writer；先停用寫入與保留個人資料，另做受控回復。未執行 revert 或任何正式資料操作。


## 主線限定整合（2026-10-06）

review後只採78151034為18224c33，五檔相對lane parent在dev無差異、無衝突，所有worktrees保留。config／UI原本已使用明示resolver，不存在LOCALAPPDATA自動候選或啟用；config註解與Manual候選同步data_root/personal，兩個App測試fixture改為內置root，涵蓋實際CLI convert／activate／rollback、UI預覽取消後合成明示啟用、Journal writer及全部reader、兩模式新process MainWindow composition。Production UI不用改路由，notes仍獨立watchlist。正式位置未建立，真migration／activation仍未准。

主線focused驗證：App／Journal storage 49 passed（含兩模式實際MainWindow新process），新子樹守衛36 passed／68 deselected；没有skip。首次新process capture用Windows預設codec產生兩個readerthread警告，driver補明示UTF-8後只重驗該案例，1 passed且無warning（已包含49項，非新增計數）。targeted mypy2、compile7及diff check通過。沿用lane已完成的232pass／2generic symlink skip，不重跑全量。Journal原8秒gate仍fail，與本policy測試分開報告。

使用者指定本案工程於2026-10-06 00:00 PDT（UTC07:00）暫停並等待新方向；診斷Luna已freeze，root本批結束不自動續開UX11。真實migration／activation、Native及SQLite市場分享契約仍未完成。
