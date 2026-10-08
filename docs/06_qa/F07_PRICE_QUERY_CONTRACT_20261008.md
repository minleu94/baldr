# F07 保存來源價格查詢契約（來源版有限接受；執行檔與效能待驗）

本項沿完整補完計畫的價格區間／排序需求，使用明示數值上下界，不自行定義高／中／低價門檻。只新增 versioned price query/view/bookmark/comparison，不改 v4 保存快照、query、session identity 或舊收藏 bytes。

價格取已核 snapshot.current_session 的觀測日，以日期及 source fingerprint 唯一命中原 raw row；session pin／row fingerprint 一致、OHLC有效且 close 為有限正 Decimal 才可用。缺件保持具名 unknown，不回退較舊列、不讀最新資料、不把決策日冒充價格日；可得時間仍 unknown、PIT false。

同次 strict parent callback 同時建 P01 session 與有界 compact price index。所有技術 AND／OR、stock filter 與 eligibility 先作用於完整已處理 included cohort，價格 pass／fail／unknown 三數覆蓋此分母，declared／excluded／pending／missing獨立保留。未知政策預設 include；明示 exclude／only 不改三態計數。Decimal區間端點可含／不含；min==max且排他是合法空區間，不能擅自擴張。全母體價格排序後才分頁，雙向空值置尾、同價代碼穩定升序，每頁最多256。

頁面以原P01 arbitrary-code materializer精確重讀當頁，一次核對已驗snapshot/source identity與已發行價格投影；不重讀child來假造另一份獨立價格證據。下鑽先驗股票屬於原價格頁，再映射真實底層selection頁取exact snapshot；價格origin與底層v4origin分開，不冒充v4頁。公共DTO替換／重排／重新雜湊不得借原issuer anchor偽造結果。

UI要求明示保存來源與價格條件，非全螢幕可閱讀／捲動；工作singleflight、取消到原生終態、stale callback拒絕，失敗保留舊已核表格。下鑽／返回／收藏必須保存原價格query/page/selection，不只傳v4query。比較逐項保存各自exact來源、日期、query與價格pins，同來源在單次operation內重用一次session，不跨operation快取；不同來源不得冒稱共同cutoff。

葉片：universe負責新增price query模組與測試；h20_summary負責新增price view、bookmark、comparison三模組與配對測試。root負責獨立審查、既有Main／watchlist／COW路由、Manual與文件同步。下方保留各輪實作與失敗紀錄；最新接受範圍見文末，沒有新正式排程或原始SQL。

驗收須含真跨256+1段母體的Decimal邊界／三態／全域排序、partial／excluded／pending、pin／child tamper與取消拒絕；視窗捲動、source/query原子切換、exact下鑽返回、價格收藏及不同程序重開、比較各欄pins。只通過DTO／小fixture不能授完整產品接受；Native／效能與完整F01–F23仍保留原門檻。

## 後端葉片凍結與中央接線進度

後端代理B輪真合成回歸6 passed／122.83秒，兩檔compile與mypy通過。真257股分兩個parent（256+1），declared258、included257、excluded1；歷史cancelled收據processed256／pending1／missing1／missing_pending1，resume完成後末段低價S0256全域排首，從價格頁下鑽確實取segment1，descending缺價S0000仍置尾。A輪兩個fixture／拒絕斷言錯誤保留，沒有改弱來源核驗。module SHA256 `41e449d2ea8eeefe3c710ba7d9562e537ac003ba12466469b6e3066cc72c01a3`；test `d00022b3e5129dca6999fc4bcac960a8e75d89264891b489b389e38ff800d7fb`。

中央補上同次索引建立取消檢查的審查要求，並要求comparison／bookmark在Decimal展開前核精度／指數界限、深度拒絕，以及UI shutdown直到native worker終態才回完成。六個UI／bookmark／comparison葉片仍在重測，不授接受。

root在既有watchlist_service新增獨立F07 schema分派／來源類別、typed保存與明確拒絕轉一般研究context；前像保存於output/qa/f07_root_integration_20261008_a/preimage。新增真來源收藏保存／去重／移除還原測試，並合併後端全檔作中央獨立回歸，session11434執行中。Main／每日研究頁／觀察清單可見路由、Manual與Native／跨程序重開仍未完成；本輪不交付新的真人版本。

