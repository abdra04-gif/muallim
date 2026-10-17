#!/usr/bin/env python3
"""PostToolUse: автоформат изменённого .py и сообщение агенту об оставшихся ошибках ruff."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, read_event


def main() -> None:
    event = read_event()
    path = str((event.get("tool_input") or {}).get("file_path", ""))
    if not path.endswith(".py") or not Path(path).exists():
        return
    run = ["uv", "run", "--quiet", "ruff"]
    subprocess.run([*run, "format", "--quiet", path], cwd=ROOT, check=False)
    subprocess.run([*run, "check", "--fix", "--quiet", path], cwd=ROOT, check=False)
    result = subprocess.run(
        [*run, "check", "--output-format", "concise", path],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if result.returncode != 0:
        print(f"ruff нашёл проблемы, исправь:\n{result.stdout[-3000:]}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
