"""Config loading tests."""

import pytest

from lra_mcp.config import load_config
from lra_mcp.errors import LraMcpError


def _write_config(path, profile_extra="", default_profile="mock", lsp_enabled=False):
    path.write_text(f"""default_profile: {default_profile}
profiles:
  mock:
    base_url: "http://127.0.0.1:8000/v1"
    api_key_env: "MOCK_KEY"
    model: "mock-model"
    temperature: 0.2
    max_tokens: 4096
    context_length: 8192
    timeout: 30
{profile_extra}
lsp:
  enabled: {str(lsp_enabled).lower()}
review:
  concurrency: 4
""", encoding="utf-8")


def test_load_config_happy_path(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    _write_config(config)
    monkeypatch.setenv("LRA_MCP_CONFIG", str(config))
    monkeypatch.setenv("LRA_MCP_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.delenv("LRA_MCP_ALLOW_INLINE_KEY", raising=False)

    cfg = load_config()
    assert cfg.lra_profile == "mock"
    assert cfg.runs_dir == tmp_path / "runs"
    assert cfg.concurrency == 4


def test_config_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("LRA_MCP_CONFIG", str(tmp_path / "nope.yaml"))
    with pytest.raises(LraMcpError) as e:
        load_config()
    assert e.value.code == "CONFIG_MISSING"


def test_profile_not_found(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    _write_config(config)
    monkeypatch.setenv("LRA_MCP_CONFIG", str(config))
    monkeypatch.setenv("LRA_MCP_PROFILE", "does-not-exist")
    with pytest.raises(LraMcpError) as e:
        load_config()
    assert e.value.code == "PROFILE_NOT_FOUND"


def test_inline_key_rejected(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    _write_config(config, profile_extra='    api_key: "sk-inline-secret"\n')
    monkeypatch.setenv("LRA_MCP_CONFIG", str(config))
    monkeypatch.delenv("LRA_MCP_ALLOW_INLINE_KEY", raising=False)
    with pytest.raises(LraMcpError) as e:
        load_config()
    assert e.value.code == "CONFIG_KEY_POLICY"


def test_lsp_enabled_rejected(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    _write_config(config, lsp_enabled=True)
    monkeypatch.setenv("LRA_MCP_CONFIG", str(config))
    with pytest.raises(LraMcpError) as e:
        load_config()
    assert e.value.code == "LSP_UNSUPPORTED"


def test_config_review_without_concurrency_defaults(tmp_path, monkeypatch):
    # Regression: config.yaml with a `review:` section that lacks `concurrency`
    # must fall back to 16, not crash on int(str(None)).
    config = tmp_path / "config.yaml"
    config.write_text("""default_profile: mock
profiles:
  mock:
    base_url: "http://127.0.0.1:8000/v1"
    api_key_env: "MOCK_KEY"
    model: "mock-model"
review:
  second_profile: mock
lsp:
  enabled: false
""", encoding="utf-8")
    monkeypatch.setenv("LRA_MCP_CONFIG", str(config))
    monkeypatch.delenv("LRA_MCP_CONCURRENCY", raising=False)
    monkeypatch.delenv("LRA_MCP_ALLOW_INLINE_KEY", raising=False)

    cfg = load_config()
    assert cfg.concurrency == 16
