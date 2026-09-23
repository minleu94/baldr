"""建構價格修訂後、非 PIT 的 ML 研究資料集。"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.ml_restatement_research_dataset import main


if __name__ == "__main__":
    raise SystemExit(main())
