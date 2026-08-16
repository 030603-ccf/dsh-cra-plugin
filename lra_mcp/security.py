"""Security layer: path / scale / parameter validation.

All functions are pure and deterministic; they raise :class:`LraMcpError` with
the codes defined in the v0.2 design doc.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from lra.analysis.languages import LANG_BY_EXT
from lra.ignore import path_is_ignored
from lra_mcp.config import McpConfig
from lra_mcp.errors import LraMcpError

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FINDING_ID_RE = re.compile(r"^F\d+$")
_BASE_REF_WHITESPACE_RE = re.compile(r"\s")


def validate_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id or ""):
        raise LraMcpError("INVALID_RUN_ID", run_id=str(run_id)[:100])
    return run_id


def validate_hint(hint: str | None, limit: int) -> str:
    hint = (hint or "").strip()
    if len(hint) > limit:
        raise LraMcpError("HINT_TOO_LONG", limit=limit, actual=len(hint))
    return hint


def validate_base_ref(base_ref: str | None) -> str:
    base_ref = (base_ref or "HEAD~1").strip()
    if len(base_ref) > 128 or _BASE_REF_WHITESPACE_RE.search(base_ref) or base_ref.startswith("-"):
        raise LraMcpError("INVALID_BASE_REF", base_ref=base_ref)
    return base_ref


def validate_finding_ids(finding_ids: list[str] | None, max_ids: int = 50) -> list[str]:
    ids = finding_ids or []
    if not ids:
        return []
    if len(ids) > max_ids:
        raise LraMcpError("TOO_MANY_FINDING_IDS", limit=max_ids, actual=len(ids))
    seen: set[str] = set()
    for fid in ids:
        if not _FINDING_ID_RE.match(fid):
            raise LraMcpError("INVALID_FINDING_ID", finding_id=fid)
        if fid in seen:
            raise LraMcpError("DUPLICATE_FINDING_ID", finding_id=fid)
        seen.add(fid)
    return ids


def _check_no_symlinks(resolved_root: Path) -> None:
    if resolved_root.is_symlink():
        raise LraMcpError("INVALID_PATH", path=str(resolved_root), reason="根路径不能是符号链接")
    for root, dirs, files in os.walk(resolved_root):
        for name in dirs:
            p = Path(root) / name
            if p.is_symlink():
                raise LraMcpError("INVALID_PATH", path=str(p), reason="项目树内不允许符号链接目录")
        for name in files:
            p = Path(root) / name
            if p.is_symlink():
                raise LraMcpError("INVALID_PATH", path=str(p), reason="项目树内不允许符号链接文件")


def validate_project_path(path: str) -> Path:
    if not path or not path.strip():
        raise LraMcpError("INVALID_PATH", reason="path 不能为空")
    raw = Path(path.strip())
    if not raw.is_absolute():
        raise LraMcpError("INVALID_PATH", path=str(raw), reason="path 必须是绝对路径")
    if raw.is_symlink():
        raise LraMcpError("INVALID_PATH", path=str(raw), reason="根路径不能是符号链接")
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise LraMcpError("INVALID_PATH", path=str(raw), reason=str(e)) from e
    if not resolved.is_dir():
        raise LraMcpError("INVALID_PATH", path=str(resolved), reason="路径不是目录")
    _check_no_symlinks(resolved)
    return resolved


def preflight_project(root: Path, cfg: McpConfig) -> int:
    """Count reviewable files with the same policy as lra (ignore dirs + languages).

    Returns the file count. Raises PROJECT_TOO_LARGE when the project exceeds
    the configured file-count or single-file byte limits.
    """
    exts = {".py"} | set(LANG_BY_EXT)
    count = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        if path_is_ignored(p.relative_to(root).parts):
            continue
        try:
            size = p.stat().st_size
        except OSError as e:
            raise LraMcpError("INVALID_PATH", path=str(p), reason=str(e)) from e
        if size > cfg.max_file_bytes:
            raise LraMcpError(
                "PROJECT_TOO_LARGE",
                file=str(p),
                file_bytes=size,
                limit=cfg.max_file_bytes,
            )
        count += 1
        if count > cfg.max_files:
            raise LraMcpError(
                "PROJECT_TOO_LARGE",
                file_count=count,
                limit=cfg.max_files,
            )
    return count
