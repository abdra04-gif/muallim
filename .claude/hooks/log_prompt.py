#!/usr/bin/env python3
"""UserPromptSubmit: сохраняет запрос человека в docs/journal/prompts/ГГГГ-ММ.md (NFR-TR-04).

Секреты маскируются до записи. Хук никогда не блокирует запрос: ошибка записи не мешает работе.
"""

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, read_event

SECRET_PATTERNS = [
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),  # токен Telegram-бота
    re.compile(r"\b(sk|pk|ghp|gho|github_pat|xox[abp])[-_][A-Za-z0-9_-]{16,}\b"),  # API-ключи
    re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\s*[=:]\s*\S+"),
    re.compile(r"postgres(ql)?(\+\w+)?://[^\s:@]+:[^\s@]+@"),  # пароль в URL БД
]


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[СКРЫТО]", text)
    return text


def main() -> None:
    event = read_event()
    prompt = str(event.get("prompt", "")).strip()
    if not prompt:
        return
    now = datetime.now(tz=UTC)
    path = ROOT / "docs" / "journal" / "prompts" / f"{now:%Y-%m}.md"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with path.open("a", encoding="utf-8") as f:
            if new:
                f.write(
                    f"# Запросы к ИИ-агенту — {now:%Y-%m}\n\nВремя — UTC. Пишет log_prompt.py.\n"
                )
            session = str(event.get("session_id", ""))[:8]
            f.write(f"\n## {now:%Y-%m-%d %H:%M} · сессия {session}\n\n{redact(prompt)}\n")
    except OSError as error:
        print(f"log_prompt: не удалось записать журнал: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
