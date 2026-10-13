# Baldr 補完恢復增量（2026-10-12）

本頁接續 [10/11 補完進度](BALDR_COMPLETION_PROGRESS_20261011.md)及[恢復交接](../agents/shared_state/BALDR_COMPLETION_RESUME_PROMPT_20261012.md)。完整範圍仍為 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4；局部 PASS 不相加成完整工作包或 Gate 接受。

## 接手與來源

接手 HEAD 為 `b834f6116dff8316d45dae7c704f260738896325`。文件產品化 owner 正在修改入口、Snapshot、架構及手冊；本輪保留其未提交內容。`dc579133` 的 Paper 身分／G9 日曆修復與 `11589244` 的 H20 中央母體迴路已提交，舊 QA 不代表新版接受。

Root 已核對舊 Health Main、P08 V4、M24 origin及 Main crash 具名收據 SHA，均與原交接一致。P08 原 5 PASS 仍僅適用指定凍結版本；Main native access violation 根因仍未知。舊 singleton 不移動、不追加，本輪依現行 `scripts/document_control.py init-task` 建立 `output/tasks/baldr-completion-resume-20261012-01a13196/task.json`。

## M27 封套與 Root 審查

M26 phase helper 的六個聚焦案例已有 native0 收據，本輪不盲重跑。同版 helper、retry tests及 setup-failure test bytes 與 M27 相同。M27 只修活動 namespace及 supervisor 四個 stale SHA，保留六角色、每角色600秒、N1000／20頁、每操作30 samples、完整DTO／serial oracle及嚴格p95低於300ms。

原 Root 審查器誤讀 raw archive `relative_path`（實際為 `path`），新審查器修正此欄位；其後靜態逐欄確認 manifest 實際只改 `candidate_artifacts` 與 `candidate_query_overlay`，修正審查器錯誤的第三個差異欄預期。原失敗均保存，未改產品、原測試 assertions 或 acceptance threshold。

M27 Root 審查 **3,497 pins／18份完整前後像／18個執行來源 compile／382項閉包通過**，Python 完整正逆與 AST 逆回一致。原3075來源 inventory 中四筆後續修復漂移，精確核對 `.t/v41407a3/repo/` 中保存的原 SHA，包含 identity provider／test與 H20 learning runner／test；新版新增 H20 test 不挪入舊 inventory。382項實際閉包無漂移。這是指定舊來源版本的候選驗證，`current_formal_version_accepted=false`。

| 證據 | Root 結果 | receipt SHA256 |
|---|---|---|
| `root/p01_m27_static_9dc7bad7252f453aa6617d7e4479b746/receipt.json` | 完整審查通過 | `55f6c36bb6a7916168725aab9260d0a0cbe9d4cab8a558617428ce53f2e23b4c` |
| `root/p01_lease_matrix_plan_aa69c24cc8ad4136a09952f72fc9066d/receipt.json` | plan native0，same named Job／suspended assignment通過 | `f822825590001eec5e5cb888bbe2f322cd539a3e257e4a4a02fc50c9c3971e6d` |
| `root/p01_lease_matrix_origin_985f8ab9f3f3402fbc5b0b95e041f875/receipt.json` | actual origin native0，query／repository／SQLite exact SHA，無store read | `a39d66a2fe7b264e4cdfc3b943b6a47a0df6246b18943adfccbd27f6ea61366b` |
| `root/m27_pure_preflight_364005b802d248d596e7b9237cff42dc/receipt.json` | 原純預檢 native0，pins不變 | `c923871e0f5119ac2b27e764d195c59478c0a2335ff965159913bbeaacb5bcda` |

上表 `root/` 均指 `output/qa/baldr_completion_20261011/root/`。各組外層Job自然0、process／Job handles閉合、mutex釋放後，才啟動下一組。

完整六角色矩陣單次執行已終態，五cold＋一warm native0，約539.24秒；外層 `single_owned_qa_3d6863bfb3884cb59f0138fc074ee9db` 自然Job0／handles閉合／mutex釋放，沒有forced cleanup。六內層角色亦無逾時／cleanup errors，清理前後Job皆0、Job handle closed；原store及來源後守衛通過。

完整矩陣收據 `root/p01_lease_matrix_matrix_4f02a325797c42c29cf906729f87031c/receipt.json`，SHA `b260a7293172696aff69e9a2e6f247fc1a07104edca66afa597e3b40612e72bd`；外層收據SHA `af5dbee6d86803d1dc46cefe0cd90eb97633b5fcb78b86f08bf2d4d56dece024`。Root獨立從每類30筆原始 `elapsed_ns` 重算nearest-rank第29筆，與原收據逐值相等；90份完整DTO的actual／serial hash與semantic equality均通過。

| 原操作類別 | 樣本數 | Root重算p95 | 原嚴格低於300ms |
|---|---:|---:|---|
| 翻頁 | 30 | 327.8650ms | FAIL |
| 篩選及頁面 | 30 | 444.9752ms | FAIL |
| 全域排序及頁面 | 30 | 934.8569ms | FAIL |

五cold啟動至首頁p95為38.2899016秒。獨立重算收據 `root/m27_independent_metrics_b352c8dd91ed4a0e9761ce5327a35026/receipt.json`，SHA `5d87287723542de0da92ac15076323353207598738ed6e498c7002903423ac7d`。`native0`只證診斷旅程完成，**三操作效能Gate皆FAIL**；不接受P01、完整母體／Main／最新版正式來源或產品Gate，不重跑挑選更快樣本。

## Main 與 Health 靜態交接

Main單次dump封套已封存，manifest SHA `b2a9732ff35188b460b4b45df2fda6bd32f398027e7614759e9d1d0c5cd90e5b`。Root純資料審查收據 `root/main_native_adapter_data_review_63d31f90dd2d49e5877e921646086f0e/receipt.json` SHA `c571c78187d617a54d6787fb7d348fbe2b255661c45ad18b8f80228802e982a7`，4299pins／3075logical module與SHA、完整8處raw正逆、protected AST及唯一Popen保持。新的origin `root/p01_main_native_capture_origin_8bbeb697362647acaca759624059e4cf/receipt.json` SHA `8a8f83cb272e1eb2e5689d3eecc141966350b967787e76404bda86896cd56a8a`，collect1／native0／guard及pins／mirror乾淨；沒有冒用舊origin。

只執行一次完整N1000 Main觀測，原QTest／GC／60秒repeat traceback／600秒期限與來源守衛保留。`root/p01_main_native_capture_suite_23afed61d0f64a4ba7a706364477b090/receipt.json` SHA `adf657ced41975d1af1a66a8ec2cfc8985851a6da4b388504ad859962de1687d`：native `c0000005`、guard false／0個完整atexit origin／fresh未完成，pins及mirror穩定。唯一次second-chance AV dump為同packet的 `native_dump/fault_22016_21952_0.dmp`，SHA `62b2f0aafd235aab2215d6d70ed2eb830c64f6ba57883b4a094bbf8f91cd81a3`、348,191bytes；ExceptionStream缺席明示。PID22016／ppid7932／creation FILETIME134363103439468400／exact base Python／same namedJob完整綁定，fault thread21952。debug log SHA `be2f9a4d2125c4f63f9ee966365a15bc757205e1a548ea580b80c3600a43d506`，539 raw lines。first／second-chance分別在creation後約262.147／262.247秒，不能套先前60.34秒timing；原writer重複記錄保留，不把duplicate當第二次exception。

debugger正常EXIT／detach、event log、observer與stub handles均閉合，cleanup及processing errors為空。外Job `root/single_owned_qa_cea88b9a170c49f8a1354784dadcdeae/receipt.json` SHA `853b25b35752c233a02883187a5f9a192aa33c8de3cbaea04287d4002ccb6f34`，root exit99、Job自然0／handles閉合／mutex釋放，無forced cleanup。此為成功取得單份診斷資料的**Main FAIL**，凍結Gov7舊3075來源資格明示，不授目前正式版本；根因仍未知，後續只做離線資料解析，不重跑Main。

Root單次離線資料解析 native0，輸出 `root/single_owned_qa_068a1b03de55492d9c5f653e0e6d56e9/stdout.log` SHA `32c5fbf50f585f9a911d67e2097a4ee719fb0452469f4e160b745a23c074c4fb`；外收據SHA `b15c12b14de6ab8e4d6c5074f15eccd94f91dea7bf75c5dff4bde097359e459b`，自然0／handles及mutex閉合。34threads／384modules，13個directory rows中9個非Unused streams；fixed輸入SHA前後不變。dump DLL與本機DLL／PDB的GUID-age精確相同，first／second AV同位址 `0x7ff964b19ce0`，RVA `0x259ce0`，唯一涵蓋舊已驗`dump_frame`原procedure區間，位移52bytes；ThreadList RIP亦相同。快照ContextFlags `0x10005f`、RDI0、RCX0，AV為read `0x70`。ExceptionStream仍absent，ThreadList僅為當時快照、不冒稱exception context；沒有unwind或私有記憶體bytes輸出。公共DLL指令與官方CPython來源之後由靜態代理核證，指標形成原因仍unknown。

