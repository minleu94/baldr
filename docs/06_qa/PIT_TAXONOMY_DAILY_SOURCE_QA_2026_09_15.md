# PIT Taxonomy Daily Source QA（2026-09-15）

## 結論摘要

本紀錄是 PIT（point-in-time）產業分類 daily source 的 implementation／research QA，目的為驗證官方來源 custody、market-scoped parser、安全型 security mapping、preopen timing 與 downstream reader/caller wiring。它不是 2026-08-25 frozen parent 的 formal credit，也沒有宣稱 2026-09-15 盤前成功或產生正式 recommendation。

目前 code 與測試可接受的結論如下：

- TWSE 在 target `2026-09-16` 的可用定義改採 `official_twse_b1212_composite_rederived`：以官方 B12.00 原始 PDF 29 碼重算，從官方 2023-05-30 公告重算 code 16 rename 與 35–38 additions，再由 B12.13 原始 PDF 的 B12.00–B12.12 歷程逐段閉合，並以現行法規頁交叉核對 33 名稱；effective safe boundary 為 `2026-05-01`。B12.13 本身仍是 115/12 實施的 future evidence，不作 target-date mapping source。
- TPEx 官方 PDF bounded parser 解析 31 rows／31 codes；V12.18 封面／履歷記載 115/05/18 實施，若 source config 提供相符的 official applicability evidence 才能進 runtime。TWSE 與 TPEx 使用不同 market-scoped parser；同 code 不跨市場覆蓋。
- 官方 ISIN security adapter 對 frozen parent 1,932 symbols 得到 1,931 個 exact current evidence；另以官方 ISIN `owncode=5371` all-market 與 TPEx market=2 精確查詢均得到 no exact match，`5371` 在這條 current security snapshot lane 維持 missing blocker，不 drop、不補綠。獨立官方 MOPS lifecycle raw 已核驗 `5371 → 3718` 的公告／核准、最後交易日、停止交易、終止／轉換與 successor 上市事件；該 identity／warm-up lane 尚待 caller 接線，且不能回寫舊 frozen parent。
- 1,928 個 common-equity、3 個明確 TDR excluded、0 個修正後真實 type/market conflict；相對於舊的 2026-08-25 frozen parent 與本次 2026-09-16 score-bearing parent，研究 join 都保留 `5371` missing，故沒有取得 formal acceptance；這不把舊 parent 的缺漏／缺 scores 變成未來每日 source 的永久前提。
- request start 與 source bundle completion 已分離；實際 live fetch 完成後重新取得 clock，completion 跨台北 08:30 會阻擋，不把 metadata completion 改寫成 request start。

B data／lifecycle implementation 已由分批提交任務記錄於 `0bfd69ac`；目前共同基線為 `f4d0744b`。本輪釋出後追加的 caller 型別收窄與本段 QA 更新刻意保留為未提交工作樹變更，交由主 agent 依 repo gate 整合；本紀錄仍不是 formal credit 或 production promotion。

## 來源 custody 與可重現 evidence

本次研究 raw、headers、metadata 與 hash 位於隔離目錄：

`<USER_HOME>\.codex\visualizations\2026\09\15\01a0a50d-08e9-70a1-9162-b73cd2161548\pit-taxonomy-official-audit`

下表為成功採信的來源 record；同目錄保存原始 bytes，沒有覆寫正式資料或歷史 artifact。

