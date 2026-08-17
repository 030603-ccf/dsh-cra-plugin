"""Security layer tests: pure validation logic."""

import pytest

from lra_mcp.config import McpConfig
from lra_mcp.errors import LraMcpError
from lra_mcp.security import (
    preflight_project,
    validate_base_ref,
    validate_finding_ids,
    validate_hint,
    validate_project_path,
    validate_run_id,
)


def _cfg(tmp_path, **kw):
    defaults = dict(
        lra_config_path=tmp_path / "config.yaml",
        lra_profile="mock",
        runs_dir=tmp_path / "runs",
        concurrency=2,
        total_timeout=1800,
        max_files=5000,
        max_file_bytes=2 * 1024 * 1024,
        max_hint_chars=500,
        max_findings=200,
        max_prompt_chars=200000,
    )
    defaults.update(kw)
    return McpConfig(**defaults)


def test_run_id_regex():
    assert validate_run_id("abc-123_XYZ") == "abc-123_XYZ"
    with pytest.raises(LraMcpError) as e:
        validate_run_id("../evil")
    assert e.value.code == "INVALID_RUN_ID"
    with pytest.raises(LraMcpError):
        validate_run_id("a b")


def test_hint_limit(tmp_path):
    cfg = _cfg(tmp_path)
    assert validate_hint("ok", 10) == "ok"
    with pytest.raises(LraMcpError) as e:
        validate_hint("x" * 11, 10)
    assert e.value.code == "HINT_TOO_LONG"


def test_base_ref_rejects_dash_and_whitespace():
    assert validate_base_ref(None) == "HEAD~1"
    with pytest.raises(LraMcpError) as e:
        validate_base_ref("--help")
    assert e.value.code == "INVALID_BASE_REF"
    with pytest.raises(LraMcpError):
        validate_base_ref("a b")


def test_finding_ids_regex_and_duplicate():
    assert validate_finding_ids(["F1", "F2"]) == ["F1", "F2"]
    with pytest.raises(LraMcpError) as e:
        validate_finding_ids(["../x"])
    assert e.value.code == "INVALID_FINDING_ID"
    with pytest.raises(LraMcpError):
        validate_finding_ids(["F1", "F1"])


def test_project_path_rejects_relative_and_missing(tmp_path):
    with pytest.raises(LraMcpError) as e:
        validate_project_path("relative/path")
    assert e.value.code == "INVALID_PATH"
    with pytest.raises(LraMcpError):
        validate_project_path(str(tmp_path / "not-there"))


def test_project_path_rejects_symlink(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("symlink not supported on this platform")
    with pytest.raises(LraMcpError) as e:
        validate_project_path(str(link))
    assert e.value.code == "INVALID_PATH"


def test_preflight_counts_only_lra_languages(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("x = 1\n", encoding="utf-8")
    (proj / "b.java").write_text("class B {}\n", encoding="utf-8")
    (proj / "c.md").write_text("# hi\n", encoding="utf-8")
    cfg = _cfg(tmp_path)
    assert preflight_project(proj, cfg) == 2


def test_preflight_file_size_limit(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "big.py").write_text("x = 1\n" * 100, encoding="utf-8")
    cfg = _cfg(tmp_path, max_file_bytes=10)
    with pytest.raises(LraMcpError) as e:
        preflight_project(proj, cfg)
    assert e.value.code == "PROJECT_TOO_LARGE"
