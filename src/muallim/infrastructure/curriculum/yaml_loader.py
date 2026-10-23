"""Загрузка учебной программы и словаря из curriculum/*.yaml."""

from pathlib import Path
from typing import Any

import yaml

from muallim.application.feedback import FeedbackCatalog, FeedbackLanguage, FeedbackTemplates
from muallim.domain.assessment import ErrorKind
from muallim.domain.curriculum import (
    Curriculum,
    ItemKind,
    Lesson,
    LessonItem,
    Lexicon,
    SourceRef,
)


def load_curriculum(course_path: Path, lexicon_path: Path) -> Curriculum:
    course = _read(course_path)
    lessons = tuple(_lesson(raw) for raw in course["lessons"])
    return Curriculum(
        id=course["id"],
        version=str(course["version"]),
        title=course["title"],
        lessons=lessons,
        lexicon=load_lexicon(lexicon_path),
    )


def load_lexicon(path: Path) -> Lexicon:
    raw = _read(path)
    return Lexicon(
        consonants={k: (v["name"], v["translit"]) for k, v in raw["consonants"].items()},
        vowels=dict(raw["vowels"]),
        letter_tips=dict(raw["letter_tips"]),
        pair_tips={frozenset(p["pair"]): p["tip"] for p in raw["pair_tips"]},
        transcription={k: str(v) for k, v in (raw.get("transcription") or {}).items()},
        transcription_legend={
            k: str(v) for k, v in (raw.get("transcription_legend") or {}).items()
        },
        vowel_tips={k: str(v) for k, v in (raw.get("vowel_tips") or {}).items()},
        sounds={
            k: (str(v["say"]), str(v.get("note") or ""))
            for k, v in (raw.get("sounds") or {}).items()
        },
        syllables={
            k: (str(v["syllables"][0]), str(v["syllables"][1]), str(v["syllables"][2]))
            for k, v in (raw.get("sounds") or {}).items()
            if v.get("syllables")
        },
        missing=str(raw.get("missing") or ""),
    )


def load_feedback_catalog(curriculum_dir: Path, default: str = "ru") -> FeedbackCatalog:
    """Все языки, для которых есть пара lexicon.<язык>.yaml + feedback.<язык>.yaml (ADR-0017)."""
    languages = {}
    for lexicon_path in sorted(curriculum_dir.glob("lexicon.*.yaml")):
        code = lexicon_path.name.split(".")[1]
        feedback_path = curriculum_dir / f"feedback.{code}.yaml"
        if not feedback_path.exists():
            raise ValueError(f"Для {lexicon_path.name} нет {feedback_path.name}")
        raw = _read(feedback_path)
        meta = raw["language"]
        if meta["code"] != code:
            raise ValueError(f"{feedback_path.name}: language.code = {meta['code']!r}")
        templates = FeedbackTemplates(
            messages={ErrorKind(k): v for k, v in raw["messages"].items()},
            where=raw["where"],
            tip=raw["tip"],
            joiner=raw.get("joiner", " + "),
            how={ErrorKind(k): v for k, v in (raw.get("how") or {}).items()},
            how_line=raw.get("how_line", ""),
            unread=raw.get("unread", ""),
            unread_how=raw.get("unread_how", ""),
            line=raw.get("line", ""),
            line_missing=raw.get("line_missing", ""),
            short={ErrorKind(k): v for k, v in (raw.get("short") or {}).items()},
        )
        missing = set(ErrorKind) - set(templates.messages)
        if missing:
            raise ValueError(f"{feedback_path.name}: нет шаблонов для {sorted(missing)}")
        languages[code] = FeedbackLanguage(
            code=code,
            title=meta["title"],
            enabled=bool(meta.get("enabled", False)),
            lexicon=load_lexicon(lexicon_path),
            templates=templates,
        )
    return FeedbackCatalog(languages, default)


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: ожидался YAML-словарь")
    return data


def _source(raw: dict[str, Any] | None) -> SourceRef | None:
    if raw is None:
        return None
    return SourceRef(
        source_id=raw["source_id"],
        page=raw.get("page"),
        line=raw.get("line"),
        note=raw.get("note", ""),
        verified=bool(raw.get("verified", False)),
    )


def _lesson(raw: dict[str, Any]) -> Lesson:
    kind = raw["kind"]  # тип карточек урока; у карточки может быть свой
    lesson_source = _source(raw.get("source"))
    items = tuple(
        LessonItem(
            id=it["id"],
            text=it["text"],
            kind=ItemKind(it.get("kind", kind)),
            sound=it.get("sound", ""),
            name=it.get("name", ""),
            tip=it.get("tip", ""),
            translation=it.get("translation", ""),
            source=_source(it.get("source")) or lesson_source,
            note=it.get("note", ""),
            quran=str(it.get("quran", "")),
        )
        for it in raw["items"]
    )
    return Lesson(
        id=raw["id"],
        number=raw["number"],
        title=raw["title"],
        items=items,
        source=lesson_source,
        accent=frozenset(raw.get("accent", "")),
        part=raw.get("part", ""),
        section=raw.get("section", ""),
    )
