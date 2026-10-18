#!/usr/bin/env python3
"""PreToolUse: каждую новую библиотеку проверить на PyPI до установки (ADR-0046).

Агент может «придумать» пакет, которого нет, или спутать имя с похожим чужим (slopsquatting,
тайпсквоттинг). Хук ловит `uv add` / `pip install` и новые строки зависимостей в pyproject.toml:
- пакета нет на PyPI → блок (exit 2): имя, скорее всего, выдумано;
- пакет есть → карточка (версия, первый выпуск, репозиторий, уязвимости OSV, тревожные признаки)
  уходит человеку в запрос подтверждения. Решение о зависимости всё равно за человеком (CLAUDE.md).
Сеть недоступна → не блокирует, а просит человека проверить вручную.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import ROOT, block, log_event, read_event

TIMEOUT = 4
NEW_DAYS = 90  # моложе — тревожный признак: у нового пакета ещё нет истории
INSTALL = re.compile(
    r"(?:^|&&|;|\|)\s*(?:uv\s+add|uv\s+pip\s+install|pip3?\s+install|poetry\s+add)\s+(.+)"
)
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
# Зависимость = имя и сразу версия: "pkg>=1", "pkg[extra]~=2" (uv add пишет именно так).
# Коды правил ruff, версии Python и плагины mypy в кавычках без версии — не зависимости.
REQUIREMENT = re.compile(r"""["']([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:[<>~!]=?|==)""")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def packages_in_command(command: str) -> list[str]:
    """Имена пакетов из команды установки; флаги, пути, URL и `-r файл` пропускаются."""
    found: list[str] = []
    for match in INSTALL.finditer(command):
        words = re.split(r"\s+", match.group(1).split("&&")[0].split(";")[0].split("|")[0])
        skip_next = False
        for word in words:
            if skip_next:
                skip_next = False
                continue
            if word in {"-r", "--requirement", "-c", "--group", "--extra", "--optional", "-e"}:
                skip_next = True
                continue
            if not word or word.startswith(("-", ".", "/", "git+", "http")):
                continue
            name = NAME.match(word.strip("'\""))
            if name:
                found.append(normalize(name.group(0)))
    return found


def declared(pyproject: str) -> set[str]:
    return {normalize(m.group(1)) for m in REQUIREMENT.finditer(pyproject)}


def new_requirements(old: str, new: str) -> list[str]:
    """Зависимости, которых не было в старом тексте pyproject.toml."""
    return sorted(declared(new) - declared(old))


def lookalike(name: str, known: set[str]) -> str | None:
    """Известная зависимость, на которую имя подозрительно похоже (одна-две буквы разницы)."""
    for other in known:
        if other != name and SequenceMatcher(None, name, other).ratio() >= 0.85:
            return other
    return None


def warnings(info: dict[str, Any], first_release: datetime | None, vulns: int) -> list[str]:
    """Тревожные признаки по метаданным PyPI — без сети, чтобы проверять тестом."""
    out: list[str] = []
    urls = info.get("project_urls") or {}
    if not any("github.com" in str(u) or "gitlab" in str(u) for u in urls.values()):
        out.append("нет ссылки на репозиторий с кодом")
    if first_release and (datetime.now(UTC) - first_release).days < NEW_DAYS:
        out.append(f"первый выпуск меньше {NEW_DAYS} дней назад")
    if not (info.get("summary") or "").strip():
        out.append("нет описания")
    if vulns:
        out.append(f"известных уязвимостей в последней версии: {vulns} (OSV)")
    return out


def _get(url: str, body: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = json.dumps(body).encode() if body else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            parsed = json.load(response)
            return parsed if isinstance(parsed, dict) else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        return None
    except (OSError, ValueError):
        return None


def card(name: str, known: set[str]) -> tuple[str, bool | None]:
    """(строка для человека, найден ли пакет: True / False / None — сеть недоступна)."""
    meta = _get(f"https://pypi.org/pypi/{name}/json")
    if meta is None:
        return f"{name}: PyPI недоступен — проверьте вручную https://pypi.org/project/{name}/", None
    if not meta:
        return f"{name}: НЕТ на PyPI — имя, скорее всего, выдумано или с опечаткой", False
    info = meta.get("info") or {}
    uploads = [
        datetime.fromisoformat(f["upload_time_iso_8601"].replace("Z", "+00:00"))
        for files in (meta.get("releases") or {}).values()
        for f in files
        if f.get("upload_time_iso_8601")
    ]
    first = min(uploads) if uploads else None
    osv = _get(
        "https://api.osv.dev/v1/query",
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": info.get("version")},
    )
    vulns = len((osv or {}).get("vulns") or [])
    urls = info.get("project_urls") or {}
    repo = next((u for u in urls.values() if "github.com" in str(u)), info.get("home_page") or "—")
    flags = warnings(info, first, vulns)
    twin = lookalike(name, known)
    if twin:
        flags.append(f"имя похоже на уже подключённую «{twin}» — не опечатка ли?")
    since = f"{first:%Y-%m}" if first else "?"
    text = f"{name} {info.get('version')} · с {since} · {repo}"
    return text + (" · ⚠ " + "; ".join(flags) if flags else " · признаков риска нет"), True


def main() -> None:
    event = read_event()
    tool = str(event.get("tool_name", ""))
    args = event.get("tool_input") or {}
    pyproject = ROOT / "pyproject.toml"
    known = declared(pyproject.read_text(encoding="utf-8")) if pyproject.exists() else set()
    if tool == "Bash":
        names = packages_in_command(str(args.get("command", "")))
    elif tool in {"Edit", "Write"} and str(args.get("file_path", "")).endswith("pyproject.toml"):
        old = str(args.get("old_string", "")) if tool == "Edit" else ""
        if tool == "Write" and pyproject.exists():
            old = pyproject.read_text(encoding="utf-8")
        names = new_requirements(old, str(args.get("new_string") or args.get("content") or ""))
        names = [n for n in names if n not in known]
    else:
        return
    if not names:
        return
    results = [card(n, known) for n in names]
    missing = [text for text, found in results if found is False]
    if missing:
        block("Пакета нет на PyPI — не устанавливаю (ADR-0046):\n" + "\n".join(missing))
    report = "Проверка библиотек (ADR-0046):\n" + "\n".join(text for text, _ in results)
    log_event("ask", report)
    decision = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": report,
    }
    print(json.dumps({"hookSpecificOutput": decision}, ensure_ascii=False))


if __name__ == "__main__":
    main()
