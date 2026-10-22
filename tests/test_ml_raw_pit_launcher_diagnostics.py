"""以隔離的假 Python executable 驗證 Windows launcher 診斷。"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_LAUNCHER = REPO_ROOT / "scripts" / "scheduled" / "run_ml_raw_pit_refresh.cmd"


_CSHARP_STUB = r'''using System;
using System.IO;
public static class FakePython
{
    public static int Main(string[] args)
    {
        Console.Out.WriteLine("FAKE_PYTHON_STDOUT_MARKER");
        Console.Error.WriteLine("FAKE_PYTHON_STDERR_MARKER");
        string marker = Environment.GetEnvironmentVariable("BALDR_TEST_FAKE_MARKER");
        File.WriteAllText(marker, String.Join("\n", args));
        return 7;
    }
}'''


@pytest.fixture
def fake_python(tmp_path: Path) -> Path:
    powershell = shutil.which("powershell.exe")
    if os.name != "nt" or powershell is None:
        pytest.skip("requires Windows PowerShell Add-Type and cmd.exe")
    source = tmp_path / "fake python source.cs"
    executable = tmp_path / "fake python.exe"
    source.write_text(_CSHARP_STUB, encoding="utf-8")
    env = os.environ.copy()
    env["BALDR_TEST_STUB_SOURCE"] = str(source)
    env["BALDR_TEST_STUB_EXE"] = str(executable)
    compile_command = (
        "Add-Type -TypeDefinition (Get-Content -Raw -LiteralPath $env:BALDR_TEST_STUB_SOURCE) "
        "-OutputAssembly $env:BALDR_TEST_STUB_EXE -OutputType ConsoleApplication -ErrorAction Stop"
    )
    compiled = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            compile_command,
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr or compiled.stdout
    assert executable.is_file()
    return executable


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "isolated repo with spaces"
    scheduled = repo / "scripts" / "scheduled"
    scheduled.mkdir(parents=True)
    shutil.copyfile(SOURCE_LAUNCHER, scheduled / SOURCE_LAUNCHER.name)
    return repo


def _run_launcher(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    launcher = repo / "scripts" / "scheduled" / SOURCE_LAUNCHER.name
    command = f'cmd.exe /d /s /c ""{launcher}""'
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        cwd=repo,
        timeout=60,
        check=False,
    )


def _launcher_environment(
    tmp_path: Path, fake_python: Path, output_root: Path, marker: Path
) -> dict[str, str]:
    data_root = tmp_path / "formal data root with spaces"
    data_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for name in (
        "PYTHON",
        "PYTHONHOME",
        "PYTHONPATH",
        "BALDR_PYTHON",
        "BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE",
        "BALDR_ENABLE_ML_DAILY_SOURCE_ROW_PROJECTION",
    ):
        env.pop(name, None)
    env["BALDR_PYTHON"] = str(fake_python)
    env["DATA_ROOT"] = str(data_root)
    env["OUTPUT_ROOT"] = str(output_root)
    env["BALDR_TEST_FAKE_MARKER"] = str(marker)
    return env


def test_launcher_captures_both_streams_preserves_exit_and_uses_unique_logs(
    tmp_path: Path, fake_python: Path
) -> None:
    repo = _fake_repo(tmp_path)
    output_root = tmp_path / "output root with spaces"
    marker = tmp_path / "fake invocation args.txt"
    env = _launcher_environment(tmp_path, fake_python, output_root, marker)

    first = _run_launcher(repo, env)
    second = _run_launcher(repo, env)

    assert first.returncode == 7
    assert second.returncode == 7
    logs_root = output_root / "scheduled" / "ml_raw_pit_refresh" / "launcher_logs"
    run_dirs = sorted(path for path in logs_root.iterdir() if path.is_dir())
    assert len(run_dirs) == 2
    assert run_dirs[0] != run_dirs[1]
    logs = [(path / "launcher.log").read_text(encoding="utf-8") for path in run_dirs]
    for content in logs:
        assert "task=baldr-ml-raw-pit-refresh-daily" in content
        assert "started_at_utc=" in content
        assert "local_timezone=" in content
        assert f'repository_root="{repo}"' in content
        assert f'data_root="{env["DATA_ROOT"]}"' in content
        assert f'output_root="{output_root}"' in content
        assert "FAKE_PYTHON_STDOUT_MARKER" in content
        assert "FAKE_PYTHON_STDERR_MARKER" in content
        assert "completed_at_utc=" in content
        assert "child_exit_code=7" in content
    invocation = marker.read_text(encoding="utf-8")
    assert "--data-root" in invocation
    assert str(Path(env["DATA_ROOT"])) in invocation
    assert "--output-root" in invocation
    assert str(output_root) in invocation
    assert "--database" in invocation
    assert "--capture-prospective-daily-price-candidate" in invocation
    assert "--project-daily-source-rows" in invocation


def test_launcher_log_creation_failure_is_nonzero_and_does_not_start_python(
    tmp_path: Path, fake_python: Path
) -> None:
    repo = _fake_repo(tmp_path)
    output_root = tmp_path / "output root with spaces"
    blocked_path = output_root / "scheduled" / "ml_raw_pit_refresh" / "launcher_logs"
    blocked_path.parent.mkdir(parents=True)
    blocked_path.write_text("block directory creation", encoding="utf-8")
    marker = tmp_path / "fake invocation args.txt"
    env = _launcher_environment(tmp_path, fake_python, output_root, marker)

    result = _run_launcher(repo, env)

    assert result.returncode == 73
    assert "launcher log setup failed" in result.stderr
    assert not marker.exists()
    assert blocked_path.is_file()
