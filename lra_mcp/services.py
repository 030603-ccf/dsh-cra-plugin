"""Business logic shared by the MCP tools."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from lra.diff import git_changes
from lra.optimizer.loop import render_fix_prompt
from lra.schemas.finding import Finding

from lra_mcp.config import McpConfig
from lra_mcp.errors import LraMcpError
from lra_mcp.runner import ReviewOptions, run_review
from lra_mcp.security import (
    preflight_project,
    validate_base_ref,
    validate_finding_ids,
    validate_hint,
    validate_project_path,
    validate_run_id,
)

_FINDING_SUMMARY_FIELDS = (
    "id", "severity", "category", "file_path",
    "line_start", "line_end", "title", "suggestion",
    "confidence", "second_verdict",
)


def _read_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise LraMcpError("RUN_NOT_FOUND", run_dir=str(path.parent)) from e
    except json.JSONDecodeError as e:
        raise LraMcpError("RUN_FAILED", detail=f"{path.name} 不是合法 JSON: {e}") from e


def _new_run_id() -> str:
    return f"{uuid.uuid4().hex[:8]}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _summary_from_findings(findings: list[dict]) -> dict:
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_category: dict[str, int] = {}
    for f in findings:
        by_severity[f.get("severity", "low")] = by_severity.get(f.get("severity", "low"), 0) + 1
        cat = f.get("category", "best_practice")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": len(findings),
        "by_severity": by_severity,
        "by_category": by_category,
    }


def _strip_findings(findings: list[dict], limit: int) -> tuple[list[dict], bool]:
    stripped = []
    for f in findings[:limit]:
        item = {k: f.get(k) for k in _FINDING_SUMMARY_FIELDS}
        item.setdefault("second_verdict")
        stripped.append(item)
    return stripped, len(findings) > limit


def read_run_products(cfg: McpConfig, run_id: str) -> dict:
    run_dir = cfg.run_dir_for(run_id)
    if run_dir.is_symlink():
        raise LraMcpError("RUN_NOT_FOUND", run_id=run_id, hint="run 目录不能是符号链接")
    if not run_dir.is_dir():
        raise LraMcpError("RUN_NOT_FOUND", run_id=run_id)
    try:
        runs_root = cfg.runs_dir.resolve()
        if run_dir.resolve().parent != runs_root:
            raise LraMcpError("RUN_NOT_FOUND", run_id=run_id, hint="run 目录不在 runs 根目录内")
    except OSError as e:
        raise LraMcpError("RUN_NOT_FOUND", run_id=run_id, hint=str(e)) from e

    summary_path = run_dir / "summary.json"
    if not summary_path.is_file():
        raise LraMcpError("RUN_NOT_COMPLETE", run_id=run_id, hint="先续跑或等待完成")
    findings_path = run_dir / "findings.json"
    if not findings_path.is_file():
        raise LraMcpError("RUN_NOT_COMPLETE", run_id=run_id, hint="findings.json 尚未生成")

    summary = _read_json(summary_path)
    if not isinstance(summary, dict):
        raise LraMcpError("RUN_FAILED", detail="summary.json 结构错误")
    findings = _read_json(findings_path)
    if not isinstance(findings, list):
        raise LraMcpError("RUN_FAILED", detail="findings.json 结构错误")
    project_map = None
    pm_path = run_dir / "project_map.json"
    if pm_path.is_file():
        project_map = _read_json(pm_path)

    return {"run_dir": run_dir, "summary": summary, "findings": findings,
            "project_map": project_map}


def _run_and_collect(cfg: McpConfig, root: Path, run_id: str,
                     options: ReviewOptions) -> dict:
    proc = run_review(cfg, str(root), run_id, options)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise LraMcpError(
            "RUN_FAILED",
            run_id=run_id,
            exit_code=proc.returncode,
            detail=tail,
        )
    products = read_run_products(cfg, run_id)
    return products


def review_project_impl(cfg: McpConfig, path: str,
                        run_id: str | None = None,
                        issue_hint: str | None = None) -> dict:
    root = validate_project_path(path)
    preflight_project(root, cfg)
    hint = validate_hint(issue_hint, cfg.max_hint_chars)
    run_id = validate_run_id(run_id) if run_id else _new_run_id()

    products = _run_and_collect(
        cfg, root, run_id,
        ReviewOptions(issue_hint=hint, incremental=False),
    )

    findings = products["findings"]
    summary = products["summary"]
    stripped, has_more = _strip_findings(findings, cfg.max_findings)
    return {
        "run_id": run_id,
        "mode": summary.get("mode", "full"),
        "status": summary.get("status", "completed"),
        "project": {
            "root": summary.get("root", str(root)),
            "file_count": (products.get("project_map") or {}).get("file_count",
                                                                  summary.get("file_count", "-")),
        },
        "summary": _summary_from_findings(findings),
        "cost": {
            "wall_seconds": summary.get("wall_seconds", 0),
            "tokens": summary.get("initial_tokens", 0),
            "requests": summary.get("initial_requests", 0),
            "second_tokens": summary.get("second_tokens", 0),
            "second_requests": summary.get("second_requests", 0),
        },
        "findings": stripped,
        "has_more": has_more,
        "warnings": _warnings_from_summary(summary),
        "report_path": str(products["run_dir"] / "report.md"),
        "summary_path": str(products["run_dir"] / "summary.json"),
    }


def _warnings_from_summary(summary: dict) -> list[dict]:
    warnings: list[dict] = []
    for block in summary.get("failed_blocks") or []:
        warnings.append({"code": "LLM_TRANSIENT", "file": block.get("file"),
                         "line_start": block.get("line_start"),
                         "line_end": block.get("line_end"),
                         "detail": block.get("error", "")})
    for err in summary.get("llm_errors") or []:
        warnings.append({"code": "LLM_PERMANENT", "file": err.get("file"),
                         "line_start": err.get("line_start"),
                         "line_end": err.get("line_end"),
                         "detail": err.get("error", "")})
    return warnings


def review_diff_impl(cfg: McpConfig, path: str,
                     run_id: str | None = None,
                     base_ref: str | None = None,
                     strict: bool = False,
                     issue_hint: str | None = None) -> dict:
    root = validate_project_path(path)
    preflight_project(root, cfg)
    hint = validate_hint(issue_hint, cfg.max_hint_chars)
    base_ref = validate_base_ref(base_ref)
    run_id = validate_run_id(run_id) if run_id else _new_run_id()

    changes = git_changes(root, base_ref=base_ref)
    if strict:
        if not changes["is_git_repo"]:
            raise LraMcpError("NOT_GIT_REPO", path=str(root))
        if changes.get("errors"):
            raise LraMcpError("INVALID_BASE_REF", base_ref=base_ref,
                              detail="；".join(changes["errors"]))
    # non-strict fallback is decided by lra itself (full_fallback); we just pass
    # incremental mode through and trust summary.mode afterwards.

    products = _run_and_collect(
        cfg, root, run_id,
        ReviewOptions(issue_hint=hint, incremental=True,
                      base_ref=base_ref, strict=strict),
    )

    findings = products["findings"]
    summary = products["summary"]
    stripped, has_more = _strip_findings(findings, cfg.max_findings)
    return {
        "run_id": run_id,
        "mode": summary.get("mode", "incremental"),
        "status": summary.get("status", "completed"),
        "summary": _summary_from_findings(findings),
        "cost": {
            "wall_seconds": summary.get("wall_seconds", 0),
            "tokens": summary.get("initial_tokens", 0),
            "requests": summary.get("initial_requests", 0),
            "second_tokens": summary.get("second_tokens", 0),
            "second_requests": summary.get("second_requests", 0),
        },
        "findings": stripped,
        "has_more": has_more,
        "warnings": _warnings_from_summary(summary),
        "report_path": str(products["run_dir"] / "report.md"),
        "summary_path": str(products["run_dir"] / "summary.json"),
    }


def get_finding_impl(cfg: McpConfig, run_id: str, finding_id: str) -> dict:
    run_id = validate_run_id(run_id)
    if not finding_id or not finding_id.startswith("F"):
        raise LraMcpError("INVALID_FINDING_ID", finding_id=finding_id)
    validate_finding_ids([finding_id])

    products = read_run_products(cfg, run_id)
    for f in products["findings"]:
        if f.get("id") == finding_id:
            src_root = (products.get("project_map") or {}).get("root")
            abs_path = ""
            if src_root:
                abs_path = str(Path(src_root) / f["file_path"])
            return {"run_id": run_id, "finding": f, "abs_path": abs_path}
    raise LraMcpError("FINDING_NOT_FOUND", run_id=run_id, finding_id=finding_id)


def generate_fix_prompt_impl(cfg: McpConfig, run_id: str,
                             finding_ids: list[str] | None = None,
                             extra_instruction: str | None = None) -> dict:
    run_id = validate_run_id(run_id)
    hint = validate_hint(extra_instruction, cfg.max_hint_chars)
    selected = validate_finding_ids(finding_ids)

    products = read_run_products(cfg, run_id)
    findings = [Finding(**f) for f in products["findings"]]
    if selected:
        by_id = {f.id: f for f in findings}
        missing = [fid for fid in selected if fid not in by_id]
        if missing:
            raise LraMcpError("FINDING_NOT_FOUND", run_id=run_id,
                              finding_id=missing[0])
        chosen = [by_id[fid] for fid in selected]
    else:
        chosen = findings

    pm = products.get("project_map") or {}
    src_root = Path(pm.get("root") or ".")
    groups: dict[str, list[Finding]] = {}
    for f in chosen:
        groups.setdefault(f.file_path, []).append(f)

    prompts: list[dict] = []
    total_chars = 0
    for file_path, fs in groups.items():
        src_path = src_root / file_path
        if not src_path.is_file():
            raise LraMcpError("FINDING_FILE_MISSING", run_id=run_id,
                              file_path=file_path)
        code = src_path.read_text(encoding="utf-8", errors="replace")
        prompt = render_fix_prompt(
            file_path, fs, code,
            keep=None, feedback=None, issue_hint=hint,
        )
        total_chars += len(prompt)
        if total_chars > cfg.max_prompt_chars:
            raise LraMcpError("FIX_PROMPT_TOO_LARGE", total_chars=total_chars,
                              limit=cfg.max_prompt_chars)
        prompts.append({
            "file_path": file_path,
            "finding_ids": [f.id for f in fs],
            "prompt": prompt,
            "char_count": len(prompt),
        })

    return {"run_id": run_id, "prompts": prompts, "total_chars": total_chars}
