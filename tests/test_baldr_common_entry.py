"""由真實新 PID 核對 launcher、直接 Qt script 與 -m 的共用設定。"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


def isolated_environment(tmp_path):
    market, output = tmp_path / "行情 data", tmp_path / "研究 output"
    config = tmp_path / "settings.json"
    config.write_text(json.dumps({"DATA_ROOT": str(market), "OUTPUT_ROOT": str(output)}), encoding="utf-8")
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith("PERSONAL_") or name in {"DATA_ROOT", "OUTPUT_ROOT", "RESEARCH_STATE_ROOT", "BALDR_CONFIG", "MPLCONFIGDIR"}:
            env.pop(name)
    env.update(BALDR_CONFIG=str(config), LOCALAPPDATA=str(tmp_path / "local"),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8", QT_QPA_PLATFORM="offscreen")
    return env


def run_entry(args, env, cwd):
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env,
                          text=True, encoding="utf-8", capture_output=True, timeout=30)


def test_three_entries_read_same_json_identity_and_paths_in_new_processes(tmp_path):
    env = isolated_environment(tmp_path)
    launcher = run_entry([str(REPOSITORY / "baldr_launcher.py"), "--launch-info"], env, tmp_path)
    direct = run_entry([str(REPOSITORY / "ui_qt/main.py"), "--launch-info"], env, tmp_path)
    module = run_entry(["-m", "ui_qt.main", "--launch-info"], env, REPOSITORY)
    for result in (launcher, direct, module):
        assert result.returncode == 0, result.stderr
    infos = [json.loads(result.stdout) for result in (launcher, direct, module)]
    assert infos[0] == infos[1] == infos[2]
    info = infos[0]
    assert info["settings"]["runtime_state_root"] == str(tmp_path / "研究 output/application_state")
    assert info["settings"]["ml_registry_repository_root"] == str(tmp_path / "local/baldr/research_state")
    assert info["build"]["channel"] == "development"
    assert len(info["build"]["source_commit"]) == 40
    assert info["build"]["source_commit"][:12] in info["build"]["version"]


@pytest.mark.parametrize("value", ["relative/data", None])
def test_invalid_json_is_rejected_by_both_entries_before_startup(tmp_path, value):
    env = isolated_environment(tmp_path)
    Path(env["BALDR_CONFIG"]).write_text(json.dumps({"DATA_ROOT": value}), encoding="utf-8")
    for script in ("baldr_launcher.py", "ui_qt/main.py"):
        result = run_entry([str(REPOSITORY / script), "--launch-info"], env, tmp_path)
        assert result.returncode != 0
        assert "DATA_ROOT" in result.stderr
        assert not (tmp_path / "研究 output").exists()
