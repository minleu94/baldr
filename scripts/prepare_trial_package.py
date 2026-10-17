"""固定試用包的明選首次設定；既有私人環境不在此命令範圍。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_module.trial_first_setup import prepare_trial_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-directory", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    receipt = prepare_trial_package(args.package_directory, args.manifest_sha256)
    print("試用包已設定；既有保存內容未覆寫。收據：" + str(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
