"""台股 L2 產業鏈與題材萃取、對應與分配獨立模組 (Industry & Theme Extraction and Mapping).

本模組為完全獨立之 Python 檔案 (`decision_module/industry_theme_map.py`)，
目前**不介入**現有系統之每日選股、回測或 UI 流程，僅透過 `data_module.config.TWStockConfig`
讀取既有設定與 `<DATA_ROOT>/meta_data/companies.csv` 位置，專門負責：

1. **萃取產業鏈與 L2 題材 (Extraction)**：
   - 官方櫃買中心／證交所「產業價值鏈資訊平台 (`ic.tpex.org.tw`)」HTML 解析與可選抓取
   - 內建台股 25 條標準產業鏈 (`STANDARD_25_CHAINS`) 與 80+ 個核心 L2 題材種子庫 (`CURATED_THEME_BASKETS`)
   - 全域同義詞與別名歸一化字典 (`SYNONYM_MERGE_RULES`)
   - 關鍵字輔助辨識規則 (`THEME_KEYWORD_RULES`) 與證交所/櫃買 L1 產業分類保底規則 (`L1_CATEGORY_TO_DEFAULT_THEME`)

2. **對應與分配方法 (Mapping & Assignment Pipeline)**：
   - 依四階優先序 (`P1_OFFICIAL_IC_TPEX` -> `P2_CURATED_CHAIN_TAXONOMY` -> `P3_KEYWORD_EXTRACTION` -> `P4_L1_CATEGORY_FALLBACK`)
     將上市櫃 4 碼普通股分配至對應之「25 大產業鏈 × 上中下游階層 × L2 題材」。
   - 支援「一檔股票對應多個題材標籤」（並以 `is_primary` 標註主題材）。
   - 執行全域同義詞合併、`(stock_id, chain_name, theme_name)` 去重、以及少於 `min_companies`（預設 3 家）之長尾題材過濾。

3. **產出三大核心檔案 (Output Artifacts)**：
   - **產業檔案 (`industry_chains_catalog.csv`)**：25 條標準產業鏈、上中下游定義、對應官方代碼與統計家數。
   - **題材檔案 (`industry_themes_catalog.csv`)**：所有有效 L2 題材、所屬產業鏈、合併同義詞、萃取來源與代表股。
   - **產業題材股票對應檔案 (`industry_theme_stock_map.csv`)**：股票 × 產業鏈 × 題材完整對應明細與分配依據，
     並同步留存季度快照 (`industry_chain_snapshots/`) 與 `manifest.json`。

設計文檔與使用指南請見：`docs/02_features/INDUSTRY_THEME_MAP_DESIGN.md`。
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data_module.config import TWStockConfig

SCHEMA_VERSION = "v1"

# 四階分配與萃取方法常數
METHOD_P1_OFFICIAL_IC = "P1_OFFICIAL_IC_TPEX"
METHOD_P2_CURATED_TAXONOMY = "P2_CURATED_CHAIN_TAXONOMY"
METHOD_P3_KEYWORD_RULE = "P3_KEYWORD_EXTRACTION"
METHOD_P4_L1_FALLBACK = "P4_L1_CATEGORY_FALLBACK"


# ---------------------------------------------------------------------------
# 1. 產業檔案定義：25 條標準產業鏈 (`STANDARD_25_CHAIN_SPECS`)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndustryChainSpec:
    """25 條標準產業鏈之結構化定義（用於生成產業檔案 `industry_chains_catalog.csv`）。"""

    chain_id: str
    chain_order: int
    chain_name: str
    official_ic_codes: Tuple[str, ...]
    mapped_l1_categories: Tuple[str, ...]
    default_theme_name: str
    default_chain_tier: str
    upstream_summary: str
    midstream_summary: str
    downstream_summary: str


STANDARD_25_CHAIN_SPECS: Tuple[IndustryChainSpec, ...] = (
    IndustryChainSpec(
        chain_id="CHAIN_01",
        chain_order=1,
        chain_name="半導體",
        official_ic_codes=("D000",),
        mapped_l1_categories=("半導體業", "半導體"),
        default_theme_name="IC設計",
        default_chain_tier="上游",
        upstream_summary="矽智財IP/ASIC、EDA、IC設計、光罩、矽晶圓與半導體特用化學材料",
        midstream_summary="晶圓代工(先進與成熟製程)、記憶體製造、半導體前段製程設備",
        downstream_summary="先進封裝(CoWoS/3DIC)、IC封裝測試、測試介面與探針卡、IC通路",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_02",
        chain_order=2,
        chain_name="電子零組件",
        official_ic_codes=("L000", "J000", "K000"),
        mapped_l1_categories=("電子零組件業", "電子零組件", "其他電子業", "電子通路業"),
        default_theme_name="PCB印刷電路板",
        default_chain_tier="中游",
        upstream_summary="玻纖布/玻纖紗、銅箔、銅箔基板CCL、被動元件陶瓷粉末與電阻材料",
        midstream_summary="PCB印刷電路板、ABF/BT載板、散熱模組、被動元件(MLCC/電感/電阻)、連接器/線束、電源供應器/BBU",
        downstream_summary="電子製造服務EMS、系統組裝與電子零組件通路代理",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_03",
        chain_order=3,
        chain_name="電腦及週邊",
        official_ic_codes=("F000", "5300"),
        mapped_l1_categories=("電腦及週邊設備業", "電腦及週邊"),
        default_theme_name="伺服器",
        default_chain_tier="下游",
        upstream_summary="伺服器機殼、滑軌、主機板與周邊控制晶片",
        midstream_summary="伺服器準系統、工業電腦IPC、儲存設備與電競周邊",
        downstream_summary="AI伺服器整機代工、通用伺服器、筆電/代工與品牌電腦",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_04",
        chain_order=4,
        chain_name="通訊網路",
        official_ic_codes=("I000", "4100"),
        mapped_l1_categories=("通信網路業", "通訊網路"),
        default_theme_name="網通設備",
        default_chain_tier="中游",
        upstream_summary="光通訊/CPO晶片、磊晶、光纖主動與被動元件",
        midstream_summary="光纖元件/模組、交換器、路由器、5G基地台與低軌衛星地面設備",
        downstream_summary="電信營運商、IDC機房/數據中心與網路系統整合",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_05",
        chain_order=5,
        chain_name="光電",
        official_ic_codes=("G000", "G300", "G400"),
        mapped_l1_categories=("光電業", "光電"),
        default_theme_name="面板/顯示器",
        default_chain_tier="中游",
        upstream_summary="光學玻璃/塑膠鏡片毛坯、LED磊晶、偏光片、背光模組材料",
        midstream_summary="光學鏡頭、面板/顯示器、miniLED/microLED、LED封裝/照明",
        downstream_summary="車載顯示模組、電子紙應用、感測與光學檢測系統",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_06",
        chain_order=6,
        chain_name="機械設備",
        official_ic_codes=("E000", "6000"),
        mapped_l1_categories=("電機機械",),
        default_theme_name="工具機",
        default_chain_tier="中游",
        upstream_summary="粉末冶金、精密齒輪、滾珠螺桿、線性滑軌、諧波減速機與控制器",
        midstream_summary="工具機、機器人/自動化設備、流體與氣動元件",
        downstream_summary="智慧工廠產線整合、半導體與PCB製程自動化整廠輸出",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_07",
        chain_order=7,
        chain_name="電動車",
        official_ic_codes=("A300",),
        mapped_l1_categories=("汽車工業",),
        default_theme_name="車用電子",
        default_chain_tier="中游",
        upstream_summary="動力電池正負極材料、車用功率半導體、車體沖壓與傳動零件",
        midstream_summary="車用電子、BMS電池管理系統、胎壓偵測TPMS、車燈與ADAS感測",
        downstream_summary="整車製造與代理、充電樁營運與電動巴士",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_08",
        chain_order=8,
        chain_name="綠能環保",
        official_ic_codes=("H100", "H200", "H400", "H500"),
        mapped_l1_categories=("綠能環保",),
        default_theme_name="水資源/環保",
        default_chain_tier="中游",
        upstream_summary="多晶矽、太陽能矽晶圓、風電鑄件、氫能燃料電池材料",
        midstream_summary="太陽能電池與模組、儲能系統、風力發電水下基礎與變流器",
        downstream_summary="再生能源電廠EPC、綠電交易、水資源處理與廢棄物循環經濟",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_09",
        chain_order=9,
        chain_name="生技醫療",
        official_ic_codes=("C100", "C200"),
        mapped_l1_categories=("生技醫療業", "生技醫療"),
        default_theme_name="新藥研發",
        default_chain_tier="上游",
        upstream_summary="原料藥API、新藥研發、細胞治療與基因檢測技術",
        midstream_summary="疫苗/生物製劑、學名藥/製劑、CDMO委託研發代工、高階醫材製造",
        downstream_summary="連鎖藥局通路、醫美保健食品、洗腎與醫療照護服務",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_10",
        chain_order=10,
        chain_name="民生消費",
        official_ic_codes=(),
        mapped_l1_categories=("食品工業", "貿易百貨", "觀光餐旅", "居家生活", "運動休閒", "農業科技"),
        default_theme_name="黃豆玉米小麥(大宗物資)",
        default_chain_tier="中游",
        upstream_summary="黃豆玉米小麥(大宗物資)、農業科技/生技飼料、食品原料與油脂",
        midstream_summary="綜合食品加工、飲料乳品、健身器材/自行車、居家衛浴廚具製造",
        downstream_summary="超商/超市、百貨零售通路、電商平台、餐飲與連鎖飯店旅遊",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_11",
        chain_order=11,
        chain_name="金融",
        official_ic_codes=("2800",),
        mapped_l1_categories=("金融保險", "金融業"),
        default_theme_name="銀行",
        default_chain_tier="整合",
        upstream_summary="資本市場、央行貨幣政策與同業拆款市場",
        midstream_summary="金控、商業銀行、壽險與產險、證券期貨與票券",
        downstream_summary="企業企金放款、消金財富管理、投信基金與租賃融資",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_12",
        chain_order=12,
        chain_name="塑膠化工",
        official_ic_codes=("1300", "1710"),
        mapped_l1_categories=("塑膠工業", "化學生技醫療", "化學工業"),
        default_theme_name="塑膠原料",
        default_chain_tier="上游",
        upstream_summary="輕油裂解、石化基本原料(乙烯/丙烯/純對苯二甲酸)",
        midstream_summary="五大泛用塑膠原料(PVC/PE/PP/ABS)、電子級特用化學、塗料與樹脂",
        downstream_summary="塑膠加工製品、工業膠帶、農用與民生化學品",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_13",
        chain_order=13,
        chain_name="鋼鐵金屬",
        official_ic_codes=("2000",),
        mapped_l1_categories=("鋼鐵工業",),
        default_theme_name="鋼鐵",
        default_chain_tier="中游",
        upstream_summary="鐵礦砂、廢鋼、高爐煉鋼、電爐煉鋼與鎳鉻合金原料",
        midstream_summary="熱軋/冷軋碳鋼、不鏽鋼、型鋼、盤元線材與鍍鋅鋼板",
        downstream_summary="金屬製品/五金、螺絲螺帽扣件、鋼構工程與航太特殊鋼",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_14",
        chain_order=14,
        chain_name="營建資產",
        official_ic_codes=("2500",),
        mapped_l1_categories=("建材營造", "營建業"),
        default_theme_name="建設/開發",
        default_chain_tier="中游",
        upstream_summary="土地資產開發、建築設計與基礎建材供應",
        midstream_summary="住宅與商辦建設/開發、公共工程/統包、高科技廠房無塵室機電工程",
        downstream_summary="資產開發/包租、商用不動產經營、代銷與物業管理",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_15",
        chain_order=15,
        chain_name="航運運輸",
        official_ic_codes=("2600",),
        mapped_l1_categories=("航運業",),
        default_theme_name="貨櫃航運",
        default_chain_tier="中游",
        upstream_summary="造船、貨櫃製造、船舶租賃與航空器維修",
        midstream_summary="貨櫃航運、散裝航運、航空客貨運",
        downstream_summary="空運物流、海運承攬、港埠貨櫃集散站與倉儲車隊",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_16",
        chain_order=16,
        chain_name="紡織成衣",
        official_ic_codes=("1400",),
        mapped_l1_categories=("紡織纖維",),
        default_theme_name="紡織纖維(化纖/聚酯)",
        default_chain_tier="上游",
        upstream_summary="CPL、EG、聚酯粒、尼龍粒與紡織纖維(化纖/聚酯)",
        midstream_summary="紡紗、織布、機能布料染整與鞋材加工",
        downstream_summary="成衣代工、運動品牌製鞋與服飾通路",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_17",
        chain_order=17,
        chain_name="軟體服務",
        official_ic_codes=("3100", "5400", "5500"),
        mapped_l1_categories=("資訊服務業", "數位雲端"),
        default_theme_name="系統整合SI",
        default_chain_tier="下游",
        upstream_summary="雲端IaaS基礎架構、AI算力平台與資安底層技術",
        midstream_summary="企業SaaS軟體、資安/雲端軟體、ERP與資料庫代理",
        downstream_summary="系統整合SI、金融與政府大型IT專案維運、第三方支付與數位平台",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_18",
        chain_order=18,
        chain_name="公用事業",
        official_ic_codes=("2300",),
        mapped_l1_categories=("油電燃氣業",),
        default_theme_name="電力/汽電共生",
        default_chain_tier="中游",
        upstream_summary="原油與天然氣進口、煉油石化裂解",
        midstream_summary="獨立民營電廠IPP、電力/汽電共生",
        downstream_summary="區域天然氣瓦斯供應、加油站營運",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_19",
        chain_order=19,
        chain_name="國防航太",
        official_ic_codes=("4000",),
        mapped_l1_categories=(),
        default_theme_name="航太零組件",
        default_chain_tier="中游",
        upstream_summary="航太級複合材料、鈦合金鍛造與軍規感測晶片",
        midstream_summary="航太引擎機匣與起落架零組件、無人機飛控與機體、軍用造船",
        downstream_summary="軍工航太整機組裝、高教機/無人機系統整合與民航機維修",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_20",
        chain_order=20,
        chain_name="水泥建材",
        official_ic_codes=("1100", "1800"),
        mapped_l1_categories=("水泥工業", "水泥類", "玻璃陶瓷"),
        default_theme_name="水泥",
        default_chain_tier="上游",
        upstream_summary="石灰石礦山開採、水泥熟料鍛燒、矽砂原料",
        midstream_summary="水泥、預拌混凝土、爐石粉、平板玻璃與衛浴陶瓷",
        downstream_summary="基礎建設工程、防火建材與低碳綠建材應用",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_21",
        chain_order=21,
        chain_name="控股",
        official_ic_codes=(),
        mapped_l1_categories=("其他", "其他業", "存託憑證"),
        default_theme_name="控股/集團",
        default_chain_tier="整合",
        upstream_summary="跨產業集團母公司資本配置與轉投資孵化",
        midstream_summary="產業控股、綜合集團事業體與跨國營運平台",
        downstream_summary="多元綜合服務、環保工程與特許經營業務",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_22",
        chain_order=22,
        chain_name="電器電纜",
        official_ic_codes=("1600",),
        mapped_l1_categories=("電器電纜",),
        default_theme_name="重電/電線電纜",
        default_chain_tier="中游",
        upstream_summary="電解銅、裸銅線、不鏽鋼盤元與絕緣材料",
        midstream_summary="超高壓電力電纜、通信電纜、重電變壓器與GIS氣體絕緣開關",
        downstream_summary="台電強韌電網工程、美國電網基礎建設外銷與智慧家電製品",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_23",
        chain_order=23,
        chain_name="造紙包材",
        official_ic_codes=("1900",),
        mapped_l1_categories=("造紙工業",),
        default_theme_name="造紙/紙器",
        default_chain_tier="中游",
        upstream_summary="林木造林、長短纖紙漿與回收廢紙",
        midstream_summary="工業用紙(牛皮紙箱原紙)、文化用紙與家庭生活用紙",
        downstream_summary="瓦楞紙箱紙器包裝、物流包材與特殊標籤紙",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_24",
        chain_order=24,
        chain_name="橡膠輪胎",
        official_ic_codes=("2100",),
        mapped_l1_categories=("橡膠工業",),
        default_theme_name="橡膠/輪胎",
        default_chain_tier="中游",
        upstream_summary="天然橡膠、合成橡膠(SBR/BR)、碳黑與橡膠助劑",
        midstream_summary="汽車與自行車輪胎製造、醫療乳膠手套與工業輸送帶",
        downstream_summary="車廠OEM配胎、售後替換胎(AM)通路與運動鞋底材料",
    ),
    IndustryChainSpec(
        chain_id="CHAIN_25",
        chain_order=25,
        chain_name="文創育樂",
        official_ic_codes=("3200",),
        mapped_l1_categories=("文化創意業",),
        default_theme_name="文創/影視展演",
        default_chain_tier="下游",
        upstream_summary="原創IP授權、音樂詞曲版權、劇本與遊戲美術研發",
        midstream_summary="影視內容製作、演唱會展演策劃、圖書出版與數位媒體",
        downstream_summary="院線通路、售票平台、文創商場與周邊授權商品",
    ),
)

STANDARD_25_CHAINS: Tuple[str, ...] = tuple(
    spec.chain_name for spec in STANDARD_25_CHAIN_SPECS
)

# 官方 ic.tpex.org.tw 代碼 -> (標準 25 產業鏈, 預設 L2 題材)
OFFICIAL_IC_CHAIN_MAP: Dict[str, Tuple[str, str]] = {
    "D000": ("半導體", "IC設計"),
    "L000": ("電子零組件", "PCB印刷電路板"),
    "J000": ("電子零組件", "被動元件(MLCC/電感)"),
    "K000": ("電子零組件", "連接器/線束"),
    "F000": ("電腦及週邊", "伺服器"),
    "I000": ("通訊網路", "網通設備"),
    "G000": ("光電", "面板/顯示器"),
    "G300": ("光電", "LED封裝/照明"),
    "G400": ("光電", "光學鏡頭"),
    "E000": ("機械設備", "工具機"),
    "6000": ("機械設備", "機器人/自動化"),
    "A300": ("電動車", "車用電子"),
    "H100": ("綠能環保", "太陽能"),
    "H200": ("綠能環保", "風力發電"),
    "H400": ("綠能環保", "儲能"),
    "H500": ("綠能環保", "水資源/環保"),
    "C100": ("生技醫療", "新藥研發"),
    "C200": ("生技醫療", "醫材/保健"),
    "2800": ("金融", "銀行"),
    "1300": ("塑膠化工", "塑膠原料"),
    "1710": ("塑膠化工", "特用化學"),
    "2000": ("鋼鐵金屬", "鋼鐵"),
    "2500": ("營建資產", "建設/開發"),
    "2600": ("航運運輸", "貨櫃航運"),
    "1400": ("紡織成衣", "紡織纖維(化纖/聚酯)"),
    "5300": ("電腦及週邊", "AI伺服器"),
    "5400": ("軟體服務", "資安/雲端軟體"),
    "5500": ("軟體服務", "資安/雲端軟體"),
    "3100": ("軟體服務", "系統整合SI"),
    "2300": ("公用事業", "電力/汽電共生"),
    "4000": ("國防航太", "軍工航太"),
    "4100": ("通訊網路", "低軌衛星/太空"),
    "1100": ("水泥建材", "水泥"),
    "1800": ("水泥建材", "玻璃陶瓷"),
    "1600": ("電器電纜", "重電/電線電纜"),
    "1900": ("造紙包材", "造紙/紙器"),
    "2100": ("橡膠輪胎", "橡膠/輪胎"),
    "3200": ("文創育樂", "遊戲"),
}

# companies.csv 證交所/櫃買 L1 產業分類 -> (標準 25 產業鏈, 預設保底 L2 題材, 預設上下游位置)
L1_CATEGORY_TO_DEFAULT_THEME: Dict[str, Tuple[str, str, str]] = {
    "半導體業": ("半導體", "IC設計", "上游"),
    "半導體": ("半導體", "IC設計", "上游"),
    "電子零組件業": ("電子零組件", "PCB印刷電路板", "中游"),
    "電子零組件": ("電子零組件", "PCB印刷電路板", "中游"),
    "電腦及週邊設備業": ("電腦及週邊", "伺服器", "下游"),
    "電腦及週邊": ("電腦及週邊", "伺服器", "下游"),
    "通信網路業": ("通訊網路", "網通設備", "中游"),
    "通訊網路": ("通訊網路", "網通設備", "中游"),
    "光電業": ("光電", "面板/顯示器", "中游"),
    "光電": ("光電", "面板/顯示器", "中游"),
    "其他電子業": ("電子零組件", "電子製造服務EMS", "下游"),
    "電子通路業": ("電子零組件", "IC通路/零組件代理", "下游"),
    "資訊服務業": ("軟體服務", "系統整合SI", "下游"),
    "數位雲端": ("軟體服務", "資安/雲端軟體", "中游"),
    "電機機械": ("機械設備", "工具機", "中游"),
    "電器電纜": ("電器電纜", "重電/電線電纜", "中游"),
    "生技醫療業": ("生技醫療", "新藥研發", "上游"),
    "生技醫療": ("生技醫療", "新藥研發", "上游"),
    "化學生技醫療": ("塑膠化工", "特用化學", "上游"),
    "化學工業": ("塑膠化工", "特用化學", "上游"),
    "塑膠工業": ("塑膠化工", "塑膠原料", "上游"),
    "鋼鐵工業": ("鋼鐵金屬", "鋼鐵", "中游"),
    "建材營造": ("營建資產", "建設/開發", "中游"),
    "營建業": ("營建資產", "建設/開發", "中游"),
    "航運業": ("航運運輸", "貨櫃航運", "中游"),
    "金融保險": ("金融", "銀行", "整合"),
    "金融業": ("金融", "銀行", "整合"),
    "紡織纖維": ("紡織成衣", "紡織纖維(化纖/聚酯)", "上游"),
    "食品工業": ("民生消費", "黃豆玉米小麥(大宗物資)", "中游"),
    "貿易百貨": ("民生消費", "零售通路", "下游"),
    "觀光餐旅": ("民生消費", "餐飲/連鎖飯店", "下游"),
    "居家生活": ("民生消費", "居家生活/衛浴廚具", "下游"),
    "運動休閒": ("民生消費", "健身器材/自行車", "下游"),
    "農業科技": ("民生消費", "農業科技/生技飼料", "上游"),
    "綠能環保": ("綠能環保", "水資源/環保", "中游"),
    "汽車工業": ("電動車", "車用電子", "中游"),
    "油電燃氣業": ("公用事業", "電力/汽電共生", "中游"),
    "水泥工業": ("水泥建材", "水泥", "上游"),
    "水泥類": ("水泥建材", "水泥", "上游"),
    "玻璃陶瓷": ("水泥建材", "玻璃陶瓷", "中游"),
    "造紙工業": ("造紙包材", "造紙/紙器", "中游"),
    "橡膠工業": ("橡膠輪胎", "橡膠/輪胎", "中游"),
    "文化創意業": ("文創育樂", "文創/影視展演", "下游"),
    "其他": ("控股", "控股/集團", "整合"),
    "其他業": ("控股", "控股/集團", "整合"),
    "存託憑證": ("控股", "控股/集團", "整合"),
}


# ---------------------------------------------------------------------------
# 2. 題材檔案定義：同義詞歸一化字典與 L2 題材種子庫
# ---------------------------------------------------------------------------

SYNONYM_MERGE_RULES: Dict[str, str] = {
    "cowos": "先進封裝(CoWoS)",
    "先進封裝": "先進封裝(CoWoS)",
    "先進封裝cowos": "先進封裝(CoWoS)",
    "3dic封裝": "先進封裝(CoWoS)",
    "晶圓製造": "晶圓代工",
    "foundry": "晶圓代工",
    "成熟製程晶圓代工": "晶圓代工(成熟製程)",
    "專業晶圓代工": "晶圓代工",
    "積體電路設計": "IC設計",
    "ic設計業": "IC設計",
    "fabless": "IC設計",
    "ic封裝測試": "IC封測",
    "封裝測試": "IC封測",
    "記憶體ic": "記憶體",
    "dram": "記憶體",
    "nandflash": "記憶體",
    "記憶體模組": "記憶體",
    "矽智財": "矽智財IP/ASIC",
    "ip設計": "矽智財IP/ASIC",
    "asic": "矽智財IP/ASIC",
    "玻纖布": "玻纖布/玻纖紗",
    "玻纖紗": "玻纖布/玻纖紗",
    "玻璃纖維布": "玻纖布/玻纖紗",
    "銅箔基板": "銅箔基板CCL",
    "ccl": "銅箔基板CCL",
    "印刷電路板": "PCB印刷電路板",
    "pcb": "PCB印刷電路板",
    "軟性印刷電路板": "PCB印刷電路板",
    "載板": "ABF/BT載板",
    "ic載板": "ABF/BT載板",
    "電子製造服務": "電子製造服務EMS",
    "ems": "電子製造服務EMS",
    "專業電子代工": "電子製造服務EMS",
    "電阻器": "電阻",
    "晶片電阻": "電阻",
    "電容器": "被動元件(MLCC/電感)",
    "mlcc": "被動元件(MLCC/電感)",
    "電感": "被動元件(MLCC/電感)",
    "散熱": "散熱模組",
    "液冷散熱": "散熱模組",
    "水冷散熱": "散熱模組",
    "ai伺服器代工": "AI伺服器",
    "人工智慧伺服器": "AI伺服器",
    "資料中心": "IDC機房/數據中心",
    "數據中心": "IDC機房/數據中心",
    "idc機房": "IDC機房/數據中心",
    "矽光子": "光通訊/CPO",
    "cpo": "光通訊/CPO",
    "共同封裝光學": "光通訊/CPO",
    "光收發模組": "光纖元件/模組",
    "光纖主動元件": "光纖元件/模組",
    "光纖被動元件": "光纖元件/模組",
    "鏡頭": "光學鏡頭",
    "光學鏡片": "光學鏡頭",
    "miniled": "miniLED/microLED",
    "microled": "miniLED/microLED",
    "led照明": "LED封裝/照明",
    "led封裝": "LED封裝/照明",
    "機器人": "機器人/自動化",
    "工業自動化": "機器人/自動化",
    "充電設備": "充電樁",
    "電動車充電樁": "充電樁",
    "胎壓偵測器": "胎壓偵測TPMS",
    "tpms": "胎壓偵測TPMS",
    "太陽能光電": "太陽能",
    "儲能系統": "儲能",
    "電池儲能": "儲能",
    "新藥": "新藥研發",
    "疫苗": "疫苗/生物製劑",
    "生物相似藥": "疫苗/生物製劑",
    "學名藥": "學名藥/製劑",
    "金融控股": "金控",
    "商業銀行": "銀行",
    "壽險產險": "保險",
    "不銹鋼": "不鏽鋼",
    "貨櫃運輸": "貨櫃航運",
    "散裝運輸": "散裝航運",
    "航空貨運": "空運物流",
    "系統整合": "系統整合SI",
    "si系統整合": "系統整合SI",
}


@dataclass(frozen=True)
class CuratedThemeSpec:
    """內建代表性 L2 題材種子定義（對齊官方產業鏈與台股市場共識概念股）。"""

    chain_name: str
    theme_name: str
    chain_tier: str
    stock_ids: Tuple[str, ...]
    is_primary: bool = True
    evidence_note: str = "official_ic_curated_taxonomy_v1"


CURATED_THEME_BASKETS: Tuple[CuratedThemeSpec, ...] = (
    # --- 半導體 ---
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="先進封裝(CoWoS)",
        chain_tier="下游",
        stock_ids=(
            "2330", "3711", "2449", "6187", "3131", "3583", "6640", "6223",
            "6510", "3680", "2467", "6438", "8027", "6683", "3455", "6196",
            "5443", "6788", "3563", "6532", "2360",
        ),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="晶圓代工",
        chain_tier="中游",
        stock_ids=("2330", "2303", "5347", "6770", "3707", "2342"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="晶圓代工(成熟製程)",
        chain_tier="中游",
        stock_ids=("2303", "5347", "6770", "3707", "2342", "2338", "6488"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="光罩",
        chain_tier="中游",
        stock_ids=("2338", "3680", "6532", "2330"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="矽智財IP/ASIC",
        chain_tier="上游",
        stock_ids=("3443", "3661", "3529", "6533", "6531", "6643", "3035", "2454"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="IC設計",
        chain_tier="上游",
        stock_ids=(
            "2454", "3034", "2379", "3035", "3443", "3661", "5269", "4966",
            "6415", "8016", "3545", "4919", "6138", "8081", "3227", "6239",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="IC封測",
        chain_tier="下游",
        stock_ids=(
            "3711", "2449", "6239", "8150", "6147", "8110", "2329", "2369",
            "3264", "3265", "6257", "6525",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="記憶體",
        chain_tier="中游",
        stock_ids=(
            "2408", "2344", "2337", "8299", "3260", "4967", "2451", "8271",
            "5351", "3006", "6531",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="半導體",
        theme_name="半導體設備與材料",
        chain_tier="上游",
        stock_ids=(
            "3131", "3583", "6187", "6640", "3680", "6196", "5536", "2404",
            "6488", "3532", "5483", "1560", "4768", "4770",
        ),
        is_primary=True,
    ),
    # --- 電子零組件 ---
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="玻纖布/玻纖紗",
        chain_tier="上游",
        stock_ids=("1802", "1815", "5340", "1303"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="銅箔基板CCL",
        chain_tier="上游",
        stock_ids=(
            "2383", "6213", "6274", "8358", "4989", "3144", "6509", "1303",
            "2313", "3037", "8046", "3189", "2368",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="ABF/BT載板",
        chain_tier="中游",
        stock_ids=("3037", "8046", "3189", "2313"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="PCB印刷電路板",
        chain_tier="中游",
        stock_ids=(
            "2313", "3037", "3044", "2368", "4958", "6269", "5469", "2355",
            "6153", "8155", "5439", "6191", "3715", "4927", "8046", "3189",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="散熱模組",
        chain_tier="中游",
        stock_ids=(
            "3017", "3324", "3653", "2421", "6230", "3338", "3483", "6125",
            "8996", "1587",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="電子製造服務EMS",
        chain_tier="下游",
        stock_ids=(
            "2317", "4938", "2312", "2392", "2328", "3706", "6282", "2365",
            "2474", "5264", "2354",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="電阻",
        chain_tier="上游",
        stock_ids=(
            "2327", "2492", "2478", "6173", "3624", "5328", "8043", "2456",
            "6207",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="被動元件(MLCC/電感)",
        chain_tier="中游",
        stock_ids=(
            "2327", "2492", "2456", "6173", "6155", "6284", "2472", "3090",
            "8163", "6449",
        ),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="連接器/線束",
        chain_tier="中游",
        stock_ids=(
            "3533", "3665", "3023", "6290", "3003", "6197", "2462", "5457",
            "6279", "3325",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電子零組件",
        theme_name="電源供應器/BBU",
        chain_tier="中游",
        stock_ids=(
            "2308", "2301", "2385", "6412", "2420", "3078", "6203", "3211",
            "6781", "4931",
        ),
        is_primary=True,
    ),
    # --- 電腦及週邊 ---
    CuratedThemeSpec(
        chain_name="電腦及週邊",
        theme_name="AI伺服器",
        chain_tier="下游",
        stock_ids=(
            "2317", "2382", "3231", "6669", "2356", "2376", "2357", "2301",
            "2377", "2308", "3017", "2383",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電腦及週邊",
        theme_name="伺服器",
        chain_tier="下游",
        stock_ids=(
            "2382", "3231", "6669", "2356", "2376", "3706", "8210", "6230",
            "3693", "2395",
        ),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="電腦及週邊",
        theme_name="筆電/代工",
        chain_tier="下游",
        stock_ids=(
            "2324", "2353", "2357", "2382", "3231", "2356", "2377", "2362",
            "2387",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電腦及週邊",
        theme_name="工業電腦IPC",
        chain_tier="下游",
        stock_ids=(
            "2395", "6414", "8114", "6166", "3022", "6245", "6577", "3416",
            "8050", "3577",
        ),
        is_primary=True,
    ),
    # --- 通訊網路 ---
    CuratedThemeSpec(
        chain_name="通訊網路",
        theme_name="IDC機房/數據中心",
        chain_tier="下游",
        stock_ids=(
            "2412", "3045", "4904", "3130", "2345", "6669", "2382", "3231",
            "2308", "3596", "5388", "6285", "3704", "2450", "6163", "3062",
            "2332", "2419", "4906", "6426",
        ),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="通訊網路",
        theme_name="光通訊/CPO",
        chain_tier="上游",
        stock_ids=(
            "3450", "4979", "3163", "3363", "6442", "3081", "4908", "6451",
            "2345", "3711",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="通訊網路",
        theme_name="光纖元件/模組",
        chain_tier="中游",
        stock_ids=(
            "3450", "4979", "3163", "3363", "6442", "3081", "4908", "3234",
            "4977",
        ),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="通訊網路",
        theme_name="低軌衛星/太空",
        chain_tier="中游",
        stock_ids=(
            "2313", "3491", "6285", "2314", "3152", "2317", "3062", "5388",
            "6191",
        ),
        is_primary=False,
    ),
    # --- 光電 ---
    CuratedThemeSpec(
        chain_name="光電",
        theme_name="光學鏡頭",
        chain_tier="中游",
        stock_ids=(
            "3008", "3406", "3019", "6209", "3362", "4976", "3441", "3630",
            "6668",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="光電",
        theme_name="miniLED/microLED",
        chain_tier="中游",
        stock_ids=(
            "3714", "2393", "6706", "2486", "6278", "2426", "3031", "3437",
            "2409", "3481",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="光電",
        theme_name="LED封裝/照明",
        chain_tier="中游",
        stock_ids=("2393", "3714", "2486", "3031", "3437", "2340", "6261", "8111"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="光電",
        theme_name="面板/顯示器",
        chain_tier="中游",
        stock_ids=("2409", "3481", "6116", "8069", "3149", "4960", "5243", "6176"),
        is_primary=True,
    ),
    # --- 機械設備 ---
    CuratedThemeSpec(
        chain_name="機械設備",
        theme_name="機器人/自動化",
        chain_tier="中游",
        stock_ids=(
            "2049", "1590", "2395", "6188", "8374", "4576", "4583", "6609",
            "1504", "2308", "3019", "6215",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="機械設備",
        theme_name="粉末冶金",
        chain_tier="上游",
        stock_ids=("4540", "1532", "2066", "4528"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="機械設備",
        theme_name="工具機",
        chain_tier="中游",
        stock_ids=(
            "2049", "1590", "1536", "4532", "1527", "1526", "4551", "1583",
            "6605",
        ),
        is_primary=False,
    ),
    # --- 電動車 ---
    CuratedThemeSpec(
        chain_name="電動車",
        theme_name="充電樁",
        chain_tier="下游",
        stock_ids=("2308", "1513", "1519", "2360", "3003", "6282", "2457", "8038"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="電動車",
        theme_name="車用電子",
        chain_tier="中游",
        stock_ids=(
            "1536", "3552", "6279", "2317", "2308", "1319", "1522", "6605",
            "2497", "8255",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="電動車",
        theme_name="胎壓偵測TPMS",
        chain_tier="中游",
        stock_ids=("2231", "2233", "4557", "2105"),
        is_primary=True,
    ),
    # --- 綠能環保 ---
    CuratedThemeSpec(
        chain_name="綠能環保",
        theme_name="太陽能",
        chain_tier="中游",
        stock_ids=("6443", "3576", "6477", "6244", "3691", "3686", "4934", "6806"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="綠能環保",
        theme_name="儲能",
        chain_tier="中游",
        stock_ids=("1513", "1519", "1503", "1504", "6806", "6869", "2308", "8926"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="綠能環保",
        theme_name="氫能",
        chain_tier="上游",
        stock_ids=("1513", "2308", "8926", "6806", "1301"),
        is_primary=False,
    ),
    # --- 生技醫療 ---
    CuratedThemeSpec(
        chain_name="生技醫療",
        theme_name="新藥研發",
        chain_tier="上游",
        stock_ids=(
            "6446", "4743", "1795", "4147", "4162", "6472", "6547", "4174",
            "4128", "6612",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="生技醫療",
        theme_name="疫苗/生物製劑",
        chain_tier="中游",
        stock_ids=("6547", "4142", "6589", "1760", "4147", "6446"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="生技醫療",
        theme_name="學名藥/製劑",
        chain_tier="中游",
        stock_ids=("1795", "1707", "1720", "1734", "4105", "1762", "4119", "1752"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="生技醫療",
        theme_name="醫材/保健",
        chain_tier="下游",
        stock_ids=("6491", "1707", "4107", "4126", "4163", "4137", "8436", "4736"),
        is_primary=True,
    ),
    # --- 民生消費 ---
    CuratedThemeSpec(
        chain_name="民生消費",
        theme_name="超商/超市",
        chain_tier="下游",
        stock_ids=("2912", "5903", "2903", "2915"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="民生消費",
        theme_name="零售通路",
        chain_tier="下游",
        stock_ids=("2912", "5904", "2903", "2915", "8454", "2908", "5903"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="民生消費",
        theme_name="黃豆玉米小麥(大宗物資)",
        chain_tier="上游",
        stock_ids=("1216", "1210", "1215", "1218", "1219", "1220", "1225", "1229"),
        is_primary=True,
    ),
    # --- 金融 ---
    CuratedThemeSpec(
        chain_name="金融",
        theme_name="金控",
        chain_tier="整合",
        stock_ids=(
            "2881", "2882", "2883", "2884", "2885", "2886", "2887", "2889",
            "2890", "2891", "2892", "5880", "2880",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="金融",
        theme_name="銀行",
        chain_tier="整合",
        stock_ids=(
            "2801", "2812", "2834", "2836", "2838", "2845", "2849", "2897",
            "5876", "2884", "2886", "2891", "2892", "5880", "2880", "2881",
            "2882", "2885", "2887", "2890", "2883",
        ),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="金融",
        theme_name="保險",
        chain_tier="整合",
        stock_ids=("2850", "2851", "2852", "2867", "2816", "2832", "2881", "2882"),
        is_primary=True,
    ),
    # --- 塑膠化工 ---
    CuratedThemeSpec(
        chain_name="塑膠化工",
        theme_name="塑膠加工製品",
        chain_tier="下游",
        stock_ids=("1303", "1307", "1319", "1321", "1325", "1305"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="塑膠化工",
        theme_name="石化",
        chain_tier="上游",
        stock_ids=("6505", "1301", "1303", "1326", "1304", "1312", "1314"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="塑膠化工",
        theme_name="塑膠原料",
        chain_tier="上游",
        stock_ids=("1301", "1303", "1326", "1304", "1308", "1309", "1312", "1313"),
        is_primary=True,
    ),
    # --- 鋼鐵金屬 ---
    CuratedThemeSpec(
        chain_name="鋼鐵金屬",
        theme_name="鋼鐵",
        chain_tier="中游",
        stock_ids=(
            "2002", "2006", "2014", "2015", "2023", "2027", "2031", "2038",
            "2010", "2029", "2032", "2028",
        ),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="鋼鐵金屬",
        theme_name="不鏽鋼",
        chain_tier="中游",
        stock_ids=("2027", "2034", "2030", "2035", "2025", "2069", "8415"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="鋼鐵金屬",
        theme_name="金屬製品/五金",
        chain_tier="下游",
        stock_ids=("2059", "2013", "2017", "2020", "2022", "2033"),
        is_primary=True,
    ),
    # --- 營建資產 ---
    CuratedThemeSpec(
        chain_name="營建資產",
        theme_name="資產開發/包租",
        chain_tier="下游",
        stock_ids=("2501", "2542", "2548", "2520", "1434", "2101"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="營建資產",
        theme_name="建設/開發",
        chain_tier="中游",
        stock_ids=("2542", "2548", "2501", "2520", "2534", "2545", "5522", "5534"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="營建資產",
        theme_name="公共工程/統包",
        chain_tier="中游",
        stock_ids=("2504", "2515", "2516", "5536", "2404", "9933", "2546"),
        is_primary=True,
    ),
    # --- 航運運輸 ---
    CuratedThemeSpec(
        chain_name="航運運輸",
        theme_name="貨櫃航運",
        chain_tier="中游",
        stock_ids=("2603", "2609", "2615", "2636"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="航運運輸",
        theme_name="散裝航運",
        chain_tier="中游",
        stock_ids=("2606", "2637", "2605", "2612", "2617", "5608", "2601"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="航運運輸",
        theme_name="空運物流",
        chain_tier="下游",
        stock_ids=("2618", "2610", "6757", "2636", "2607", "2608"),
        is_primary=True,
    ),
    # --- 紡織成衣 ---
    CuratedThemeSpec(
        chain_name="紡織成衣",
        theme_name="紡織纖維(化纖/聚酯)",
        chain_tier="上游",
        stock_ids=("1402", "1409", "1434", "1440", "1444", "1455", "1457"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="紡織成衣",
        theme_name="成衣代工",
        chain_tier="下游",
        stock_ids=("1476", "1477", "4438", "1464", "1451"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="紡織成衣",
        theme_name="製鞋",
        chain_tier="下游",
        stock_ids=("9904", "9910", "9802", "6768", "9938"),
        is_primary=True,
    ),
    # --- 軟體服務 ---
    CuratedThemeSpec(
        chain_name="軟體服務",
        theme_name="系統整合SI",
        chain_tier="下游",
        stock_ids=("6214", "2453", "3029", "6112", "2471", "5203", "2427", "4994"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="軟體服務",
        theme_name="遊戲",
        chain_tier="下游",
        stock_ids=("3293", "5478", "6180", "3546", "6111", "4994", "3083"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="軟體服務",
        theme_name="軟體",
        chain_tier="中游",
        stock_ids=("6689", "6761", "6741", "6870", "5203", "6592"),
        is_primary=False,
    ),
    # --- 公用事業 ---
    CuratedThemeSpec(
        chain_name="公用事業",
        theme_name="煉油石化",
        chain_tier="上游",
        stock_ids=("6505", "1301", "1303", "1326"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="公用事業",
        theme_name="電力/汽電共生",
        chain_tier="中游",
        stock_ids=("8926", "6505", "9931", "9908", "9918"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="公用事業",
        theme_name="瓦斯",
        chain_tier="下游",
        stock_ids=("9908", "9918", "9926", "9931", "9937"),
        is_primary=True,
    ),
    # --- 國防航太 ---
    CuratedThemeSpec(
        chain_name="國防航太",
        theme_name="航太零組件",
        chain_tier="中游",
        stock_ids=("2634", "4545", "8222", "6829", "4572", "3004"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="國防航太",
        theme_name="無人機",
        chain_tier="下游",
        stock_ids=("8033", "2634", "5371", "2359", "3694"),
        is_primary=False,
    ),
    CuratedThemeSpec(
        chain_name="國防航太",
        theme_name="軍工航太",
        chain_tier="整合",
        stock_ids=("2634", "2208", "8033", "8222", "4545"),
        is_primary=False,
    ),
    # --- 水泥建材 ---
    CuratedThemeSpec(
        chain_name="水泥建材",
        theme_name="水泥",
        chain_tier="上游",
        stock_ids=("1101", "1102", "1103", "1104", "1108", "1109", "1110"),
        is_primary=True,
    ),
    CuratedThemeSpec(
        chain_name="水泥建材",
        theme_name="玻璃陶瓷",
        chain_tier="中游",
        stock_ids=("1802", "1806", "1809", "1810", "1817"),
        is_primary=True,
    ),
    # --- 控股 ---
    CuratedThemeSpec(
        chain_name="控股",
        theme_name="控股/集團",
        chain_tier="整合",
        stock_ids=(
            "1101", "1216", "1301", "1303", "1402", "2002", "2301", "2308",
            "2317", "2324", "2353", "2357", "2382", "2881", "2882", "2884",
            "2885", "2886", "2891", "2892", "2912", "3702", "3711", "9904",
        ),
        is_primary=False,
    ),
    # --- 電器電纜 ---
    CuratedThemeSpec(
        chain_name="電器電纜",
        theme_name="重電/電線電纜",
        chain_tier="中游",
        stock_ids=(
            "1503", "1504", "1513", "1514", "1519", "1605", "1608", "1609",
            "1612", "1618",
        ),
        is_primary=True,
    ),
    # --- 造紙包材 ---
    CuratedThemeSpec(
        chain_name="造紙包材",
        theme_name="造紙/紙器",
        chain_tier="中游",
        stock_ids=("1904", "1905", "1906", "1907", "1909", "6790"),
        is_primary=True,
    ),
    # --- 橡膠輪胎 ---
    CuratedThemeSpec(
        chain_name="橡膠輪胎",
        theme_name="橡膠/輪胎",
        chain_tier="中游",
        stock_ids=("2101", "2103", "2104", "2105", "2106", "2108", "6582"),
        is_primary=True,
    ),
    # --- 文創育樂 ---
    CuratedThemeSpec(
        chain_name="文創育樂",
        theme_name="文創/影視展演",
        chain_tier="下游",
        stock_ids=("8446", "6539", "6625", "4804", "8450", "5299"),
        is_primary=True,
    ),
)

# 關鍵字匹配規則（供公司名稱或營業項目文字補充辨識 L2 題材，無須呼叫外部 LLM）
THEME_KEYWORD_RULES: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("電子零組件", "玻纖布/玻纖紗", "上游", ("玻纖", "玻璃纖維")),
    ("電子零組件", "銅箔基板CCL", "上游", ("銅箔基板", "CCL", "銅箔")),
    ("電子零組件", "散熱模組", "中游", ("散熱", "水冷", "均熱片", "風扇")),
    ("半導體", "先進封裝(CoWoS)", "下游", ("CoWoS", "先進封裝", "3D封裝")),
    ("半導體", "矽智財IP/ASIC", "上游", ("矽智財", "ASIC", "IP授權")),
    ("通訊網路", "光通訊/CPO", "上游", ("矽光子", "CPO", "光收發", "光通訊")),
    ("電腦及週邊", "AI伺服器", "下游", ("AI伺服器", "GPU伺服器")),
    ("綠能環保", "太陽能", "中游", ("太陽能", "太陽光電")),
    ("綠能環保", "儲能", "中游", ("儲能", "電池模組")),
    ("國防航太", "無人機", "下游", ("無人機", "UAV")),
    ("金融", "金控", "整合", ("金控",)),
    ("金融", "銀行", "整合", ("銀", "銀行")),
    ("金融", "保險", "整合", ("產險", "壽險", "人壽", "保")),
    ("鋼鐵金屬", "不鏽鋼", "中游", ("不鏽鋼", "不銹鋼")),
)


# ---------------------------------------------------------------------------
# 3. 三大產出檔案之資料契約 (Data Contracts)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThemeMapPaths:
    """集中管理題材地圖所需之檔案路徑（由 `TWStockConfig` 衍生）。"""

    data_root: Path
    meta_data_dir: Path
    companies_file: Path
    industry_chains_catalog_csv: Path
    industry_themes_catalog_csv: Path
    industry_theme_stock_map_csv: Path
    latest_mapping_csv: Path
    snapshots_dir: Path
    snapshot_manifest_json: Path


@dataclass(frozen=True)
class IndustryChainCatalogRow:
    """檔案一：產業檔案 (`industry_chains_catalog.csv`) 單列結構。"""

    chain_id: str
    chain_order: int
    chain_name: str
    official_ic_codes: str
    mapped_l1_categories: str
    default_theme_name: str
    default_chain_tier: str
    upstream_summary: str
    midstream_summary: str
    downstream_summary: str
    active_theme_count: int
    mapped_company_count: int
    snapshot_date: str


@dataclass(frozen=True)
class IndustryThemeCatalogRow:
    """檔案二：題材檔案 (`industry_themes_catalog.csv`) 單列結構。"""

    theme_id: str
    chain_name: str
    theme_name: str
    default_chain_tier: str
    synonyms_merged: str
    keyword_rules: str
    extraction_sources: str
    company_count: int
    primary_company_count: int
    sample_stock_ids: str
    sample_stock_names: str
    snapshot_date: str


@dataclass(frozen=True)
class ThemeMappingRow:
    """檔案三：產業題材股票對應檔案 (`industry_theme_stock_map.csv`) 單列結構。"""

    snapshot_date: str
    available_date: str
    stock_id: str
    stock_name: str
    market_type: str
    l1_industry_category: str
    chain_name: str
    chain_tier: str
    theme_name: str
    is_primary: bool
    assignment_method: str
    source_name: str
    source_tier: str
    pit_mode: str
    evidence_note: str


# ---------------------------------------------------------------------------
# 4. 輔助函式：路徑、代號、日期與同義詞歸一化
# ---------------------------------------------------------------------------


def get_theme_map_paths(config: Optional[TWStockConfig] = None) -> ThemeMapPaths:
    """從既有 `TWStockConfig` 解析所有產業與題材檔案路徑，不重複建構設定。"""
    cfg = config or TWStockConfig()
    meta_dir = Path(cfg.meta_data_dir)
    snapshots_dir = meta_dir / "industry_chain_snapshots"
    companies_csv = Path(getattr(cfg, "companies_file", meta_dir / "companies.csv"))
    return ThemeMapPaths(
        data_root=Path(cfg.data_root),
        meta_data_dir=meta_dir,
        companies_file=companies_csv,
        industry_chains_catalog_csv=meta_dir / "industry_chains_catalog.csv",
        industry_themes_catalog_csv=meta_dir / "industry_themes_catalog.csv",
        industry_theme_stock_map_csv=meta_dir / "industry_theme_stock_map.csv",
        latest_mapping_csv=meta_dir / "industry_chains_latest.csv",
        snapshots_dir=snapshots_dir,
        snapshot_manifest_json=snapshots_dir / "manifest.json",
    )


def normalize_stock_id(raw: object) -> str:
    """標準化台股 4 碼普通股代號；非 4 碼普通股回傳空字串。"""
    code = str(raw or "").strip()
    if code.endswith(".TW") or code.endswith(".TWO"):
        code = code.split(".", 1)[0]
    if len(code) == 4 and code.isdigit():
        return code
    return ""


def normalize_iso_date(raw: object) -> str:
    """將 `YYYYMMDD`、`YYYY/MM/DD` 或 `YYYY-MM-DD` 統一轉為 `YYYY-MM-DD`。"""
    text = str(raw or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    raise ValueError(f"無法解析日期格式: {raw!r}")


def compact_date_key(raw: object) -> str:
    """將日期轉為 8 碼 `YYYYMMDD` 供檔名與排序使用。"""
    return normalize_iso_date(raw).replace("-", "")


def normalize_theme_name(raw_name: str) -> str:
    """全域同義詞合併與標準化題材名稱。"""
    cleaned = re.sub(r"\s+", "", str(raw_name or "").strip())
    if not cleaned:
        return ""
    lookup_key = cleaned.lower().replace("（", "(").replace("）", ")")
    lookup_compact = re.sub(r"[()/\-_]", "", lookup_key)
    if lookup_key in SYNONYM_MERGE_RULES:
        return SYNONYM_MERGE_RULES[lookup_key]
    if lookup_compact in SYNONYM_MERGE_RULES:
        return SYNONYM_MERGE_RULES[lookup_compact]
    return cleaned


# ---------------------------------------------------------------------------
# 5. 官方「產業價值鏈資訊平台 (ic.tpex.org.tw)」HTML 解析器与可選抓取器
# ---------------------------------------------------------------------------

_CHAIN_BLOCK_RE = re.compile(
    r'<div\s+class="chain">\s*<div\s+class="chain-title-panel">(?P<tier>[^<]+)</div>(?P<body>.*?)(?=<div\s+class="chain">|<script|$)',
    re.DOTALL | re.IGNORECASE,
)
_SUBCHAIN_PANEL_RE = re.compile(
    r'id="ic_link_(?P<subcode>[A-Za-z0-9_]+)"[^>]*>\s*(?P<title>[^<]+?)\s*</div>',
    re.DOTALL | re.IGNORECASE,
)
_COMPANY_LIST_RE = re.compile(
    r'<div\s+id="companyList_(?P<subcode>[A-Za-z0-9_]+)"\s+title="(?P<title>[^"]*)"[^>]*>(?P<links>.*?)</div>\s*</div>',
    re.DOTALL | re.IGNORECASE,
)
_STK_LINK_RE = re.compile(
    r'stk_code=(?P<code>[0-9A-Za-z]+)"[^>]*title="(?P<name>[^"]*)"[^>]*>(?P<label>[^<]*)</a>',
    re.DOTALL | re.IGNORECASE,
)


def parse_ic_tpex_chain_html(
    html_text: str,
    chain_name: str,
    *,
    snapshot_date: str,
    available_date: str,
) -> List[ThemeMappingRow]:
    """解析 `https://ic.tpex.org.tw/introduce.php?ic=<CODE>` 單頁 HTML 為標準 `ThemeMappingRow`。"""
    subcode_to_tier: Dict[str, str] = {}
    for match in _CHAIN_BLOCK_RE.finditer(html_text):
        raw_tier = html.unescape(match.group("tier")).strip()
        tier = "整合"
        for candidate in ("上游", "中游", "下游"):
            if candidate in raw_tier:
                tier = candidate
                break
        body = match.group("body")
        for panel in _SUBCHAIN_PANEL_RE.finditer(body):
            subcode_to_tier[panel.group("subcode").strip()] = tier

    rows: List[ThemeMappingRow] = []
    for block in _COMPANY_LIST_RE.finditer(html_text):
        subcode = block.group("subcode").strip()
        raw_theme = html.unescape(block.group("title")).strip()
        theme_name = normalize_theme_name(raw_theme)
        if not theme_name:
            continue
        tier = subcode_to_tier.get(subcode, "中游")
        links_html = block.group("links")
        for link in _STK_LINK_RE.finditer(links_html):
            stock_id = normalize_stock_id(link.group("code"))
            if not stock_id:
                continue
            raw_label = html.unescape(link.group("label") or link.group("name")).strip()
            stock_name = re.sub(r"\([0-9A-Za-z]+\)$", "", raw_label).strip() or stock_id
            rows.append(
                ThemeMappingRow(
                    snapshot_date=snapshot_date,
                    available_date=available_date,
                    stock_id=stock_id,
                    stock_name=stock_name,
                    market_type="",
                    l1_industry_category="",
                    chain_name=chain_name,
                    chain_tier=tier,
                    theme_name=theme_name,
                    is_primary=False,
                    assignment_method=METHOD_P1_OFFICIAL_IC,
                    source_name="official_ic_tpex",
                    source_tier="T1",
                    pit_mode="quarterly_snapshot",
                    evidence_note=f"ic_tpex:{subcode}",
                )
            )
    return rows


def fetch_official_ic_tpex_chains(
    ic_codes: Optional[Sequence[str]] = None,
    *,
    snapshot_date: str,
    available_date: str,
    timeout_sec: int = 15,
    opener: Optional[Callable[[str, int], str]] = None,
) -> List[ThemeMappingRow]:
    """選擇性向官方 `ic.tpex.org.tw` 抓取最新季度產業鏈分類（每季執行一次即可）。"""
    codes = list(ic_codes or OFFICIAL_IC_CHAIN_MAP.keys())
    all_rows: List[ThemeMappingRow] = []

    def _default_fetch(url: str, timeout: int) -> str:
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BaldrThemeMapper/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
        return raw_bytes.decode("utf-8", errors="replace")

    fetch_fn = opener or _default_fetch
    for ic_code in codes:
        chain_name, _ = OFFICIAL_IC_CHAIN_MAP.get(ic_code, ("控股", "控股/集團"))
        url = f"https://ic.tpex.org.tw/introduce.php?{urlencode({'ic': ic_code})}"
        parsed = parse_ic_tpex_chain_html(
            fetch_fn(url, timeout_sec),
            chain_name=chain_name,
            snapshot_date=snapshot_date,
            available_date=available_date,
        )
        all_rows.extend(parsed)
    return all_rows


# ---------------------------------------------------------------------------
# 6. 核心服務：IndustryThemeMapService (專職產業與題材萃取、對應分配與三檔輸出)
# ---------------------------------------------------------------------------


class IndustryThemeMapService:
    """台股產業鏈與 L2 題材萃取、對應分配與三檔建置服務。"""

    def __init__(self, config: Optional[TWStockConfig] = None) -> None:
        self.config = config or TWStockConfig()
        self.paths = get_theme_map_paths(self.config)

    def _load_companies_universe(
        self, companies_file: Optional[Path] = None
    ) -> Dict[str, Dict[str, str]]:
        """讀取 `companies.csv` 取得台股 4 碼普通股母體、市場別與原始 L1 產業分類。"""
        target = Path(companies_file or self.paths.companies_file)
        universe: Dict[str, Dict[str, str]] = {}
        if not target.exists():
            return universe
        with target.open("r", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stock_id = normalize_stock_id(row.get("stock_id"))
                if not stock_id:
                    continue
                stock_name = str(row.get("stock_name") or "").strip() or stock_id
                industry_category = str(row.get("industry_category") or "其他").strip() or "其他"
                market_type = str(row.get("type") or row.get("market_type") or "").strip()
                universe[stock_id] = {
                    "stock_id": stock_id,
                    "stock_name": stock_name,
                    "industry_category": industry_category,
                    "market_type": market_type,
                }
        return universe

    def refresh_theme_mapping(
        self,
        *,
        snapshot_date: Optional[str] = None,
        available_date: Optional[str] = None,
        min_companies: int = 3,
        fetch_official_ic: bool = False,
        extra_official_rows: Optional[Sequence[ThemeMappingRow]] = None,
        companies_file: Optional[Path] = None,
        persist: bool = True,
    ) -> Tuple[List[ThemeMappingRow], Dict[str, Any]]:
        """執行產業與題材萃取、四階對應分配，並生成三大核心 CSV 檔案：
        1. `industry_chains_catalog.csv` (產業檔案)
        2. `industry_themes_catalog.csv` (題材檔案)
        3. `industry_theme_stock_map.csv` (產業題材股票對應檔案)
        """
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snap_iso = normalize_iso_date(snapshot_date or today_iso)
        avail_iso = normalize_iso_date(available_date or snap_iso)

        universe = self._load_companies_universe(companies_file=companies_file)
        candidate_rows: List[ThemeMappingRow] = []

        # -------------------------------------------------------------------
        # P1: 匯入官方 ic.tpex.org.tw 解析結果（若有開啟連線或傳入 HTML 解析列）
        # -------------------------------------------------------------------
        official_rows: List[ThemeMappingRow] = list(extra_official_rows or [])
        if fetch_official_ic:
            try:
                official_rows.extend(
                    fetch_official_ic_tpex_chains(
                        snapshot_date=snap_iso,
                        available_date=avail_iso,
                    )
                )
            except Exception as exc:
                official_fetch_warning = f"official_ic_tpex_fetch_failed:{type(exc).__name__}"
            else:
                official_fetch_warning = ""
        else:
            official_fetch_warning = ""

        for row in official_rows:
            norm_sid = normalize_stock_id(row.stock_id)
            if not norm_sid:
                continue
            comp = universe.get(norm_sid)
            sname = comp["stock_name"] if comp else row.stock_name
            mtype = comp["market_type"] if comp else row.market_type
            l1_cat = comp["industry_category"] if comp else row.l1_industry_category
            candidate_rows.append(
                ThemeMappingRow(
                    snapshot_date=snap_iso,
                    available_date=avail_iso,
                    stock_id=norm_sid,
                    stock_name=sname,
                    market_type=mtype,
                    l1_industry_category=l1_cat,
                    chain_name=row.chain_name,
                    chain_tier=row.chain_tier,
                    theme_name=normalize_theme_name(row.theme_name),
                    is_primary=row.is_primary,
                    assignment_method=METHOD_P1_OFFICIAL_IC,
                    source_name=row.source_name or "official_ic_tpex",
                    source_tier=row.source_tier or "T1",
                    pit_mode="quarterly_snapshot",
                    evidence_note=row.evidence_note,
                )
            )

        # -------------------------------------------------------------------
        # P2: 匯入內建權威 L2 題材種子庫 (`CURATED_THEME_BASKETS`)
        # -------------------------------------------------------------------
        for spec in CURATED_THEME_BASKETS:
            canonical_theme = normalize_theme_name(spec.theme_name)
            for sid in spec.stock_ids:
                norm_sid = normalize_stock_id(sid)
                if not norm_sid:
                    continue
                comp = universe.get(norm_sid)
                sname = comp["stock_name"] if comp else norm_sid
                mtype = comp["market_type"] if comp else ""
                l1_cat = comp["industry_category"] if comp else ""
                candidate_rows.append(
                    ThemeMappingRow(
                        snapshot_date=snap_iso,
                        available_date=avail_iso,
                        stock_id=norm_sid,
                        stock_name=sname,
                        market_type=mtype,
                        l1_industry_category=l1_cat,
                        chain_name=spec.chain_name,
                        chain_tier=spec.chain_tier,
                        theme_name=canonical_theme,
                        is_primary=spec.is_primary,
                        assignment_method=METHOD_P2_CURATED_TAXONOMY,
                        source_name="curated_ic_taxonomy",
                        source_tier="T1",
                        pit_mode="quarterly_snapshot",
                        evidence_note=spec.evidence_note,
                    )
                )

        # -------------------------------------------------------------------
        # P3: 針對 companies.csv 母體進行關鍵字萃取 (P3)
        # -------------------------------------------------------------------
        stocks_with_primary: set[str] = {
            r.stock_id for r in candidate_rows if r.is_primary
        }
        for sid, info in sorted(universe.items()):
            sname = info["stock_name"]
            l1_cat = info["industry_category"]
            mtype = info["market_type"]
            for kw_chain, kw_theme, kw_tier, keywords in THEME_KEYWORD_RULES:
                if any(kw in sname for kw in keywords):
                    candidate_rows.append(
                        ThemeMappingRow(
                            snapshot_date=snap_iso,
                            available_date=avail_iso,
                            stock_id=sid,
                            stock_name=sname,
                            market_type=mtype,
                            l1_industry_category=l1_cat,
                            chain_name=kw_chain,
                            chain_tier=kw_tier,
                            theme_name=normalize_theme_name(kw_theme),
                            is_primary=(sid not in stocks_with_primary),
                            assignment_method=METHOD_P3_KEYWORD_RULE,
                            source_name="keyword_rule",
                            source_tier="T2",
                            pit_mode="quarterly_snapshot",
                            evidence_note=f"name_keyword:{l1_cat}",
                        )
                    )
                    stocks_with_primary.add(sid)

        # P4 (第一輪): 僅對尚未命中任何 P1/P2/P3 題材之普通股進行 L1 保底分配
        mapped_so_far: set[str] = {r.stock_id for r in candidate_rows}
        for sid, info in sorted(universe.items()):
            if sid in mapped_so_far:
                continue
            sname = info["stock_name"]
            l1_cat = info["industry_category"]
            mtype = info["market_type"]
            default_chain, default_theme, default_tier = L1_CATEGORY_TO_DEFAULT_THEME.get(
                l1_cat, ("控股", "控股/集團", "整合")
            )
            candidate_rows.append(
                ThemeMappingRow(
                    snapshot_date=snap_iso,
                    available_date=avail_iso,
                    stock_id=sid,
                    stock_name=sname,
                    market_type=mtype,
                    l1_industry_category=l1_cat,
                    chain_name=default_chain,
                    chain_tier=default_tier,
                    theme_name=normalize_theme_name(default_theme),
                    is_primary=True,
                    assignment_method=METHOD_P4_L1_FALLBACK,
                    source_name="companies_l1_fallback",
                    source_tier="T2",
                    pit_mode="quarterly_snapshot",
                    evidence_note=f"l1_category:{l1_cat}",
                )
            )

        # -------------------------------------------------------------------
        # 全域去重：以 (stock_id, chain_name, theme_name) 為唯一鍵，保留最高優先序來源
        # -------------------------------------------------------------------
        method_priority = {
            METHOD_P1_OFFICIAL_IC: 1,
            METHOD_P2_CURATED_TAXONOMY: 2,
            METHOD_P3_KEYWORD_RULE: 3,
            METHOD_P4_L1_FALLBACK: 4,
        }
        dedup_map: Dict[Tuple[str, str, str], ThemeMappingRow] = {}
        for row in candidate_rows:
            key = (row.stock_id, row.chain_name, row.theme_name)
            existing = dedup_map.get(key)
            if existing is None:
                dedup_map[key] = row
            else:
                new_prio = method_priority.get(row.assignment_method, 99)
                old_prio = method_priority.get(existing.assignment_method, 99)
                if new_prio < old_prio or (
                    new_prio == old_prio and row.is_primary and not existing.is_primary
                ):
                    dedup_map[key] = row

        deduped_rows = list(dedup_map.values())

        # -------------------------------------------------------------------
        # 過濾少於 min_companies (預設 3 家) 的長尾題材，並對因過濾而失去唯一題材之股票補做 P4 回退
        # -------------------------------------------------------------------
        theme_stock_sets: Dict[Tuple[str, str], set[str]] = {}
        for row in deduped_rows:
            theme_stock_sets.setdefault((row.chain_name, row.theme_name), set()).add(
                row.stock_id
            )

        surviving_themes: set[Tuple[str, str]] = {
            k for k, members in theme_stock_sets.items() if len(members) >= max(1, min_companies)
        }
        filtered_long_tail_count = len(theme_stock_sets) - len(surviving_themes)

        surviving_rows: List[ThemeMappingRow] = [
            row
            for row in deduped_rows
            if (row.chain_name, row.theme_name) in surviving_themes
        ]

        # 若某檔 universe 股票因其題材少於 min_companies 被過濾後無任何題材，回退至其 L1 預設題材
        surviving_stock_ids = {r.stock_id for r in surviving_rows}
        for sid, info in sorted(universe.items()):
            if sid in surviving_stock_ids:
                continue
            sname = info["stock_name"]
            l1_cat = info["industry_category"]
            mtype = info["market_type"]
            default_chain, default_theme, default_tier = L1_CATEGORY_TO_DEFAULT_THEME.get(
                l1_cat, ("控股", "控股/集團", "整合")
            )
            surviving_rows.append(
                ThemeMappingRow(
                    snapshot_date=snap_iso,
                    available_date=avail_iso,
                    stock_id=sid,
                    stock_name=sname,
                    market_type=mtype,
                    l1_industry_category=l1_cat,
                    chain_name=default_chain,
                    chain_tier=default_tier,
                    theme_name=normalize_theme_name(default_theme),
                    is_primary=True,
                    assignment_method=METHOD_P4_L1_FALLBACK,
                    source_name="companies_l1_fallback",
                    source_tier="T2",
                    pit_mode="quarterly_snapshot",
                    evidence_note=f"l1_long_tail_fallback:{l1_cat}",
                )
            )

        # 確保每檔股票恰好只有一筆 is_primary=True（依優先序與原標記決定）
        rows_by_stock: Dict[str, List[ThemeMappingRow]] = {}
        for r in surviving_rows:
            rows_by_stock.setdefault(r.stock_id, []).append(r)

        final_rows: List[ThemeMappingRow] = []
        for sid, s_rows in rows_by_stock.items():
            s_rows.sort(
                key=lambda r: (
                    not r.is_primary,
                    method_priority.get(r.assignment_method, 99),
                )
            )
            for idx, r in enumerate(s_rows):
                final_rows.append(
                    ThemeMappingRow(
                        snapshot_date=r.snapshot_date,
                        available_date=r.available_date,
                        stock_id=r.stock_id,
                        stock_name=r.stock_name,
                        market_type=r.market_type,
                        l1_industry_category=r.l1_industry_category,
                        chain_name=r.chain_name,
                        chain_tier=r.chain_tier,
                        theme_name=r.theme_name,
                        is_primary=(idx == 0),
                        assignment_method=r.assignment_method,
                        source_name=r.source_name,
                        source_tier=r.source_tier,
                        pit_mode=r.pit_mode,
                        evidence_note=r.evidence_note,
                    )
                )

        final_rows.sort(
            key=lambda r: (
                STANDARD_25_CHAINS.index(r.chain_name)
                if r.chain_name in STANDARD_25_CHAINS
                else 999,
                r.chain_name,
                r.theme_name,
                r.stock_id,
            )
        )

        # 建立檔案一（產業檔案）與檔案二（題材檔案）內容
        chain_catalog_rows = self.build_industry_chains_catalog(
            final_rows, snapshot_date=snap_iso
        )
        theme_catalog_rows = self.build_industry_themes_catalog(
            final_rows, snapshot_date=snap_iso
        )

        unique_themes = {(r.chain_name, r.theme_name) for r in final_rows}
        unique_chains = {r.chain_name for r in final_rows}
        unique_stocks = {r.stock_id for r in final_rows}

        manifest_entry: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_date": snap_iso,
            "available_date": avail_iso,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_companies": min_companies,
            "total_rows": len(final_rows),
            "total_themes": len(unique_themes),
            "total_chains": len(unique_chains),
            "total_companies": len(unique_stocks),
            "filtered_long_tail_themes": filtered_long_tail_count,
            "files": {
                "industry_chains_catalog_csv": str(self.paths.industry_chains_catalog_csv),
                "industry_themes_catalog_csv": str(self.paths.industry_themes_catalog_csv),
                "industry_theme_stock_map_csv": str(self.paths.industry_theme_stock_map_csv),
                "latest_mapping_csv": str(self.paths.latest_mapping_csv),
            },
            "warnings": [official_fetch_warning] if official_fetch_warning else [],
        }

        if persist:
            self._persist_all_files(
                chain_catalog_rows=chain_catalog_rows,
                theme_catalog_rows=theme_catalog_rows,
                stock_map_rows=final_rows,
                manifest_entry=manifest_entry,
            )

        return final_rows, manifest_entry

    @staticmethod
    def build_industry_chains_catalog(
        mapping_rows: Sequence[ThemeMappingRow],
        *,
        snapshot_date: str,
    ) -> List[IndustryChainCatalogRow]:
        """根據映射結果建置「產業檔案 (`industry_chains_catalog.csv`)」。"""
        themes_by_chain: Dict[str, set[str]] = {}
        stocks_by_chain: Dict[str, set[str]] = {}
        for r in mapping_rows:
            themes_by_chain.setdefault(r.chain_name, set()).add(r.theme_name)
            stocks_by_chain.setdefault(r.chain_name, set()).add(r.stock_id)

        out: List[IndustryChainCatalogRow] = []
        for spec in STANDARD_25_CHAIN_SPECS:
            out.append(
                IndustryChainCatalogRow(
                    chain_id=spec.chain_id,
                    chain_order=spec.chain_order,
                    chain_name=spec.chain_name,
                    official_ic_codes=";".join(spec.official_ic_codes),
                    mapped_l1_categories=";".join(spec.mapped_l1_categories),
                    default_theme_name=spec.default_theme_name,
                    default_chain_tier=spec.default_chain_tier,
                    upstream_summary=spec.upstream_summary,
                    midstream_summary=spec.midstream_summary,
                    downstream_summary=spec.downstream_summary,
                    active_theme_count=len(themes_by_chain.get(spec.chain_name, set())),
                    mapped_company_count=len(stocks_by_chain.get(spec.chain_name, set())),
                    snapshot_date=snapshot_date,
                )
            )
        return out

    @staticmethod
    def build_industry_themes_catalog(
        mapping_rows: Sequence[ThemeMappingRow],
        *,
        snapshot_date: str,
    ) -> List[IndustryThemeCatalogRow]:
        """根據映射結果建置「題材檔案 (`industry_themes_catalog.csv`)」。"""
        synonyms_by_theme: Dict[str, List[str]] = {}
        for alias, canonical in sorted(SYNONYM_MERGE_RULES.items()):
            synonyms_by_theme.setdefault(canonical, []).append(alias)

        keywords_by_theme: Dict[Tuple[str, str], List[str]] = {}
        for c_name, t_name, _, kw_tuple in THEME_KEYWORD_RULES:
            norm_t = normalize_theme_name(t_name)
            keywords_by_theme.setdefault((c_name, norm_t), []).extend(kw_tuple)

        grouped: Dict[Tuple[str, str], List[ThemeMappingRow]] = {}
        for r in mapping_rows:
            grouped.setdefault((r.chain_name, r.theme_name), []).append(r)

        out: List[IndustryThemeCatalogRow] = []
        for (chain_name, theme_name), members in grouped.items():
            members_sorted = sorted(
                members, key=lambda m: (not m.is_primary, m.stock_id)
            )
            tier_counts: Dict[str, int] = {}
            sources_set: set[str] = set()
            for m in members_sorted:
                tier_counts[m.chain_tier] = tier_counts.get(m.chain_tier, 0) + 1
                sources_set.add(m.assignment_method)

            dominant_tier = max(tier_counts.items(), key=lambda kv: kv[1])[0]
            primary_cnt = sum(1 for m in members_sorted if m.is_primary)
            sample_members = members_sorted[:5]

            out.append(
                IndustryThemeCatalogRow(
                    theme_id=f"{chain_name}::{theme_name}",
                    chain_name=chain_name,
                    theme_name=theme_name,
                    default_chain_tier=dominant_tier,
                    synonyms_merged=";".join(synonyms_by_theme.get(theme_name, [])),
                    keyword_rules=";".join(
                        keywords_by_theme.get((chain_name, theme_name), [])
                    ),
                    extraction_sources=";".join(sorted(sources_set)),
                    company_count=len(members_sorted),
                    primary_company_count=primary_cnt,
                    sample_stock_ids=";".join(m.stock_id for m in sample_members),
                    sample_stock_names=";".join(m.stock_name for m in sample_members),
                    snapshot_date=snapshot_date,
                )
            )

        out.sort(
            key=lambda row: (
                STANDARD_25_CHAINS.index(row.chain_name)
                if row.chain_name in STANDARD_25_CHAINS
                else 999,
                -row.company_count,
                row.theme_name,
            )
        )
        return out

    def _persist_all_files(
        self,
        *,
        chain_catalog_rows: Sequence[IndustryChainCatalogRow],
        theme_catalog_rows: Sequence[IndustryThemeCatalogRow],
        stock_map_rows: Sequence[ThemeMappingRow],
        manifest_entry: Dict[str, Any],
    ) -> None:
        """將產業檔案、題材檔案與產業題材股票對應檔案寫入 `<DATA_ROOT>/meta_data/`。"""
        self.paths.meta_data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.snapshots_dir.mkdir(parents=True, exist_ok=True)

        # 1. 寫入產業檔案 (`industry_chains_catalog.csv`)
        chain_fields = [
            "chain_id",
            "chain_order",
            "chain_name",
            "official_ic_codes",
            "mapped_l1_categories",
            "default_theme_name",
            "default_chain_tier",
            "upstream_summary",
            "midstream_summary",
            "downstream_summary",
            "active_theme_count",
            "mapped_company_count",
            "snapshot_date",
        ]
        with self.paths.industry_chains_catalog_csv.open(
            "w", encoding="utf-8-sig", newline=""
        ) as fh:
            writer = csv.DictWriter(fh, fieldnames=chain_fields)
            writer.writeheader()
            for chain_row in chain_catalog_rows:
                writer.writerow(asdict(chain_row))

        # 2. 寫入題材檔案 (`industry_themes_catalog.csv`)
        theme_fields = [
            "theme_id",
            "chain_name",
            "theme_name",
            "default_chain_tier",
            "synonyms_merged",
            "keyword_rules",
            "extraction_sources",
            "company_count",
            "primary_company_count",
            "sample_stock_ids",
            "sample_stock_names",
            "snapshot_date",
        ]
        with self.paths.industry_themes_catalog_csv.open(
            "w", encoding="utf-8-sig", newline=""
        ) as fh:
            writer = csv.DictWriter(fh, fieldnames=theme_fields)
            writer.writeheader()
            for theme_row in theme_catalog_rows:
                writer.writerow(asdict(theme_row))

        # 3. 寫入產業題材股票對應檔案 (`industry_theme_stock_map.csv`、相容別名與季度快照)
        snap_compact = compact_date_key(manifest_entry["snapshot_date"])
        snapshot_csv = (
            self.paths.snapshots_dir / f"industry_theme_stock_map_{snap_compact}.csv"
        )
        map_fields = [
            "snapshot_date",
            "available_date",
            "stock_id",
            "stock_name",
            "market_type",
            "l1_industry_category",
            "chain_name",
            "chain_tier",
            "theme_name",
            "is_primary",
            "assignment_method",
            "source_name",
            "source_tier",
            "pit_mode",
            "evidence_note",
        ]
        for target_csv in (
            self.paths.industry_theme_stock_map_csv,
            self.paths.latest_mapping_csv,
            snapshot_csv,
        ):
            with target_csv.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=map_fields)
                writer.writeheader()
                for row in stock_map_rows:
                    writer.writerow(asdict(row))

        # 4. 更新季度快照索引 `manifest.json`
        manifest_data: Dict[str, Any] = {"schema_version": SCHEMA_VERSION, "snapshots": []}
        if self.paths.snapshot_manifest_json.exists():
            try:
                loaded = json.loads(
                    self.paths.snapshot_manifest_json.read_text(encoding="utf-8")
                )
                if isinstance(loaded, dict) and isinstance(loaded.get("snapshots"), list):
                    manifest_data = loaded
            except Exception:
                pass

        snapshots_list: List[Dict[str, Any]] = [
            item
            for item in manifest_data.get("snapshots", [])
            if item.get("snapshot_date") != manifest_entry["snapshot_date"]
        ]
        entry_with_file = dict(manifest_entry)
        entry_with_file["file_name"] = snapshot_csv.name
        snapshots_list.append(entry_with_file)
        snapshots_list.sort(key=lambda x: str(x.get("available_date", "")))
        manifest_data["snapshots"] = snapshots_list
        manifest_data["latest_snapshot_date"] = manifest_entry["snapshot_date"]
        manifest_data["latest_available_date"] = manifest_entry["available_date"]

        self.paths.snapshot_manifest_json.write_text(
            json.dumps(manifest_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_pit_mapping(
        self, as_of_date: str
    ) -> Tuple[List[ThemeMappingRow], str, str, str, List[str]]:
        """載入符合 `available_date <= as_of_date` 的 PIT 產業題材股票對應表。"""
        as_of_iso = normalize_iso_date(as_of_date)
        warnings: List[str] = []

        if self.paths.snapshot_manifest_json.exists():
            try:
                manifest = json.loads(
                    self.paths.snapshot_manifest_json.read_text(encoding="utf-8")
                )
                snapshots = manifest.get("snapshots", [])
                eligible = [
                    s
                    for s in snapshots
                    if normalize_iso_date(s.get("available_date", "9999-12-31"))
                    <= as_of_iso
                ]
                if eligible:
                    chosen = sorted(
                        eligible,
                        key=lambda s: (
                            normalize_iso_date(s["available_date"]),
                            normalize_iso_date(s["snapshot_date"]),
                        ),
                    )[-1]
                    csv_path = self.paths.snapshots_dir / str(chosen["file_name"])
                    if csv_path.exists():
                        rows = self._read_mapping_csv(csv_path)
                        return (
                            rows,
                            normalize_iso_date(chosen["snapshot_date"]),
                            normalize_iso_date(chosen["available_date"]),
                            "pit_snapshot_aligned",
                            warnings,
                        )
                elif snapshots:
                    chosen = sorted(
                        snapshots,
                        key=lambda s: normalize_iso_date(s["available_date"]),
                    )[0]
                    csv_path = self.paths.snapshots_dir / str(chosen["file_name"])
                    if csv_path.exists():
                        warnings.append("theme_mapping_uses_post_hoc_snapshot")
                        rows = self._read_mapping_csv(csv_path)
                        return (
                            rows,
                            normalize_iso_date(chosen["snapshot_date"]),
                            normalize_iso_date(chosen["available_date"]),
                            "current_snapshot_replay_only",
                            warnings,
                        )
            except Exception as exc:
                warnings.append(f"snapshot_manifest_read_error:{type(exc).__name__}")

        for candidate_csv in (
            self.paths.industry_theme_stock_map_csv,
            self.paths.latest_mapping_csv,
        ):
            if candidate_csv.exists():
                rows = self._read_mapping_csv(candidate_csv)
                if rows:
                    snap_iso = normalize_iso_date(rows[0].snapshot_date)
                    avail_iso = normalize_iso_date(rows[0].available_date)
                    if avail_iso <= as_of_iso:
                        return rows, snap_iso, avail_iso, "pit_snapshot_aligned", warnings
                    warnings.append("theme_mapping_uses_post_hoc_snapshot")
                    return rows, snap_iso, avail_iso, "current_snapshot_replay_only", warnings

        warnings.append("theme_mapping_auto_built_in_memory")
        rows, meta = self.refresh_theme_mapping(
            snapshot_date=as_of_iso,
            available_date=as_of_iso,
            persist=False,
        )
        return (
            rows,
            meta["snapshot_date"],
            meta["available_date"],
            "in_memory_bootstrap",
            warnings,
        )

    @staticmethod
    def _read_mapping_csv(csv_path: Path) -> List[ThemeMappingRow]:
        rows: List[ThemeMappingRow] = []
        with csv_path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                stock_id = normalize_stock_id(r.get("stock_id"))
                if not stock_id:
                    continue
                rows.append(
                    ThemeMappingRow(
                        snapshot_date=str(r.get("snapshot_date") or ""),
                        available_date=str(r.get("available_date") or ""),
                        stock_id=stock_id,
                        stock_name=str(r.get("stock_name") or stock_id),
                        market_type=str(r.get("market_type") or ""),
                        l1_industry_category=str(r.get("l1_industry_category") or ""),
                        chain_name=str(r.get("chain_name") or "控股"),
                        chain_tier=str(r.get("chain_tier") or "整合"),
                        theme_name=str(r.get("theme_name") or "控股/集團"),
                        is_primary=str(r.get("is_primary") or "").lower()
                        in {"true", "1", "yes"},
                        assignment_method=str(
                            r.get("assignment_method") or METHOD_P4_L1_FALLBACK
                        ),
                        source_name=str(r.get("source_name") or ""),
                        source_tier=str(r.get("source_tier") or "T2"),
                        pit_mode=str(r.get("pit_mode") or "quarterly_snapshot"),
                        evidence_note=str(r.get("evidence_note") or ""),
                    )
                )
        return rows

    def inspect_stock_themes(
        self, stock_id: str, *, as_of_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """查詢單一股票所屬之產業鏈、上中下游位置、L2 題材與分配依據。"""
        norm_sid = normalize_stock_id(stock_id)
        if not norm_sid:
            raise ValueError(f"無效的 4 碼股票代號: {stock_id!r}")
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target_iso = normalize_iso_date(as_of_date or today_iso)
        rows, snap_iso, avail_iso, pit_status, warnings = self.load_pit_mapping(
            target_iso
        )
        matched = [r for r in rows if r.stock_id == norm_sid]
        return {
            "stock_id": norm_sid,
            "stock_name": matched[0].stock_name if matched else "",
            "as_of_date": target_iso,
            "mapping_snapshot_date": snap_iso,
            "mapping_available_date": avail_iso,
            "pit_status": pit_status,
            "themes": [asdict(r) for r in matched],
            "warnings": warnings,
        }

    def inspect_theme_constituents(
        self, theme_name: str, *, as_of_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """查詢單一 L2 題材（自動套用同義詞歸一化）之所有概念股清單與分配方法。"""
        canonical = normalize_theme_name(theme_name)
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target_iso = normalize_iso_date(as_of_date or today_iso)
        rows, snap_iso, avail_iso, pit_status, warnings = self.load_pit_mapping(
            target_iso
        )
        matched = [r for r in rows if r.theme_name == canonical]
        return {
            "requested_theme": theme_name,
            "canonical_theme_name": canonical,
            "chain_name": matched[0].chain_name if matched else "",
            "company_count": len(matched),
            "as_of_date": target_iso,
            "mapping_snapshot_date": snap_iso,
            "pit_status": pit_status,
            "constituents": [asdict(r) for r in matched],
            "warnings": warnings,
        }

    def get_status(self) -> Dict[str, Any]:
        """回傳三大產業題材檔案之路徑與目前就緒狀態。"""
        manifest_info: Dict[str, Any] = {}
        if self.paths.snapshot_manifest_json.exists():
            try:
                manifest_info = json.loads(
                    self.paths.snapshot_manifest_json.read_text(encoding="utf-8")
                )
            except Exception:
                manifest_info = {"error": "manifest_corrupted"}
        return {
            "schema_version": SCHEMA_VERSION,
            "data_root": str(self.paths.data_root),
            "companies_file": str(self.paths.companies_file),
            "companies_file_exists": self.paths.companies_file.exists(),
            "industry_chains_catalog_csv": str(self.paths.industry_chains_catalog_csv),
            "industry_chains_catalog_exists": self.paths.industry_chains_catalog_csv.exists(),
            "industry_themes_catalog_csv": str(self.paths.industry_themes_catalog_csv),
            "industry_themes_catalog_exists": self.paths.industry_themes_catalog_csv.exists(),
            "industry_theme_stock_map_csv": str(self.paths.industry_theme_stock_map_csv),
            "industry_theme_stock_map_exists": self.paths.industry_theme_stock_map_csv.exists(),
            "snapshot_manifest_json": str(self.paths.snapshot_manifest_json),
            "manifest_summary": {
                "latest_snapshot_date": manifest_info.get("latest_snapshot_date"),
                "latest_available_date": manifest_info.get("latest_available_date"),
                "snapshot_count": len(manifest_info.get("snapshots", [])),
            },
        }


# ---------------------------------------------------------------------------
# 7. CLI 入口 (專供建置三大檔案、查詢單一個股或題材對應)
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m decision_module.industry_theme_map",
        description="台股 L2 產業鏈與題材萃取、對應分配與三檔建置工具 (不介入現有選股/UI流程)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd_name in ("build-files", "refresh-mapping"):
        p_build = sub.add_parser(
            cmd_name,
            help="執行產業與題材萃取分配，產出產業檔案、題材檔案與產業題材股票對應檔案",
        )
        p_build.add_argument(
            "--snapshot-date", default=None, help="快照基準日 (YYYY-MM-DD)"
        )
        p_build.add_argument(
            "--available-date", default=None, help="PIT 可見日 (YYYY-MM-DD)"
        )
        p_build.add_argument(
            "--min-companies",
            type=int,
            default=3,
            help="過濾少於 N 家公司的長尾題材 (預設 3)",
        )
        p_build.add_argument(
            "--fetch-official-ic",
            action="store_true",
            help="是否連線向官方 ic.tpex.org.tw 抓取最新產業鏈節點",
        )
        p_build.add_argument(
            "--dry-run",
            action="store_true",
            help="僅於記憶體計算並印出摘要，不寫入磁碟",
        )

    p_stock = sub.add_parser(
        "inspect-stock", help="查詢單一股票所屬之產業鏈、L2 題材與分配方法"
    )
    p_stock.add_argument("--stock-id", required=True, help="4 碼股票代號，例如 2330")
    p_stock.add_argument("--as-of-date", default=None, help="PIT 查詢日期 (YYYY-MM-DD)")

    p_theme = sub.add_parser(
        "inspect-theme", help="查詢單一 L2 題材之所有概念股與分配來源"
    )
    p_theme.add_argument(
        "--theme-name", required=True, help="題材名稱或同義詞，例如 CoWoS 或 玻纖布"
    )
    p_theme.add_argument("--as-of-date", default=None, help="PIT 查詢日期 (YYYY-MM-DD)")

    sub.add_parser("status", help="檢視三大產業題材檔案路徑與就緒狀態")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    service = IndustryThemeMapService()

    if args.command in {"build-files", "refresh-mapping"}:
        rows, manifest = service.refresh_theme_mapping(
            snapshot_date=args.snapshot_date,
            available_date=args.available_date,
            min_companies=args.min_companies,
            fetch_official_ic=args.fetch_official_ic,
            persist=not args.dry_run,
        )
        print(
            json.dumps(
                {
                    "action": args.command,
                    "persisted": not args.dry_run,
                    "manifest": manifest,
                    "sample_stock_map_rows": [asdict(r) for r in rows[:5]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "inspect-stock":
        info = service.inspect_stock_themes(
            args.stock_id, as_of_date=args.as_of_date
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.command == "inspect-theme":
        info = service.inspect_theme_constituents(
            args.theme_name, as_of_date=args.as_of_date
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        print(json.dumps(service.get_status(), ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
