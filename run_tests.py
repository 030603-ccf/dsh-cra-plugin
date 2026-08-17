"""Write lra-mcp test/compileall output to test_output.log as clean UTF-8."""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "test_output.log"


def _append():
    return LOG.open("a", encoding="utf-8", errors="replace")


def run_step(name: str, cmd: list[str]) -> int:
    with _append() as f:
        f.write(f"\n=== {name} ===\n")
        f.write(f"cmd: {' '.join(cmd)}\n")
        f.write(f"start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    with _append() as f:
        proc = subprocess.run(
            cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        f.write(f"\n{name} exit code: {proc.returncode}\n")
        return proc.returncode


def main() -> int:
    if LOG.exists():
        LOG.write_text("", encoding="utf-8")
    with _append() as f:
        f.write("=== lra-mcp test run ===\n")
        f.write(f"start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    py_code = run_step("pytest", ["python", "-m", "pytest", "tests", "-q"])
    cc_code = run_step("compileall", ["python", "-m", "compileall", "lra_mcp"])

    with _append() as f:
        f.write(f"\nSUMMARY pytest={py_code} compileall={cc_code}\n")

    print(f"pytest exit code: {py_code}")
    print(f"compileall exit code: {cc_code}")
    print(f"LOG SAVED: {LOG}")
    return 0 if (py_code == 0 and cc_code == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
