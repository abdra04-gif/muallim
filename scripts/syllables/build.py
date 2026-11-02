"""Разобрать аяты уроков «Суры» на слоги (FR-61, ADR-0077): ``make syllables``.

Для каждого пункта урока ``section: sura`` с ``quran`` фонетизатор Хафса (``quran_transcript``,
extra ``ml``) даёт фонемы и для каждой буквы текста — её звуки (``mappings``). Слоги фонем
(``domain.phonetics.syllables``) режут слово на кусочки-клетки, звуки кусочка — подпись простой
кириллицей (``application.transcription.plain``, FR-54). Правила склейки:

- немая буква (ٱ, «ль» перед солнечной) — в клетке со следующей звучащей; в конце слова — с
  предыдущей;
- ٱ в начале аята звучит («а»), но отдельной клеткой не стоит — вместе со следующей;
- гунна, мадд лин, идгам танвина в و/ي — повторы звука сжаты («мм», а не «ммм»);
- хуруф мукатта'а (الٓمٓ) — всё слово одна клетка.

Результат — ``curriculum/syllables/ayat.yaml``: одна строка на уникальный текст пункта (басмала —
одна на все суры). Статусы человека сохраняются, если разбор не изменился (``merge.py``).
Падает, если хоть один пункт не разобран или кусочки не складываются ровно в текст.
"""

import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from quran_transcript import MoshafAttributes, quran_phonetizer

from muallim.application.transcription import plain
from muallim.domain.arabic import ALIF_WASL
from muallim.domain.curriculum import Curriculum, Lexicon
from muallim.domain.phonetics import CONSONANTS, syllables
from muallim.infrastructure.asr.muaalem import MOSHAF_PARAMS
from muallim.infrastructure.asr.script import for_phonetizer
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum

sys.path.insert(0, str(Path(__file__).parent))
from merge import UNCHECKED, Row, merge_status

ROOT = Path(__file__).resolve().parents[2]
CURRICULUM = ROOT / "curriculum"
OUT = CURRICULUM / "syllables" / "ayat.yaml"

HEADER = """# Аяты уроков «Суры» по слогам (ADR-0077, FR-61): кусочек слова и как он звучит.
# Разобрано фонетизатором Хафса (quran_transcript) с параметрами moshaf, подписи — простой
# кириллицей (FR-54). Связь с программой — по точному тексту пункта; номер аята — не здесь.
# status: unchecked → человек смотрит картинки и ставит ok или bad (bad бот не показывает).
# Собирает scripts/syllables/build.py (make syllables); руками не править.
"""

ALIF_FORMS = frozenset("اأإآٱ")  # с ل перед ними — лигатура «لا», клетку не рвём
SMALL_MADD = "ۥۦ"  # маленькие و ي после буквы — знак, а не буква
MADDA_ABOVE = "ٓ"
OWN_VOWELS = "َُِْ"  # фатха, дамма, кясра, сукун — у хуруф мукатта'а их нет
NASAL = "ں۾"  # фонемы гунны без своей буквы в CONSONANTS

Cell = tuple[str, str]  # кусочек, подпись
Span = tuple[int, int] | None  # звуки кластера в фонемах; None — немая буква


def _clusters(text: str) -> list[tuple[int, int]]:
    """Буква со знаками после неё (и пробел — отдельным кластером)."""
    out = []
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and unicodedata.category(text[j]) == "Mn":
            j += 1
        out.append((i, j))
        i = j
    return out


def squeeze(sounds: str) -> str:
    """Гунна и мадд лин — повторы согласной: обычная согласная → две, و/ي → одна."""

    def repeat(m: re.Match[str]) -> str:
        ch = m[1]
        if ch not in CONSONANTS and ch not in NASAL:
            return m[0]
        return ch if ch in "وي" else ch * 2

    sounds = re.sub(r"(.)\1{2,}", repeat, sounds)
    return re.sub(r"(?<=[َُِ])([وي])\1$", r"\1", sounds)  # идгам танвина в و/ي: «биу-уа»


def is_muqattaat(word: str) -> bool:
    return MADDA_ABOVE in word and not any(v in word for v in OWN_VOWELS)


def _spans(text: str, moshaf: MoshafAttributes) -> tuple[str, list[Span]]:
    """Фонемы аята и звуки каждого кластера текста."""
    source = for_phonetizer(text)
    res = quran_phonetizer(source, moshaf)
    phonemes, maps = res.phonemes, res.mappings
    if len(maps) != len(source):
        raise ValueError(f"mappings {len(maps)} != {len(source)}")
    if len(_clusters(text)) != len(_clusters(source)):
        raise ValueError("кластеры текста и фонетизатора не совпали")
    spans: list[Span] = []
    for a, b in _clusters(source):
        pos = [
            maps[k].pos
            for k in range(a, b)
            if not maps[k].deleted and maps[k].pos[0] < maps[k].pos[1]
        ]
        spans.append((min(p[0] for p in pos), max(p[1] for p in pos)) if pos else None)
    return phonemes, spans


def _group(text: str, phonemes: str, spans: list[Span]) -> list[list[list[int]]]:
    """Слово → клетки → номера кластеров. Клетка открывается на начале слога."""
    starts = {a for a, _ in syllables(phonemes) if phonemes[a] != " "}
    words: list[list[list[int]]] = []
    pending: list[int] = []  # немые кластеры до следующей звучащей буквы
    for n, (a, _) in enumerate(_clusters(text)):
        if text[a].isspace():
            if pending:  # немая в конце слова — к предыдущей клетке
                if words and words[-1]:
                    words[-1][-1].extend(pending)
                else:
                    words.append([pending])
                pending = []
            words.append([])
            continue
        if not words:
            words.append([])
        span, word = spans[n], words[-1]
        if span is None:
            pending.append(n)
            continue
        if not word or any(span[0] <= s < span[1] for s in starts):
            word.append([*pending, n])
        else:
            word[-1].extend([*pending, n])
        pending = []
    if pending:
        words[-1][-1].extend(pending)
    return [w for w in words if w]


