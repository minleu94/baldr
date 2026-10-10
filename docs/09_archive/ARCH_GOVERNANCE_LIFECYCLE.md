# Architecture Governance Lifecycle

> **早期架構治理流程提案（2026-06-24 自 core 歸檔）**：本頁不代表專案目前已有這套架構治理生命週期或必做流程。現行模組邊界看[系統架構](../01_architecture/system_architecture.md)，目標遷移順序看[Final Migration Sequence](../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)；文件治理的生命週期則由[文件覆蓋地圖](../00_core/DOC_COVERAGE_MAP.md)與[文件結構](../00_core/DOCUMENTATION_STRUCTURE.md)說明，兩者範圍不同。

## 1) Audit（掃描）
- 定期盤點模組責任與依賴關係  
- 識別跨層依賴與 Legacy 擴散  

## 2) Policy（定義）
- 建立 Architecture Boundary Policy  
- 明確 Allowed / Forbidden / Exceptions  

## 3) Checklist（落地）
- 將政策轉為可勾選的治理清單  
- 插入到新功能前/PR Review 前  

## 4) Evolution（Phase C Refactor）
- 在治理規範穩定後，進入結構收斂  
- 執行 Legacy 移除與層級修正  
