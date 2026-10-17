#!/usr/bin/env python3
"""SessionStart: короткая сводка состояния проекта в контекст агента (ADR-0034).

TDD-фаза, установлена ли реальная модель, сколько открыто блокирующего техдолга, последняя
сводка сессии. Секреты и данные не читает: .env и data/ не открываются.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, phase

PHASE_NOTE = {
    "tests": "пишутся падающие тесты, src/ не трогать",
    "impl": "тесты заморожены хуком; неверный тест — стоп-сигнал, спросить человека",
    "off": "вне TDD-цикла",
}
OPEN_T1 = re.compile(r"^\| TD-.*🔴 T1.*\|\s*открыт", re.MULTILINE)


def model_installed() -> bool:
    return any(ROOT.glob(".venv/lib/python3*/site-packages/quran_muaalem"))


def open_t1() -> int:
    try:
        return len(OPEN_T1.findall((ROOT / "docs" / "tech-debt.md").read_text(encoding="utf-8")))
    except OSError:
        return -1


def last_session() -> str:
    sessions = sorted((ROOT / "docs" / "journal" / "sessions").glob("*.md"))
    sessions = [s for s in sessions if s.name != "README.md"]
    return sessions[-1].relative_to(ROOT).as_posix() if sessions else "нет"


def main() -> None:
    current = phase()
    model = (
        "установлена (uv sync --extra ml)"
        if model_installed()
        else "НЕ установлена — бот с заглушкой засчитывает всё; ученику так не отдавать"
    )
    lines = [
        "Состояние проекта Muallim (хук session_context):",
        f"- TDD-фаза: {current} — {PHASE_NOTE.get(current, '?')}",
        f"- Модель Muaalem: {model}",
        f"- Открытый техдолг T1 (блокирует пилот с незнакомыми): {open_t1()}",
        f"- Последняя сводка сессии: {last_session()}",
    ]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