def _caption(syllabled: str, two_syllables: bool) -> str:
    """Подпись клетки: слог слитно («ррах»); клетка «لا» из двух слогов — через дефис («ли-ии»)."""
    return syllabled if two_syllables else syllabled.replace("-", "")


def _keep_lam_alif(
    word: list[list[int]], text: str, clusters: list[tuple[int, int]]
) -> tuple[list[list[int]], list[list[int]]]:
    """«ٱلْ | أَكْ» → «ٱلْأَكْ»: ل и алиф после него — одна лигатура, как в мусхафе.

    Возвращает клетки и те из них, что склеены (в них два слога — подпись через дефис)."""

    def base(k: int) -> str:
        return text[clusters[k][0]]

    out: list[list[int]] = []
    joined: list[list[int]] = []
    for cell in word:
        letters = [k for k in sorted(cell) if base(k) not in SMALL_MADD]
        if out and letters and base(letters[0]) in ALIF_FORMS:
            previous = [k for k in sorted(out[-1]) if base(k) not in SMALL_MADD]
            if previous and base(previous[-1]) == "ل":
                out[-1] = out[-1] + cell
                joined.append(out[-1])
                continue
        out.append(cell)
    return out, joined


def split_ayah(text: str, lexicon: Lexicon, moshaf: MoshafAttributes) -> list[list[Cell]]:
    """Аят → слова → клетки (кусочек, подпись)."""
    phonemes, spans = _spans(text, moshaf)
    clusters = _clusters(text)

    def piece(cell: list[int]) -> str:
        return "".join(text[clusters[k][0] : clusters[k][1]] for k in sorted(cell))

    def sounds(cell: list[int]) -> str:
        out = ""
        for k in sorted(cell):
            span = spans[k]
            if span is not None:
                out += phonemes[span[0] : span[1]]
        return out.replace(" ", "")

    out: list[list[Cell]] = []
    for grouped in _group(text, phonemes, spans):
        first, word = grouped[0], grouped
        starts_silent = all(spans[k] is None or k == first[0] for k in first)
        if len(word) > 1 and text[clusters[first[0]][0]] == ALIF_WASL and starts_silent:
            word = [first + word[1], *word[2:]]  # ٱ в начале аята — со следующей звучащей
        word, joined = _keep_lam_alif(word, text, clusters)
        whole = [k for cell in word for k in cell]
        if is_muqattaat(piece(whole)):
            out.append([(piece(whole), plain(squeeze(sounds(whole)), lexicon))])
            continue
        out.append(
            [(piece(c), _caption(plain(squeeze(sounds(c)), lexicon), c in joined)) for c in word]
        )
    rebuilt = " ".join("".join(p for p, _ in w) for w in out)
    if rebuilt != text:
        raise ValueError("кусочки не складываются в текст")
    empty = [p for w in out for p, s in w if not s.strip()]
    if empty:
        raise ValueError(f"нет подписи у {empty}")
    return out


def sura_texts(curriculum: Curriculum) -> list[str]:
    """Уникальные тексты пунктов с ``quran`` в уроках «Суры», в порядке программы."""
    seen: dict[str, None] = {}
    for lesson in curriculum.lessons:
        if lesson.section == "sura":
            for item in lesson.items:
                if item.quran:
                    seen.setdefault(item.text)
    return list(seen)


def _flow(value: Any) -> str:
    """Одна строка YAML: слово аята, параметры мусхафа, текст."""
    dumped = yaml.safe_dump(
        value, allow_unicode=True, default_flow_style=True, width=10**9, sort_keys=False
    )
    return dumped.strip()


def dump(rows: list[Row]) -> str:
    lines = [HEADER.rstrip("\n"), f"moshaf: {_flow(dict(MOSHAF_PARAMS))}", "ayat:"]
    for row in rows:
        lines += [f"- text: {_flow([row['text']])[1:-1]}", f"  status: {row['status']}"]
        lines += ["  words:", *(f"  - {_flow(word)}" for word in row["words"])]
    text = "\n".join(lines) + "\n"
    expected = {"moshaf": dict(MOSHAF_PARAMS), "ayat": rows}
    if yaml.safe_load(text) != expected:
        raise ValueError("YAML не читается обратно в те же данные")
    return text


def main() -> None:
    curriculum = load_curriculum(CURRICULUM / "course.ru.yaml", CURRICULUM / "lexicon.ru.yaml")
    moshaf = MoshafAttributes(**MOSHAF_PARAMS)
    rows: list[Row] = []
    errors: list[str] = []
    for text in sura_texts(curriculum):
        try:
            words = split_ayah(text, curriculum.lexicon, moshaf)
        except Exception as e:  # noqa: BLE001 — собрать все неразобранные, потом упасть
            errors.append(f"{text}: {e!r}")
            continue
        rows.append(
            {"text": text, "status": UNCHECKED, "words": [list(map(list, w)) for w in words]}
        )
    if errors:
        print(f"не разобрано {len(errors)}:", *errors, sep="\n")
        sys.exit(1)
    old = (yaml.safe_load(OUT.read_text(encoding="utf-8")) or {}) if OUT.is_file() else {}
    rows = merge_status(old.get("ayat") or [], rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dump(rows), encoding="utf-8")
    statuses = {s: sum(r["status"] == s for r in rows) for s in ("ok", "bad", UNCHECKED)}
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} аятов, {statuses}")


if __name__ == "__main__":
    main()
