"""Subprocess runner: launch `python -m lra review` exactly once per tool call."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from lra_mcp.config import McpConfig
from lra_mcp.errors import LraMcpError


@dataclass(frozen=True)
class ReviewOptions:
    issue_hint: str = ""
    incremental: bool = False
    base_ref: str = "HEAD~1"
    strict: bool = False


def run_review(cfg: McpConfig, root: str, run_id: str, options: ReviewOptions):
    """Run lra review as a subprocess and return its raw exit status."""
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "lra", "review", root,
        "--config", str(cfg.lra_config_path),
        "--profile", cfg.lra_profile,
        "--run-dir", str(cfg.runs_dir),
        "--thread-id", run_id,
        "--concurrency", str(cfg.concurrency),
    ]
    if options.incremental:
        cmd += ["--incremental", "--base-ref", options.base_ref]
        if options.strict:
            cmd += ["--incremental-strict"]
    if options.issue_hint:
        cmd += ["--issue-hint", options.issue_hint]

    try:
        return subprocess.run(
            cmd,
            cwd=str(cfg.runs_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=cfg.total_timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise LraMcpError(
            "TIMEOUT",
            run_id=run_id,
            timeout=cfg.total_timeout,
            partial=True,
            resume=f"run 目录与 checkpoint 已保留，用相同 run_id={run_id} 重新调用即可续跑",
        ) from e
    except OSError as e:
        raise LraMcpError(
            "RUN_FAILED",
            run_id=run_id,
            error_type=type(e).__name__,
            detail=str(e),
        ) from e
