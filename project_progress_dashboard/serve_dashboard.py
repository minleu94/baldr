"""提供 Baldr 進度 dashboard 的 loopback-only 唯讀刷新 API。"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE = REPO_ROOT / "ui_qt" / "main_window_coordinator.py"
SNAPSHOT = REPO_ROOT / "docs" / "00_core" / "PROJECT_SNAPSHOT.md"
H20_EVIDENCE = REPO_ROOT / "docs" / "06_qa" / "BALDR_A02_H20_GROSS_MODEL_20261006.md"
ALLOCATION_EVIDENCE = REPO_ROOT / "docs" / "06_qa" / "RESTATED_ALLOCATION_REPAIR_TRAINING_2026_09_23.md"
ALLOWED_STATIC_ROOTS = ("project_progress_dashboard", "docs")
MAX_STATIC_BYTES = 5 * 1024 * 1024


def iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def file_digest(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def assigned_value(tree: ast.Module, name: str) -> ast.expr | None:
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in statement.targets
        ):
            return statement.value
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            if statement.target.id == name:
                return statement.value
    return None


def call_rows(value: ast.expr | None, function_name: str, arg_count: int) -> list[list[str]]:
    if not isinstance(value, (ast.Tuple, ast.List)):
        return []
    rows: list[list[str]] = []
    for item in value.elts:
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name):
            continue
        if item.func.id != function_name or len(item.args) < arg_count:
            continue
        try:
            row = [ast.literal_eval(argument) for argument in item.args[:arg_count]]
        except (ValueError, TypeError):
            continue
        if all(isinstance(part, str) for part in row):
            rows.append(row)
    return rows


def read_route_schema() -> dict[str, object]:
    try:
        source = ROUTE_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(ROUTE_SOURCE))
        groups = call_rows(assigned_value(tree, "PRIMARY_NAVIGATION"), "WorkspaceDefinition", 2)
        route_rows = call_rows(assigned_value(tree, "PRODUCT_ROUTES"), "ProductRoute", 4)
        routes = [
            {"id": route_id, "group": group_id, "label": label, "workspace": workspace}
            for route_id, group_id, label, workspace in route_rows
        ]
        route_groups = [
            {"id": group_id, "label": label}
            for group_id, label in groups
        ]
        if not route_groups or not routes:
            raise ValueError("目前導覽定義不是可安全解析的 literal route list")
        return {
            "groups": route_groups,
            "routes": routes,
            "modifiedAt": iso_mtime(ROUTE_SOURCE),
            "sourceSha256": file_digest(ROUTE_SOURCE),
        }
    except (OSError, SyntaxError, ValueError) as error:
        return {"groups": [], "routes": [], "modifiedAt": iso_mtime(ROUTE_SOURCE), "error": str(error)}


def snapshot_entries() -> tuple[str | None, list[dict[str, str]]]:
    try:
        text = SNAPSHOT.read_text(encoding="utf-8-sig")
    except OSError:
        return None, []
    paragraphs = re.split(r"\n\s*\n", text)
    entries: list[dict[str, str]] = []
    for paragraph in paragraphs:
        content = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        match = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$", content)
        if not match:
            continue
        entries.append({"date": match.group(1), "text": content[:700]})
        if len(entries) == 5:
            break
    return (entries[0]["date"] if entries else None), entries


def paragraph_containing(text: str, needle: str) -> str | None:
    for paragraph in re.split(r"\n\s*\n", text):
        compact = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if needle in compact:
            return compact[:650]
    return None


def read_ml_evidence() -> dict[str, object]:
    try:
        h20_text = H20_EVIDENCE.read_text(encoding="utf-8-sig")
    except OSError:
        h20_text = ""
    h20_no_fit = "沒有載入三個來源未證候選、真 fit" in h20_text
    h20_summary = paragraph_containing(h20_text, "沒有載入三個來源未證候選、真 fit")

    try:
        allocation_text = ALLOCATION_EVIDENCE.read_text(encoding="utf-8-sig")
    except OSError:
        allocation_text = ""
    fit_match = re.search(r"Final fit \*\*([\d,]+) 列\*\*", allocation_text)
    dataset_match = re.search(r"資料 \*\*([\d,]+) 列\*\*", allocation_text)
    fit_rows = int(fit_match.group(1).replace(",", "")) if fit_match else None
    dataset_rows = int(dataset_match.group(1).replace(",", "")) if dataset_match else None
    training_date = re.search(r"(20\d{2})[_-](\d{2})[_-](\d{2})", ALLOCATION_EVIDENCE.name)
    date_value = "-".join(training_date.groups()) if training_date else None
    allocation_summary = paragraph_containing(allocation_text, "不支持把 candidate 升格")

    return {
        "h20": {
            "statusLabel": "A02 lane 未做真實 fit" if h20_no_fit else "A02 訓練狀態需人工核對",
            "summary": h20_summary or "目前無法從 A02 來源確認真實 fit 狀態；不推估作業百分比。",
            "modifiedAt": iso_mtime(H20_EVIDENCE),
            "sourceSha256": file_digest(H20_EVIDENCE),
            "evidenceReadable": bool(h20_text),
        },
        "allocation": {
            "statusLabel": "此份 H5 訓練收據已完成" if fit_rows is not None else "未讀到可辨識的完整 fit 收據",
            "trainingDate": date_value or "日期未知",
            "datasetRows": dataset_rows,
            "fitRows": fit_rows,
            "progress": 100 if fit_rows is not None else None,
            "summary": allocation_summary or "訓練評估摘要需由權威 QA 人工確認；不能只靠列數授予資格。",
            "modifiedAt": iso_mtime(ALLOCATION_EVIDENCE),
            "sourceSha256": file_digest(ALLOCATION_EVIDENCE),
            "evidenceReadable": bool(allocation_text),
        },
    }


def read_storage_status() -> dict[str, object]:
    """以應用程式相同的唯讀、有界服務盤點明示儲存根。"""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from app_module.application_bootstrap import resolve_application_settings
        from app_module.storage_overview import inspect_storage

        settings = resolve_application_settings(resource_root=REPO_ROOT, frozen=False)
        data_root = Path(settings.environment["DATA_ROOT"])
        output_root = Path(settings.environment["OUTPUT_ROOT"])
        profile = os.environ.get("PROFILE", "prod").strip().lower()
        if profile == "test":
            data_root = data_root / "_test"
            output_root = output_root / "_test"
        roots = {
            "市場資料": data_root,
            "產品輸出": output_root,
            "應用狀態": settings.runtime_state_root,
        }
        overview = inspect_storage(roots, REPO_ROOT / "dist")
        return {
            "inventoryPath": overview.inventory_path,
            "inventoryStatus": overview.inventory_status,
            "inventoryAvailable": overview.inventory_available,
            "limited": overview.limited,
            "locations": [
                {
                    "name": item.name,
                    "path": item.path,
                    "totalBytes": item.total_bytes,
                    "freeBytes": item.free_bytes,
                    "status": item.status,
                }
                for item in overview.locations
            ],
            "artifacts": [
                {
                    "name": item.name,
                    "measuredBytes": item.measured_bytes,
                    "complete": item.complete,
                    "status": item.status,
                }
                for item in overview.artifacts
            ],
            "source": "app_module.storage_overview.inspect_storage",
        }
    except Exception as error:
        return {
            "inventoryPath": None,
            "inventoryStatus": "儲存盤點未完成；設定解析或唯讀盤點失敗",
            "inventoryAvailable": False,
            "limited": False,
            "locations": [],
            "artifacts": [],
            "source": "app_module.storage_overview.inspect_storage",
            "error": str(error).splitlines()[0][:400],
        }


def git_facts() -> dict[str, object]:
    def git(*arguments: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT), *arguments],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    commit = git("rev-parse", "--short", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=normal")
    dirty_count = len(status.splitlines()) if status is not None else None
    return {"branch": branch or "未知", "commit": commit or "未知", "dirtyCount": dirty_count if dirty_count is not None else "未知"}


def build_refresh_payload() -> dict[str, object]:
    latest_date, entries = snapshot_entries()
    ml_status = read_ml_evidence()
    ml_status["snapshotNote"] = next(
        (entry for entry in entries if re.search(r"\bML\b|模型", entry["text"], re.IGNORECASE)),
        None,
    )
    storage_status = read_storage_status()
    storage_status["refreshedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "schema": "baldr-dashboard-refresh.v1",
        "refreshedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "repository": git_facts(),
        "routeSchema": read_route_schema(),
        "snapshot": {
            "latestDate": latest_date,
            "entries": entries,
            "modifiedAt": iso_mtime(SNAPSHOT),
            "sourceSha256": file_digest(SNAPSHOT),
        },
        "ml": ml_status,
        "storage": storage_status,
    }


def static_file_for_path(request_path: str) -> Path | None:
    decoded = unquote(request_path).lstrip("/")
    if not decoded:
        decoded = "project_progress_dashboard/index.html"
    if "\\" in decoded or any(part in {".", ".."} for part in Path(decoded).parts):
        return None
    if not any(decoded == root or decoded.startswith(root + "/") for root in ALLOWED_STATIC_ROOTS):
        return None
    candidate = (REPO_ROOT / decoded).resolve()
    if not candidate.is_relative_to(REPO_ROOT) or not candidate.is_file():
        return None
    if candidate.suffix.lower() not in {".html", ".md", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp"}:
        return None
    try:
        if candidate.stat().st_size > MAX_STATIC_BYTES:
            return None
    except OSError:
        return None
    return candidate


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "BaldrDashboard/1.0"

    def do_GET(self) -> None:
        request_path = urlsplit(self.path).path
        if request_path == "/api/ping":
            payload = json.dumps({"service": "BaldrDashboard", "readOnly": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/api/refresh":
            payload = json.dumps(build_refresh_payload(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)
            return

        target = static_file_for_path(request_path)
        if target is None:
            self.send_error(404, "Not found")
            return
        content = target.read_bytes()
        content_type = "text/markdown" if target.suffix.lower() == ".md" else "text/html" if target.suffix.lower() == ".html" else "application/octet-stream"
        if target.suffix.lower() in {".html", ".md", ".css", ".js"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        self.send_error(405, "Read-only dashboard")

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[dashboard] {self.address_string()} {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Baldr dashboard 的 loopback-only 唯讀伺服器")
    parser.add_argument("--port", type=int, default=8765, help="本機服務連接埠（預設 8765；0 表示由作業系統分配）")
    parser.add_argument("--open", action="store_true", help="啟動後開啟 dashboard；若服務已在執行則直接開啟現有服務")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port 必須是 0 或介於 1 到 65535")
    requested_port = args.port
    if args.open and requested_port != 0:
        try:
            with urlopen(f"http://127.0.0.1:{requested_port}/api/ping", timeout=0.7) as response:
                existing = json.loads(response.read(1024).decode("utf-8"))
            if isinstance(existing, dict) and existing.get("service") == "BaldrDashboard" and existing.get("readOnly") is True:
                url = f"http://127.0.0.1:{requested_port}/project_progress_dashboard/index.html"
                print(f"Dashboard server already running: {url}")
                webbrowser.open_new_tab(url)
                return
        except (OSError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
            pass
    try:
        server = ThreadingHTTPServer(("127.0.0.1", requested_port), DashboardHandler)
    except OSError as requested_error:
        if requested_port == 0:
            parser.error(f"無法建立本機唯讀服務：{requested_error}")
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        except OSError as fallback_error:
            parser.error(
                f"本機連接埠 {requested_port} 無法使用：{requested_error}；"
                f"作業系統自動分配連接埠也失敗：{fallback_error}。"
            )
        actual_port = int(server.server_address[1])
        print(f"本機連接埠 {requested_port} 無法使用，已改用作業系統分配的連接埠 {actual_port}。")
    else:
        actual_port = int(server.server_address[1])
    url = f"http://127.0.0.1:{actual_port}/project_progress_dashboard/index.html"
    print(f"Dashboard: {url}")
    print("Loopback-only read-only server. Use the dashboard refresh button; press Ctrl+C to stop.")
    if args.open:
        webbrowser.open_new_tab(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
