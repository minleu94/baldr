# 文件產品化原件與處置

本批保存 2026-10-12 文件產品化前的原件，原 bytes、當時的 PASS／FAIL／unknown 及限制保持。原件只支持當時版本、日期與範圍；現況回[Snapshot](../../00_core/PROJECT_SNAPSHOT.md)，架構回[目前架構](../../01_architecture/system_architecture.md)，操作回[Manual](../../07_guides/APPLICATION_MANUAL.md)。

## 查找與恢復

- [逐檔處置清冊](DISPOSITION_MANIFEST.json)：原路徑、原件 SHA／bytes、保留或替換理由、目前落點與恢復方法。
- [核心章節映射](CORE_SECTION_MAPPING.md)與[上手／操作章節映射](ONBOARDING_SECTION_MAPPING.md)：保留現行契約與移出歷史的判定。
- [Agent 與流程映射](AGENT_WORKFLOW_MAPPING.md)：共同規則、角色短卡、平台入口與任務狀態的處置。
- [計畫與驗收要求](../../superpowers/plans/documentation_productization_plan_20261012.md)。

`originals/<原相對路徑>` 是逐 bytes 原文，沒有加標頭或重寫引用。其 Markdown 連結按原 repository 路徑語境解讀，不能用封存容器中的相對位置當現行導航；當前文件及處置清冊提供替代入口。這項例外只適用於本批 exact-byte originals，不適用於 active 正文。

本目錄的 `.gitattributes` 對 `originals/**` 停用換行轉換與空白修正檢查，使 Git blob 與清冊原件 SHA 保持一致，包括原有 CRLF 與尾空白。這是精確原件的保全例外；現行正文仍執行空白與連結檢查，內容雜湊按清冊明示的正規化規則核對。

恢復前先確認原件 SHA 與來源版本，保存目前工作樹差異並核對其他任務所有權。只在授權的精確路徑恢復本任務變更；不得整樹還原、覆寫其他任務或修改正式原始資料。

原件的保留／刪除以內容是否需要追溯或恢復判定。無本次修改的預備副本可移除；其原文仍在基線 Git tree，清冊會明示，不把它當正式資料清理。
