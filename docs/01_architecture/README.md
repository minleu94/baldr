# 架構文件導覽

目前架構、target 背景與 target 實作設計分開閱讀。現況先看 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md)；目標文件不得用來推定 current 能力或產品 Gate 已通過。

## 目前架構

- [目前系統架構](system_architecture.md)：系統用途、實際分層、主要資料流、儲存／排程邊界與不變條件。
- [目前架構分冊](current/README.md)：依工作區與 application、決策／研究／Portfolio、資料／保存／Runtime 三個主題閱讀穩定契約。
- [Application Manual](../07_guides/APPLICATION_MANUAL.md)：使用者操作入口、步驟、判讀、安全限制與排錯。
- [Runtime Observatory 規則](runtime_observatory_rules.md)：Runtime DTO、UI bridge、生命週期及依賴方向細節。

## 目標架構

- [目標領域背景與 Current → Target 導覽](target_system_architecture.md)：描述方向及 target-only 限制，不授權新 package。
- [FINAL 目標實作設計](target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md)：package owner、資料流、核心契約與遷移順序的唯一設計權威。
- [FINAL 分冊、DAG 與 task specs](target_architecture_2026_09_22/README.md)：查閱受控執行契約、驗證矩陣與風險登錄。這些文件描述設計和任務，不等於目前接受狀態。

## 產品定位與模型閱讀

[系統願景](system_vision_specification.md)維護 North Star、bounded Advice、evidence 要求、成功標準與 non-goals；產品能力優先序看 [Product Roadmap](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md)，工程順序看 [6M Roadmap](../00_core/ROADMAP_6M_ENGINEERING.md)。

ML 文件須分辨三條用途：

1. Recommendation ML Shadow 的目前資格看 Snapshot 與 current 分冊；長期領域 boundary 看 [Target ML Shadow](target_system_architecture.md#1011-ml-shadow-layer)。
2. Portfolio Allocation ML 的條件式 Gate 7 看 [產品 Gate](../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md#15-六個月產品-gate)、[6M Gate 7](../00_core/ROADMAP_6M_ENGINEERING.md#11-gate-7ml-shadow-layer條件式)與 [Gate 7 工程 QA](../06_qa/GATE_7_ML_SHADOW_ENGINEERING.md)。
3. Personal H20 是個股研究路徑；其目前 evidence、PIT 與 maturity 限制看 Snapshot 及相關具名 QA。它不等於全域 Recommendation ML 或 Portfolio Allocation Gate 7。

## 歷史追溯

本架構入口不保存日期化工程流水。2026-10-12 核心文件整理前的完整原 bytes 位於 `docs/09_archive/documentation_productization_20261012/originals/`；封存位置、hash、引用替代及原章節映射由同批治理 manifest／mapping 維護。其他日期化架構切片按其主題連到 `docs/09_archive/` 或 `docs/06_qa/`，其當時 PASS／FAIL 不代替 Snapshot 的現況判讀。
