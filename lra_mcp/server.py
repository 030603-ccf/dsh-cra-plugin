"""MCP stdio server for lra (dependency-free JSON-RPC implementation).

This deliberately does NOT import the third-party `mcp` SDK. The MCP stdio
transport is newline-delimited JSON-RPC, which is small enough to implement
directly and removes a whole class of installation/dependency issues. stdout
carries only protocol JSON; all diagnostics go to stderr.
"""

from __future__ import annotations

import json
import sys
import traceback

from lra_mcp.config import load_config
from lra_mcp.errors import LraMcpError
from lra_mcp.services import (
    generate_fix_prompt_impl,
    get_finding_impl,
    review_diff_impl,
    review_project_impl,
)

SERVER_NAME = "lra"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"

# ---------- tool definitions (name -> JSON Schema + handler) ----------

_TOOL_SPECS: list[dict] = [
    {
        "name": "review_project",
        "description": "Run a full code review on an absolute project path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to an existing directory (no symlinks inside)."},
                "run_id": {"type": "string", "description": "Optional stable run id; omit to generate a new one."},
                "issue_hint": {"type": "string", "description": "Optional hint (max 500 chars) for the reviewer to focus on."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "review_diff",
        "description": "Review only git diff changes in a git working directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to an existing git working directory."},
                "run_id": {"type": "string", "description": "Optional stable run id."},
                "base_ref": {"type": "string", "description": "Git base ref (default HEAD~1)."},
                "strict": {"type": "boolean", "description": "When true, fail on non-git repo or invalid base ref instead of full fallback."},
                "issue_hint": {"type": "string", "description": "Optional hint (max 500 chars)."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_finding",
        "description": "Fetch one finding's full record (evidence, verdicts) by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run id returned by review_project / review_diff."},
                "finding_id": {"type": "string", "description": "Finding id such as F1."},
            },
            "required": ["run_id", "finding_id"],
        },
    },
    {
        "name": "generate_fix_prompt",
        "description": "Generate a per-file fix prompt (read-only, zero LLM tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run id returned by review_project / review_diff."},
                "finding_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional list of finding ids; default all findings."},
                "extra_instruction": {"type": "string", "description": "Optional hint (max 500 chars) appended to the prompt."},
            },
            "required": ["run_id"],
        },
    },
]


def _dispatch(name: str, args: dict) -> dict:
    cfg = load_config()
    if name == "review_project":
        return review_project_impl(cfg, args.get("path", ""),
                                   run_id=args.get("run_id"),
                                   issue_hint=args.get("issue_hint"))
    if name == "review_diff":
        return review_diff_impl(cfg, args.get("path", ""),
                                run_id=args.get("run_id"),
                                base_ref=args.get("base_ref"),
                                strict=bool(args.get("strict", False)),
                                issue_hint=args.get("issue_hint"))
    if name == "get_finding":
        return get_finding_impl(cfg, args.get("run_id", ""),
                                args.get("finding_id", ""))
    if name == "generate_fix_prompt":
        return generate_fix_prompt_impl(cfg, args.get("run_id", ""),
                                        finding_ids=args.get("finding_ids"),
                                        extra_instruction=args.get("extra_instruction"))
    raise LraMcpError("UNKNOWN_TOOL", name=name)


def _call_tool(name: str, args: dict) -> dict:
    try:
        result = _dispatch(name, args or {})
        return {
            "content": [{"type": "text",
                         "text": json.dumps(result, ensure_ascii=False)}],
            "isError": False,
        }
    except LraMcpError as e:
        return {
            "content": [{"type": "text", "text": e.to_json()}],
            "isError": True,
        }
    except Exception as e:  # defensive: never leak a traceback to the client
        traceback.print_exc(file=sys.stderr)
        payload = json.dumps({
            "code": "INTERNAL_ERROR",
            "detail": f"{type(e).__name__}: {str(e)[:300]}",
        }, ensure_ascii=False)
        return {
            "content": [{"type": "text", "text": payload}],
            "isError": True,
        }


def _handle(msg: dict) -> dict | None:
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        requested = (params.get("protocolVersion") or PROTOCOL_VERSION)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": _TOOL_SPECS},
        }
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": _call_tool(name, args),
        }
    if method.startswith("notifications/"):
        return None  # notifications have no response
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }, ensure_ascii=False), flush=True)
            continue
        response = _handle(msg)
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