| source | URL | HTTP／content type | 完成時間（UTC） | bytes | SHA-256 |
|---|---|---|---|---:|---|
| TWSE all securities | `https://isin.twse.com.tw/isin/e_single_main.jsp` | 200 / `text/html;charset=big5` | `2026-09-15T14:18:47.8862457+00:00` | 33,888,436 | `sha256:15ed3587313c875acbcc4ca98ab2d8dc469da10b99e3d6e570aea42a2132a9d6` |
| TWSE listed cross-check | `https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=2` | 200 / `text/html;charset=big5` | `2026-09-15T14:07:24.3513090+00:00` | 8,887,336 | `sha256:36e5a2c1c17b2d15f60dfb4010ce35ebeca9dc8ac684a64ae9979a07ff08662b` |
| TPEx OTC cross-check | `https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=4` | 200 / `text/html;charset=big5` | `2026-09-15T14:10:36.1849212+00:00` | 2,946,200 | `sha256:3124a53b1ee6aae053099f6b7aff68fbfb4e4c7caf7cd492294a2e5bfafd4b2e` |
| TPEx classification definition | `https://dsp.tpex.org.tw/storage/regular_system/%E4%B8%8A%E6%AB%83%E8%82%A1IP%E8%A1%8C%E6%83%85%E7%B6%B2%E8%B7%AF%E8%A6%8F%E6%A0%BC%E6%9B%B8%28V.12.18_TCPIP%29.pdf` | 200 / `application/pdf` | `2026-09-15T14:30:00.6391626+00:00` | 695,752 | `sha256:d9211860d9384ff43c63f75f79272d936e68f4969402278262fefa405aa1dd56` |
| TWSE B12.12 composite base | `https://wwwc.twse.com.tw/staticFiles/product/broker/ff80808166388ea1016676ac941001e0.pdf` | 200 / `application/pdf` | `2026-09-15T16:32:43.734657+00:00` | 1,080,714 | `sha256:3739f28acba7bdce2c1d21016a2c8c3c8c63b2ca14d013446f9448d733f4a5dc` |
| TWSE B12.12 composite change notice | `https://eshop.twse.com.tw/zh/news/detail/0000000087e9b84901886b8d96940024` | 200 / `text/html;charset=UTF-8` | `2026-09-15T16:35:09.487703+00:00` | 10,202 | `sha256:bd4e92d51820186f2aee87cdfbb54927beb4c8826114cba7c345c2aa6b4f99ff` |
| TWSE B12.12 composite revision-history evidence | `https://dsp.twse.com.tw/public/static/downloads/computerPlanningOperationsDepartment/TWSE%E9%9B%86%E4%B8%AD%E5%B8%82%E5%A0%B4%E5%8D%B3%E6%99%82%E4%BA%A4%E6%98%93%E8%B3%87%E8%A8%8A%E5%82%B3%E8%BC%B8%E8%A6%8F%E6%A0%BC%E6%9B%B8(B.12.13)(202612)_20260911094449.pdf` | 200 / `application/pdf` | `2026-09-15T16:37:00.156735+00:00` | 2,632,322 | `sha256:465f69ef65e58c3a2c2469ac186fec658f988645a0b267ea886b471032a9b035` |
| TWSE B12.12 composite current-regulation cross-check | `https://twse-regulation.twse.com.tw/tw/law/DOC01_print.aspx?FLCODE=FL007104&FLNO=2` | 200 / `text/html; charset=utf-8` | `2026-09-15T16:35:28.987023+00:00` | 4,146 | `sha256:3eaabe4f46ee22ad16d99d8311d6b12905b05fd51c8d064adbb38489cd6324a3` |

