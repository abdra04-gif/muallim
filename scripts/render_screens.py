"""Макеты экранов бота из настоящего кода: docs/design/screens/*.png + screens.json (make design).

Пример ученика: пройдены уроки 2–4, начат 5, серия 4 дня. Картинки и подписи — те же функции,
что использует бот (presentation/telegram/screens.py), поэтому макет не расходится с ботом.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

from muallim.application.breakdown import build_breakdown
from muallim.application.feedback import Explanation
from muallim.application.transcription import as_text, legend, reading
from muallim.application.use_cases.progress import LessonProgress, Progress
from muallim.application.use_cases.quiz import QuizResult, QuizView
from muallim.application.use_cases.reading import HowToRead
from muallim.application.use_cases.recitation import RecitationResult
from muallim.domain.assessment import assess, unread_from
from muallim.domain.attempt import Attempt
from muallim.domain.curriculum import lesson_letter, letters_before
from muallim.domain.learner import Learner
from muallim.domain.policy import GradingPolicy
from muallim.domain.quiz import Pick, PickReason, RoundSummary, build_question, letter_heads
from muallim.domain.settings import LearnerSettings
from muallim.infrastructure.asr.reading import QuranReadingGuide
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum, load_feedback_catalog
from muallim.presentation.telegram import render, screens

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "screens"


def main() -> None:
    if not render.available():
        raise SystemExit("Нет libraqm: brew install fribidi и запуск через make design")
    c = load_curriculum(
        ROOT / "curriculum" / "course.ru.yaml", ROOT / "curriculum" / "lexicon.ru.yaml"
    )
    letters = [les for les in c.lessons if les.section == "letter"]
    done, started = {les.id for les in c.lessons[:5]}, letters[3].id  # пройдены 1–5, начат мим
    lessons = []
    for lesson in c.lessons:
        n = len(lesson.practice_items)
        weak = (lesson.practice_items[1],) if lesson.id == started else ()
        mastered = n if lesson.id in done else (1 if lesson.id == started else 0)
        lessons.append(LessonProgress(lesson, mastered, weak))
    current = c.lesson(started).items[1]
    week = (True, True, False, True, True, True, True)  # 7 дней, последний — сегодня
    p = Progress(
        tuple(lessons), 37, streak_days=4, today_attempts=6, continue_item=current,
        today=date(2026, 10, 18), week=week,
    )  # fmt: skip

    def find(pred) -> str:  # type: ignore[no-untyped-def]
        return next(i.id for les in c.lessons for i in les.items if pred(les, i))

    catalog = load_feedback_catalog(ROOT / "curriculum")
    renderer = catalog.renderer("ru")
    guide = QuranReadingGuide()
    learner = Learner(UUID(int=1), 1, "L-демо", "ru", datetime.now(UTC))
    how = HowToRead(guide, catalog)

    def card(item_id: str, has_audio: bool = True, teacher: bool = False) -> screens.Screen:
        item = c.item(item_id)
        return screens.card(c, item, has_audio, teacher, how.execute(learner, item))

    def result(item_id: str, swap: tuple[str, str] | None, completed: bool) -> RecitationResult:
        """Попытка с настоящим эталоном фонетизатора; ``swap`` — какую ошибку изобразить."""
        item = c.item(item_id)
        ref = guide.phonemes(item.text) or item.text
        heard = ref.replace(*swap, 1) if swap else ref
        a = assess(ref, heard)
        attempt = Attempt(
            UUID(int=7), UUID(int=1), item.id, c.version, "muaalem", a, GradingPolicy().verdict(a),
            None, 900, 300, datetime.now(UTC),
        )  # fmt: skip
        lex = renderer.lexicon
        expected = reading(ref, lex, [e.syllable for e in a.errors])
        heard_r = reading(heard, lex)
        return RecitationResult(
            item, attempt, tuple(Explanation(t) for t in renderer.render(a.errors, ref)),
            as_text(heard_r),
            c.next_item(item.id), completed,
            expected_reading=expected, heard_reading=heard_r,
            legend=legend(as_text(expected) + as_text(heard_r), lex),
            practice=tuple(dict.fromkeys(text for text, wrong in expected if wrong)),
            breakdown=build_breakdown(
                a, item.text, lex, unread=unread_from(ref, heard),
                lesson_letter=lesson_letter(c.locate(item.id)[0]),
            ),
        )  # fmt: skip

    sad = next(les for les in letters if les.title.split(" · ")[0].endswith("ص"))
    sad_line = next(i for i in sad.items if i.kind.value == "line")
    mim = c.lesson(started)
    heads = letter_heads(letters[:6])
    q = build_question(c, Pick(heads[-1], 1, 2, PickReason.NEW), heads)
    view = QuizView(UUID(int=1), q, round_no=1, position=3, correct_so_far=2)
    hear = QuizView(
        UUID(int=2), build_question(c, Pick(heads[-2], 2, 0, PickReason.OLD), heads), 1, 4, 3
    )
    shots = {
        "01_home": screens.home(c, p),
        "02_parts": screens.lessons(c, p, part=-1),
        "03_part_letters": screens.lessons(c, p, part=1),
        "04_rule": screens.card(
            c, c.item(find(lambda les, i: i.kind.value == "rule")), False, False
        ),
        "05_alphabet": screens.card(
            c, c.item(find(lambda les, i: i.kind.value == "alphabet")), False, False
        ),
        "06_letter": card(next(i.id for i in mim.items if i.kind.value == "letter")),
        "07_line": card(mim.items[1].id),
        "08_quran": card(find(lambda les, i: i.quran == "112:1")),
        "09_result_errors": screens.result(c, result(sad_line.id, ("ص", "س"), False), True),
        "10_result_done": screens.result(c, result(mim.items[-1].id, None, True), True),
        "11_quiz": screens.quiz(view),
        "12_quiz_answer": screens.quiz_answer(
            QuizResult(view, (q.answer + 1) % 4, correct=False, finished=False)
        ),
        "12b_quiz_hear": screens.quiz(hear),
        "12c_quiz_summary": screens.quiz_summary(
            c, RoundSummary(8, 10, tuple(heads[1:3]), confident=2, letters=len(heads))
        ),
        "13_signs": screens.signs(c, p),
        "14_progress": screens.progress(c, p),
        "15_help": screens.help_screen(),
        "16_teacher": card(letters[4].items[0].id, has_audio=False, teacher=True),
        "17_opening": screens.opening(c),
        "18_postcard": screens.postcard(c, mim, p, bot_username="muallim_bot"),
        "19_settings": screens.settings(LearnerSettings()),
        "20_letters_sheet": screens.letters_sheet(
            c,
            mim.id,
            audio=frozenset(h.id for h in letters_before(c, mim.id)),
            back_item=mim.items[1].id,
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    for name, s in shots.items():
        if s.image:
            (OUT / f"{name}.png").write_bytes(s.image)
        rows = [[b.text for b in row] for row in s.keyboard.inline_keyboard]
        meta[name] = {
            "caption": s.caption,
            "details": s.details,
            "buttons": rows,
            "image": f"{name}.png" if s.image else None,
        }
    (OUT / "screens.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    print(f"Экранов: {len(meta)} → {OUT}")


if __name__ == "__main__":
    main()