中央session11434已exit0：後端全檔加真收藏儲存整合7 passed／125.42秒，basetemp C:/t/f07_root_watchlist_20261008_a。Workbench85 passed；update validator A輪沙箱fixture同步失敗21／3／4已保存，B輪全新隔離TEMP25 passed／0 failed／4 skipped。full-roots mypy初次發現新schema union漏一處remove路徑型態，補完整後907檔clean；不是關閉檢查。root修改service／測試compile通過。中央另啟六檔葉片與舊官方／H20收藏回歸session18739，結果尚待；程式仍未stage／commit或打包。

session18739已exit0：原六檔葉片及舊官方／H20收藏16 passed／140.40秒，限定當時的854085版price view。後續接線審查發現Stock DTO不足以安全重建原價格Query/Page；來源view受控改為stockSelected(stock, originalPriceSelectionV1)，詳細頁嚴格核兩者pins再原樣返回，不偽造v4 origin。觀察清單控件另須提供同一次fresh操作的state交接，避免Main重開第二遍來源，且busy／shutdown／forged anchors拒絕。這些新接線與測試仍在實作，原16項不是修改後版本的接受證據。

root再發現Result發行bindings漏公開base_query_identity_sha256／classification_identity_sha256；合法SHA替換亦須拒絕，因此兩欄補入execute發行、建構及使用時anchor核驗，新增對應dataclasses.replace拒絕測試。原41e4版本證據保留；新7項真跨段／收藏回歸session70167執行中，完成前不授更新後後端接受。局部mypy首次module mapping重複，改explicit-package-bases重驗，不更動測試或關閉檢查。

session70167已exit0：7 passed／126.91秒。兩個proof拒絕斷言的dynamic kwargs型態錯誤改成明確replace參數後，4檔explicit-package-bases mypy clean／compile clean，最後test_source再次獨立targeted 1 passed／2.13秒；沒有略過任一proof欄位。更新後module SHA256 `88c4b9081e0f22fc302fd4eee79a752dbec68c7166a81ab23989c5b3da273c93`；test `f1ea739567cce3c6d815a79d4bd1c0032932fd2d22174934e2a39f9cada8a24f`。後端與儲存回歸有限接受；價格詳情／比較、收藏控件及新雙參數signal的UI／主路由還在整合，不等同F07完整接受。

## 主入口接線與COW前檢（未打包）

root已在每日研究條件頁新增價格來源view，個股／比較詳情各回傳自己的PriceSelection，收藏確認前後核目前query/page/選股一致；Main接同次fresh收藏state，不再讀第二遍來源。觀察清單有獨立價格收藏列表、來源標籤與typed重開路由；價格source被歸在獨立namespace，不會轉一般context或Advice。關閉加入price view／control原生worker終態檢查。三個舊UI檔的前像在root integration QA目錄，沒有覆寫其他聊天修改。

中央補審COW發現快速JSON轉換路徑只前檢H20，價格收藏可能轉換後才拒絕。root增加僅挑價格source／schema-prefix rows的前檢，交既有typed payload／外層身份validator後才允許轉換；一般舊JSON欄位別名仍由原converter判讀，未放寬損毀價格收藏。真正JSON→明示COW啟用→SQLite保存／移除還原→新程序重開與壞schema／outer身份拒絕案例正在補驗。

本輪接線後Workbench85 passed，validator全新隔離TEMP25 passed／0 failed／4 skipped，full-roots mypy910檔clean；舊每日研究、watchlist版面／技術／官方收藏UI路由16 passed／7.13秒。新增父視窗drill／返回／確認競態與watchlist→Main真來源旅程尚在測試；控制項首次列表尚未load或refresh時的doubleclick，還須排exactID待原worker終態後自動fresh開啟，不能要求另點第二次當作同一步完成。Manual已補開發來源版入口、條件／價格日／未知與排序、比較／收藏／取消／失敗解讀，尚未加入bd5d執行檔。

中央獨立COW驗證已完成：`output/qa/f07_root_cow_20261008_51e5a2ba/pytest.log` 記錄價格收藏新程序重開及既有COW啟用／JSON啟用／儲存接線共24 passed／7.21秒。價格測試凍結SHA256為 `24ee3d08b48dc1fea21bd81b49a85b92dfa712103b66c72685d1647e56414956`，核對JSON原bytes及合成研究來源檔案大小、mtime與SHA未改動，五種損毀收藏拒絕啟用。新程序沿原venv及實際launcher鏈核PID／PPID、執行檔與prefix，60秒逾時由既有Windows Job收束；未借換runtime通過。首次sandbox TEMP遇WinError5（15 failed／3 passed／6 errors），失敗目錄保留；改為全新專案QA隔離目錄才完成，沒有削弱路徑核驗。這份證據不包含Native EXE、真實全市場或真人驗收。

