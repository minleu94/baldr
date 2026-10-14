"""document_control 的唯讀暫時視圖；不建立索引、不 import 產品。"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import stat
import subprocess
from typing import Any

from scripts import document_control as dc

ISSUES = "docs/00_core/DOCUMENT_GOVERNANCE_ISSUES.json"
TEXT_SUFFIXES = {".md", ".py", ".json", ".csv", ".txt", ".toml", ".yaml", ".yml", ".ini", ".ps1", ".bat"}
ISSUE_STATUSES = {"policy_resolved_external_unknown", "denominator_resolved_trigger_unknown",
    "denominator_resolved_raw_unknown", "caller_fixed_qualification_unknown", "wording_resolved_acceptance_unknown",
    "resolved", "scope_resolved_source_unknown", "optional_nonblocking", "engineering_fixed_natural_unknown",
    "open_external_unknown", "blocked"}


def bounded_bytes(target: Path) -> bytes:
    if target.stat().st_size > 2_000_000:
        raise ValueError("source_size_limit")
    with target.open("rb") as handle:
        raw = handle.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("source_size_limit")
    return raw


def linked_path(root: Path, path: str) -> bool:
    """resolve 不保留 link 身份；在讀 bytes 前另查 lexical components／Windows reparse。"""
    dc.confined(root, path)
    current = root / path
    while current != root:
        if current.is_symlink():
            return True
        try:
            if getattr(current.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return True
        except FileNotFoundError:
            pass
        current = current.parent
    return False


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=root,
                            capture_output=True, encoding="utf-8", errors="strict", check=False)
    if result.returncode:
        raise ValueError(f"Git 無法取得來源版本：{' '.join(args)}")
    return result.stdout


def tree(root: Path, ref: str = "HEAD") -> dict[str, dict[str, str]]:
    # 將 ref 解析成 commit，避免 options／pathspec 被當成來源。
    commit = git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").strip()
    result = {}
    for entry in git(root, "ls-tree", "-r", "-z", commit).split("\0"):
        if entry:
            metadata, path = entry.split("\t", 1)
            mode, kind, oid = metadata.split()
            result[path] = {"mode": mode, "kind": kind, "blob_oid": oid}
    return result


def changes(root: Path) -> dict[str, str]:
    items = iter(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0"))
    result = {}
    for item in items:
        if not item:
            continue
        state, path = item[:2], item[3:]
        result[path] = state
        if "R" in state or "C" in state:
            old = next(items)
            result.setdefault(old, "rename_source")
    return result


def classification(path: str) -> str:
    if path.startswith("docs/09_archive/") or "_HISTORY" in path or "/originals/" in path:
        return "historical"
    if "/target_architecture_" in path or path.endswith("target_system_architecture.md"):
        return "target_only"
    if path.startswith("docs/06_qa/"):
        return "dated_evidence_or_evidence_navigation"
    if path.endswith("README.md") or "INDEX" in path or path == "PROJECT_NAVIGATION.md":
        return "navigation"
    if path.endswith(".py"):
        return "test" if path.startswith("tests/") else "code"
    if path in {dc.FEATURE_MAP, ISSUES}:
        return "routing_or_issue_metadata"
    return "scoped_contract_or_status" if path.endswith(".md") else "configuration_or_asset"


def source(root: Path, path: str, tracked: dict[str, Any], dirty: dict[str, str]) -> dict[str, Any]:
    target = dc.confined(root, path)
    meta: dict[str, Any] = {"path": path, "classification": classification(path),
                            "head_blob_oid": tracked.get(path, {}).get("blob_oid"),
                            "git_status": dirty.get(path, "clean" if path in tracked else "untracked_or_ignored")}
    if tracked.get(path, {}).get("mode") == "120000" or linked_path(root, path) or not target.is_file():
        meta.update(available=False, reason="missing_or_symlink")
    elif path in tracked and target.suffix in TEXT_SUFFIXES and target.stat().st_size <= 2_000_000:
        meta.update(available=True, working_sha256=hashlib.sha256(bounded_bytes(target)).hexdigest())
    else:
        meta.update(available=False, reason="untracked_ignored_binary_or_size_limit")
    return meta


def symbols(content: str, wanted: str | None = None) -> list[dict[str, Any]]:
    parsed = ast.parse(content)
    result: list[dict[str, Any]] = []

    def visit(nodes: list[ast.stmt], prefix: str = "") -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                if wanted is None or name == wanted:
                    if isinstance(node, ast.ClassDef):
                        signature = "class " + name + "(" + ", ".join(ast.unparse(b) for b in node.bases) + ")"
                        fields = [ast.unparse(item) for item in node.body if isinstance(item, ast.AnnAssign)]
                    else:
                        signature = ("async " if isinstance(node, ast.AsyncFunctionDef) else "") + name + "(" + ast.unparse(node.args) + ")"
                        if node.returns:
                            signature += " -> " + ast.unparse(node.returns)
                        fields = []
                    result.append({"symbol": name, "line": node.lineno, "signature": signature, "fields": fields})
                if isinstance(node, ast.ClassDef):
                    visit(node.body, name + ".")
    visit(parsed.body)
    return result


def excerpt(content: str, selector: dict[str, Any]) -> tuple[str, list[int], bool]:
    lines = content.splitlines()
    if selector["path"].endswith(".py") and not selector.get("symbol") and not selector.get("contains"):
        records = symbols(content)[:12]
        return json.dumps(records, ensure_ascii=False), [record["line"] for record in records], True
    if selector.get("symbol"):
        records = symbols(content, selector["symbol"])
        if not records:
            raise ValueError(f"symbol 缺件：{selector['symbol']}")
        return json.dumps(records, ensure_ascii=False), [record["line"] for record in records], False
    if selector.get("preamble"):
        end = next((i for i,line in enumerate(lines[1:],1) if line.startswith("## ")), len(lines))
        selected = list(enumerate(lines[:end],1))
    elif selector.get("contains"):
        terms = selector["contains"]
        selected = [(i+1, line) for i, line in enumerate(lines) if any(term.casefold() in line.casefold() for term in terms)]
    elif selector.get("section"):
        anchor = selector["section"]
        selected = []
        active_level = 0
        for i, line in enumerate(lines):
            if line.startswith("#") and " " in line:
                level = len(line.split(" ", 1)[0])
                if active_level and level <= active_level:
                    break
                if not active_level and anchor.casefold() in line.casefold():
                    active_level = level
            if active_level:
                selected.append((i+1, line))
    else:
        # 無精確 selector 時只給標題，明示尚須深入，不假裝讀過正文。
        selected = [(i+1, line) for i, line in enumerate(lines) if line.startswith("#")][:12]
    if not selected:
        raise ValueError("selector 無命中")
    return "\n".join(line for _, line in selected) + "\n", [i for i, _ in selected], not bool(selector.get("contains") or selector.get("section") or selector.get("preamble"))


def metadata_source(root: Path, path: str, tracked: dict[str, Any], dirty: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    if path not in {dc.FEATURE_MAP, ISSUES} or tracked.get(path,{}).get("mode") == "120000" or linked_path(root,path):
        raise ValueError("routing／issue metadata不得透過link讀取")
    raw = bounded_bytes(dc.confined(root,path))
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value,dict):
        raise ValueError("metadata根節點必須是object")
    return value, {"path":path,"head_blob_oid":tracked.get(path,{}).get("blob_oid"),
                   "git_status":dirty.get(path,"clean" if path in tracked else "untracked_or_ignored"),
                   "working_sha256":hashlib.sha256(raw).hexdigest()}


def issue_view(root: Path, ids: list[str] | None = None, *, register: dict[str, Any] | None = None) -> dict[str, Any]:
    if register is None:
        register, _ = metadata_source(root,ISSUES,tree(root),changes(root))
    if register.get("schema_version") != "baldr-governance-issues.v1":
        raise ValueError("Issue schema 不符")
    records = register["issues"]
    if ids is not None:
        records = [item for item in records if item["id"] in ids]
    return {"issues": records, "authority": register["authority"],
            "limitation": "已解治理範圍不重開；owner=null 表示沒有具名責任證據；外部資格不因整理而通過。"}


def context(root: Path, *, domain: str, request: str = "", level: int = 2,
            inspect: list[str] | None = None, changed: list[str] | None = None,
            max_chars: int = 12000, include_history: bool = False) -> dict[str, Any]:
    if not 1000 <= max_chars <= 100000 or level not in range(5):
        raise ValueError("level 必須為 0–4；max_chars 必須為 1000–100000")
    if level == 4 and not include_history:
        raise ValueError("Level 4 必須明示 --include-history")
    inspect = [p.replace("\\", "/") for p in inspect or []]
    changed = [p.replace("\\", "/") for p in changed or []]
    head = git(root, "rev-parse", "HEAD").strip()
    tracked, dirty = tree(root,head), changes(root)
    mapping, map_meta = metadata_source(root,dc.FEATURE_MAP,tracked,dirty)
    register, issue_meta = metadata_source(root,ISSUES,tracked,dirty)
    routes = mapping.get("reading_routes", {})
    if domain not in routes:
        raise ValueError("未知閱讀領域；可用：" + ", ".join(routes))
    rule = routes[domain]
    selected_features = [f for f in mapping["features"] if f["id"] in rule["features"]]
    candidates = list(mapping["context_entry"])
    if level >= 1:
        candidates += rule.get("entry", [])
    if level >= 2:
        candidates += rule.get("documents", [])
    if level >= 3:
        candidates += rule.get("code", []) + rule.get("tests", [])
        candidates += [{"path":p} for p in inspect or []]
    elif inspect:
        for path in inspect:
            dc.confined(root, path)
    if level == 4:
        candidates += rule.get("history", [])
    for path in changed or []:
        dc.confined(root, path)
    read_sources, unknown = [], []
    used = 0
    seen: set[tuple[str, str]] = set()
    for selector in candidates:
        path = selector["path"].replace("\\", "/")
        key = (path, json.dumps(selector, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        meta = source(root, path, tracked, dirty)
        if classification(path) == "historical" and not include_history:
            unknown.append({"path":path, "reason":"history_requires_explicit_opt_in"})
            continue
        if path not in tracked or not meta["available"] or Path(path).suffix not in {".md", ".py"}:
            unknown.append({"path":path, "reason":"not_committed_text_or_missing; 不自動讀ignored/private evidence"})
            continue
        target = dc.confined(root, path)
        if target.stat().st_size > 2_000_000:
            unknown.append({"path":path, "reason":"source_size_limit"})
            continue
        try:
            raw = bounded_bytes(target)
            if hashlib.sha256(raw).hexdigest() != meta["working_sha256"]:
                raise ValueError("source_changed_during_read")
            text, line_numbers, headings_only = excerpt(raw.decode("utf-8-sig"), selector)
        except (ValueError, SyntaxError, UnicodeError) as exc:
            unknown.append({"path":path, "reason":str(exc)})
            continue
        # 不截斷一個命中到誤失安全限制；整個摘錄放不下便明列未讀。
        if used + len(text) > max_chars:
            unknown.append({"path":path, "reason":"budget_omitted", "required_characters":len(text)})
            continue
        used += len(text)
        read_sources.append({**meta, "selector":selector, "lines":line_numbers, "text":text,
                             "headings_only":headings_only})
        if headings_only:
            unknown.append({"path":path,"reason":"headings_only; 正文及行為尚未核讀"})
    payload = "".join(item["text"] for item in read_sources)
    if git(root,"rev-parse","HEAD").strip() != head:
        unknown.append({"reason":"HEAD_changed_during_context; 需重建視圖"})
    return {"schema_version":"baldr-task-context.v1", "task":request, "domain":domain, "level":level,
            "source_version":{"head":head,"working_tree_changes":dirty,"metadata_sources":[map_meta,issue_meta]},
            "relevant_docs_code_contracts_tests_status":read_sources,
            "features":[f["id"] for f in selected_features],
            "related_paths":{key:sorted({p for f in selected_features for p in f[key]}) for key in ["contracts","code","tests","evidence"]},
            "known_issues":issue_view(root, rule.get("issues", []), register=register),
            "documentation_impact":{"changed_paths":changed or [],"required_review":sorted({p.split("#",1)[0] for f in mapping["features"] if dc.match_paths(changed or [],f["change_patterns"]) for p in f["sync_documents"]})},
            "constraints":{"authority":"docs/agents/shared_context.md", "inspection_is_not_change":True,
                           "runtime_tests_and_gate":"unknown; 靜態存在、舊QA、目標架構不能證明現行接受",
                           "budget_scope":"source excerpt characters only; metadata/envelope 另計；未知不算完成"},
            "unverified_unknown":unknown,
            "metrics":{"files":len({item["path"] for item in read_sources}),"characters":len(payload),
                       "utf8_bytes":len(payload.encode("utf-8")),"estimated_tokens":math.ceil(len(payload.encode("utf-8"))/3),
                       "token_method":"ceil(UTF8 bytes/3), 非模型tokenizer實測","character_budget":max_chars}}


def trace(root: Path, paths: list[str], symbol: str | None = None) -> dict[str, Any]:
    head = git(root,"rev-parse","HEAD").strip()
    tracked, dirty = tree(root,head), changes(root)
    records = []
    for path in paths:
        path = path.replace("\\", "/")
        meta = source(root, path, tracked, dirty)
        features = dc.feature_impacts(root, [path])
        matches = []
        if path in tracked and meta["available"] and path.endswith(".py"):
            raw = bounded_bytes(dc.confined(root,path))
            if hashlib.sha256(raw).hexdigest() != meta["working_sha256"]:
                raise ValueError(f"trace source_changed_during_read: {path}")
            matches = symbols(raw.decode("utf-8-sig"), symbol)
        records.append({**meta,"symbols":matches if symbol else matches[:20],
                        "symbols_omitted":max(0,len(matches)-20) if not symbol else 0,
                        "features":[f["id"] for f in features],
                        "contracts":sorted({p for f in features for p in f["contracts"]}),
                        "tests":sorted({p for f in features for p in f["tests"]}),
                        "evidence":sorted({p for f in features for p in f["evidence"]}),
                        "documentation_review":dc.required_documents(root,[path]),
                        "unknown":not meta["available"] or not features or bool(symbol and not matches)})
    if git(root,"rev-parse","HEAD").strip() != head:
        raise ValueError("trace HEAD_changed_during_read")
    return {"head":head,"records":records,
            "limitation":"AST僅證明名稱、簽名、宣告欄位；不import、不執行、不能證明API語意或測試PASS。測試關聯是代表性候選。QA須回驗具名commit/source hash/data/run。"}


def inventory(root: Path, *, base: str | None = None, details: bool = False) -> dict[str, Any]:
    tracked, dirty = tree(root), changes(root)
    docs = {p:v for p,v in tracked.items() if p.startswith("docs/") or p.endswith(".md")}
    rows = [source(root,p,tracked,dirty) for p in sorted(docs)] if details else []
    delta = None
    if base:
        old = tree(root,base)
        delta = {"base":git(root,"rev-parse","--verify","--end-of-options",base+"^{commit}").strip(),
                 "added":sorted(set(tracked)-set(old)),"deleted":sorted(set(old)-set(tracked)),
                 "modified":sorted(p for p in set(old)&set(tracked) if old[p] != tracked[p])}
    return {"schema_version":"baldr-document-inventory.v1", "head":git(root,"rev-parse","HEAD").strip(),
            "tracked_total":len(tracked),"head_document_paths":len(docs),
            "head_document_classes":dict(Counter(classification(p) for p in docs)),
            "working_tree_changes":dirty,"head_delta":delta,"documents":rows,
            "excluded_assets":"ignored output/DB/models/Graphify/secret assets不掃內容；git status untracked另列；不等同不存在。",
            "historical_manifest":"docs/00_core/DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv 是固定1520歷史基線，不與目前分母等同。"}


def check_metadata(root: Path) -> list[str]:
    errors = []
    tracked, dirty = tree(root), changes(root)
    mapping, _ = metadata_source(root,dc.FEATURE_MAP,tracked,dirty)
    ids = {item["id"] for item in mapping["features"]}
    register, _ = metadata_source(root,ISSUES,tracked,dirty)
    issues = issue_view(root,register=register)["issues"]
    issue_ids = {item["id"] for item in issues}
    if len(issue_ids) != len(issues):
        errors.append("Issue ID重複")
    if issue_ids != set(register.get("expected_ids",[f"G{i:02}" for i in range(1,11)])):
        errors.append("Issue ID與宣告的治理範圍不符")
    for issue in issues:
        for field in ["id","owner","owner_evidence","affected_domain","current_status","resolved_scope","supporting_evidence","source_date","source_commit","blocking_scope","resolution_criteria"]:
            if field not in issue:
                errors.append(f"Issue缺欄位：{issue.get('id')} {field}")
        if issue.get("current_status") not in ISSUE_STATUSES:
            errors.append(f"Issue未知狀態：{issue.get('id')}")
        if not issue.get("owner_evidence") or (issue.get("owner") is None and "unknown" not in issue.get("owner_evidence","")):
            errors.append(f"Issue owner缺unknown／具名證據：{issue.get('id')}")
        if issue.get("source_commit"):
            try:
                commit = git(root,"rev-parse","--verify","--end-of-options",issue["source_commit"]+"^{commit}").strip()
                git(root,"merge-base","--is-ancestor",commit,"HEAD")
            except ValueError:
                errors.append(f"Issue source commit缺件或非HEAD祖先：{issue.get('id')}")
        for path in issue["supporting_evidence"]:
            if not dc.confined(root,path.split("#",1)[0]).is_file():
                errors.append(f"Issue來源缺件：{path}")
    for name, rule in mapping.get("reading_routes",{}).items():
        if set(rule["features"])-ids or set(rule.get("issues",[]))-issue_ids:
            errors.append(f"閱讀路由引用未知ID：{name}")
        for selector in mapping["context_entry"] + sum([rule.get(key,[]) for key in ["entry","documents","code","tests","history"]],[]):
            path = selector["path"]
            target = dc.confined(root,path)
            if path not in tracked or Path(path).suffix not in {".md", ".py"} or not source(root,path,tracked,dirty)["available"]:
                errors.append(f"閱讀來源不是HEAD普通文字或缺件／過大／link：{name} {path}")
                continue
            try:
                excerpt(bounded_bytes(target).decode("utf-8-sig"),selector)
            except (ValueError,SyntaxError,UnicodeError) as exc:
                errors.append(f"閱讀selector失效：{name} {path}: {exc}")
    return errors


def render_context(result: dict[str, Any]) -> str:
    """供 Agent 閱讀的短格式；完整機械 metadata 留在同一命令的 JSON 視圖。"""
    lines = [f"Task: {result['task']}", f"Domain: {result['domain']} / Level {result['level']}",
             f"HEAD: {result['source_version']['head']}",
             f"Working tree: {len(result['source_version']['working_tree_changes'])} changes; 每份來源各列XY，完整清單用inventory",
             "Constraints: docs/agents/shared_context.md；inspection≠change；只讀AST/來源，不證明執行、QA或Gate；contains是命中行，非完整章節。",
             "Relevant Docs / Code / Key Contracts / Status / Tests:"]
    for meta in result["source_version"]["metadata_sources"]:
        lines.append(f"Metadata: {meta['path']} / XY={meta['git_status']} / HEAD blob={meta['head_blob_oid']} / working SHA256={meta['working_sha256']}")
    for item in result["relevant_docs_code_contracts_tests_status"]:
        selector = {k:v for k,v in item["selector"].items() if k != "path"}
        line_list = item["lines"]
        ranges: list[list[int]] = []
        for number in line_list:
            if ranges and ranges[-1][1]+1 == number:
                ranges[-1][1] = number
            else:
                ranges.append([number,number])
        line_label = ",".join(str(a) if a==b else f"{a}-{b}" for a,b in ranges)
        lines += [f"\n{item['path']} [{item['classification']}; XY={item['git_status']}; L{line_label}; selector={json.dumps(selector,ensure_ascii=False)}]",
                  f"HEAD blob={item['head_blob_oid']} / working SHA256={item['working_sha256']}",item["text"]]
    lines.append("Related paths (未核讀正文):")
    for key, values in result["related_paths"].items():
        lines.append(key+": "+", ".join(values))
    lines.append("Known Issues (owner unknown維持null):")
    for issue in result["known_issues"]["issues"]:
        lines.append(f"{issue['id']} / {issue['current_status']} / blocking={issue['blocking_scope']} / resolution={issue['resolution_criteria']} / source={issue['supporting_evidence'][0]} @{issue['source_commit']}")
    lines += ["Documentation impact: "+json.dumps(result["documentation_impact"],ensure_ascii=False),
              "Unverified / Unknown: "+json.dumps(result["unverified_unknown"],ensure_ascii=False),
              "Metrics (僅摘錄；包裝另計): "+json.dumps(result["metrics"],ensure_ascii=False)]
    return "\n".join(lines)+"\n"
