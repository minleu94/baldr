# 固定來源封存不探測上層 Git

原十股 Main 診斷 `20261008T110913Z_b02a583d0b31` 在程序建立前拒絕一次 Popen；有界 telemetry 將呼叫定位至固定 b61 的 `build_identity._read_git_identity`。固定來源封存位於開發 checkout 的子目錄，沒有自己的 `.git`，仍嘗試呼叫 Git。該原診斷保持 failed，不能以摘要成功或安全拒絕改成通過。

修正只在來源根自身有 Git 標記時讀 Git 身分。沒有標記的封存直接沿原建置 metadata／來源與依賴核驗；不放行任何 QA Popen。真正 checkout 命令失敗仍是未核實，不會退回舊 release metadata。

隔離 native 回歸 22 passed，1.79 秒，包含實際 checkout 的 HEAD／dirty／失敗分支，及封存放在 checkout 內、禁止任何 subprocess.run 仍與 frozen 身分相同。沙箱首輪17 passed／5 failed皆為臨時 Git fixture 建立遭權限拒絕，原失敗保留，不改測試或產品期待來繞過。

此修正尚未進新的固定 archive／exe，也未用新來源重跑原 H20 Main；原件、模型、PIT、效能或真人資格均未因此接受。
