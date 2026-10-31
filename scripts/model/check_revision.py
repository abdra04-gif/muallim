"""Не обновилась ли модель Muaalem на Hugging Face (TD-FN-121).

Сверяет последний коммит obadx/muaalem-model-v3_2 с EXPECTED_MODEL_REVISION из кода бота.
Новые коммиты → список и код выхода 1, проверка не состоялась (сеть, ответ API) → код 2;
в обоих случаях GitHub присылает письмо об упавшей проверке, разница — в сводке запуска
(`.github/workflows/model-revision.yml`, раз в неделю). Вручную: `make model-check`.
Только стандартная библиотека — проверке в GitHub не нужны зависимости бота.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = "obadx/muaalem-model-v3_2"
API = f"https://huggingface.co/api/models/{REPO}/commits/main"
ADAPTER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "muallim"
    / "infrastructure"
    / "asr"
    / "muaalem.py"
)


def expected_revision() -> str:
    text = ADAPTER.read_text(encoding="utf-8")
    found = re.search(r'^EXPECTED_MODEL_REVISION: Final = "([0-9a-f]{40})"', text, re.M)
    if not found:
        raise SystemExit(f"не нашёл EXPECTED_MODEL_REVISION в {ADAPTER}")
    return found.group(1)


def failed(reason: object) -> str:
    return f"Проверка не состоялась (это не обновление модели): {reason}"


def compare(history: Any, expected: str) -> tuple[bool | None, str]:
    """История — новые сверху (как отдаёт API).

    Возвращает (True — без изменений, False — обновилась, None — проверка не состоялась; текст).
    """
    if not isinstance(history, list) or not history or not isinstance(history[0], dict):
        return None, failed(f"неожиданный ответ API: {str(history)[:200]}")
    latest = history[0]
    if latest["id"] == expected:
        return True, f"Без изменений: {REPO} @ {expected[:7]} от {latest['date'][:10]}."
    ids = [c["id"] for c in history]
    new = history[: ids.index(expected)] if expected in ids else history
    lines = [
        f"Модель {REPO} обновилась: ожидали {expected[:7]}, последняя {latest['id'][:7]}.",
        ""
        if expected in ids
        else "Ожидаемой ревизии нет на первой странице истории: новых коммитов много"
        " или история переписана — смотри ссылку ниже.",
        "Новые коммиты (новые сверху):",
        *(f"  {c['date'][:10]}  {c['id'][:7]}  {c['title']}" for c in new),
        f"Изменения: https://huggingface.co/{REPO}/commits/main",
        "Что делать: TD-FN-121 в docs/tech-debt.md (решить, переходить ли на новую версию).",
    ]
    return False, "\n".join(line for line in lines if line)


def main() -> int:
    try:
        with urllib.request.urlopen(API, timeout=30) as response:
            history = json.load(response)
        ok, text = compare(history, expected_revision())
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
        ok, text = None, failed(error)
    print(text)
    return {True: 0, False: 1, None: 2}[ok]


if __name__ == "__main__":
    sys.exit(main())
