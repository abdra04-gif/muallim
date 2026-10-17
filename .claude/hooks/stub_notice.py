#!/usr/bin/env python3
"""PostToolUse (Bash): бот запущен с заглушкой → агент обязан сказать об этом человеку.

Заглушка засчитывает любое аудио и не объясняет ошибок; человек, не знающий об этом, решит, что
бот сломан (2026-10-17). Хук ничего не запрещает, только добавляет напоминание в контекст.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import read_event

STUB = re.compile(r"(make\s+run-stub|ASR_BACKEND=stub)")


def main() -> None:
    event = read_event()
    command = str((event.get("tool_input") or {}).get("command", ""))
    if event.get("tool_name") != "Bash" or not STUB.search(command):
        return
    note = (
        "Бот запущен с ЗАГЛУШКОЙ распознавания: любое чтение засчитывается, ошибки не объясняются. "
        "Скажи человеку об этом явно. Для настоящей проверки — `uv sync --extra ml && make run`."
    )
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
