"""從封存的重述資料列訓練不可變更的研究版配置 release。"""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_module.restated_h5_training_runner import main


if __name__ == "__main__":
    raise SystemExit(main())
