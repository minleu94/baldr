# Safe Refactor Four Extra Cycles Implementation Plan

> **歷史計畫（2026-07-11）**：本文的一次性 automation、舊排程與 Git commit／push 操作只記錄當日循環，不是目前派工、automation 或發佈授權；不得直接重啟。現況與優先序看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md) 與 [6M Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md)。

> **來源與生命週期核對（2026-10-12）**：本文計畫 D–G 四輪、共 12 個 Planner／Implementation／QA 設定；另一份 H–L 下午計畫為五輪、15 個設定，兩組是不同時段與 scope，不是同一組計畫的互斥數字。2026-09-25 的 [Codex automation inventory](../../06_qa/BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json) 逐列保存兩組 ID、狀態與 TOML 雜湊；目前 CODEX_HOME 的 TOML 為 PAUSED。兩組本機 automation `memory.md` 及 ignored `output/automation/version_loop/` closeout 記錄了 D–G 所屬 00:00–12:00 執行鏈與 H–L 下午執行鏈；記錄的切片數分別為當日總計 6 個、H–L 完成 4 個（J 為 `NO_SAFE_SLICE`），不可與設定支數互換。沒有獨立 Codex host event/audit receipt 能確認每次執行的觸發來源；排程器或受控手動流程的來源仍未知。本文未勾選步驟只代表此歷史計畫沒有回填執行勾選，不證明未執行。詳見 [本次治理核對收據](../../06_qa/DOCUMENT_GOVERNANCE_ISSUE_RESOLUTION_20261012.md)；本文記錄的是規劃步驟，不是目前 automation 授權。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將安全重構 automation 從 08:00 延長至 12:00，新增四個完整 Planner → Implementation → QA 循環。

**Architecture:** 當時以現已歸檔的 `docs/09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md` 為唯一執行依據。08:00 改為中繼 QA；新增十二支 cron，透過 exact artifact、stage、baseline SHA 與 handoff 串接；12:00 才執行 Final QA / Closeout。

**Tech Stack:** Codex app automation、TOML 設定讀回、PowerShell、Git、Markdown。

## Global Constraints

- 直接在 `C:\Projects\PythonProjects\technical_analysis` 的 `dev` 執行，不建立 worktree。
- 保留既有 00:00–08:00 automation id、時間、ACTIVE 狀態、模型與 local project。
- 新增時段固定為 08:20/08:40/09:00、09:20/09:40/10:00、10:20/10:40/11:00、11:20/11:40/12:00。
- 12:00 是唯一 Final QA / Closeout。
- 不修改 App 程式、正式資料、production DB、production scheduler 或交易邏輯。

---

### Task 1: 更新總報告時段契約

**Files:**
- Modify: `docs/09_archive/SAFE_REFACTORING_MASTER_REPORT_2026_07_12.md`（目前歸檔位置）
- Modify: `docs/00_core/DOCUMENTATION_INDEX.md`
- Create: `docs/superpowers/specs/2026-07-11-safe-refactor-four-extra-cycles-design.md`
- Create: `docs/superpowers/plans/2026-07-11-safe-refactor-four-extra-cycles.md`

**Interfaces:**
- Consumes: 現有 00:00–08:00 三輪 automation 產物鏈。
- Produces: 00:00–12:00 七輪完整循環與唯一 12:00 closeout 契約。

- [ ] **Step 1: 在總報告加入完整時段表**

明列 08:00 為中繼 QA，四個新增循環與 12:00 Final QA。

- [ ] **Step 2: 執行文件自查**

Run: `git diff --check`

Expected: exit code 0。

### Task 2: 建立更新前快照

**Files:**
- Create ignored: `output/automation/version_loop/20260711-four-extra-cycles-prechange-snapshot.md`

**Interfaces:**
- Consumes: 08:00 automation 完整 TOML。
- Produces: 可恢復 08:00 prompt 並刪除十二支新 automation 的回滾依據。

- [ ] **Step 1: 保存 08:00 設定與新 automation id 清單**

快照必須含原 prompt、rrule、model、reasoning、status、target 與新增 ids。

### Task 3: 更新 08:00 並新增十二支 automation

**Files:**
- Modify external automation: `baldr-milestone-final-closeout-0800`
- Create external automations: 四輪 Planner / Implementation / QA。

**Interfaces:**
- Consumes: Master Report、上一階段 exact artifact。
- Produces: 08:00 → 08:20 → 08:40 → 09:00 → 09:20 → 09:40 → 10:00 → 10:20 → 10:40 → 11:00 → 11:20 → 11:40 → 12:00。

- [ ] **Step 1: 將 08:00 改為中繼 QA**

輸出 stage 0800 QA artifact，handoff 到 08:20。

- [ ] **Step 2: 建立四個 Planner**

Planner stages 固定為 0820、0920、1020、1120。

- [ ] **Step 3: 建立四個 Implementation**

Implementation stages 固定為 0840、0940、1040、1140，只消費同輪 Plan。

- [ ] **Step 4: 建立四個 QA**

QA stages 固定為 0900、1000、1100、1200；只有 1200 產生 nightly closeout。

### Task 4: 讀回驗證與交付

**Files:**
- Inspect: 08:00 與十二支新 automation TOML。

**Interfaces:**
- Consumes: Task 3 更新結果。
- Produces: 時間、角色、artifact、handoff、安全邊界與 rollback 驗證證據。

- [ ] **Step 1: 驗證十三支設定**

確認 ACTIVE、rrule、model、reasoning、local project、Master Report、stage、consumed artifact 與 handoff。

- [ ] **Step 2: 驗證唯一 closeout**

確認 08:00、09:00、10:00、11:00 不產生 nightly closeout；只有 12:00 產生。

- [ ] **Step 3: 驗證 repo**

Run: `git diff --check`、documentation encoding tests、`git status --short`。

Expected: 只包含本次四份文件變更；App 程式無 diff。