TWSE 的 current B12.13 PDF 仍從官方 [證券商作業手冊頁](https://dsp.twse.com.tw/brokerManual/list) 取得，角色限定為 B12.00–B12.12 revision-history evidence；B12.13 的 115/12 implementation 在 target date 之後，不能直接作 target-date mapping。target `2026-09-16` 的 `effective_from=2026-05-01` 定義由四份 raw 組成：B12.00 PDF base、官方 2023-05-30 change notice、B12.13 PDF 的 bounded history、現行上市公司產業分類法規頁。四份原始路徑、HTTP completion 與 hash 以實際 config 及 research receipt 為準。

官方 [2023 產業格式變更公告](https://eshop.twse.com.tw/zh/news/detail/0000000087e9b84901886b8d96940024) 的 raw 由 adapter 直接解析，明確取得 code 35–38 新增及 code 16 `觀光事業 → 觀光餐旅`；B12.13 原始 PDF 的歷程再確認 B12.07 是唯一 B12.00–B12.12 的 Appendix 3/code-name event，B12.12 只改格式欄位。現行 [上市公司產業類別法規頁](https://twse-regulation.twse.com.tw/tw/law/DOC01_print.aspx?FLCODE=FL007104&FLNO=2) 僅作 33 名稱 cross-check，不作 mapping source。

### 不採信的 capture

- `twse_all_attempt2.html` 為 curl exit 28／120 秒 timeout 的 23,662,779-byte partial body；`twse_isin_all.html` 沒有可配對的 status／completion metadata；`twse_listed_attempt3.html` 只有 body、沒有同次 status metadata。三者不進 security map 結論。
- 舊 TWSE 分類 URL 與先前猜測的 current URL 都回到 `https://dsp.twse.com.tw/` 的 18,854-byte HTML（content type `text/html;charset=UTF-8`），不是 PDF；保存於 `twse_classification_definition_attempt1.*` 與 `twse_classification_definition_current_attempt1.*`，沒有冒充分類定義採用。
- 官方搜尋索引提供的 B.12.12 historical URL 於本次直接 probe 回 HTTP 302 至 `https://dsp.twse.com.tw/`，follow 後仍是 18,854-byte HTML（保存於 `twse_classification_definition_applicable_attempt1.*`，SHA-256 `sha256:a60aa27c8568bcc129a8954c628e8b60cd034364ccf219a52536053e8fe6c406`），不是可採用的 historical PDF。此 gap 不再阻擋由四份官方 raw 重算 B12.12；但仍不能把 current B12.13 的頁面更新日回填成 target-date mapping source。
- TPEx／TWSE raw、headers、metadata 各自保存；不以成功來源的 metadata 推測另一個來源的完成時間或 hash。

## Definition parser QA

`data_module/pit_taxonomy_definition_adapter.py` 的 parser version 為 `official-pit-taxonomy-definition-adapter.v4`。PDF 只接受依 `market_scope` 派送的受控格式，且 runtime 另要求明確的 `effective_date_basis`／`effective_date_evidence`；PDF 的 `http.captured_at`、`Date`、`Last-Modified` 或頁面更新日只屬 availability/transport evidence，不會自動成為 classification applicability：

- TPEx：`附錄三：產業別代碼` → `一、上櫃證券產業別代碼` → `代碼／產業別` 表頭，直到 `附錄四`。
- TWSE：`附錄三：證券產業別` → 多欄 `產業別代碼／產業別` 表頭，直到 `附錄四`；長名稱跨行只在該 bounded table 內合併。
- 找不到對應市場的明確 appendix／table marker 即拒絕；沒有全 PDF 掃描兩位數字 fallback，也不把 TWSE table 交給 TPEx parser。
- 已知 PDF 版本先從封面／文件標頭讀取 current revision，再核對該 revision 的 implementation record；不會因履歷中出現舊版 B12.12/B12.13 就接受未知的 current B12.14。未知 current revision 在 runtime 一律拒絕；只有明確 `require_effective_date_evidence=False` 的隔離 research parse 可繼續做 mapping QA。

實際 parse 結果：

| market | rows／codes | 關鍵 code |
|---|---:|---|
| TPEx | 31／31 | `17=金融業`、`26=光電業`、`32=文化創意業`、`80=管理股票` |
| TWSE B.12.12 composite | 33／33 | `16=觀光餐旅`、`17=金融保險`、`25=電腦及週邊設備業`、`35=綠能環保`、`36=數位雲端`、`38=居家生活` |

因此 code `17` 的跨市場差異是有意保留的 market-scoped definition，不是 conflict 或覆蓋。測試 fixture 同時包含目錄／附錄二／頁尾／附錄四之後的不相關數字；正測試確認不滲入，負測試確認缺少明確 table 時 fail closed。

實際 TWSE B12.12 composite 驗證的 wrapper 呼叫（只讀保存的四份 raw，不產生 bundle）：

```powershell
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -c "load the four component paths from pit_taxonomy_research_config_20260916.json; call parse_official_twse_b1212_composite_classification_definition with those raw bytes and the saved applicability evidence; print parser version, count, source_kind and lineage hashes"
```

stdout：

```text
PARSER official-pit-taxonomy-composite-definition-adapter.v1
COUNT 33
TARGETS {'16': '觀光餐旅', '17': '金融保險', '25': '電腦及週邊設備業', '35': '綠能環保', '36': '數位雲端', '38': '居家生活'}
SOURCE_KIND official_twse_b1212_composite_rederived
EFFECTIVE_FROM 2026-05-01
```

官方 PDF 解析依賴 runtime `pypdf>=6.0.0`，已加入 `requirements-runtime.txt`；raw PDF／HTML 本身與 parser projection 分離保存，可由各 component hash 重新驗證。B12.13 封面為 current version，但其 115/12 implementation 仍是 target 後的 future evidence；composite adapter 不使用 B12.13 Appendix 3 作 mapping，只使用 B12.00–B12.12 bounded history。B12.12 的 month-level implementation 以 `2026-05-01` 作 no-early-use safe boundary，並要求 evidence source version 明確識別 B12.12。

適用日期契約的負向驗證也已隔離：current B12.13 直接作 target source 仍因 115/12 future gate 拒絕；composite 若改寫成非 `2026-05-01` 的 effective date、缺少 B12.12 evidence、變更公告遭竄改，或 B12.10 等中間版本插入產業變更，都 fail closed。TPEx V12.18 的封面／履歷給出 `115/05/18 實施`，在 source config 提供 `official_manual_implementation_record`、相符 `V.12.18` evidence 後通過；同樣不使用 HTTP publication timestamp。

### Runtime source-config shape（無假 raw／無手寫 mapping）

欄位契約如下；實際可執行的 research-only config 已保存於：

`C:\Projects\PythonProjects\technical_analysis\output\research_qa\pit_taxonomy\2026-09-16\score-bearing-parent-probe-20260916-r1\pit_taxonomy_research_config_20260916.json`

該檔是可供 adapter／producer 讀取的實際研究設定，不是 placeholder：TPEx 指向保存的官方 PDF，TWSE 使用 `official_twse_b1212_composite_rederived`，其四個 component 分別指向 B12.00 base PDF、2023 公告、B12.13 history-only PDF、現行法規 HTML；config 不含 `mapping`，mapping 由同一次保存的 raw bytes 重新解析。TWSE composite 在 `2026-09-16` 以實際 raw 解析為 33 碼，effective safe boundary 為 `2026-05-01`。這份 config 不代表 production 授權或當日 formal credit；security full map 也不是同日 fresh snapshot。

以下 JSON 是 composite 欄位契約示意；實際 URL、raw path、metadata、hash 與 applicability evidence 以前述 config 及研究收據為準。B12.13 只作 history-only future evidence，不作 target-date mapping；TPEx V12.18 的 exact `115/05/18` 可在 evidence 與 raw current revision 對讀後使用。

```json
{
  "schema_version": "pit-industry-taxonomy-source-config.v1",
  "classification": {
    "twse_listed": {
      "source_kind": "official_twse_b1212_composite_rederived",
      "source_url": "https://dsp.twse.com.tw/brokerManual/list",
      "source_id": "official:twse:broker-manual:O-126-A10",
      "source_version": "B.12.12-rederived-from-official-B12.00-and-2023-patch",
      "classification_version": "twse-industry-definition.v1",
      "effective_from": "2026-05-01",
      "effective_date_basis": "official_manual_implementation_record",
      "effective_date_evidence": {
        "scope": "official_manual_revision_implementation",
        "source_id": "official:twse:broker-manual:O-126-A10",
        "source_version": "B.12.12-rederived-from-official-B12.00-and-2023-patch",
        "effective_from": "2026-05-01",
        "evidence_url": "https://dsp.twse.com.tw/brokerManual/list"
      },
      "components": {
        "base_definition": {"path": "<B12.00-PDF>", "http": "<saved-http>"},
        "change_notice": {"path": "<2023-公告-HTML>", "http": "<saved-http>"},
        "revision_history": {"path": "<B12.13-history-PDF>", "http": "<saved-http>"},
        "current_regulation": {"path": "<現行法規-HTML>", "http": "<saved-http>"}
      }
    }
  },
  "security": {
    "all": {"url": "<official-isin-url>"}
  }
}
```

producer 會禁止 config 內的 `mapping`，重新從同一份 raw bytes 解析並將 applicability evidence 寫入 classification source／raw manifest；reader 也會以同一 evidence 重新解析。若 config 只把 `effective_from` 改成過去、缺 evidence、current revision 未知、或 PDF 仍未跨 implementation safe boundary，capture／reader 均保持 blocked，不能把 current mapping 變成歷史或 formal proof。

## 2026-09-16 score-bearing parent 與同日 chain 實際 probe

本節是以真實台北時間 `2026-09-16` 執行的 research-only chain evidence；完整 command、exit code、路徑、hash、readback 與未採用原因集中保存於：

`C:\Projects\PythonProjects\technical_analysis\output\research_qa\pit_taxonomy\2026-09-16\score-bearing-parent-probe-20260916-r1\taxonomy_chain_research_receipt_20260916.json`

### Parent producer

- 以 `data_module.formal_rule_source_producer.produce_current_rule_source_bundle` 產生實際 score-bearing parent，再以 `validate_machine_revalidation_bundle` readback；兩者 process exit code 均為 `0`，readback status 為 `machine_revalidation_verified`。
- bundle：`C:\Projects\PythonProjects\technical_analysis\output\research_qa\pit_taxonomy\2026-09-16\score-bearing-parent-probe-20260916-r1\clock-20260916-machine-v2-11c434ff5e8d-85d50c270d9a`。
- `symbol_count=1,932`、`scores_bp_count=1,932`、`universe_hash_symbols_count=1,932`、`rank_order_count=1,932`；`rank_order_source=parent.universe_hash_symbols`。父 producer v3 的 identity 未提供獨立 `rank_order` 時，wrapper 保留 score／hash 的原始順序，不做 sorted fallback。
- `data_as_of_date=2026-09-15`、`activation_trading_day=2026-09-16`；`universe_hash=sha256:d929c58bca132b7f298fab9fa0e0471c2ac29971b59b3df3fd08179f658a6a04`，clock manifest hash 為 `sha256:68beadc4a509f46c55fc35a7ba101b7288fce08d441a6cbc89c947d3d422c04f`。
- 該 parent 為 candidate-only、`formal_oos_allowed=false`、`promotion_eligible=false`、`broker_order_allowed=false`，沒有 formal credit。

### Company source exact join

- 同日以完整 1,932-symbol parent 呼叫既有 `capture_pit_candidate_before_cutoff`，process exit code `1`，`MachinePITSourceError: official company source is missing expected symbols: 5371`。沒有 drop `5371`、沒有以舊 archive 補件，也沒有將 1,931 rows 發佈成 full parent bundle。
- 為保存同日 raw custody，另以 `expected_symbols=None` 做 research-only raw capture；process exit code `0`，archive readback verified，archive row count `1,985`。archive manifest：`C:\Projects\PythonProjects\technical_analysis\output\research_qa\pit_taxonomy\2026-09-16\company-source-probe-20260916-r3\pit_candidate_archive\2026-09-16\750ec8bd986a287c-fb52e48bbc028fad\archive_manifest.json`，manifest hash `sha256:d8cabca68f66c1f80736fcdec44a3d350526c4f5934b227aa704f36b82300868`。
- 同日 raw exact join 對 parent 得 `1,931/1,932`：TWSE `1,065`、TPEx `866`、duplicate company symbol `0`，唯一 missing 為 `5371`。TWSE／TPEx raw source completion 分別為台北 `00:42:56.628125`／`00:42:59.811832`，publication date 分別為 `2026-09-14`／`2026-09-15`；這些時間與各 raw hash 都在 receipt 內逐一保存。

### Security evidence 邊界

同日 exact `owncode=5371` all-market 與 TPEx `market=2` query 均為 HTTP 200、277 bytes、no exact row，body hash 均為 `sha256:e6882d1bd96d75d810a444afbd2e958fb0c51e96671dab6bacaaea58f8e3ece7`。既有 44,821-row all-securities HTML 的 completion 是前一個研究 capture，故只用來做 diagnostic：排除 missing 後 join `1,931`、common-equity `1,928`、TDR `3`、unknown `0`。這不是同日完整 security snapshot；這兩個 bounded query 本身不證明 lifecycle，但獨立 MOPS raw 已核驗 `5371 → 3718` 的 2026-07-29 公告／核准、2026-08-21 最後交易、2026-08-24 停止交易、2026-09-03 終止／1:1 轉換與 successor 上市事件。該事件不搬移 legacy price、不改 frozen parent identity，且尚未接入本線 producer／reader 的 score-ready 判定。

### Definition 與完整 taxonomy bundle

- 以實際 research config 讀取保存的官方 PDF raw bytes，TWSE／TPEx parser 實際分別解析 `33/33`、`31/31`；live fetch bytes 與 saved raw hash 相同。
- 四元件 definition component probe process exit code `0`，status 為 `classification_components_verified`：TWSE composite 實際解析 `33` 碼、TPEx 實際解析 `31` 碼；TWSE 的 `B12.00 + 2023 change notice + B12.13 bounded history + current regulation cross-check` lineage、B12.12 `effective_from=2026-05-01` 與中間版本歷程閉合均通過。current B12.13 的 `115/12` 只作 history-only future evidence，不直接作 target-date mapping。
- 接著以完整 1,932 parent、company archive readback 與同一 config 呼叫 `capture_configured_daily_pit_taxonomy_bundle`；因 `5371` exact join blocker 在發佈前 fail closed，taxonomy bundle root 沒有建立，也沒有 bundle readback。這是實際 blocker receipt，不是把缺件降級成 subset 成功。
- 另以隔離 composite fixture 完成 producer → formal publisher → reader 的正向 readback：primary classification 保留 B12.00 base 的真實 HTTP metadata，aggregate 只保存 `derived_metadata`；reader 由四個 component 的實際 HTTP `captured_at` 重算 completion，結果 `accepted`／`industry_filter_usable=true`。負向測試將 base `captured_at` 改到 cutoff 後並同步重算 raw logical hash、taxonomy source／identity／bundle、sidecar 與 receipt 外層 hash，reader 仍以 `captured_after_derived` fail closed。

調查期間另有一次 module CLI probe 受到 active date-scoped runtime config 覆寫，實際寫到 `C:\Projects\PythonProjects\technical_analysis\output\formal_daily_publications\rule_source\clock-20260916-machine-v2-11c434ff5e8d-85d50c270d9a`；該結果保持 candidate-only 且未採作研究 isolation evidence，原始路徑未刪除或覆寫，詳情見 receipt。

另完成 research output-root route preflight：研究 caller 必須把 `output_root` 與已解析的隔離 research root 同時傳入 `produce_current_rule_source_bundle(..., expected_output_root=...)`；若 API 解析出的實際 root 與 expected root 不一致，會在讀取 baseline／market source 及任何寫入前以 `rule_source_expected_output_root_mismatch` fail closed。上述 module CLI incident 的 date-scoped formal artifact 保持原樣、只作 candidate／incident evidence；正式 scheduler 不傳入此研究 guard，仍使用 `TWStockConfig` 的正式 date-scoped runtime binding。負向測試已驗證 mismatch 時兩個候選輸出根都不會被建立。

## Security map QA

`official-isin-security-adapter.v1` 解析現行 TWSE all body 的結果為 44,821 rows／44,821 unique `(symbol, market, ISIN)` numeric security identities：

- type：`common_equity=1,976`、`warrant=42,268`、`bond=387`、`etf=160`、`etn=20`、`tdr=10`；unknown numeric records 為 0。
- section：`Stocks=12,663`、`Other=32,158`。
- normalized market：`twse_listed=33,230`、`tpex_otc=11,591`。
- `HA1303`、`HB1203` 等完整 alphanumeric security code 不再截成 `1303`／`1203`，所以 municipal bond 不會偽造 common-equity conflict。

以 frozen 2026-08-25 parent 的 denominator 做 exact symbol + market join：

| outcome | count | 判讀 |
|---|---:|---|
| parent denominator | 1,932 | TWSE 1,065 + TPEx OTC 867 |
| selected current evidence | 1,931 | 同 ISIN／market／type／CFI 的一致 duplicate semantic-dedup；展示名稱差異不製造 conflict |
| common-equity | 1,928 | `Stocks` + `ESVUFR` + normalized market |
| explicit TDR | 3 | `9103`、`9105`、`9136`；明確 excluded，不納入 eligible |
| missing | 1 | `5371`；不 drop、不補綠 |
| true type/market conflicts | 0 | 修正完整 token 後的 actual map 結果；測試仍保留真實 conflict fail-closed cases |
| eligible common-equity | 1,928 | 不含 TDR、missing |

`5371` 的 frozen parent t187 raw record 是 `中強光電股份有限公司`、industry `26`、date `1150820`（2026-08-20）。本次官方 TWSE all 與 TPEx OTC/listed cross-check body 都沒有 exact numeric `5371` row，只出現含 `5371` 的其他 warrant code；因此 current security map 保留 missing blocker。這個 query 結果只描述該 snapshot 的 exact-row 狀態；獨立 MOPS raw 已另行核驗 `5371 → 3718` 的 lifecycle event，identity／warm-up／score-ready 仍由後續 contract/caller lane 處理，且不回寫 frozen parent。

為把 exact-row 結論限制在可重驗的官方 bounded query，本次另保存 ISIN 查詢表單與兩個 exact request：

| query | official request | response | 判讀 |
|---|---|---|---|
| all markets, `owncode=5371` | `https://isin.twse.com.tw/isin/class_main.jsp?Page=1&chklike=Y&industry_code=&isincode=&issuetype=&market=&owncode=5371&stockname=` | HTTP 200 `text/html;charset=MS950`，277 bytes，body SHA-256 `e6882d1bd96d75d810a444afbd2e958fb0c51e96671dab6bacaaea58f8e3ece7` | official no-exact-match redirect |
| TPEx, `market=2&owncode=5371` | `https://isin.twse.com.tw/isin/class_main.jsp?Page=1&chklike=Y&industry_code=&isincode=&issuetype=&market=2&owncode=5371&stockname=` | HTTP 200 `text/html;charset=MS950`，277 bytes，同 body hash | official no-exact-match redirect |

兩個 response 的 completion 分別為 `2026-09-15T15:34:41+00:00` 與 `2026-09-15T15:35:06+00:00`，raw／headers／metadata 保存於上述隔離 audit 目錄（`twse_isin_5371_query_attempt1.*`、`twse_isin_5371_query_tpex_attempt1.*`）。這兩個 query 只描述當次 snapshot 沒有 exact row；MOPS lifecycle raw 已提供 `5371 → 3718` 的獨立官方事件證據，本線仍不以 query response 單獨改寫 market／identity。

跨來源去重只接受一致 semantic identity：同 ISIN／market／security type／CFI 的展示名稱差異可 dedup；same ISIN type/CFI conflict、不同 ISIN 的 multiple common、unknown competition 仍 fail closed。沒有以 `t187` 公司基本資料默認 common stock，也沒有將缺漏補成可用。

## Timing 與 runtime wiring QA

目前 production chain 為：

```text
preopen capture entrypoint
  → live official source fetch + raw/metadata/hash custody
  → daily PIT taxonomy bundle（capture_started_at ≠ captured_at）
  → formal publisher license/readback gate
  → exact-date reader（preopen bundle only；postcutoff 不 refetch）
  → industry strength caller（只接 security_eligible rows）
```

timing contract：

- request start 只記錄 capture 起點；所有 source fetch 完成後，live fetch 由 `now_provider` 或 real UTC clock 重新取得 bundle completion。
- source metadata 的實際 completion 不會被回寫成 request start；若 metadata completion 早於 request start、或 completion clock 倒退，producer fail closed。
- injected clock 測試涵蓋 request 07:55、source completion 08:00 的成功；completion 08:31、或 metadata completion 08:31／final 08:29 的跨 08:30 阻擋；preopen entrypoint 也涵蓋成功與 blocked。
- postcutoff runner 只讀指定 `pit_taxonomy_preopen/YYYY-MM-DD/bundle_manifest.json`，不 refetch、不以 latest bundle 代替當日 preopen evidence。
- publisher 只做 custody／schema／license／readback gates，不把 candidate 推成 formal recommendation；industry caller 不對缺漏或 excluded security 產生 industry strength input。

### Security lifecycle caller → publisher → reader → industry traceability

同日 lifecycle contract 的研究 fixture 已完成完整唯讀接線，且沒有把 predecessor `5371` 的舊價格、分數或 ticker carry-forward 到 successor `3718`：

- source publication date 為 `2026-09-03`；company／classification／security source completion 分別為台北 `06:00`／`06:10`／`06:20`，preopen capture 為 `07:55`，decision cutoff 為 `08:30`。所有來源完成時間均早於 cutoff，publication、available、captured 與 decision 時間維持分離。
- publisher receipt 的 `status=formal_source_publication` 僅表示 sidecar 通過 custody／schema／license/readback gate，不代表 production formal credit；reader 回傳 `status=accepted`、`industry_filter_usable=true`。
- reader 以 verified taxonomy identity map 補足 row-level optional `security_type`：`3718=common_equity`、`9103=tdr`；因此可保留已知的 `membership_security_type_unrecorded` warning，但 TDR 仍以 taxonomy eligibility 明確 excluded，不把此 degraded warning 升格為 publisher blocker，也不放寬 special-security guard。
- full PIT denominator 為 `2`，eligible `1`、excluded `1`、unknown `0`；industry coverage 使用 `mapping_mode=pit_accepted_prospective` 與 `coverage_denominator=accepted_pit_membership_rows`，只將 `3718` 送入光電業 constituent，且 readback lineage 暴露 `taxonomy_identity_path` 與 source／sidecar hashes。
- successor 只使用自己的 `2026-09-03`、`09-04`、`09-07`、`09-08`、`09-09` trading sessions；warm-up `5` 完成後仍維持 `HISTORY_WARMUP_COMPLETE_REQUIRES_SCORER`，不產生新 score，也不授予 formal／natural credit。

這條 caller chain 的適用邊界仍是 research-only：2026-09-16 的 real-source capture 不是 production historical PIT，`5371` 的 current official exact join 仍缺件，`3718` 必須使用自己的價格／交易日／warm-up evidence；不得以舊 parent、broker、scheduler 或自然重跑補足。

## Test／static verification evidence

以下均在 repository root `C:\Projects\PythonProjects\technical_analysis` 執行；pytest 的唯一 warning 是既有 `.pytest_cache` 權限不足，非 test failure。

### PIT source／security／timing targeted

```powershell
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m pytest tests\test_pit_taxonomy_daily_source.py -q -o addopts=
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m pytest tests\test_formal_rule_source_producer.py -q -o addopts=
```

目前結果：本輪加入 TWSE 四元件 composite parser、B12.00–B12.12 中間版本產業變更 negative test、component raw custody／producer reparse、composite derived-completion revalidation、metadata+outer-hash tamper negative 與 route preflight negative test 後，taxonomy targeted 為 `31 passed, 1 warning`；`formal_rule_source_producer` targeted 為 `20 passed, 1 warning`。重跑初期曾被 working tree 內另一個未相關的 `ml_module/recommendation_inference_provenance.py` 缺少 `dataclass` import 阻斷 collection；該檔屬其他 agent 變更，本線未修改，主 agent 已修復。adapter／security／producer／reader／formal rule producer 四檔 targeted `mypy`、本線 `py_compile` 均通過。

涵蓋 TWSE／TPEx bounded parser 正／負 fixture、current revision／month-precision applicability、unknown current + known history rejection、research-only escape hatch、producer reparse 不接受 research PDF、跨市場 definition、完整 alphanumeric token、semantic duplicate、same-ISIN／multiple-common／unknown conflict、5371 missing preservation、composite primary/base byte+HTTP binding、四 component completion revalidation、metadata+outer-hash tamper rejection、producer timing 與 preopen entrypoint timing。

### Cross-module regression

```powershell
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m pytest tests\test_pit_taxonomy_daily_source.py tests\test_pit_sector_membership_reader.py tests\test_pit_industry_callers.py tests\test_pit_preopen_schedule.py tests\test_formal_runtime_roll_forward.py tests\test_formal_pit_sector_publisher.py tests\test_formal_pit_sector_publisher_cli.py -q -o addopts=
```

stdout／result：`81 passed, 1 warning`。warning 是既有 `.pytest_cache` 權限不足，非 test failure。

### Lifecycle caller focused verification

分批提交任務在同一 B baseline 執行完整 data／PIT regression：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pit_taxonomy_daily_source.py tests\test_security_lifecycle_caller.py tests\test_formal_rule_source_producer.py tests\test_pit_industry_callers.py tests\test_pit_sector_membership_reader.py tests\test_pit_preopen_schedule.py tests\test_formal_pit_sector_publisher.py tests\test_formal_pit_sector_publisher_cli.py tests\test_formal_runtime_roll_forward.py -q -o addopts=
```

delegated result：`103 passed, 1 warning`；warning 為既有 `.pytest_cache` 權限不足。釋出後本線以以下精確命令聚焦執行 `test_lifecycle_caller_wires_published_new_cohort_to_pit_and_industry`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_security_lifecycle_caller.py -k lifecycle_caller_wires_published_new_cohort_to_pit_and_industry -q -o addopts= --tb=short
```

結果為 `1 passed, 1 deselected, 1 warning`；warning 同樣不是 test failure。原始 tool evidence 由 reviewer 以提交任務 command execution 定位：targeted mypy `exec-a7a13180-ba38-426d-859b-5a73711ae677`、focused pytest `exec-7dcd7307-30f3-43e4-b44c-7e7721291e75`、py_compile `exec-94b5550b-f81b-423c-bb70-841a700f96d9`。

### Python syntax

```powershell
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m py_compile app_module\industry_strength_service.py app_module\security_lifecycle_caller.py data_module\formal_pit_sector_publisher.py data_module\formal_rule_source_producer.py data_module\pit_sector_membership_reader.py data_module\pit_taxonomy_definition_adapter.py data_module\pit_taxonomy_security_adapter.py data_module\pit_taxonomy_source_producer.py scripts\scheduled\run_formal_pit_sidecar_postcutoff.py scripts\scheduled\run_pit_sector_membership_preopen_capture.py tests\pit_test_support.py tests\test_formal_rule_source_producer.py tests\test_pit_taxonomy_daily_source.py tests\test_security_lifecycle_caller.py
```

exit code `0`；stdout empty。

### Targeted mypy

```powershell
$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe -m mypy data_module\pit_taxonomy_definition_adapter.py data_module\pit_taxonomy_security_adapter.py data_module\pit_taxonomy_source_producer.py data_module\pit_sector_membership_reader.py data_module\formal_pit_sector_publisher.py data_module\formal_rule_source_producer.py app_module\industry_strength_service.py app_module\security_lifecycle_caller.py scripts\scheduled\run_pit_sector_membership_preopen_capture.py scripts\scheduled\run_formal_pit_sidecar_postcutoff.py --show-error-codes
```

本次釋出後增量檢查的 10 檔 stdout：`Success: no issues found in 10 source files`。較早的原指定 8 檔與依 repo gate 執行的 `ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime --show-error-codes` 也通過，後者為 `Success: no issues found in 621 source files`；只有兩個既有 untyped-function note，沒有 error。

## 變更範圍與待辦 blocker

本次 implementation 變更範圍：

- `data_module/pit_taxonomy_definition_adapter.py`：TWSE／TPEx market-scoped bounded parser、TWSE B12.12 四元件 raw-derived mapping、applicability／歷程閉合與 v4/composite parser version。
- `data_module/pit_taxonomy_security_adapter.py`：完整 security token、market/type/CFI semantic identity 與 fail-closed selector。
- `data_module/pit_taxonomy_source_producer.py`：source completion timing、capture start/completion custody、四元件 classification raw custody、producer reparse 與 bundle validation。
- `data_module/formal_rule_source_producer.py`：研究 caller 的 resolved output-root preflight；正式 scheduler 的 date-scoped default 不變。
- `data_module/pit_sector_membership_reader.py`、`data_module/formal_pit_sector_publisher.py`：strict bundle/raw/readback gate。
- `app_module/industry_strength_service.py`：只使用 eligible membership，保留 coverage／excluded／unknown diagnostics。
- `app_module/security_lifecycle_caller.py`：研究用 predecessor／successor identity、官方交易日驗證、PIT publisher／reader／industry readback 與 no-carry-forward gate。
- `scripts/scheduled/run_pit_sector_membership_preopen_capture.py`、`run_formal_pit_sidecar_postcutoff.py`：preopen injection 與 exact-date postcutoff read path。
- `tests/pit_test_support.py`、`tests/test_pit_taxonomy_daily_source.py`、`tests/test_security_lifecycle_caller.py`、`tests/test_formal_rule_source_producer.py`、`requirements-runtime.txt` 與本 QA evidence。

尚未跨越的 production gate：

1. 本次 research source capture 實際落在 2026-09-16 台北 00:32–00:50 的 preopen window，具備研究用 preopen timing evidence；仍不能宣稱 formal credit。正式日需由 scheduler 於台北 08:30 前完成官方 raw／metadata／hash custody。
2. 已有實際 2026-09-16 score-bearing parent：1,932 symbols／scores，machine readback verified，且保留原始 score-bound hash 順序；它是隔離 candidate-only evidence，不給 formal credit，也不覆寫舊 parent。
3. 同日完整 parent exact join 實際因 `5371` missing fail closed；raw-only archive 雖可 readback，但只得到 `1,931/1,932`，因此不產生 full taxonomy bundle，不 drop、不補綠、不沿用舊 archive。
4. TWSE B12.12 composite definition component probe 已通過：B12.00 base、2023 change notice、B12.13 bounded history 與 current regulation cross-check 可重驗，safe boundary 為 2026-05-01；current B12.13 的 `115/12` 只作 target 後的 history evidence。TPEx V12.18 可依 explicit applicability evidence 使用。production environment 必須提供可採用的官方 source config、runtime `pypdf>=6.0.0` 與有效的 preopen clock；不得以 hand-written mapping、latest bundle 或 t187 fallback 代替。
5. 同日完整 security snapshot 尚未取得；目前是前一份 44,821-row full map 加同日 `5371` exact negative query 的 mixed-date diagnostic，不能宣稱 fresh same-day security evidence。MOPS lifecycle raw 已另行核驗 `5371 → 3718`，但 lifecycle／warm-up／score-ready 仍須由獨立 contract 與 caller 接線處理。
6. 即使 parent／source chain 都齊全，正式 preopen credit 仍須等自然日台北 08:30 前的 raw／metadata／hash custody；本輪 2026-09-16 evidence 為研究 probe，不作 formal／recommendation credit。

相關旁證卡：`output/research_qa/pit_taxonomy/2026-09-15/security_map_qa_card.md`。本檔與旁證卡都只記錄可重現 evidence 與 blocker，不代表 release approval。

## 2026-09-17 late denominator transport probe addendum

Root 另以唯讀方式核對 receipt `output/qa/pit_denominator_urlopen_transport_probe_20260917_receipt.json`：
實際 `_fetch_one`＋`urlopen` 僅發出一次請求，時間為 `2026-09-17T19:18:23Z–19:18:26Z`，HTTP
`200`、`672,624` bytes，body SHA-256=`7954eb03c42e22704f71ff39ef7e20c900b0334b9661cb97d1f086f813b53e30`；
與 requests 取得的 bytes／hash 相同，URL metadata 無漂移。這項證據只表示該晚到觀測時點的 transport
可用，不能回補已過的 9/17 PIT cutoff，也不能把 same-day denominator、taxonomy publication、formal
sidecar 或 Paper／formal credit 寫成完成。先前 `PIT_COMPLETION_AUDIT_20260917.json` 所記錄的 DNS／
HTTP response 前失敗仍是該次 audit 的歷史結果；同 URL 9/11 可解析不代表 9/17 cutoff 已驗證。

目前既有條件維持精確分類：D read-only／既有 candidate10 apply 與 heavy rebuild holds；未來合法時窗的
新 PIT／Paper capture 與 actual terminal receipt；真實 human thesis／actions／entry custody 缺件；
historical source 缺件；natural maturity；formal input／owner license gates。正式 D、formal job、Paper 與
V4 均未完成，亦未啟動 scheduler 或修改正式資料。