另對使用者d9版回報的長理由裁切進行目前來源版驗證：窄至460×700視窗的理由／分數／排名因素及文件最後一行可由整頁捲動看到，連同篩選原因呈現共3 passed／2.68秒。這不是d9執行檔的追溯接受，也不等同完整補完計畫完成；bd5d真人版本仍待實際驗收。

## 最新來源版UI整合有限接受

觀察清單實際雙擊已接 `open_bookmark(exact_id)`；未載／刷新中排隊後自動重開，沒有第二擊要求。取消／關閉清掉待辦，連續指定不同身份只開最後一筆；非目前worker的晚到native回呼只釋放自身，不處理目前待辦。準備收藏先顯示尚未保存，再同步通知父頁，因此保存成功或拒絕訊息不被覆蓋。

中央全新隔離 `output/qa/f07_root_final_ui_20261008_15292f34/pytest.log` 為21 passed／25.98秒，涵蓋價格view、收藏控制項、個股／比較詳情及真父頁→watchlist→Main路由。忙碌拒絕後須再次透過控制項建立新的讀取state；兩次明示開啟正好兩次來源opener，Main接手不重讀，也沒有重播前次state當成新操作。controls SHA256 `cbacd9677be17b6daf20b8621bc98186aae0ffdfcaee463c3dcf077bb5eeebbc`；整合test SHA256 `4b79b59db72f8b1c5f7560b6d81e484679a7fd40f38f2c829ea4e30237c616b0`。

最終接線後Workbench85 passed／3.86秒，validator25 passed／0 failed／4 skipped（全新 `f07_root_validator_20261008_092fa357`），full-roots mypy910檔clean及修改來源compile通過。此處授來源版功能整合有限接受；未提交的新檔仍待集中保存，Native／同版EXE／全市場及真人尚未接受，四類合成效能門檻失敗仍有效。
# 2026-10-08 主選股與比較籃重疊修正

真 Main 驗證發現：主選 S0250 同時列在 S0256/S0250 比較籃時，收藏準備被 `technical_universe_price_bookmark_duplicate_selection` 拒絕。第三股替代流程不代表此自然操作路徑通過。

修正後只禁止比較籃內重複；主選與籃內同一 key 必須完整 selection DTO 相同，矛盾證據以 `technical_universe_price_bookmark_selected_comparison_conflict` 拒絕。重新開啟時先對唯一選取錨點做 fresh reader 驗證，再按保存的比較籃順序組回；不移除使用者的籃內主選股，不放寬 reader qualification，也不改既有合法收藏的序列化格式與雜湊。

根代理後端驗證：`tests/test_daily_market_technical_universe_price_bookmark_v1.py` 四項通過，3.99 秒，隔離目錄 `C:/t/f07-overlap-root-20261008-c`。涵蓋重疊收藏 JSON roundtrip、fresh read、籃內重複拒絕、同 key 重新計算傳輸雜湊後的矛盾證據拒絕，以及既有取消／身分驗證。第一次測試因父目錄不存在在 fixture 前失敗；第二次測試揭露 reader 仍拒絕重複，修正唯一選取讀回後第三次通過。真 Main／新 PID 自然流程仍待本輪獨立結果；f2fba4c7 候選 EXE 不包含此修正。

## 真 Main／新 PID 自然流程追加結果（未通過）

新隔離 attempt `output/qa/f07_fulln_price_main_new_process_20261008_a/attempt_32f961a8fa2141d7900cec900a6d3098`：pytest 1 failed／218.33秒。父 Main 33.032秒完成 S0250 主選及 S0256/S0250 比較籃的收藏保存、原詳情返回、取消與原生關閉；新 PID 23644（父43464）fresh reader 11.672秒完成原來源、query、page、股票與比較籃核驗。來源 inventory 前後 SHA256同為 `80d1f155698a94181564862da72c89dcef2822678c3187cb1d6f9277b2bc028a`，子程序網路嘗試為空。

本輪失敗在 Main 還原後的捲動位置；保存位置為2，舊 trace沒有記錄實際還原值，不能補造差值。另以隔離 Qt 表格重現：隱藏頁面 scrollbar maximum為0，設2被限制為0；顯示後 maximum變2但 value仍0。產品目前先套收藏狀態再切換頁面，與此時序缺陷相符。正在補可見布局完成後的原頁限定還原及晚到／關閉保護；本輪不授完整自然流程接受，不以延長等待或移除捲動驗收替代修正。
