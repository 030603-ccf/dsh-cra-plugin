FROM python:3.12-slim

# lra-code-review-mcp pulls the lra-code-review agent as a dependency from PyPI
RUN pip install --no-cache-dir lra-code-review-mcp

# MCP stdio server: speaks JSON-RPC over stdin/stdout.
# Run with `docker run -i` and mount your lra config.yaml at /config.yaml.
ENTRYPOINT ["lra-code-review-mcp"]
