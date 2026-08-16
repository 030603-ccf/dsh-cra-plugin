"""Service layer tests with subprocess and LLM boundaries monkeypatched."""

import json
from pathlib import Path

import pytest

from lra_mcp.config import McpConfig
from lra_mcp.errors import LraMcpError
from lra_mcp.services import (
    _strip_findings,
    _summary_from_findings,
    generate_fix_prompt_impl,
    get_finding_impl,
    review_diff_impl,
    review_project_impl,
)


def _cfg(tmp_path, **kw):
    defaults = dict(
        lra_config_path=tmp_path / "config.yaml",
        lra_profile="mock",
        runs_dir=tmp_path / "runs",
        concurrency=2,
        startup_timeout=30,
        total_timeout=1800,
        max_files=5000,
        max_file_bytes=2 * 1024 * 1024,
        max_hint_chars=500,
        max_findings=200,
        max_prompt_chars=200000,
    )
    defaults.update(kw)
    return McpConfig(**defaults)


def _write_project(tmp_path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    return proj


def _products(run_dir, findings):
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "mode": "full", "status": "completed",
        "root": str(run_dir), "findings_count": len(findings),
        "initial_requests": 3, "initial_tokens": 100,
        "second_requests": 0, "second_tokens": 0,
        "failed_blocks": [], "llm_errors": [],
        "wall_seconds": 1.2,
    }
    project_map = {"root": str(run_dir), "file_count": 1}
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
    (run_dir / "project_map.json").write_text(json.dumps(project_map), encoding="utf-8")
    return {"run_dir": run_dir, "summary": summary, "findings": findings,
            "project_map": project_map}


class _FakeProc:
    returncode = 0
    stdout = ""
    stderr = ""


def test_strip_findings_caps_and_flags_more():
    findings = [{"id": f"F{i + 1}", "severity": "low", "category": "best_practice",
                 "file_path": "a.py", "line_start": i, "line_end": i,
                 "title": f"t{i}", "suggestion": "s", "confidence": 0.5}
                for i in range(5)]
    stripped, has_more = _strip_findings(findings, 3)
    assert len(stripped) == 3
    assert has_more is True
    assert stripped[0]["id"] == "F1"
    assert "evidence" not in stripped[0]


def test_summary_counts():
    findings = [
        {"severity": "critical", "category": "security"},
        {"severity": "low", "category": "security"},
        {"severity": "low", "category": "readability"},
    ]
    s = _summary_from_findings(findings)
    assert s["total"] == 3
    assert s["by_severity"]["critical"] == 1
    assert s["by_category"]["security"] == 2


def test_review_project_impl_returns_stripped_findings(tmp_path, monkeypatch):
    proj = _write_project(tmp_path)
    cfg = _cfg(tmp_path)
    run_dir = cfg.runs_dir / "r1"
    findings = [{"id": "F1", "severity": "high", "category": "security",
                 "file_path": "a.py", "line_start": 1, "line_end": 1,
                 "title": "bug", "description": "d", "evidence": "e",
                 "suggestion": "s", "confidence": 0.8, "second_verdict": None}]
    products = _products(run_dir, findings)
    monkeypatch.setattr("lra_mcp.services.run_review", lambda *a, **k: _FakeProc())
    monkeypatch.setattr("lra_mcp.services.read_run_products", lambda *a, **k: products)

    out = review_project_impl(cfg, str(proj), run_id="r1", issue_hint="sql")
    assert out["run_id"] == "r1"
    assert out["findings"][0]["title"] == "bug"
    assert out["summary"]["total"] == 1
    assert out["has_more"] is False


def test_review_diff_impl_strict_non_git(tmp_path, monkeypatch):
    proj = _write_project(tmp_path)
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "lra_mcp.services.git_changes",
        lambda *a, **k: {"is_git_repo": False, "files": [], "errors": []},
    )
    with pytest.raises(LraMcpError) as e:
        review_diff_impl(cfg, str(proj), strict=True)
    assert e.value.code == "NOT_GIT_REPO"


def test_get_finding_impl(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    run_dir = cfg.runs_dir / "r1"
    findings = [{"id": "F1", "severity": "high", "category": "security",
                 "file_path": "a.py", "line_start": 1, "line_end": 1,
                 "title": "bug", "description": "d", "evidence": "e",
                 "suggestion": "s", "confidence": 0.8, "second_verdict": None}]
    products = _products(run_dir, findings)
    monkeypatch.setattr("lra_mcp.services.read_run_products", lambda *a, **k: products)

    out = get_finding_impl(cfg, "r1", "F1")
    assert out["finding"]["id"] == "F1"
    with pytest.raises(LraMcpError) as e:
        get_finding_impl(cfg, "r1", "F99")
    assert e.value.code == "FINDING_NOT_FOUND"


def test_generate_fix_prompt_impl(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    run_dir = cfg.runs_dir / "r1"
    findings = [{"id": "F1", "severity": "high", "category": "security",
                 "file_path": "a.py", "line_start": 1, "line_end": 1,
                 "title": "bug", "description": "d", "evidence": "x = 1",
                 "suggestion": "s", "confidence": 0.8, "second_verdict": None}]
    products = _products(run_dir, findings)
    # point project_map.root at a directory that actually contains a.py
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n", encoding="utf-8")
    products["project_map"]["root"] = str(src)
    products["summary"]["root"] = str(src)
    monkeypatch.setattr("lra_mcp.services.read_run_products", lambda *a, **k: products)
    monkeypatch.setattr(
        "lra_mcp.services.render_fix_prompt",
        lambda file_path, findings, code, keep=None, feedback=None, issue_hint="": f"# FIX {file_path}",
    )

    out = generate_fix_prompt_impl(cfg, "r1", finding_ids=["F1"], extra_instruction="sql")
    assert out["run_id"] == "r1"
    assert out["prompts"][0]["file_path"] == "a.py"
    assert "# FIX" in out["prompts"][0]["prompt"]
