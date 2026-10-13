---
name: baldr-obsidian-workflow
description: "在 baldr 專案用官方 Obsidian CLI 尋找目標、目前定位、權威文件及文件關聯；只在使用者要求修改文件時進入寫入流程。"
---

# baldr 文件查找工作流程

這個 Skill 讓 Codex 透過官方 Obsidian CLI 導覽 baldr 的文件。查詢結果是定位線索；產品方向、目前狀態、架構契約、操作與 QA 結果仍以各自的 repository Scoped SSOT 為準。

## CLI 前置條件

- Obsidian 官方 CLI 需要 Obsidian 1.12.7 以上的安裝版，並在 Obsidian 設定的 General 頁啟用 Command line interface。CLI 未安裝或未啟用時，說明前置條件並使用 repository 文件索引與一般唯讀搜尋作為替代，不宣稱已執行 CLI。
- 從 repository 根目錄執行命令，並明確附上 `vault=technical_analysis`，避免查到其他已開啟或已註冊的 vault。專案 vault 的註冊路徑應為本 repository 根目錄。
- Windows 若 CLI 回報找不到 Obsidian，先確認命令是否在 sandbox 隔離環境執行。隔離 shell 可能看不到使用者桌面程序或使用者的 AppData 路徑，即使 Obsidian 桌面程式已開啟；不得只依隔離 shell 的程序清單判斷 App 未執行。使用允許連到桌面程式的 host execution context 重試唯讀 CLI 呼叫；若環境不允許，明確回報隔離限制並改用 repository 索引與一般唯讀搜尋。
- 本機已驗證：即使從 host execution context 執行，Obsidian 桌面程式關閉時 CLI 仍回報 `The CLI is unable to find Obsidian`，不會自動啟動 App；使用 CLI 前需先讓 Obsidian 桌面程式保持開啟。官方文件描述的首次呼叫啟動行為在本機未能重現，換機後可重新驗證。
- 使用 `path="docs/.../FILE.md"` 指定檔案。若同名文件可能存在，不用只靠檔名的 `file=` 選取。
- `.obsidian/` 屬本機設定且被 Git 忽略。不要在此 Skill 任務中啟用、安裝、更新外掛或改全域 Obsidian 設定；機器移轉時依 `docs/agents/git_exclusions.md` 另行核對。

## 先定位，再讀權威正文

先由索引縮小範圍；找不到時才用 CLI 搜尋，並讀取搜尋命中的文件與它連到的權威文件。Obsidian CLI 的文字搜尋不是語意搜尋，也不會自行判定哪份文件有權威。

```powershell
# 在專案文件索引與核心文件中找目標用語並顯示命中行
obsidian search:context query="產品目標" path=docs/00_core limit=20 vault=technical_analysis

# 讀取確定的權威文件
obsidian read path="docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md" vault=technical_analysis

# 查看這份文件的出站連結或哪些文件連回它
obsidian links path="docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md" vault=technical_analysis
obsidian backlinks path="docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md" verbose vault=technical_analysis
```

如果結果太多，先把搜尋範圍限制在 `docs/00_core`、`docs/01_architecture`、`docs/07_guides` 或 `docs/agents`，再依命中內容進一步查找。不要一次讀取整個 vault，也不要把檔名排序或命中次數當成權威判斷。

## baldr 問題導覽

| 使用者想知道 | 優先閱讀 |
|---|---|
| 這個專案是什麼、如何開始 | `README.md`、`PROJECT_NAVIGATION.md` |
| 產品要達成什麼、產品能力與 Gate | `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` |
| 目前進度、當前風險與優先事項 | `docs/00_core/PROJECT_SNAPSHOT.md`；重要結論再核對其具名來源 |
| 近期工程順序 | `docs/00_core/ROADMAP_6M_ENGINEERING.md` |
| 現行系統怎麼運作 | `docs/01_architecture/system_architecture.md` 與 `docs/01_architecture/current/` 分冊 |
| 希望系統最後長什麼樣 | `docs/01_architecture/target_system_architecture.md` 與 `docs/01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md` |
| 操作某個功能 | `docs/07_guides/APPLICATION_MANUAL.md` 與 `docs/07_guides/manuals/` 對應分冊 |
| 應該找哪份文件 | `docs/00_core/DOCUMENTATION_INDEX.md` |
| Agent 如何選角色與遵守規則 | `docs/agents/skills_registry.md`、`docs/agents/shared_context.md` |

回答時用短清單說明「先看哪幾份、各自回答什麼、下一個適合查哪裡」，並附上 repository 相對路徑。若現況文件、歷史紀錄與目標設計互相不同，清楚標出它們的責任，不把舊紀錄當成現在狀態。

## 命令使用邊界

文件查找預設只用官方 CLI 的 `search`、`search:context`、`read`、`links`、`backlinks`、`files`、`unresolved`、`orphans` 與 `outline` 等讀取命令。`unresolved` 和 `orphans` 是全 vault 維護線索；使用時先確認範圍，結果不能取代 `scripts/document_control.py` 的 repository 連結與文件覆蓋檢查。

官方 CLI 也有 `create`、`append`、`prepend`、`move`、`rename`、`delete`、`property:set` 等寫入命令。使用者只要求查找、了解或判斷文件時不執行寫入命令；若使用者要求改文件，依 `docs/00_core/PRODUCT_CHANGE_WORKFLOW.md` 核定範圍並完成必要文件同步。CLI 幫助進行閱讀，不能取代 Git diff、連結檢查或 Scope/QA 紀錄。

## 官方說明

- [Obsidian CLI](https://obsidian.md/help/cli)：版本需求、vault 選擇、搜尋、讀取、連結及唯讀／寫入命令。
- [baldr 文件索引](../../../docs/00_core/DOCUMENTATION_INDEX.md)：依主題導向文件權威。
- [baldr 文件覆蓋地圖](../../../docs/00_core/DOC_COVERAGE_MAP.md)：依變更範圍確認需要同步的文件。
