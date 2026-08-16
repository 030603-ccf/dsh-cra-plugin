# lra-code-review-mcp

[lra-code-review](https://github.com/030603-ccf/code-review-agent)（基于 LangGraph 的代码审查智能体）的 MCP server。它把 lra-code-review 包装成只读工具，任何 MCP 客户端（Claude Desktop、Cursor、Windsurf……）都能通过 LLM 审查代码。

通过 stdio 暴露 4 个只读工具：

| 工具 | 用途 |
| --- | --- |
| `review_project` | 全量代码审查，返回 findings 摘要 |
| `review_diff` | 只审 git diff 变更 |
| `get_finding` | 按 id 取单条 finding 的完整证据 |
| `generate_fix_prompt` | 生成单文件的修复任务 prompt（零 LLM token） |

## 安装

需要 Python 3.11+。

```bash
# 临时跑一次
uvx lra-code-review-mcp

# 或安装
pip install lra-code-review-mcp
lra-code-review-mcp
```

`lra-code-review` 是依赖项，会从 PyPI 自动安装。

## Docker

每次打 tag 都会发布一个容器镜像到 GHCR，无需安装 Python 就能跑：

```bash
docker run -i --rm \
  -v /absolute/path/to/lra/config.yaml:/config.yaml \
  -e LRA_MCP_CONFIG=/config.yaml \
  -e LRA_MCP_PROFILE=deepseek \
  -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  ghcr.io/030603-ccf/dsh-cra-plugin
```

- `-i` 保持 stdio 打开——MCP 传输走 stdin/stdout。
- 挂载你的 lra `config.yaml`，并把 `LRA_MCP_CONFIG` 指向 `/config.yaml`。
- 用 `-e`（或 `--env-file`）传 API key；绝不要把 key 打进镜像。

## 配置

server 的一切配置都来自环境变量；工具参数从不携带 API key。

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `LRA_MCP_CONFIG` | 是 | `config.yaml` 的路径——复制本仓库的 `config.example.yaml` 并填自己的 profile |
| `LRA_MCP_PROFILE` | 否 | 该 config 里的 profile 名（默认用它的 `default_profile`） |
| `LRA_MCP_RUNS_DIR` | 否 | 审查产物的存放目录（默认 `~/.lra-code-review-mcp/runs`） |

### API key

你的 key 存在环境变量里，由 config 中的 `api_key_env` 声明变量名：

```yaml
profiles:
  deepseek:
    api_key_env: "DEEPSEEK_API_KEY"
```

三种方式设置这个变量：

1. **Shell**（CLI）：`export DEEPSEEK_API_KEY=sk-...`
2. **MCP 客户端的 `env` 块**（Claude Desktop / Cursor）：在 server 的 `env` 里加 `"DEEPSEEK_API_KEY": "sk-..."`
3. **Docker**：`docker run -i --rm ... -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" ...`

要求（继承自 lra）：

- `api_key` 必须来自 `api_key_env`，不能内联写在文件里。
- `lsp.enabled` 必须是 `false`。

## MCP 客户端配置

让任意 MCP 客户端指向这个 stdio server：

```json
{
  "mcpServers": {
    "lra": {
      "command": "uvx",
      "args": ["lra-code-review-mcp"],
      "env": {
        "LRA_MCP_CONFIG": "/absolute/path/to/lra/config.yaml",
        "LRA_MCP_PROFILE": "deepseek",
        "LRA_MCP_RUNS_DIR": "/absolute/path/to/runs"
      }
    }
  }
}
```

- Claude Desktop：`claude_desktop_config.json`
- Cursor：`.cursor/mcp.json`
- 绝不要把真实 API key 写进这个文件——它来自 `api_key_env` 指定的环境变量。

工具暴露在 `mcp__lra__*` 命名空间下（例如 `mcp__lra__review_project`）。

## 本地开发

```bash
# 1. 安装 lra（源码可编辑安装）
git clone https://github.com/030603-ccf/code-review-agent
cd code-review-agent && pip install -e .

# 2. 安装 lra-code-review-mcp（可编辑 + dev）
git clone https://github.com/030603-ccf/dsh-cra-plugin
cd dsh-cra-plugin && pip install -e ".[dev]"

# 3. 测试
pytest tests -q
```

## 说明

- 4 个工具都是只读的：server 从不修改被审查的项目。
- 审查产物（`findings.json`、`report.md`、`summary.json`）落在 `LRA_MCP_RUNS_DIR/<run_id>/`。
