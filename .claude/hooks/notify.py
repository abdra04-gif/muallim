#!/usr/bin/env python3
"""Notification: уведомление macOS, когда агент ждёт человека (подтверждение, ответ).

Длинные задачи (модель, нарезка, тесты) идут минутами; без уведомления агент простаивает,
пока человек не заглянет в окно. На других ОС ничего не делает.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import read_event


def main() -> None:
    if sys.platform != "darwin":
        return
    message = (
        str(read_event().get("message") or "Агент ждёт ответа")
        .replace("\\", "/")
        .replace('"', "'")[:180]
    )
    script = f'display notification "{message}" with title "Muallim — Claude Code"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=5)


if __name__ == "__main__":
    main()
