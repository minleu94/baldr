"""治理暫時視圖的版本、預算、隔離與反例；不 import 產品。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts import document_context as ctx
from scripts import document_control as dc


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git","-c","core.fsmonitor=false",*args],cwd=root,text=True).strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    _git(tmp_path,"init")
    files = {
        "docs/entry.md":"# Entry\n\n## Safety\n不得升格 Gate。\n",
        "docs/current.md":"# Current\n\n## Contract\nunknown不是通過。\n",
        "docs/09_archive/old.md":"# Old\n歷史PASS不是current。\n",
        "module.py":"class DTO:\n    value: int\n    def encode(self, mode: str = 'strict', *, version: int = 1) -> str:\n        raise RuntimeError('不得import或執行')\n",
        "tests/test_module.py":"def test_contract():\n    assert True\n",
    }
    feature={"id":"f","change_patterns":["module.py"],"contracts":["docs/current.md"],"code":["module.py"],"tests":["tests/test_module.py"],"evidence":["docs/current.md"],"sync_documents":["docs/current.md"]}
    mapping={"features":[feature],"context_entry":[{"path":"docs/entry.md","section":"Safety"}],"reading_routes":{"example":{"features":["f"],"documents":[{"path":"docs/current.md","section":"Contract"}],"code":[{"path":"module.py","symbol":"DTO.encode"}],"tests":[{"path":"tests/test_module.py","symbol":"test_contract"}],"history":[{"path":"docs/09_archive/old.md","preamble":True}],"issues":[]}}}
    files[dc.FEATURE_MAP]=json.dumps(mapping)
    files[ctx.ISSUES]=json.dumps({"schema_version":"baldr-governance-issues.v1","authority":"matrix","expected_ids":[],"issues":[]})
    for path, content in files.items():
        target=tmp_path/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding="utf-8")
    _git(tmp_path,"add","--",*files)
    _git(tmp_path,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-m","seed")
    return tmp_path


def test_context_inspection_is_not_change_or_gate(repository: Path) -> None:
    result=ctx.context(repository,domain="example",level=3,inspect=["module.py"])
    assert result["documentation_impact"]["required_review"]==[]
    assert result["documentation_impact"]["changed_paths"]==[]
    assert "unknown" in result["constraints"]["runtime_tests_and_gate"]
    assert ctx.context(repository,domain="example",changed=["module.py"])["documentation_impact"]["required_review"]==["docs/current.md"]


def test_source_versions_distinguish_head_index_and_working(repository: Path) -> None:
    original=ctx.context(repository,domain="example")
    target=repository/"docs/current.md"
    target.write_text("# Current\n## Contract\nWIP尚未接受。\n",encoding="utf-8")
    working=ctx.context(repository,domain="example")
    entry=next(s for s in working["relevant_docs_code_contracts_tests_status"] if s["path"]=="docs/current.md")
    assert entry["git_status"]==" M"
    assert entry["working_sha256"]==hashlib.sha256(target.read_bytes()).hexdigest()
    assert entry["head_blob_oid"]==next(s for s in original["relevant_docs_code_contracts_tests_status"] if s["path"]=="docs/current.md")["head_blob_oid"]
    _git(repository,"add","--","docs/current.md")
    assert ctx.changes(repository)["docs/current.md"]=="M "


@pytest.mark.parametrize("path",["../secret.md","C:/outside/file.md","/outside/file.md"])
def test_context_and_trace_reject_escape(repository: Path,path: str) -> None:
    with pytest.raises(ValueError):
        ctx.context(repository,domain="example",level=3,inspect=[path])
    with pytest.raises(ValueError):
        ctx.trace(repository,[path])


def test_budget_omits_whole_contract_and_reports_unknown(repository: Path) -> None:
    (repository/"docs/current.md").write_text("# Current\n## Contract\n"+"重要限制"*300+"\n",encoding="utf-8")
    result=ctx.context(repository,domain="example",max_chars=1000)
    assert result["metrics"]["characters"]<=1000
    assert any(s["reason"]=="budget_omitted" for s in result["unverified_unknown"])
    assert not any(s["path"]=="docs/current.md" for s in result["relevant_docs_code_contracts_tests_status"])


def test_metric_matches_actual_excerpt_bytes(repository: Path) -> None:
    result=ctx.context(repository,domain="example",level=3)
    text="".join(s["text"] for s in result["relevant_docs_code_contracts_tests_status"])
    assert result["metrics"]["characters"]==len(text)
    assert result["metrics"]["utf8_bytes"]==len(text.encode("utf-8"))
    assert result["metrics"]["estimated_tokens"]==(len(text.encode("utf-8"))+2)//3


def test_history_requires_explicit_level4_and_is_classified(repository: Path) -> None:
    with pytest.raises(ValueError):
        ctx.context(repository,domain="example",level=4)
    assert all(s["classification"]!="historical" for s in ctx.context(repository,domain="example",level=3)["relevant_docs_code_contracts_tests_status"])
    result=ctx.context(repository,domain="example",level=4,include_history=True)
    assert any(s["classification"]=="historical" for s in result["relevant_docs_code_contracts_tests_status"])


def test_untracked_private_and_json_do_not_enter_context(repository: Path) -> None:
    (repository/"secret.py").write_text("SECRET_DO_NOT_EMIT",encoding="utf-8")
    (repository/".gitignore").write_text("secret.py\n",encoding="utf-8")
    result=ctx.context(repository,domain="example",level=3,inspect=["secret.py",dc.FEATURE_MAP])
    assert "SECRET_DO_NOT_EMIT" not in json.dumps(result)
    assert any(s["path"]=="secret.py" for s in result["unverified_unknown"])
    assert not ctx.source(repository,"secret.py",ctx.tree(repository),ctx.changes(repository)).get("working_sha256")


def test_ast_signature_and_fields_without_execution(repository: Path) -> None:
    result=ctx.trace(repository,["module.py"],"DTO.encode")
    assert result["records"][0]["symbols"][0]["signature"]=="DTO.encode(self, mode: str='strict', *, version: int=1) -> str"
    assert not result["records"][0]["unknown"]
    assert ctx.trace(repository,["module.py"],"DTO")["records"][0]["symbols"][0]["fields"]==["value: int"]
    assert ctx.trace(repository,["module.py"],"Missing")["records"][0]["unknown"]


def test_inventory_delta_handles_added_deleted_and_rename(repository: Path) -> None:
    baseline=_git(repository,"rev-parse","HEAD")
    _git(repository,"mv","docs/current.md","docs/replacement.md")
    _git(repository,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-m","rename")
    result=ctx.inventory(repository,base=baseline,details=True)
    assert "docs/current.md" in result["head_delta"]["deleted"]
    assert "docs/replacement.md" in result["head_delta"]["added"]
    assert result["head_document_classes"]["historical"]==1
    assert all(s["head_blob_oid"] for s in result["documents"])
    _git(repository,"mv","docs/replacement.md","docs/renamed.md")
    assert "R" in ctx.changes(repository)["docs/renamed.md"]


def test_unknown_domain_and_bad_ref_fail_closed(repository: Path) -> None:
    with pytest.raises(ValueError):
        ctx.context(repository,domain="ambiguous")
    with pytest.raises(ValueError):
        ctx.inventory(repository,base="--help")
    assert dc.main(["--repo-root",str(repository),"context","--domain","ambiguous"])==2


def test_metadata_detects_selector_drift(repository: Path) -> None:
    assert ctx.check_metadata(repository)==[]
    (repository/"docs/current.md").write_text("# Renamed\n",encoding="utf-8")
    assert any("selector" in e for e in ctx.check_metadata(repository))


def test_text_format_preserves_versions_unknowns_and_contract(repository: Path,capsys: pytest.CaptureFixture[str]) -> None:
    assert dc.main(["--repo-root",str(repository),"context","--domain","example","--level","3","--format","text"])==0
    output=capsys.readouterr().out
    for value in ["HEAD:","HEAD blob=","working SHA256=","unknown不是通過","DTO.encode","Documentation impact:","Unverified / Unknown:","非完整章節"]:
        assert value in output


def test_git_symlink_checkout_mode_cannot_read_ignored_target(repository: Path) -> None:
    # Windows可將Git symlink以普通文字checkout；同樣必須拒讀，不需要升權建立link。
    oid=_git(repository,"hash-object","-w","module.py")
    _git(repository,"update-index","--cacheinfo",f"120000,{oid},module.py")
    _git(repository,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-m","symlink mode")
    assert ctx.tree(repository)["module.py"]["mode"]=="120000"
    assert not ctx.source(repository,"module.py",ctx.tree(repository),ctx.changes(repository))["available"]
    result=ctx.context(repository,domain="example",level=3)
    assert not any(s["path"]=="module.py" for s in result["relevant_docs_code_contracts_tests_status"])


def test_lexical_link_detection_precedes_resolved_target_read(repository: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    real=Path.is_symlink
    monkeypatch.setattr(Path,"is_symlink",lambda p: p==repository/"module.py" or real(p))
    assert ctx.linked_path(repository,"module.py")
    assert not ctx.source(repository,"module.py",ctx.tree(repository),ctx.changes(repository))["available"]


def test_metadata_wip_source_hash_and_issue_escalation_guard(repository: Path) -> None:
    result=ctx.context(repository,domain="example")
    assert len(result["source_version"]["metadata_sources"])==2
    p=repository/ctx.ISSUES
    data=json.loads(p.read_text(encoding="utf-8"))
    data.update(expected_ids=["G01"],issues=[{"id":"G01","owner":None,"owner_evidence":"unknown","affected_domain":"test","current_status":"product_accepted","resolved_scope":"test","supporting_evidence":["docs/current.md"],"source_date":"2026-10-13","source_commit":"bad-ref","blocking_scope":"unknown","resolution_criteria":"test"}])
    p.write_text(json.dumps(data),encoding="utf-8")
    errors=ctx.check_metadata(repository)
    assert any("未知狀態" in e for e in errors)
    assert any("source commit" in e for e in errors)
    version=next(s for s in ctx.context(repository,domain="example")["source_version"]["metadata_sources"] if s["path"]==ctx.ISSUES)
    assert version["git_status"]==" M"
    assert version["working_sha256"]==hashlib.sha256(p.read_bytes()).hexdigest()


def test_trace_rejects_source_change_between_hash_and_ast(repository: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    real_source=ctx.source
    def source_then_change(root,path,tracked,dirty):
        metadata=real_source(root,path,tracked,dirty)
        (root/path).write_text("class Different: pass\n",encoding="utf-8")
        return metadata
    monkeypatch.setattr(ctx,"source",source_then_change)
    with pytest.raises(ValueError,match="source_changed_during_read"):
        ctx.trace(repository,["module.py"],"DTO")


def test_config_read_rejects_lexical_link(repository: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    real=Path.is_symlink
    monkeypatch.setattr(Path,"is_symlink",lambda p: p==repository/dc.FEATURE_MAP or real(p))
    with pytest.raises(ValueError):
        dc.feature_impacts(repository,["module.py"])
    with pytest.raises(ValueError):
        ctx.context(repository,domain="example")


def test_windows_separators_have_same_documentation_impact(repository: Path) -> None:
    mapping=json.loads((repository/dc.FEATURE_MAP).read_text(encoding="utf-8"))
    mapping["features"][0]["change_patterns"].append("app/module.py")
    (repository/dc.FEATURE_MAP).write_text(json.dumps(mapping),encoding="utf-8")
    result=ctx.context(repository,domain="example",changed=["app\\module.py"])
    assert result["documentation_impact"]["changed_paths"]==["app/module.py"]
    assert result["documentation_impact"]["required_review"]==["docs/current.md"]


def test_metadata_selector_cannot_read_untracked_private_source(repository: Path) -> None:
    (repository/"private.md").write_text("# Private\nDO_NOT_READ\n",encoding="utf-8")
    mapping=json.loads((repository/dc.FEATURE_MAP).read_text(encoding="utf-8"))
    mapping["reading_routes"]["example"]["documents"].append({"path":"private.md","preamble":True})
    (repository/dc.FEATURE_MAP).write_text(json.dumps(mapping),encoding="utf-8")
    assert any("不是HEAD普通文字" in e for e in ctx.check_metadata(repository))


def test_oversized_metadata_fails_before_read(repository: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    target=repository/dc.FEATURE_MAP
    with target.open("wb") as handle:
        handle.truncate(2_000_001)
    original=Path.open
    def disallow_open(path,*args,**kwargs):
        if path==target:
            raise AssertionError("不應讀取過大metadata")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"open",disallow_open)
    with pytest.raises(ValueError,match="source_size_limit"):
        ctx.context(repository,domain="example")