Main 靜態代理核對29個固定來源pins無漂移，準備只讀 exact DLL／PDB 的 DBI section／OMAP 候選，SHA `fe0994a156e88dfcb3f002ccd7c355077b8fff6dd2d43aa53c1ea1df6010b157`。Root逐byte複製後的首次純資料Job停在optional debug header的22bytes假設；保存原FAIL。新observation入口保留原斷言，實測24bytes且完整尾界正確，再以exact24 sibling保存第12未分類slot。格式可有多於11個索引，參見[LLVM DBI格式](https://llvm.org/docs/PDB/DbiStream.html)。此純資料階段沒有更換Python或執行Main。

exact24純資料Job native0，收據 `root/single_owned_qa_b8b1e6f15da240fda2c68aab2225d515/receipt.json` SHA `a987359ea1cb34e72dbc26772960e00551b4155b849fa6bf724a81ef3283302c`。PDB／DLL exact GUID＋age相同，7個section metadata相同；OMAP雙向與SectionHdrOrig均absent，額外slot11亦absent。原symbol parser的無matching procedure不能歸因OMAP或不同section。每次data Job自然0、handles閉合、mutex釋放，資料證據不授Main成功。

一次split-code查核保存278 modules／8,927原procedures／3,717 split ranges，但因nonlexical `flags0/pParent0`套用lexical parent鏈而FAIL。原FAIL收據SHA `01a7628dcb4ebd9392970c3156bdcc8c91b1d8d91a919daeb09d6c48a4c55d91` 保留。新窄分支只接受同module、segment／offset／RVA精確唯一的code-parent起點，split與procedure end守衛及原唯一matching斷言不變；不猜nearest symbol、不偽造pParent鏈。[Microsoft欄位語意](https://github.com/microsoft/microsoft-pdb/blob/master/include/cvinfo.h)支持這份exact資料的地址綁定，不外推所有nonlexical記錄。

窄分支純資料Job native0，收據 `root/single_owned_qa_9cf375554c6a4a5b8900f22000ecf890/receipt.json` SHA `5a9b3bd1af3329605f673813dbfc46a7ad8982ce6cc9237b0704e7d814c19fd2`，完整stdout SHA `5736c334b64563ab655faab3cac52038a5f4f6262d72a6ed6bbecdd3e80f4ac5`。兩fault皆唯一合法範圍：`0x1aaaeb` split的exact code parent為`PyCode_Addr2Line`；`0x259cf3`原procedure為`dump_frame`。事件距程序建立60.3530122／60.3378567秒，與原首次60秒traceback觀測接近；timeout與fatal handler都可走這條路徑，仍不能區分初始錯誤或次生診斷fault，不認定faulthandler根因、不移除60秒觀測、GC或600秒期限。

受控native dump工具以隔離自有子程序正例驗證：原`ctypes.string_at(0)`未驗入口保留，新probe沿官方`faulthandler._read_null()`直接NULL讀取；helper只新增第二份dump fail-closed。原40秒、exact PID／creation／exe／ppid／sameJob與native c0000005／自然退出斷言不變。工具收據 `root/owned_native_dump_probe_11c3fdff53854c72aaeb2a504b11bd91/receipt.json` SHA `c2403e5ae461fbb79e05069de41be84439f4db7334589b108625e22f161edee3`：probe PASS、無forced cleanup、1 dump；header／directory bounds、12 streams、4 threads、15 modules、AMD64與exact fault thread均核對。ExceptionStream缺席明示，dump SHA `a3b779c9d2e23a014c2c6efc5c88a8e0ee904bcbe9811bd0a8a473ec1abf2b23`。[CPython實作](https://github.com/python/cpython/blob/v3.11.9/Modules/faulthandler.c)、[Microsoft dump結構](https://learn.microsoft.com/en-us/windows/win32/api/minidumpapiset/ns-minidumpapiset-minidump_header)為格式／觸發依據。外Job收據SHA `1517e15ce418eb718b5326237866db71a479df2060575409ba296c5266bc280c`，自然0／handles閉合／mutex釋放；未附加任何其他程序或執行Main。

Health 原manifest及46封套檔、10 upstream overlay與7 formal tests pins保持一致；7個既有產品前像raw SHA與Git canonical blob均吻合，3個新產品目標仍不存在。原完整Main來源封套已有11個formal漂移，不能重跑舊3079封套。C1新封套3146件／73,558,202bytes、正式來源3076（tracked3069＋原ignored7）／Health映像3080，manifest SHA `1ccaea9e06a0606fc2abd087367b002af6b6aa02d9cee38cd05bc8a4424aefd7`。封存前攔到治理owner的`auto_state_sync.py`額外drift，保持HEAD snapshot／live-equality guard並保存完整新舊raw；C1仍`execution_ready=false`，不能執行或稱最新版PASS。Root已靜態核對此工具改為default只讀Git狀態、明示own task／owner才更新JSON，沒有Health／金融／PIT改動；C2僅新來源row與明示dirty-owner lineage重封，仍待Root完整審查，未正式套用。

C2已另封存3152件／74,281,710bytes，manifest SHA `09343457eef4c60a71505ba847812a97bcd3a6a0f7ee170443568d07c9729a99`；Root小型loader逐byte等於範本，SHA `681896bd9f0b1d7afaa363f2144883c247d1373edf12d58a875e79823960469d`。3076來源／3080映像中只有`auto_state_sync.py`的logical SHA改變，25個產品／test／assembly／patch保護檔相同。Root審查6276pins、13完整raw delta與正逆重建、產品AST及runner五個精確來源替換；formal15／Main24原assert保留，600秒不變，current live equality成立。範圍明示current tracked＋一筆peer dirty，未提交治理tool/tests保持held，formal/source/version qualification仍false。

| C2 Root步驟 | 原件（`root/`同前） | SHA256／實測 |
|---|---|---|
| raw／AST／pins審查 | `root/health_current_lineage_static_02ee7faf0ffa482b8b5b942f73b73dc8/receipt.json` | `d3a02ab849ad4e23352109d7ea1eb398d13896a2fed3ce98fbde02581c1f447d`；PASS |
| formal origin | `root/health_formal_candidate_origin_3fd9be729eda47da83f32bc93e5eb82b/receipt.json` | `39c03f965a70bb6e3a9189ab943b5799a4cc851e6ee79f6b2bef319763147a57`；五canonical module、native0 |
| panel | `root/health_formal_candidate_panel_38506ff19eb843b0a64d11ba1c218718/receipt.json` | `3c4d24bef17a9399ce3ef2d35ca8f00e07fe7d047530e534e8027ee6d80a6b6d`；3 PASS／2.33秒 |
| reader六檔 | `root/health_formal_candidate_reader_47144e1abbe0442e939aff18471a4905/receipt.json` | `77bb86e994b26e2f0c9c94dc36eb5dd1e6f0dd7098720455708dcfd046c635e8`；110 PASS／2 SKIP／13.29秒 |
| Main origin | `root/health_main_portable_origin_e54aedb808ec4118bc5fa69b38fc691a/receipt.json` | `07bd279904cf06cff335951516a23b1dd03e3da3d428443b0cb6c60c847d25b5`；collect1、native0 |
| Main與fresh PID | `root/health_main_portable_suite_77a44bd21e5f47ef9c7092700ea3b87b/receipt.json` | `339b19d0e3b167cadb4b577bdb86847fc8b6cc3e6234b65ba8e659a9acccd0ec`；1 PASS／27.55秒 |

每一步source guard／pins／mirror乾淨，reader有3 actual PID，Main有2 actual PID及1個owned fresh child。reader兩SKIP均為Windows不能建立symlink；未把SKIP改成PASS。fresh PID29552在子程式碼前驗明sameJob，native0，process／query handles閉合，正常Main關閉及native TaskWorker registry drain；精確保存身分重開仍保留degraded／unknown／WATCH與research-only。最後外Job `root/single_owned_qa_6c845914408049778bfa6915561321d6/receipt.json` SHA `28c7dfae93791d48dd9297b327862642e8f1211bb4fefc734236f91469d2cf13`，自然0／handles閉合／mutex釋放且無forced cleanup。候選旅程通過不授正式採入、來源資格或完整Gate。

文件已分冊，Health操作增量應落 `docs/07_guides/manuals/WATCHLIST_AND_PORTFOLIO.md`，架構增量落 `docs/01_architecture/current/decision_research_portfolio.md`；不套舊巨幅Manual／架構／Navigation全文。正式提升尚需Root精確採入收據、同版正式回歸、UI85、validator、八根mypy及compile，並保留Paper身分與H20新lane。真來源／自然producer／同版exe／真人及完整P06／M3／Gate仍未接受。

治理owner另提交 `9ff7bc5b0ae170677c4f3e5f30356df581261c43`（145paths），原C2的3076來源raw均未變；新增tracked Python四件：`document_control.py`與其兩個治理tests，以及archive中的原`auto_state_sync.py`。現行auto_state_sync的5dfe bytes／60e83 blob已正式提交，C2的peer-dirty描述保留為歷史範圍。Health正式採入草稿的HEAD守衛因此拒絕seal，原pending包保留，未直接更換HEAD pin或正式採入。Root重讀新AGENTS／baldr-product-workflow／共享規則與適用角色，另授靜態sibling完整raw來源rebase；active來源應為tracked3072＋原ignored7，archive1僅歷史pin、不進runtime namespace；Health映像3083仍需Root實測審查。C2候選PASS不授新HEAD完整版本接受。

新h9ff7封套已seal，manifest SHA `b23270a18a37101d42cb8e17f7408cb82969e0328eb580696ea40fbfbded81bc`，3480件／95,211,519bytes。Root首次完整review在C2 loaded closure的suffix唯一性斷言停止；外收據 `root/single_owned_qa_610fec1bac93428a9a389e99a5af6b33/receipt.json` SHA `74b7e45abc893f5c633f47a888b86b681462ef33da31ddb13807ff2616528ef0`，exit1、自然Job0／handles閉合／mutex釋放。原FAIL及封套保留，尚未apply。18筆actual loaded來源同時匹配qualified rel與原ignored短別名，例如`decision_module/reason_engine.py`及`reason_engine.py`；這是reviewer路徑歧義，不是來源drift。新r02須用原guard mapping raw SHA、原copy protocol、各actual origin唯一去重mirror及完整logical rel建立精確physical映射，不能以最長suffix或hash挑選來消除歧義；仍須重新Root review。

公共DLL的fault bytes已由Root唯讀核為 `48 8b 47 70`，即 `MOV RAX,[RDI+0x70]`；base是RDI，不是RCX。直線prologue從第二入口參數的`+0x20`讀入RDI，在七字元前綴write之後讀code的`co_filename`。exact binary operands及已pin的3.11.9 release headers支持本次局部code為NULL；RCX／RDX是call後volatile快照，不能當原frame參數。這仍不證明frame/code為何無效，或是否次生fatal診斷。[CPython原碼](https://github.com/python/cpython/blob/v3.11.9/Python/traceback.c#L1174)及[Windows ABI](https://learn.microsoft.com/en-us/cpp/build/x64-calling-convention?view=msvc-170)為對照；靜態封套`output/qa/main_dump_frame_cause_static_20261012_root_resume/manifest.json` SHA `81dfa50d2c1c93549475ea9be926ac4b6a35d7093144432401012156b434485d`，未編譯offsetof候選、未改Python、未重跑Main。上游3.13／3.14安全getter修正不能直接當3.11本案已修復。

r02封套manifest SHA `0b81f8d77d6d741112e64011f24e892da8b956c9fbbc4461657d00da2e926a53`。Root逐份核3507件的size及SHA，獨立重算131,317,993bytes；原總size欄null缺陷不改寫，獨立資料紀錄SHA `0cbb22ff99dfa0154dc28963363bec3570d2cf0c4a3c3c6f8382bd5181e926be`。新exact physical mapper核五組各3080筆、2946個loaded rows；原9份控制全文與r02四份完整raw端點、所有3474 inherited bytes及AST、145路徑Git literal raw lineage、3079 active來源與archive排除、11path完整patch正逆／原Main24assert及600秒全部通過。

| 正式提升步驟 | 原件（`root/`同前） | SHA256／結果 |
|---|---|---|
| r02 Root完整review | `root/health_formal_adoption_review_341aac90634b4bf8922f3464b0acda72/receipt.json` | `9b92b6efb46162f4e2df6f6f5b802f12da1841e69e6cce7def8921e31b6eaf89`；PASS，舊FAIL保持 |
| 精確11path apply | `root/health_formal_adoption_apply_4ce20d067cdf4f72a594b48dfd0f1e19/receipt.json` | `6817a326e501952eb7e67e8b1cc4645647bea288ef210afcb981a16533e3255f`；7前像＋intent保存、7既有／4新增寫入，前後守衛PASS |
| 正式runtime映射review | `root/health_formal_runtime_review_021b46601990494a9802c45841acebcf/receipt.json` | `5097c498dcadaae47bd10e3c0ca519cd161316ed7329155af0ca79a36bb7246c`；3083來源均綁正式repository，QA尚待 |

三組均native0、自然Job0／handles閉合／mutex釋放，沒有forced cleanup。正式產品已精確採入，不改Paper身分／H20現行來源；其餘產品、peer文件及singleton保持。這是採入與來源映射證據，正式同版QA、source/version及完整Gate仍未接受。

正式origin收據 `root/health_formal_adoption_QA_origin_05ec0e585cd74ffa95d8856ba53d39cd/receipt.json` SHA `b89fab26524465c23a4813d9f15ade8caedea070071bc4bd9344ead495aaa552`，native0／actual products均為formal／來源守衛與pins乾淨。接續原23檔caller收據 `root/health_formal_adoption_QA_callers23_112e589387e644e3ac7897d7e4fc373e/receipt.json` SHA `24191349e001bd6ded7c0b3185853772bd4807bcdfeb908891dd88b013ec5a7f`，**320 PASS／2平台symlink SKIP／9 FAIL／24.58秒**；JUnit SHA `a70c8ba8a08ada9afcdc4a880ed551827508f80c848120a5e559c80988dbb0a8`。九FAIL均在`test_user_declared_holding_research.py`原`saved_recommendation_query_root` fixture的repo旁`.tmp_srqr_*`寫入，由完整normal child audit的`formal_calendar_health_QA_write_outside_private_roots`拒絕；不是放寬guard的理由。產品／assert／clock／PIT不改，只準備fixture改到runner短私有根與精確單檔source lineage。此正式caller組來源／pins仍乾淨，外Job自然0／handles／mutex閉合，原FAIL不改寫。

Main saved RBP的RVA為`0x421bc8`，exact公共DLL`.data`覆蓋；named export`_PyRuntime`起點`0x597000`，排除內嵌成員假說。Root公共PDB data-symbol查詢首跑在segment-bound斷言FAIL：外收據 `root/single_owned_qa_4a5427eeb7714f5aa5e36cb9a4ae8dd6/receipt.json` SHA `8870ac148b2b3abd59378c470f1f8b43b60d3251042bc7dc74512aa83231dd4f`。單次642bytes前置record觀測保留原assert後仍FAIL：外收據 `root/single_owned_qa_37bf2b19700442b68e391a93d02e159d/receipt.json` SHA `83283086e6f4ea10981ae5a600ad7c1a136b1a234a937606f49ddb7ef7ffd46b`，actual stream289／record[4128,4196)／S_GDATA32 `_OptionsStorage`／segment0、offset0、type0x23，raw SHA `de72bfaecf4660c81a53fa954e11a8b9ebefe9b9656a64d3203a083c9d8db21b`。無section RVA的記錄不作nearest或猜discarded原因；新窄分支須明示unknown並保存原始記錄，原非該分支bound仍保持。兩組自然Job0／handles／mutex閉合，未執行Main或讀private memory，原Main FAIL與因果unknown保持。Root前置清冊欄位／前像檔名錯誤也保留工具結果：首次wrapper在script尚未copy時於Job建立前FileNotFound，後續前置錯誤未啟動Python；已核正欄位及exact raw inverse，不冒稱成功。

新public符號查詢完成Root五組raw inverse及AST投影，原AST／來源pins／有效section bounds／55秒內部及60秒外期限保留。`root/single_owned_qa_569fc0b61cc04796ad20aa160a08d6d9` native0，自然Job0／handles／mutex閉合，receipt SHA `32abb8239338a20eab830a81f3e323d336b3f1007b04b0d6bbb024b245f50235`；stdout SHA `7e1a6a03880aab4ac9b46673792d962ac556df7c7e43e47ef5df6e7e1ecb021b`、AST review stderr SHA `6ac79ae4e8d665041677c65ec1343a9608967b3fbfcd873fc134c11c468da50d`。449,828個symbol records中29,793個modern data/public為29,770 located＋2無section location＋21 absolute，完整保留兩種非PE-relative分類；exact DBI map原始SHA `fbd1fde8bdb3f837bd7b86e0acf29c2eda8c71c0a4e6d3eec861ac266a9c1d2c`，[LLVM固定13.0.0格式](https://releases.llvm.org/13.0.0/docs/PDB/DbiStream.html#section-map-substream)明示absolute bit9，Microsoft旗標定義未公開的限制仍記錄。

Saved RBP的`0x421bc8`起點精確同時匹配S_GDATA32及S_PUB32的`_Py_FalseStruct`，不是nearest。兩record原始SHA分別 `387947956485e2a8c78f48bd433330aa813f3eac0ed9145211e2dea2e2bb04a8`及`f951dce2855479cd45130cea6570ed574688607c38c837f9a435a01c2356b276`；未讀TPI或private memory。正常prologue／ABI推論下，保存的frame參數正好是False singleton地址，不能當成有效frame；呼叫路徑、指標形成及初始因果仍unknown。沒有新Main旅程或source/version/Gate接受。

Health fixture小型continuation原包SHA `94a9f1901a4abe772d992859c7f7bc4a661e5a210d74a1407e8db1d11b486040`首跑在loader第20行extended-path字串SyntaxError終止，尚未執行fixture review／apply。原外收據 `root/single_owned_qa_d8429cb3be4341d8b5927ba646e2418a/receipt.json` SHA `48730eb9404d74126ae54f61d913b5fa17a59873d8cc946d66a4426879c298eb`，自然0／handles／mutex閉合；原24files與loader e882不可改寫。最小r02 sibling只取親包已有效raw字串及重綁真實namespace／attestation鏈；所有fixture、產品、正常child guard與protocol保持。Root需先預編譯整份派生control，再review／apply；原FAIL不盲重跑。

續驗r02 manifest SHA `db7b5df332017aa1d4534995a964ccd8a2021a0747f338ea3784e96fbb25cc46` 的八份當前Python controls完成Root AST／compile，receipt SHA `c4005592586b12bc6504094a93020a53bd561df123249561b7436f2a16a4db91`、outer SHA `06ca72df3c6342dc471c77dc63a0d9e04476aaa30f51d07b8231fff937850128`。隨後fixture review已核before與現行來源，但在抽取原reconstruct函式後缺少其`re`全域依賴而NameError；outer `root/single_owned_qa_14acbbe0be33495dbeb8bf56fe8c8055/receipt.json` SHA `738b63627a4c563c378cf34386054107ab64a93d304056ff6a1f1d41eefd4808`、native1、自然Job0／handles／mutex閉合。未完成完整review、未apply fixture；原r02及FAIL不改寫，另準備僅補控制import與新namespace的r03。

同DLL有界unwind新封套SHA `6a9c499c1199b67680fe5ebcc977f7cda36cc87bfcdc998cd922b87f747fb849` 經Root全文及3901 AST nodes／9 artifacts／14 evidence pins審查後，只解析原唯一dump的已捕獲512byte範圍，actual讀17個unique qwords＝136bytes。data Job `root/single_owned_qa_99e9dd833ad447d7a051a0609c0d2020/receipt.json` SHA `3a905a736c6fbbde444eb3a8dc2cb84f841d4d9e79c1f018aac649152ae68a52`，native0／自然Job0／handles／mutex閉合；stdout SHA `cfa5bb04e2b70264f36201adbc3b813d7814a41cd699ddc45de938f4fe84a0ec`、AST review stderr SHA `a157685a1ead0effb79a9e7177c654a04772771c57503f8d9797222ffb2fa101`。精確public pdata／PDB範圍還原`dump_frame → dump_traceback`（合法split／chain）`→ _Py_DumpTracebackThreads → faulthandler_thread`（RVA2146760）；route層仍被非epilogue opcode保守白名單拒絕，`route=unknown`，沒有解讀該層stack，也不以符號名字跳過其metadata守衛。只授本次資料解析PASS，原Main與initial／secondary／根因／整Gate皆未接受。[Microsoft unwind契約](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)與[epilogue形態](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog?view=msvc-170)作為固定binary metadata的查核依據。

r03續驗封套SHA `52e8451cc3be95908ce8dfd8dabedc1d1b28d2d7100720f2357a30a7d6ece85c` 已獨立核51files／1,085,571bytes／aggregate `6169e43cc04a5cbff86f7b5395b909fb95966330d518c4e7dae44f9f016d1459`。Root八control compile＋reconstruct全部10個global（含builtin enumerate）的symbol table檢查PASS，receipt SHA `9f7e4365cca56e8813f284bf0708201befe745879b03a17951ea89bce34a4002`；沒有exec親helper module。完整fixture／三control literal正逆、AST、原Main9transforms及600秒、全部親封套pins PASS後，精確採入單fixture；原before／intent保存，十一Health不再寫入。

| r03當前正式步驟 | 收據原件（`root/`同前） | SHA256／實際結果 |
|---|---|---|
| Root完整fixture review | `root/health_formal_fixture_review_619442eaa5be4823bea36321a1730001/receipt.json` | `866122e847533d06e38b0fe55b6b8d269d57d7c0df40f159e3f1926db56d1ae5`；PASS review-only |
| 精確單fixture apply | `root/health_formal_fixture_apply_74b6a3aef79e4789a3bdc26596dfc111/receipt.json` | `57c1203c261ca7ef7bd7010688ab331649cf10ee9e9c536414ef9e66f4904f59`；before23177／aftera24cc，intent SHA `f109759acf2940e0c2ce1f8805342a0bb295349da6bc51ca151e91df0fd1307b` |
| 正式runtime3083 | `root/health_formal_fixture_runtime_e494987f006043c3a05be210b67010fa/receipt.json` | `eb916ed9ff0c86eae27ada919076e930998f00728789a63ed1bb039a87372b4c`；舊all-other=false、新explicit-except-exact-fixture=true |
| 新正式origin | `root/health_formal_adoption_QA_origin_cf459c89e7d84bafbee456c320cde089/receipt.json` | `2d49e46ae316fd3d3ef335f9182f097b92ab0b98b23f4f002b1c6ea54555c02b`；actual formal／guard／pins PASS |
| 原23檔callers | `root/health_formal_adoption_QA_callers23_05fd594f42464544a3b32b11a1465af2/receipt.json` | `bb40c0b67f6567d04c6b76c63ca5fa05f91fb152136412fa217ae45ac7098863`；329 PASS／2 Windows symlink SKIP／21.63秒；JUnit SHA `41b6e7a340710651a37bde324a3bf2bcd4c30493066acd558d32e057c6879514` |
| 新增七檔回歸 | `root/health_formal_adoption_QA_incremental_3a6fb2f9ca274d05bd109a8f43ec7304/receipt.json` | `a48f68b4ea255af622d77e24079c561205251c0cedc1b1dbc011c9e52889a3ed`；103 PASS／1 FAIL／84.06秒；JUnit SHA `7096baaf1239c5a88b11542145a3e5afcf4e351c5d62fe3cd0fb62f0a3a88375` |

上述各組自然Job0／handles／mutex閉合；callers原9FAIL與r01／r02控制FAIL不改寫。新增FAIL在`test_daily_main_missing_snapshot_is_recoverable_and_unblocks_same_day`原1451行，預期第二次run completed、實際failed_lineage；保存private synthetic latest_status的reason是首個候選artifact write的FileNotFoundError。靜態核candidate目錄存在且空（227字元）、joblib完整路徑261字元；本機LongPathsEnabled=0。這支持長路徑方向，尚未用有界正反例確認因果，沒有修改產品、縮fixture或降低lineage／PIT。來源／pins／formal origins乾淨仍不能把此組當PASS。

Main exact CMP siblingSHA `7d7788765f2c6384015e2ccfbf02e8dad3ca23b642ac07bdcaaeb430182be765`只加576bytes的唯一RVA／end／literal guard；Root完整raw inverse與AST投影等於原6490 source，原一般opcode守衛／512bytes／8frames／55-60秒皆保持。資料Job `root/single_owned_qa_d072fe95eb7c4a12bbbde5114c15b5d3/receipt.json` SHA `b5af77e4d24b3dff593855fee087cac675c7b2f78541093c002a6d3ce829b496`，native0／自然Job0／handles／mutex閉合；stdout SHA `0594fb6ddb913e7752050e55f020bd81138fc8de427321e323b1f1caa9ca6faa`、AST stderr SHA `57b0a136f79a4f95367564ef674e92114b8048e20d0f83937a14316c4f811cf2`。同樣只讀136bytes，第四層exact faulthandler_thread的CMP與完整public unwind metadata通過，授本snapshot之`exact_watchdog_function_on_unwound_stack`，到此即停、未讀route層stack。原unknown資料收據保持；不授Main、memory責任或initial／secondary根因。[Intel固定SDM CMP／RIP-relative格式](https://cdrdv2-public.intel.com/812383/253666-sdm-vol-2a.pdf#page=289)與[Microsoft epilogue契約](https://learn.microsoft.com/en-us/cpp/build/prolog-and-epilog?view=msvc-170)支持此exact literal分類。

Health r03其餘當前正式回歸：Main／fresh `root/health_main_portable_suite_bb0830032b2242189d2b03336d1fa9e7/receipt.json` SHA `9ee2941b130bef87bdb02d02b8fa31055aeaad72ce64dc3740b393bb57680e98`，1 PASS／20.67秒、兩actual PID、one owned fresh child，guard／pins／mirror均乾淨。治理兩檔收據 SHA `61451ee927f9193d405982311653f327d0182ab231c94315b9e943c40d7a8e94`（51 PASS／3.20秒），UI85 SHA `0ccb6d8c42c8ee8a809fb4489e6e1801d780aa0035aa7e419aad2771261c8570`（85 PASS／2.49秒），validator SHA `343bd3313b491e118c2cd7a844476f763e58607df51a7f427939b09fcad194bd`，syntax12 SHA `540ab1f17b7abb26a587c615137fc9a8e93fd748bc3f4ace0eb4385c3dbada60` 均native0／guard／pins乾淨；validator只保留原兩具名QA輸出前後證據。所有外Job自然0／handles／mutex閉合。

八根mypy工具stdout報957sources無問題，native0／58.203秒，正常UI ignore_errors既有設定明示保留；但完整來源guard **FAIL**，收據 `root/health_formal_adoption_QA_types_f4acdb3dba7c435488a0da557426d9c0/receipt.json` SHA `75a29fc9bd06519d2c5669a3bd1b06b035dde60d4ded8abc4951fc04616b62b5`。唯一violation為Qt虛擬`signature_bootstrap`三個code hash（bootstrap／EmbeddableZipImporter.__init__／exec_module）與原policy不同，其餘6個相符；actual source origin有589 loaded及10formal products，不能把codehash拒絕改成atexit缺失。原`--no-fast-exit`已使用，nested_PID_source_acceptance=false保持，整組不授PASS；outer SHA `97021a39c8ad7b0eaa21b81d5b6e7a7b656d05995a894113d2c55cc6429035f7` 自然Job0／handles／mutex閉合。只準備有界code-field觀察，沒有換expectedhash、略過signature guard或盲重跑mypy。

Root單次私有9bytes長路徑正反例收據 `root/owned_windows_path261_78716b3a25c7489fadf83bdf65d33af7/receipt.json` SHA `1b18d55044bd3acc844182116c2d35eb2ee81ed9b6c2ebd6df2b2cca957e1ae4`：普通261字元Path.write_bytes得到FileNotFoundError／errno2，existing227字元目錄下同canonical extended path寫入、readback、lstat／regular single link及hash均通過；短path control也通過，LongPathsEnabled保持0、不改registry、不訓練或寫正式資料。outer SHA `b647fecc0ccf6e7a5a504df924f2c3d1e4aaa13dd9ba96112a4a1ded3c1e97cb` 自然0／handles／mutex閉合。這證明本機普通I/O邊界缺口，沒有授producer修復。

ML完整artifact chain修正設計已另封存 `output/qa/ml_candidate_long_path_static_20261012_root_resume/manifest.json` SHA `aa88f9aa1e3b6991020c1defc81d6e4195a202da67006a9b3689f727e0c19616`；Root審Scope與測試計畫後只授靜態候選六既有source＋中立runtime renderer＋新測試，不改任何formal bytes。所有write／readback／authority／loader／consumer pair read／scandir／no-follow／hard-link／hash守衛與金融／PIT及canonical identity保持，不能縮fixture掩蓋產品長路徑缺口；舊收據不授新ML來源版本。

P01單次warm profiling靜態設計封套 SHA `81c183f4686cf5c1d00d62e6af839d2fc7eb4f4b71873af2c88908a42ca3a394` 保持不可執行。722payload／39,826,612bytes，保存四行fullraw漂移與517分層引用／439physical原件；actual loaded51與runtime package594相等，但current全declared closure379/382、startup79/80，full source equality=false。原3075inventory、新loader／完整after／AST及fresh origin均pending；只因51loaded相等不得重跑舊guard或換pins。原M27三p95 FAIL與舊61c profile界線保留。

## 資源、授權與文件覆蓋

Python／QA只由Root串行執行；subagent只靜態讀寫候選。每Job committed memory上限8GiB、12程序，至少8GiB可用RAM才起跑；named workspace mutex、suspended assign-before-resume及自然Job0／handles關閉／mutex釋放契約保持。其他IDE／MCP／專案程序不回收。

本增量已精確採入11個Health產品／panel test檔案及單fixture私有根修正，沒有正式原始資料寫入或stage／commit／push。自身Health操作／架構增量已同步現行分冊、Application Manual入口、UI能力及Guides索引；archived PROJECT_NAVIGATION不改寫。完整工作包仍因新增回歸FAIL與mypy來源guard FAIL未接受，文件同步不能折抵未通過QA。Coverage與安全接手點由自身task管理，不覆寫legacy singleton。

### Qt strict 有界觀察 root01：初始九項不符即停止

Root 控制 SHA `9132d23a29de44c90ff6272263f9b712c19324a3adce34875fff01cde1ed9fec` 先做完整 child 正逆與 AST 投影，原 guard bytes `12a46dbb…` 保持；compile-only 收據 `3c27c1e0454f6a2e1a8460ba537bc373fb0a44b45cb0c2aaaaf1ef6654017b0e`、外 Job `e37952624c1d6aea920b7f8feeff74b1c01424f33836b6fcd6ace9b20ac3f2e9`。

單次≤60秒 observation 收據 [21e8fe54](../../output/qa/baldr_completion_20261011/root/qt_signature_observation_observe_ce4a4904cef3405e9e0b95cb50daf613/receipt.json)；完整 observation SHA `4caf40213992f378c5d9d3f4ce71842e297e591ae8597fd52a3c2a67e4efcadd`；outer SHA `6ae8beef280384706f30a0c4cf87c9bc89899cca85f3398d2e2885423fdb1209`。原九項 initial strict 全不符，依約 `STOP_INITIAL_ORIGINAL_STRICT_HASH_MISMATCH`、native126，沒有 fields 收集或 mypy。原 atexit 守衛再核反而相等（clean=true），不抵銷 initial STOP，也不授原 types PASS；collector 尚未執行，不能宣稱完整欄位或 identity 相等。合併 hook 的 compile 常數／引用可能擾動 marshal，僅列待核機制，不認定根因。

十份正式來源、3083 mapping、七 Qt 原生 pins 與82封套 raw pins 全核且不變。兩 Job 真正 terminal、natural0、process／Job handles closed、mutex released；types／Health／版本／完整 Gate 仍未接受。
### ML 候選相容性複核與 P01 full3075 映像

ML implementation 原manifest `9a84c8622f3e7f8fd2747cdf1b5b7473830bb739c2222a6f25f59432aae82bae` 保存六份完整before／after與兩份new source，但未執行／未採入。靜態複核發現公開 `runner.run(frozen_candidate_root=relative)` 會在原 no-follow lstat 前由新 `_io_path` 拋 ValueError；另有absolute alias／ADS／尾空點／reserved的transport新拒絕可能逃逸原OSError-only fallback。此版本不接受介面相容性；Root要求新r02僅保留舊短relative／absolute／dotdot與原不安全lexical值的OS receiver／resolve行為，只有可安全render的長canonical路徑才轉換。保留strict internal renderer、自有OS inverse、原no-follow/hash/PIT/except，另補公開relative與舊Path對照回歸。r02仍製作中，不拿structural AST逆回當helper語義驗收。

P01 static [full3075封存映像](../../output/qa/p01_m27_full_namespace_static_20261012_root01/manifest.json) SHA `23631be6086a610c9b287ab866d83e496bc5629d3087a70dc72cd1c03b9d2e1c`；capture SHA `20863d4ff9d79f0b52b5cd2db6e03026304f997d676a8edcad5d203a1f91139e`。Root純PowerShell I/O逐exact logical比對原inventory `6d8e3e34…`：3070列用C2同SHA完整raw、四列M27原frozen overrides、一列auto_state_sync用原historical private mirror acda。完整3075來源已建立 `.t/pf8a305d/repo`，原517 layered rows／439 unique physical sources也精確映射至repo／overlay；總3106 physical files逐raw核對。Formal startup SQLite f608與actual overlay1280兩層不合併。沒有Python、import、compile、QA或profiling，沒有改現行Health或原始資料。新controls／AST核對／fresh origin／一次warm診斷仍pending，execution_ready／版本／完整Gate全部false，原M27三效能FAIL保持。
### Qt staged root02、ML r02 精確採入與原失敗案例回歸

Qt staged proposal SHA `9b0f1db8e184bd22aba8a28a83d0cd5e31afd2a1ac8f578c7622216efa6766e3` 後，Root另加 exact current module／loader／class／九函式及code的live-member檢查，完整19fields collector原件保存。Root control SHA `3a5770edfec8c4a973d6a05cbc6efd94478a55282691d0568bfc7a2fa91a4542`／payload SHA `a6a16a808eaaf262e4ec7f435971f4add3c0cbec98614a19c620be13db599d8f`；只在 initial strict PASS 後讀／compile外部payload。compile-only收據 `893124fed4dd55fb1bcf28cc0dbd4035ea9176f846494db2abc80fc2ebe0cd2a`／outer `3d3a713567de50c42b86d4661c07b414c9b9d7216dfcf4d901503c45010a16e6`，全child raw inverse與AST projection相等。Root實際child SHA `5b66bcac…` 比proposal `cf863800…` 僅多一個空行，完整diff保存且原guard12a46不變。首次錯傳controlSHA由wrapper在Job建立前拒絕，紀錄 `qt_staged_root02_preJob_wrong_sha.json` 保留，不作QA。

單次staged observation [9a81399b](../../output/qa/baldr_completion_20261011/root/qt_signature_staged_root02_observe_9444bff15d294312adc152cf4bf6c454/receipt.json)，SHA `9a81399b7f66317fb23d5bfb0097ca68e59c3eb6da2917fa5fc1f6b59434f4fb`，outer `64eebd39a20a4aaae6b9c90e7e87e9e2f4ca44f7fc065f2951c071feecf946ee`。初始九項仍完全等於Root01／歷史reference_before、全不符original policy；native126依約STOP。Child沒有讀／compile payload、fields或mypy未執行；atexit原guard再核相等，不能折抵STOP。此證據已排除「必須inline完整collector才出現九hash差異」的簡單解釋，尚不能認定具體reference/cache原因，不再原樣重跑。Types原FAIL不改。

ML第二版manifest [8df75b8b](../../output/qa/ml_candidate_long_path_candidate_20261012_root_resume_r02/manifest.json)，SHA `8df75b8b805e76c966868909f90146ae5730bf60ec259abb6b395d15d362ccdf`。Root full6 raw正逆／整AST逆投影、8來源compile及新QA driver compile，review收據 `f142e7cc66d1d38b5f3a16f7a6c42dd95d6429cdf9efbf683e02492b63cd7dd1`、outer `1e3f036306629fa91cd3e820f7f5d486a7f719ac8f5932b000a2f5129c093d84`。全部原assert、constants、金融/PIT、if／try／except、publication順序等AST保持；newhelper／test完整原件及270行prefix核對。

精確六來源＋helper／test已採入，完整before備份及intent在 [ML apply](../../output/qa/baldr_completion_20261011/root/ml_long_paths_apply_7321093dc2b247ea834ec6a6dab09f53/receipt.json)，SHA `e419e75c364d5018718d69ce33b035d369366109b9641f13d54affc98ed1a86c`／outer `cf4e309319be138f78f43f341b182fe6528cc111cfef3e4bd5b2613fdafb03d8`。Current formal mapping3085，其他3077列精確不變。新17個Health／ML formal product actual-origin原guardPASS，收據 `e1874b995ea256852d22b586b4b34e902949dc98e668c7633c34c7d39525de84`／outer `e22a2c8c5233c468dec242b69aa37d84e60c6c0ead18044733fedf300546fa46`。Root QA driver真path SHA `34e0f174868188c89ba787442e0a8f0be4032c63f3608349e3a02f22db396aa6`，沿原 child12a46／600秒、原私有basetemp長度與guard，非整包PYTHONPATH替代，不借舊Health版本信用。

新16案例 **14PASS／2FAIL／0SKIP／2.26秒**，收據 [85d27e19](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_new_tests_2d8f3eb610f14693ac2e30004a873f5d/receipt.json)，SHA `85d27e198eedb20df138e668bc49dd7ef5bba1356aa54157b0cfa7b9d8456b8a`／outer `c96d09f0ad6c0f92dad161e68180dc33c68e74ee5b55e29b265afb8085457463`。261 UTF16模型保存／readback／authority／default及same-buffer、hash篡改拒deserialize、customcanonical／拒verifiedcustom、lineage長hard-link與cleanup、pair mutation、same-run禁止重訓、公開frozen-relative及OS結果／例外／列舉反例通過。兩FAIL是real symlink建立在本機被WinError1314拒絕，沒有skip／mock／縮path／提高權限；因此長leaf／ancestor及短relative symlink no-follow尚未驗證，不能宣稱全組通過。已詢問有無既有可建立symlink的QA環境，仍繼續不受影響工作。

原同日恢復失敗case保持original body／日期2026-10-02／realTrainingService／live guards／私有根長度，現 **1PASS／0.92秒**，收據 [b897d5d4](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_focused_30668e18a536430eb00be0ccbf669bef/receipt.json)，SHA `b897d5d44f0355a730dcf4c9a18ff220ea958f06809566b2982da43f5ff879e5`／outer `677005a94d88bc9210e6569bf53f397d2d9e1f5cecb7d5916fd0ddaac9335644`。原103PASS／1FAIL收據保留，不以新單case外推整incremental組。十檔ML原回歸仍在1022／ecdba同Job，不能標PASS或啟下一Python。

上述完成Job均真正terminal／natural0／process及Job handlesclosed／mutexreleased，8GiB／12程序保持，沒有正式原始資料寫入、模型／Task啟用或交易。新版同版廣QA、two no-follow未驗、types、Health完整Main與完整產品Gate仍待。架構data_storage_runtime與ML shadow操作runbook已同步scope、canonical identity／custom／長dotdot限制；不授全域長root支援或來源／promotion資格。
### ML r03 暫存 leaf 修正與新版完整回歸

r02 原十檔159回歸收據 `75571377581c7cd5dca4d11a5e9ce04cc96353ec1a72eb0a23b2dfa964118faf` 保留 **143PASS／16FAIL**。精確分組為9項pipeline與7項lineage。Lineage實際parent241 UTF16加21字元temp leaf與separator形成263普通路徑；不是 frozen read 另有新漏洞。Pipeline source priority未改，QA private OUTPUT_ROOT優先於test自己的data_root/output造成fixture隔離污染。第一次adapter模組名不符且0calls，第二版exactfilename/SHA已15calls，收據 `490db2867b489a4a755ba5802908899a47c41a82c4d2cd18b19258abfe210bec`為33PASS／1FAIL；最後missing分支直接建fixture，需精確tmp_path context。

r03 candidate manifest `71af4a592c1e736097ef0efd0e3b8abab7b01d1fd6671fd3bab51ef8204413ac` 經Root三檔完整raw／AST逆投影審核 [8364e017](../../output/qa/baldr_completion_20261011/root/ml_temp_leaf_review_06e5f93588d347f98e0fc70c674191e1/receipt.json)。精確採入 [148161ab](../../output/qa/baldr_completion_20261011/root/ml_temp_leaf_apply_d11277863b9b4414a829f3e01dc59639/receipt.json)，完整3085 source map、3082其餘列不變；helper增加預設false的force_extended，僅原lineage mkstemp自有canonical parent明示true，原guard／hardlink／fsync／finally順序保持。原404行tests prefix完整保留並新增兩項實作回歸。

新版17產品origin收據 [66f7731c](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_origin_489646bc564e482cbccf7af5bfbab34b/receipt.json)，實際formal／source guard／pins乾淨。新18案例 [1e294c0a](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_new_tests_f9e91087791a45258ce8720bd8d9f2dd/receipt.json)為 **16PASS／2FAIL／0SKIP／2.333秒**；新增真parent241／temp263及forced短drive／UNC與strict negatives已PASS，兩個symlink case仍真WinError1314，未skip／mock／升權，no-follow尚未驗證。

新Root QA控制器SHA `529a863df72d549c14e98cb15331e16c610bf60fd366347e5cac4b7160529a8e`／adapter SHA `53907693bd4070d26433f34b827bcd0f89e72e22e5ea98906d7987dfcf296def` 保持產品與原test bytes，完整child正逆只加入真file/spec/SHA plugin載入與pytest plugins keyword，原source/write/network守衛predicates及600秒不變；整child bytes_equal如實false，沒有借舊12a46當實際child SHA。Adapter只在exact test source、兩個original fixture及具名missing case取自有source output，保留private QA_OUTPUT_ROOT及test自訂override，pytest monkeypatch自動restore。控制編譯收據 `f7824dbd94dcc0ac46a6d8c4e05edd9563b199296e0f400e02b75a2218bd5b72` 僅編譯，不授產品PASS。

新版完整十檔159回歸 [d258bcaf](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_ml_regression_4642420bdc2048899ee47e58a7234e25/receipt.json)為 **159PASS／0FAIL／0SKIP／90.615秒**；adapter16actual calls、實際來源與全部pins前後相等。outer `e22c174504ff9d34ad56f2899128682392bbf987756077c8fb778748271a1f38` native0、自然Job0、process／Job handles關閉、mutex釋放。原FAIL receipts保持不可覆寫。此組只授新版ML scoped QA，incremental／23callers／UI等新同版QA仍依序執行，Qt types／P01／symlink／完整工作包／完整Gate仍未接受。

P01 profile新靜態manifest `fd93bc6d0c1bcddcec58434b405e974d9cb276332f44da56e4f52cd39f666cdb` 已封存64payload。Root與static第二複核發現closedmodule map遺漏已封存ui_qt三個file modules與兩個實際namespace；尚未啟動origin或warm，需新exact file/namespace metadata封套。未改舊M27三p95FAIL或借今日Health／ML版本授歷史來源資格。

新版incremental七檔104案例收據 [1d64a5e3](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_incremental_13180df54ed34804a5e53954097482e3/receipt.json)為 **104PASS／0FAIL／0SKIP／80.700秒**，original child guard bytes12a46完整保持，actualformal／sourceguard／pins相等；outer `c08bf36d31da9d89030709fd39f64f8f7e8198d6edfecb7168eb547999a187aa` native0且自然歸零／handlesclosed／mutexreleased。原Health r03的103PASS／1FAIL仍保留，這份新3085同版完整incremental可解該組失敗，不能折抵Qt types／P01／symlink或完整Gate。

### 新版其餘必要 QA 與 Qt 保存 snapshot 診斷

以下均綁r03 apply148161與new3085 origin66f773，實際formal來源／原guard／pins乾淨；各outer Job自然PID0、process與Job handles關閉、mutex釋放後才啟下一組。不是將舊Health PASS折抵新版。

| 檢查 | 實際結果 | 新版receipt SHA |
|---|---|---|
| 原23callers | 329PASS／2SKIP／21.547秒 | fe224122e896eb94b9c9148485533aa8d5f381ee38ed979d07965e8a56ba11d4 |
| 必要UI workbench | 85PASS／2.448秒 | 5f6d60803be1b3a4d985296ce925b3f6605fc28572389f561f11a7c4c563ccce |
| governance | 51PASS／3.760秒 | 0cd00ca5983b5dadbb02e82acb53d142b3ef9ac7ace4dc40cafe79f7fad5616d |
| validator | native0，兩固定QA輸出完整before／after備份 | 129f4171a11ba529a2f6a77be63e232fec0b1d6e9245620ed285bd7f7b866f36 |
| 精確20檔syntax | native0 | 0520771a876ede22a4200773f13f7ca171a77723bb71957af856a5d52046fe8c |

Validator首次路徑少字由wrapper在Job前FileNotFound拒絕，無OWNED_QA_START／無validator執行；記錄ml_r03_validator_preJob_wrong_path_root01.json保存，核真formal_QA檔SHA後才執行。沒有盲重跑成功組或更新舊FAIL。

Qt離線靜態proposal `eec5dd41b10a43803bbf637010d41f443fc868b76182cf089cb9d1f460d9cbf3` 後，Root控制 `6f02af0e3d3bd1d64d8bdbda4dab10460eb9cb56368a677b0a6fb6c80f146289` 的完整canonical文字／AST及compile核對通過（outer8d481145…）。單次≤60秒stdlib-only保存raw診斷 [30682b1d](../../output/qa/baldr_completion_20261011/root/qt_saved_raw_offline_ea2f2dfcd34d4aa3b2fbba5bb0d9906e/receipt.json)：九raw共9657bytes、marshal.loads恰九次；3.11.9下全部19fields／nested constants／co_lines／co_positions完整等歷史1aa8baseline，九fieldhash均重算吻合、完整diff為零。兩方完整JSON SHA `f5550179dd9e8199d263c8e0f2806eb988797463bfc3dd3cb119ea53fc8d6317`；全部inputs/runtime pins前後相等，outer `627092570113676ebe7d15977aab8e2d20c631fff3dcae21f5ebc2e1b0a099da` native0、natural0／handlesclosed／mutexreleased。

此結果僅支持「已保存snapshot在指定decode runtime呈現的public fields相等」，沒有讀currentQt CodeType、import產品或執行decoded code、marshal.dumps新object、建立FunctionType、重跑mypy或更新accepted policy。marshal builtin file=None/spec_origin=built-in真實讀回；loads尾部API邊界於receipt明示。原initial STOP與typesFAIL保持；今日live member／code identity、privatecache／reference與mypy三hash因果均未證明。下一診斷只可依新機制假說做有界、單變量新scope，不原樣重跑957檔types。

### 新3085正常 Health Main、P01 r02 origin與權限邊界

Health Main新增Root控制保持原旅程／fresh／source guard與原期限：完整原Main九變換及AST逆回，Root globals綁真HERE；原3083Health來源只退ML已review六before、沿r03 apply精確3085，不借舊Main PASS。初版runtime917b956後origin [e2df4554](../../output/qa/baldr_completion_20261011/root/health_main_portable_origin_5d3a2296b8874ce69677acb9984f67e0/receipt.json)因ML map八列缺module欄位，sitecustomize KeyError即停，未載產品，native1／outer99，FAIL保持。Root僅六列沿parent原具名metadata、兩new source明示module补齊；3085path/SHA逐值不變，原guard predicates無修改。新runtime [0df6fd4a](../../output/qa/baldr_completion_20261011/root/health_ml_formal_Main_runtime_19e83380a1f54820b56b41b378eba743/receipt.json)，newMain真file SHA `e30640bf4189756603f6c3d1c72f40f7fc4beb727d7e42ffb443ac61f5c998a4`。

新Main origin6973407335191e35cf7cbe9f2d581a6be22b9d2d47920acc9e2d9549725f6bf3通過；正常Main回返及同Jobfresh [cd8d7d67](../../output/qa/baldr_completion_20261011/root/health_main_portable_suite_b12e59e127bc41cda561ec94f01e41a0/receipt.json)為 **1PASS／20.298秒**。兩個actual-origin PID、一个fresh owned-child receipt（fresh PID22776/parent22560）、native_taskworker_registry_drained等原旅程條件保留；source guard／full3085pins／mirror before-after乾淨。outer `a1d6651c10a4bdf9e27b9ab671c4544adaec1170ab4dc0ef0bc4ae05d53642fe` native0、天然Job0／handlesclosed／mutexreleased。只授Health同版Main旅程，不授P01千檔fullMain或原native crash根因。

P01 fd93第一版Root datareview98f51b841218f75ec55163865eaf8570989d181aadfe42ca2f269d770f4316b0核11fullraw正逆／6protected完整AST／matrix10行全文和AST投影／nestedrecord oracle，全pins保持，但declared-only map欠已封存UI來源與namespace，未授release。新r02 manifest `c07f464d7a72b20f59007ed531a7b93ac280561698dbb63e591c0aca9d7d4655` 96payload／16raw封存：403file只合併原declared/startup/loaded的433具名行，同module完整identity一致；僅models/views/workers三個明示namespace，None file／spec.origin、真NamespaceLoader／specloaderidentity／唯一路徑／已pin ui_qt parent／無initializer等拒絕條件保持，未知fileless不忽略。

Root r02 data審核初次outer3f86a0b0216e26f1873f6dccd8ee2d9af82463582ce6dafeb8da402ab9991554止於m20 manifest新403／3 metadata key，未授runtime；明示窄key投影后新 [52ceb513](../../output/qa/baldr_completion_20261011/root/p01_warm_profile_r02_review_7917fdf88c0541819650f8c8f9b76dba/receipt.json)核16raw正逆、10完整ModuleAST、七歷史表、八protected函式全文、profiler全raw不變與33資料差異，只有精確路徑／控制SHA／size及403／3 metadata，PIT／N／600／timer原式保持。Root完整讀197行新helper、driver/profiler/fresh與33data差異。真HERE loader7e28356d1c76e1a235167e08304c58b4ed61a4ec6ddba748eb55bc74009d1979編譯、新release819c4e2381b5c9478b875922a321f42d00b335d1c88651addea2cb3bc142979f封存，native binding仍false。

首次新origin [d105956a](../../output/qa/baldr_completion_20261011/root/p01_profile_origin_34c0efa0200648c3acced414a290e43d/receipt.json) **native1**，context736999bytes低於原1MiB；原supervisor pre/post guard同停212 `candidate_query_overlay_manifest_pin_mismatch:formal_parent_initializer`，query_origin_probe=null，未probe/fresh/warm。實際physical在pf8a305d/repo，原metadata是logical app_module/__init__.py，guard以workspace-relative錯算；其他八metadata path/SHA相等。outer `cc579bb23b3bae6806a32aa0edc4f3b54b5e7bdc8cc04924ad1fa9f27576114b` natural0／handlesclosed／mutexreleased。Root要求靜態全面核後續同型logical/physical接點再做r03封套，不改metadata歷史七表、不弱化比較／更新expected、不盲重跑。warm onceintent尚未建立；原三p95FAIL保持。

使用者更正沒有另一個QA主機／工作目錄。本機只讀TOKEN_QUERY [1f1be957](../../output/qa/baldr_completion_20261011/root/owned_symlink_token_query_2747b0536ca54bf7ac2f93af4a074226/receipt.json)確認目前QA token無SeCreateSymbolicLinkPrivilege、elevationtype3，token handle已關，沒有調權、OS／帳戶設定變更或symlink測試。兩項真WinError1314原FAIL保持。已備只跑原兩個完整no-follow test nodes的QA控制cf65171372bcf2950ebec545ce6ab267f627d48336698702e2103a5b681fffc2（原child12a46／guard全文保持）、compile-only18083db3d922989cc8f50e12d01677481cc258a8a728ee32961b26f49dde8fc9；UAC launcher02 SHA6158fa1cd0dc2171e1bf27d2dc36750bf562b3c4fcfdcbe39ead45cd5d83c659有lastClosed檢查、精確source pins、唯一attempt、8GiB／12程序／600、hidden helper及process handle Dispose，PS語法PASS，尚未執行，等人類明示批准及Windows UAC回應。不改registry／Developer Mode或永久權限設定。

Qt下一機制靜態proposal `8b7cfdf2f32493bdaad0af9cda4cc1dd5c887e0f5e35cc633df044e301fb33f0` 已封存兩個互斥設計，Root尚未建controller或執行。原三phase混入read／compile／bind／getter／retained tree／identity持有，不能冒稱單變量；新的有界scope必分介入並保留所有strictFalse／最終126，不自动雙跑、不更新expected／accepted policy。原typesFAIL、decoded保存snapshot9fields相等的資料界線與完整Gate false保持。

### 原兩項 no-follow：一次明示 UAC 驗證

使用者明確授權「允許一次兩項 QA 的 UAC 提權」。Root依已封存launcher02執行一次，只有原兩個完整test nodes，沒有改registry／Developer Mode／帳戶永久權限。原18案例16PASS／2FAIL收據保持，沒有重跑其餘16案例或改原assert／source/write/network guards。

新收據 [273203c2](../../output/qa/baldr_completion_20261011/root/ml_long_paths_QA_new_tests_4b3601448e8f42e793372c739df7eb71/receipt.json)，完整SHA `273203c21bb35abe8878c7c3b99268eabb3ad5542a2ec6e86b9fe8ace83c155a`：**2PASS／0FAIL／0SKIP／0.770秒**，長leaf／ancestor及短relative真symlink no-follow皆完成。Current apply148161／origin66f773、actual formal／原child12a46與所有pins保持。這是兩項另組驗證，不把原18案例FAIL改寫為單組18PASS。

Outer [968c0351](../../output/qa/baldr_completion_20261011/root/single_owned_qa_fd73cbf4b11a4095846493e71762d474/receipt.json)，完整SHA `968c03511de561392b88dda86992c95744f2d42f2e31bea06870f55101025da6`：native0、remaining／final PID均0、process／Job handlesclosed／mutexreleased。UAC PID53984自然exit0，其launcher process handle亦Dispose關閉；once intent及launch result保留，沒有自動第二次提權。P01、Qt types及完整Gate仍未接受，下一組Python須沿此真正收尾點。

### P01 r03 origin 新失敗與 Qt 窄 compile-lifetime 診斷

P01 r03 manifest `82f6cedd0ad2234dba26f5e0881f6d8c581877b3d1e69a45890ead2f7267726f` 58payload由Root核20完整raw正逆、13完整AST、12control compile、七張歷史table／403file＋3namespace／八個protected函式全文及profiler不變。首次Root04審核誤把sidecar當bare SHA，outer `eead83004ac20b12fcd880736f2cd5ae604d1dc873b6821f35ffbbe778938187` FAIL保留；Root05以實際「SHA＋兩空白＋檔名」精確語法核後，[d01e9b99](../../output/qa/baldr_completion_20261011/root/p01_warm_profile_r03_review_9a260427e3a445748bc1ac8efc511936/receipt.json)通過，26項完整data差異由Root閱讀，只有control path／SHA／size，不變更原PIT／600／N1000／20頁／90 DTO oracle。新真HERE loader02 `db16c2fbfd76b0642cef3d6f29a0772e8f57e2814a491369135fa20f5a1ab849` compile／完整template文字及AST inverse通過，release [a02d6e49](../../output/qa/baldr_completion_20261011/root/p01_single_warm_profile_r03_release_e7ef42ef815a4dd8beee0a417a9c8e38/release.json)，native binding仍false。

新origin [9fccb064](../../output/qa/baldr_completion_20261011/root/p01_profile_origin_cc362d35ccf84df88994f1628457f83c/receipt.json)仍 **native1／FAIL**。原前後九overlay pins已通過；primary probe完成，fresh子程序runner85被bridge225的原 `p01_qa_formal_parent_package_origin_mismatch`拒絕。實際fresh role receipt SHA `733989e10a6d713df48191efc718d6df77291739b9171e3af934a7f628164cac`明示cwd為workspace、`-s -c`→runpy；stderr SHA `e7bd4dfb9db3541fee1349523dccc318ab58beb4056f7df50a02ccc777b66236`。fresh stdout空，沒有保存fresh實際parent file／path／sys.path，不能冒稱已直接觀測其來源。靜態追查指出cwd空entry可能先選workspace parent；新r04只候選修fresh launch cwd及truthful child_cwd metadata，其他workspace result/event路徑不能泛化改frozen。沒有warm intent或p95新證據。outer `00a5c0c6943322479d7e709b3219e1b4599eaa0c417d2c42cb49fa3b3686682b`自然0／handlesclosed／mutexreleased；fresh inner 5秒自然排空，beforecleanup／aftercleanup均0、無cleanup errors、沒有timeout。

Qt proposal8b7選互斥較窄A，另建Root-only observer `47a4df3bb9841350a72a3eddb4d2bf77e4fae951d64e8e4710f60c22d1d01ad0`；原normal child12a46／policyfe854／原helper0444完整保持，未移除product loop或修改原types控制。Control-only [98aaa1f2](../../output/qa/baldr_completion_20261011/root/qt_compile_lifetime_control_5c5723f33dcd4d09a4946934d2db1e8f/receipt.json)先核原helper全文／AST和新控制compile，沒有Qt／product import。

單次≤60秒新scope [b36984cb](../../output/qa/baldr_completion_20261011/root/qt_compile_lifetime_a8ad7c5316fa4ac2823ffd655c0783ec/receipt.json)，完整SHA `b36984cb99aebf1bd723d9d00af36c11cbb51191e431c509a9e567b896aaef31`：stable-held baseline→read1474bytes→compile once held→release compiled unit/helper frame四階段，九livefunction／code、bootstrap module／loader／importer class、26virtual aliases、13ZIP raw members及七native pins始終一致；兩個獨立dump途徑每份hash亦相等。四階段九份raw沒有任何變化，四個original strict結果皆false，終態 **126**保留。只支持指定holding制度下未觀察到compile／release造成raw變化；沒有getter、canonical exec、fullfieldpolicy parse、product import、mypy、policy更新或根因結論。此封套unique intent保留，不自動雙跑B或重跑A。outer `5179fb07517860b4a61f8170eb8f32510043ed66542b73deb52a1260d1f11ba6`自然0／handlesclosed／mutexreleased，無forced cleanup。原typesFAIL及完整Gate未接受。

### P01 r04 新 origin／native binding 通過，唯一 warm 進行中

新r04 manifest `e6f9091a69e3acfcf7782cd255ab6604d83de9c349deec0925959c2623dfb6ea`完整72payload／20raw／13AST／12compile／15protected切片／26資料差異與七表／403file＋3namespace由Root重驗通過，[8551be23](../../output/qa/baldr_completion_20261011/root/p01_warm_profile_r04_review_a638022fbf05487a8555a6093561c8c8/receipt.json)。唯一語義改動是fresh launch cwd及truthful child_cwd；所有原命令／flags／環境／來源守衛／600秒／N1000／20頁／90 DTO原貌保持。新的true HERE loader03 `5a25569aeeed1e42a6407f8c7e718fd6d1645f50a481288fdb359b912444213c` compile／完整template inverse通過，新的origin release [04657c96](../../output/qa/baldr_completion_20261011/root/p01_single_warm_profile_r04_release_cfbe33158e1b4431801a437d84130650/release.json)保留native binding false。

新origin [1c03a325](../../output/qa/baldr_completion_20261011/root/p01_profile_origin_a09d258e847f48f5aa91528d1919ec62/receipt.json)，完整SHA `1c03a325cc0397d1382d314ab816e9b3497021111261bf1cac4441f406da0f31`，native0／原前後來源守衛通過／pins不變。primary actualPID57068、fresh actualPID11740各有三個完整import events，明示parent都來自凍結pf8a305d；fresh role／stderr／完整stdout與result皆核對，原600秒、inner自然排空、同outer named Job-before-code attestation維持。outer `634f902887284f30bf6f1f47776fcabddb2065e831b1e7f7c5b18d45976be342`自然0／handlesclosed／mutexreleased。

Root另以data-only控制 `af0c2cf7db253bb4d79ace81b5517aa30fde51dc9a372906396d824d70f40d09`完整核fresh result SHA `72abed2dc37f5a7a7cc2585defce5bb8ab3a499a682b3f518b50342ce9b33b69`、51個file與3namespace、所有helpers／兩組三events／actual native provenance。cProfile／profile／pstats為真Program Files標準庫來源及SourceFileLoader，`_lsprof`／time／marshal實際file=None、spec_origin=built-in、listed_builtin=true；配合精確CPythonDLL／exe與stdlib pins，不以缺pyd猜builtin。新 [52b30862](../../output/qa/baldr_completion_20261011/root/p01_r04_native_binding_release_93d9a608710f42268813f4bab26b3e3c/release.json)才記Root nativebinding reviewed=true；原payload和04657的false保持不可覆写。這份data-only Job outer `fc5910759774c29038ac8d455d9dd6b2ea76308a41afe518db8cef2387267e33`也已natural0／handles／mutexclosed。

沿新release與origin，Root已啟動該e6f9封套唯一warm，same exec session74466／outer directory single_owned_qa_033e1dee21f04402aafe551e7ab0cf74。原atomic x intent保持，尚無完成／p95／profile接受；不能開下一Python或重啟warm。這是原M27凍結來源的診斷，沒有借今日3085Health／ML資格、沒有另跑五cold矩陣；原M27三p95FAIL／完整Main／產品Gate仍保持。

Qt新純靜態資料封套 `d1e53ad94cbebad5c5ee40dfc162ff0a523f75de4c9554272e80f50485e05ea6`保存83payload／45原有raw／36逐byte比較：QtA四階段全部raw等Root01，零差位。原types／最早expected／歷史after目前只有hash沒有raw，不能定位token差異；也缺該次actual mypy main/build loader來源（本機py與pyd並存），不能由py文字推定走了該實作。建包PS Measure-Object失敗及partial保留，新metadata-only continuation才封存；沒有Python／新runtime／B封套或policy更新，types／Gate依然未接受。

### 使用者要求暫停與 commit：停點

使用者明確要求「先停下來然後紀錄好我們的進度並commit」。補完 goal 已設 **paused**，兩位靜態subagent均completed；最後exec74466已terminal，沒有active QA、待輪詢session或背景writer。沒有再啟動Python、profile分析、模型／Task、正式資料寫入或新的補完驗證。此節是恢復入口，前節「warm進行中」為該時點歷史狀態。

唯一warm新完整收據 [5e4b9396](../../output/qa/baldr_completion_20261011/root/p01_profile_warm_fc83cc390b324149843dc6fb7d3f37a0/receipt.json)，完整SHA `5e4b93960385b4831bfb8e810d9b6286b42b870f1f4e4108cf70cc5d0e9e2323`：native0、pins前後保持，三類各30份共90份取樣，原role終態 `completed_profiled_diagnostic_not_gate_evidence`。原source/store及module穩定、postguard／finalization通過、observer restore／shutdown failures為空。90份profile metadata與binary已產出；這是原driver收據所支持的狀態，Root尚未逐一獨立核全部DTO壓縮原件／profile SHA／三domain完整性，也尚未執行pstats熱點分析。

- outer [e5b30c1d](../../output/qa/baldr_completion_20261011/root/single_owned_qa_033e1dee21f04402aafe551e7ab0cf74/receipt.json)，完整SHA `e5b30c1d5472982b306af70b7ea4f992ace2ed4ae0805fb6ff9f83847c74aeec`：native0、remaining／final PIDs均0、process／Job handlesclosed、mutexreleased、forced_cleanup=false。全程8GiB／12程序及原每角色600秒保持。
- 原role完整result：`output/qa/p01_m27_single_warm_profile_candidate_20261012_root_resume_r04/m20/runs/m_5fbf4cbb0831/roles/warm_01/result.json`，SHA `1ea0f79f753370ea0d50881f54bc5c01062afbc8fd1f3968605a91bd1f27eff3`；原owned role receipt SHA `f443e0c927887bc9a73ef07284602742373b79ef60d9bf79c571b018da1fe74c`。Profile metadata明示cProfile為elapsed wall、不是function CPU；thread CPU另列，不得把wall−CPU當disk wait，也沒有deferred Qt paint completion證據。
- r04 unique warm intent已建立，**禁止重跑相同e6f9封套的warm**。原M27無profile的三p95FAIL保持，新診斷耗時不授效能／完整P01／Main或產品Gate接受。凍結3075歷史來源不借今日3085Health／ML資格。

本次可提交範圍是Health精確來源／保存選取與回訪面板、ML canonical長路徑／lineage暫存leaf修補及其測試與必要十一份文件。既有新版ML159、incremental104、callers329PASS／2SKIP、UI85、governance51、validator、syntax20、Health正常／freshMain1PASS，以及另組原兩no-follow UAC2PASS之收據全部保留；不把這些局部結果加成完整Gate。Qt types原957檔mypy本體native0但來源守衛FAIL保持；最新3085的完整types接受尚未取得。P01完整Main原生崩潰根因、P08最新版完整包、真來源、同版EXE與真人G0–G4等原完整計畫仍待。

恢復後先核本task owner／HEAD／dirty與lastClosed e5b3及各source／receipt pins，再逐一核90個profile metadata、壓縮DTO oracle與binary stats；沿三domain及實際artifact groups分析counts／self及cumulative elapsed／thread CPU，**不新增同封套warm**。之後再依原交接處理P01效能與Main、Qt types來源／raw缺口、P08與完整補完計畫。QtA四phase原strict126及資料包d1e53保持，不自動執行B或重跑A，不改accepted policy／expected hashes／原守衛。

本機 `output/`、`.t/`、`C:/t/`、task JSON、封套／收據／binary profiles依Git排除規則保留在原處，不提交或刪除；本頁記載其精確路徑與SHA，commit只保存程式／測試與可追溯摘要。另有AGENTS、skills、git_exclusions及目標架構的其他聊天dirty，維持原貌，不納入本任務commit。舊singleton active_task／handoff_log／resume prompt不覆寫。
