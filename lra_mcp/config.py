"""Configuration loading for lra-code-review-mcp.

All values come from environment variables; tool parameters never carry keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from lra_mcp.errors import LraMcpError


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _as_int(name: str, raw: object) -> int:
    """Parse an env/config value as int; raise CONFIG_MISSING on garbage."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise LraMcpError("CONFIG_MISSING", f"{name} 不是合法整数: {raw!r}", env=name)


def _as_float(name: str, raw: object) -> float:
    """Parse an env/config value as float; raise CONFIG_MISSING on garbage."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise LraMcpError("CONFIG_MISSING", f"{name} 不是合法数字: {raw!r}", env=name)


@dataclass(frozen=True)
class McpConfig:
    lra_config_path: Path
    lra_profile: str
    runs_dir: Path
    concurrency: int
    total_timeout: float
    max_files: int
    max_file_bytes: int
    max_hint_chars: int
    max_findings: int
    max_prompt_chars: int

    def run_dir_for(self, run_id: str) -> Path:
        return self.runs_dir / run_id


def _candidate_config_paths() -> list[Path]:
    env = _env("LRA_MCP_CONFIG")
    if env:
        # 显式指定后不要再退回 cwd/home：路径写错应当报 CONFIG_MISSING，
        # 而不是静默加载另一份配置。
        return [Path(env)]
    return [
        Path.cwd() / "config.yaml",
        Path.home() / ".config" / "lra-code-review-mcp" / "config.yaml",
    ]


def _load_profile(cfg: dict, profile_name: str) -> dict:
    profiles = cfg.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise LraMcpError("CONFIG_MISSING", "config.yaml 缺少 profiles 节")
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        available = list(profiles.keys())
        raise LraMcpError(
            "PROFILE_NOT_FOUND",
            profile=profile_name,
            available=available,
        )
    return profile


def _validate_profile(profile: dict, profile_name: str) -> None:
    if not profile.get("base_url"):
        raise LraMcpError(
            "CONFIG_MISSING",
            f"profile {profile_name!r} 缺少 base_url",
            profile=profile_name,
        )
    if not profile.get("model"):
        raise LraMcpError(
            "CONFIG_MISSING",
            f"profile {profile_name!r} 缺少 model",
            profile=profile_name,
        )
    api_key = str(profile.get("api_key") or "")
    api_key_env = str(profile.get("api_key_env") or "")
    if not api_key and not api_key_env:
        raise LraMcpError(
            "CONFIG_MISSING",
            f"profile {profile_name!r} 既没有 api_key 也没有 api_key_env",
            profile=profile_name,
        )
    if api_key and not _env("LRA_MCP_ALLOW_INLINE_KEY"):
        raise LraMcpError(
            "CONFIG_KEY_POLICY",
            "config 不允许内联 api_key，请改用 api_key_env 指向环境变量",
            profile=profile_name,
        )


def load_config() -> McpConfig:
    path: Path | None = None
    for candidate in _candidate_config_paths():
        if candidate.is_file():
            path = candidate
            break
    if path is None:
        searched = [str(p) for p in _candidate_config_paths()]
        raise LraMcpError(
            "CONFIG_MISSING",
            "找不到 config.yaml；请设置 LRA_MCP_CONFIG",
            searched=searched,
        )

    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise LraMcpError("CONFIG_MISSING", f"config.yaml 解析失败: {e}") from e

    profile_name = _env("LRA_MCP_PROFILE") or str(cfg.get("default_profile") or "")
    if not profile_name:
        raise LraMcpError("CONFIG_MISSING", "config.yaml 缺少 default_profile 且未设置 LRA_MCP_PROFILE")

    profile = _load_profile(cfg, profile_name)
    _validate_profile(profile, profile_name)

    lsp_cfg = cfg.get("lsp") or {}
    if lsp_cfg.get("enabled"):
        raise LraMcpError("LSP_UNSUPPORTED", "MCP 模式要求 lsp.enabled=false")

    runs_dir = Path(_env("LRA_MCP_RUNS_DIR") or str(Path.home() / ".lra-code-review-mcp" / "runs"))
    concurrency = _as_int("LRA_MCP_CONCURRENCY", _env("LRA_MCP_CONCURRENCY") or (cfg.get("review") or {}).get("concurrency") or 16)
    total_timeout = _as_float("LRA_MCP_TOTAL_TIMEOUT", _env("LRA_MCP_TOTAL_TIMEOUT") or 1800.0)

    return McpConfig(
        lra_config_path=path,
        lra_profile=profile_name,
        runs_dir=runs_dir,
        concurrency=concurrency,
        total_timeout=total_timeout,
        max_files=_as_int("LRA_MCP_MAX_FILES", _env("LRA_MCP_MAX_FILES") or 5000),
        max_file_bytes=_as_int("LRA_MCP_MAX_FILE_BYTES", _env("LRA_MCP_MAX_FILE_BYTES") or 2 * 1024 * 1024),
        max_hint_chars=_as_int("LRA_MCP_MAX_HINT_CHARS", _env("LRA_MCP_MAX_HINT_CHARS") or 500),
        max_findings=_as_int("LRA_MCP_MAX_FINDINGS", _env("LRA_MCP_MAX_FINDINGS") or 200),
        max_prompt_chars=_as_int("LRA_MCP_MAX_PROMPT_CHARS", _env("LRA_MCP_MAX_PROMPT_CHARS") or 200000),
    )
