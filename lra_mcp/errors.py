"""Error model for lra-mcp.

Every business error is an :class:`LraMcpError` carrying a stable machine
readable ``code``. The FastMCP layer turns it into an isError result whose
text content is the JSON object from :meth:`LraMcpError.to_json`.
"""

from __future__ import annotations

import json


class LraMcpError(Exception):
    """Business error with a stable code for MCP clients."""

    def __init__(self, code: str, detail: str = "", **extra):
        self.code = code
        self.detail = detail
        self.extra = extra
        super().__init__(code if not detail else f"{code}: {detail}")

    def to_json(self) -> str:
        payload = {"code": self.code, **self.extra}
        if self.detail:
            payload["detail"] = self.detail
        return json.dumps(payload, ensure_ascii=False)
