"""Пересборка `tests/fixtures/maroof_cards.json` (FR-70 п. 1, ADR-0088).

Записи фонетизатора бота (wasl и waqf) для каждой карточки уроков 1–41, которую бот проверяет
голосом. Нужна, чтобы тест «все карточки переводятся в звуки MostafaMaroof» шёл без quran-transcript
(его нет в CI). Пересобрать после правки программы или фонетизатора — окружением с extra ``ml``:

    PYTHONPATH=src /путь/к/.venv-с-ml/bin/python tests/fixtures/make_maroof_cards.py
"""

import json
from pathlib import Path

from muallim.infrastructure.curriculum.yaml_loader import load_curriculum

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("maroof_cards.json")
LESSONS = range(1, 42)


def main() -> None:
    try:  # ADR-0088 п. 2: фонетизатор выносится в общий модуль
        from muallim.infrastructure.asr.phonetizer import _references  # noqa: PLC0415
    except ImportError:
        from muallim.infrastructure.asr.muaalem import _references  # noqa: PLC0415

    curriculum = load_curriculum(
        ROOT / "curriculum" / "course.ru.yaml", ROOT / "curriculum" / "lexicon.ru.yaml"
    )
    cards = [
        {"id": item.id, "text": item.text, **dict(_references(item.text)[1])}
        for lesson in curriculum.lessons
        if lesson.number in LESSONS
        for item in lesson.items
        if item.is_checkable
    ]
    OUT.write_text(json.dumps(cards, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
