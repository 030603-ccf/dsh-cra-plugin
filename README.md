# lra-mcp

MCP server for [lra](https://github.com/030603-ccf/code-review-agent) — a LangGraph-based code review agent. It wraps lra as read-only tools so any MCP client (Claude Desktop, Cursor, Windsurf, …) can review code through an LLM.

Exposes 4 read-only tools over stdio:

| Tool | Purpose |
| --- | --- |
| `review_project` | run a full code review, return a findings summary |
| `review_diff` | review only git diff changes |
| `get_finding` | fetch one finding's full evidence by id |
| `generate_fix_prompt` | build a per-file fix task prompt (zero LLM tokens) |

## Install

Requires Python 3.11+.

```bash
# run on demand
uvx lra-mcp

# or install
pip install lra-mcp
lra-mcp
```

`lra` is a dependency and is installed automatically from PyPI.

## Configure

The server reads everything from environment variables; tool parameters never carry API keys.

| Variable | Required | Description |
| --- | --- | --- |
| `LRA_MCP_CONFIG` | yes | path to an lra `config.yaml` (copy lra's `config.example.yaml` and fill in your own profile) |
| `LRA_MCP_PROFILE` | no | profile name inside that config (default: its `default_profile`) |
| `LRA_MCP_RUNS_DIR` | no | where review runs are stored (default: `~/.lra-mcp/runs`) |

Config requirements (inherited from lra):

- `api_key` must come from `api_key_env` (an environment variable), not inline in the file.
- `lsp.enabled` must be `false`.

Put your API key in the env var named by your config's `api_key_env` (e.g. `DEEPSEEK_API_KEY`).

## MCP client config

Point any MCP client at the stdio server:

```json
{
  "mcpServers": {
    "lra": {
      "command": "uvx",
      "args": ["lra-mcp"],
      "env": {
        "LRA_MCP_CONFIG": "/absolute/path/to/lra/config.yaml",
        "LRA_MCP_PROFILE": "deepseek",
        "LRA_MCP_RUNS_DIR": "/absolute/path/to/runs"
      }
    }
  }
}
```

- Claude Desktop: `claude_desktop_config.json`
- Cursor: `.cursor/mcp.json`
- Never put a real API key in this file — it comes from the env var named by `api_key_env`.

Tools surface under the `mcp__lra__*` namespace (e.g. `mcp__lra__review_project`).

## Local development

```bash
# 1. install lra (editable, from source)
git clone https://github.com/030603-ccf/code-review-agent
cd code-review-agent && pip install -e .

# 2. install lra-mcp (editable + dev)
git clone https://github.com/030603-ccf/lra-mcp
cd lra-mcp && pip install -e ".[dev]"

# 3. test
pytest tests -q
```

## Notes

- All four tools are read-only: the server never mutates the reviewed project.
- Run products (`findings.json`, `report.md`, `summary.json`) land in `LRA_MCP_RUNS_DIR/<run_id>/`.
