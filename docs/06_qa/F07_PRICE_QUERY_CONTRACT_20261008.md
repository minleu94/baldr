# F07 保存來源價格查詢契約（實作中，未接受）

本項沿完整補完計畫的價格區間／排序需求，使用明示數值上下界，不自行定義高／中／低價門檻。只新增 versioned price query/view/bookmark/comparison，不改 v4 保存快照、query、session identity 或舊收藏 bytes。

價格取已核 snapshot.current_session 的觀測日，以日期及 source fingerprint 唯一命中原 raw row；session pin／row fingerprint 一致、OHLC有效且 close 為有限正 Decimal 才可用。缺件保持具名 unknown，不回退較舊列、不讀最新資料、不把決策日冒充價格日；可得時間仍 unknown、PIT false。

同次 strict parent callback 同時建 P01 session 與有界 compact price index。所有技術 AND／OR、stock filter 與 eligibility 先作用於完整已處理 included cohort，價格 pass／fail／unknown 三數覆蓋此分母，declared／excluded／pending／missing獨立保留。未知政策預設 include；明示 exclude／only 不改三態計數。Decimal區間端點可含／不含；min==max且排他是合法空區間，不能擅自擴張。全母體價格排序後才分頁，雙向空值置尾、同價代碼穩定升序，每頁最多256。

頁面以原P01 arbitrary-code materializer精確重讀當頁，一次核對已驗snapshot/source identity與已發行價格投影；不重讀child來假造另一份獨立價格證據。下鑽先驗股票屬於原價格頁，再映射真實底層selection頁取exact snapshot；價格origin與底層v4origin分開，不冒充v4頁。公共DTO替換／重排／重新雜湊不得借原issuer anchor偽造結果。

UI要求明示保存來源與價格條件，非全螢幕可閱讀／捲動；工作singleflight、取消到原生終態、stale callback拒絕，失敗保留舊已核表格。下鑽／返回／收藏必須保存原價格query/page/selection，不只傳v4query。比較逐項保存各自exact來源、日期、query與價格pins，同來源在單次operation內重用一次session，不跨operation快取；不同來源不得冒稱共同cutoff。

葉片：universe負責新增price query模組與測試；h20_summary負責新增price view、bookmark、comparison三模組與配對測試。root負責獨立審查、既有Main／watchlist／COW路由、Manual與文件同步。所有檔案尚未接受，沒有新正式排程或原始SQL。

驗收須含真跨256+1段母體的Decimal邊界／三態／全域排序、partial／excluded／pending、pin／child tamper與取消拒絕；視窗捲動、source/query原子切換、exact下鑽返回、價格收藏及不同程序重開、比較各欄pins。只通過DTO／小fixture不能授完整產品接受；Native／效能與完整F01–F23仍保留原門檻。
