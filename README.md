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

## Docker

A container image is published to GHCR on every tag, so you can run it without installing Python:

```bash
docker run -i --rm \
  -v /absolute/path/to/lra/config.yaml:/config.yaml \
  -e LRA_MCP_CONFIG=/config.yaml \
  -e LRA_MCP_PROFILE=deepseek \
  -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  ghcr.io/030603-ccf/lra-mcp
```

- `-i` keeps stdio open — the MCP transport rides stdin/stdout.
- Mount your lra `config.yaml` and point `LRA_MCP_CONFIG` at `/config.yaml`.
- Pass the API key via `-e` (or `--env-file`); never bake it into the image.

## Configure

The server reads everything from environment variables; tool parameters never carry API keys.

| Variable | Required | Description |
| --- | --- | --- |
| `LRA_MCP_CONFIG` | yes | path to a `config.yaml` — copy this repo's `config.example.yaml` and fill in your profile |
| `LRA_MCP_PROFILE` | no | profile name inside that config (default: its `default_profile`) |
| `LRA_MCP_RUNS_DIR` | no | where review runs are stored (default: `~/.lra-mcp/runs`) |

### API key

Your key lives in an environment variable; `api_key_env` in the config names it:

```yaml
profiles:
  deepseek:
    api_key_env: "DEEPSEEK_API_KEY"
```

Set that variable one of three ways:

1. **Shell** (CLI): `export DEEPSEEK_API_KEY=sk-...`
2. **MCP client `env` block** (Claude Desktop / Cursor): add `"DEEPSEEK_API_KEY": "sk-..."` to the server's `env`.
3. **Docker**: `docker run -i --rm ... -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" ...`

Requirements (inherited from lra):

- `api_key` must come from `api_key_env`, not inline in the file.
- `lsp.enabled` must be `false`.

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
