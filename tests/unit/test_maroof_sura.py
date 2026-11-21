"""Сура целиком на MostafaMaroof: адаптер ``MaroofListener.listen_sura`` (FR-70 ч. 7, FR-57;
ADR-0076, ADR-0088 «Суры — решения автора», PHASE_3 §11.8k; прототип
`docs/research/phase3/sura_align_check.py`, ключи ``--second`` и ``--window``).

Предложенный интерфейс (порт ``SuraListener`` в `application/ports/recognition.py`, принимает
человек)::

    listen_sura(audio, ayahs: Sequence[tuple[item_id, номер, текст]], opening: str,
                preamble: str, *, long_is_short: bool) -> SuraListening
    SuraListening(ayahs: tuple[AyahListening, ...], prefix: tuple[str, ...], raw: str,
                  model_version: str, audio_duration_ms: int, pauses=(), chunks=())
    AyahListening(item_id, number, references, raw, score, sounds, score_many,
                  span_ms: tuple[int, int] | None,
                  rehear: Callable[[], Awaitable[Listening]] | None)

``prefix`` — что прозвучало перед сурой: ``"preamble"`` (истиаза), ``"opening"`` (басмала).
``span_ms is None`` — аят не прозвучал (не дочитал). ``rehear()`` — второй проход: аят вырезается
из записи по найденным границам и слушается моделью отдельно; решение «слушать ли второй раз»
принимает сценарий (`test_sura_maroof.py`), адаптер не зовёт модель, пока ``rehear`` не вызван.
Длинная запись (> ``WHOLE_MAX_S`` = 180 с) — окнами ``WINDOW_S`` = 30 с с перекрытием
``OVERLAP_S`` = 4 с, логиты склеиваются по середине перекрытия; короче — одним вызовом модели.

Модель не грузится: ``maroof._load`` отдаёт подставную модель. Запись «кодирует» номер кадра в
каждом отсчёте (кадр — 320 отсчётов, 20 мс), поэтому подставная модель по куску записи знает, какие
кадры ей дали, — так видно, что именно слушали. Эталоны — `tests/fixtures/maroof_cards.json`
(тексты программы и записи фонетизатора бота); истиаза и «بِسْمِ» вместо басмалы — `_OPENINGS`,
строки уроков 34–41 вместо аятов (у сур в фикстуре записей нет; для механики выравнивания
неважно). numpy ставится с моделью (extra ``ml``); без него тесты пропускаются.
"""

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

np = pytest.importorskip("numpy")

from muallim.application.ports.recognition import RecognitionError  # noqa: E402
from muallim.domain.card_check import accepted_references, decide  # noqa: E402
from muallim.domain.policy import CardPolicy  # noqa: E402
from muallim.infrastructure.asr import maroof  # noqa: E402
from muallim.infrastructure.asr.maroof import MaroofListener  # noqa: E402
from muallim.infrastructure.asr.maroof_script import to_maroof  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "maroof_cards.json"
# Начала перед сурой: истиаза и «بِسْمِ» — записи фонетизатора бота из прежней фикстуры. Карточек
# L001-01/02 в программе больше нет (ADR-0089), но адаптер «начала» перед сурой по-прежнему умеет.
_OPENINGS = [
    {"id": "L001-01", "text": "بِسْمِ", "wasl": "بِسمِ", "waqf": "بِسم"},
    {"id": "L001-02", "text": "أَعُوذُ بِٱللَّهِ مِنَ ٱلشَّيْطَانِ ٱلرَّجِيمِ",
     "wasl": "ءَعُۥۥذُبِللَااهِمِنَششَيطَاانِررَجِۦۦمِ",
     "waqf": "ءَعُۥۥذُبِللَااهِمِنَششَيطَاانِررَجِۦۦۦۦم"},
]  # fmt: skip
CARDS: dict[str, dict[str, str]] = {
    c["id"]: c for c in [*json.loads(FIXTURE.read_text(encoding="utf-8")), *_OPENINGS]
}
BY_TEXT = {c["text"]: c for c in CARDS.values()}

_SOUNDS = """
$ $$ * ** < << A AA AH D DD E EE H HH I II S SS T TT U UU Z ZZ ^ ^^
a aa b bb d dd f ff g gg h hh i ii j jj k kk l ll m mm n nn p pp q qq r rr
s sh ss t th tt u uu v w ww x xx y yy z zz
"""  # словарь MostafaMaroof (как в test_maroof_book_cards.py)
VOCAB: dict[str, int] = {"[PAD]": 0, "|": 1, "sil": 2, "[UNK]": 3}
for _s in sorted(_SOUNDS.split()):
    VOCAB[_s] = len(VOCAB)
BLANK = VOCAB["[PAD]"]
HOP = 320  # отсчётов на кадр (20 мс при 16 кГц)
FRAME_MS = 20
LEAD, PAUSE = 10, 20  # кадры тишины в начале и между целями

PREAMBLE = CARDS["L001-02"]["text"]  # истиаза
OPENING = CARDS["L001-01"]["text"]
AYAHS = [("A-1", 1, CARDS["L036-06"]["text"]), ("A-2", 2, CARDS["L034-04"]["text"]),
         ("A-3", 3, CARDS["L040-02"]["text"])]  # fmt: skip
LONG = ["L041-02", "L040-05", "L040-01", "L040-06", "L040-07", "L041-01", "L040-02"]
POLICY = CardPolicy()


def _ids(text: str) -> list[int]:
    return [VOCAB[s] for s in to_maroof(BY_TEXT[text]["waqf"])]


def _speak(texts: Sequence[str], *, at: Sequence[int] | None = None, total: int | None = None
           ) -> tuple[Any, list[int]]:  # fmt: skip
    """Логиты «прочитанного» (с остановкой на каждой цели): звук — 2 кадра, между звуками
    «пустой». ``at`` — кадры начала целей (по умолчанию подряд с паузами), ``total`` — длина."""
    frames: list[int] = [BLANK] * LEAD
    starts: list[int] = []
    for k, text in enumerate(texts):
        if at is not None:
            frames += [BLANK] * (at[k] - len(frames))
        starts.append(len(frames))
        for sym in _ids(text):
            frames += [sym, sym, BLANK]
        frames += [BLANK] * PAUSE
    if total is not None:
        frames += [BLANK] * (total - len(frames))
    p = np.full((len(frames), len(VOCAB)), 0.02 / (len(VOCAB) - 1))
    p[np.arange(len(frames)), frames] = 0.98
    return np.log(p), starts


class Model:
    """Подставная модель: по куску записи — его кадры из ``lp``; каждый вызов записан."""

    def __init__(self) -> None:
        self.lp: Any = None
        self.calls: list[tuple[int, int]] = []  # (первый кадр, число кадров)

    def forward(self, wave: Any) -> Any:
        idx = np.clip(np.asarray(wave[::HOP]).astype(int), 0, len(self.lp) - 1)
        self.calls.append((int(idx[0]), len(idx)))
        return self.lp[idx]


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Model:
    m = Model()
    monkeypatch.setattr(maroof, "_load", lambda *a, **k: (m.forward, VOCAB))

    async def decode(audio: bytes, *args: Any, **kwargs: Any) -> bytes:
        wave = np.repeat(np.arange(len(m.lp), dtype=np.float32), HOP)
        return bytes(wave.tobytes())

    def references(text: str) -> Any:
        card = BY_TEXT[text]
        return None, (("wasl", card["wasl"]), ("waqf", card["waqf"]))

    monkeypatch.setattr(maroof, "decode_to_pcm", decode)
    monkeypatch.setattr(maroof, "_references", references)
    return m


async def _listen(model: Model, lp: Any, ayahs: Sequence[tuple[str, int, str]] = AYAHS) -> Any:
    model.lp = lp
    return await MaroofListener().listen_sura(b"ogg", ayahs, OPENING, PREAMBLE, long_is_short=False)


def _decide(ayah: Any, text: str | None = None) -> Any:
    """``decide`` по аяту с правилами урока суры; ``text`` — текст аята (для отдельных слогов)."""
    accepted = [r for _, r in accepted_references(text or "", ayah.references)]
    return decide(
        accepted, ayah.score, POLICY, separate_syllables=False, rules=POLICY.rules_for(123),
        sounds=ayah.sounds, score_many=ayah.score_many,
    )  # fmt: skip


def _near_ms(span: tuple[int, int] | None, frame: int, *, slack: int = 3) -> None:
    assert span is not None
    assert abs(span[0] - frame * FRAME_MS) <= slack * FRAME_MS, (span, frame * FRAME_MS)
    assert span[1] > span[0]


# ---------- аяты, их отрезки и решения ----------
async def test_each_ayah_keeps_its_card_and_number(model: Model) -> None:
    lp, _ = _speak([t for _, _, t in AYAHS])
    sura = await _listen(model, lp)
    assert [(a.item_id, a.number) for a in sura.ayahs] == [("A-1", 1), ("A-2", 2), ("A-3", 3)]
    for ayah, (_, _, text) in zip(sura.ayahs, AYAHS, strict=True):
        card = BY_TEXT[text]
        assert dict(ayah.references) == {"wasl": card["wasl"], "waqf": card["waqf"]}


async def test_ayah_spans_are_found_where_the_ayahs_were_read(model: Model) -> None:
    lp, starts = _speak([t for _, _, t in AYAHS])
    sura = await _listen(model, lp)
    for ayah, start in zip(sura.ayahs, starts, strict=True):
        _near_ms(ayah.span_ms, start)


async def test_clean_recording_passes_every_ayah_on_its_own_stretch(model: Model) -> None:
    """Каждый аят — ``decide`` на своём отрезке: чистое чтение засчитано (соседний аят на
    отрезок не попадает и «другой слог» не выигрывает)."""
    lp, _ = _speak([t for _, _, t in AYAHS])
    sura = await _listen(model, lp)
    assert [_decide(a, t).outcome for a, (_, _, t) in zip(sura.ayahs, AYAHS, strict=True)] == [
        "passed"
    ] * 3


async def test_recording_has_version_duration_and_raw(model: Model) -> None:
    lp, _ = _speak([t for _, _, t in AYAHS])
    listener = MaroofListener()
    model.lp = lp
    sura = await listener.listen_sura(b"ogg", AYAHS, OPENING, PREAMBLE, long_is_short=False)
    assert sura.model_version == listener.model_version
    assert sura.audio_duration_ms == len(lp) * FRAME_MS
    assert sura.raw  # жадная расшифровка всей записи — учителю


# ---------- необязательные начала и оборванный конец ----------
@pytest.mark.parametrize(
    ("spoken", "prefix"),
    [
        ([], ()),
        ([PREAMBLE], ("preamble",)),
        ([OPENING], ("opening",)),
        ([PREAMBLE, OPENING], ("preamble", "opening")),
    ],
)
async def test_prefix_tells_which_openings_were_read(
    model: Model, spoken: list[str], prefix: tuple[str, ...]
) -> None:
    lp, starts = _speak([*spoken, *(t for _, _, t in AYAHS)])
    sura = await _listen(model, lp)
    assert tuple(sura.prefix) == prefix
    for ayah, start in zip(sura.ayahs, starts[len(spoken) :], strict=True):
        _near_ms(ayah.span_ms, start)


async def test_reading_cut_short_leaves_the_last_ayah_unheard(model: Model) -> None:
    lp, starts = _speak([t for _, _, t in AYAHS[:2]])
    sura = await _listen(model, lp)
    _near_ms(sura.ayahs[0].span_ms, starts[0])
    _near_ms(sura.ayahs[1].span_ms, starts[1])
    assert sura.ayahs[2].span_ms is None
    assert sura.ayahs[2].rehear is None


async def test_skipped_middle_ayah_has_no_span_and_neighbours_pass(model: Model) -> None:
    """Наизусть забыл аят 2: у него нет отрезка (и второго прохода), аяты 1 и 3 найдены и
    засчитаны — пропуск не даёт соседям ложной «ошибки»."""
    lp, starts = _speak([AYAHS[0][2], AYAHS[2][2]])
    sura = await _listen(model, lp)
    assert sura.ayahs[1].span_ms is None and sura.ayahs[1].rehear is None
    _near_ms(sura.ayahs[0].span_ms, starts[0])
    _near_ms(sura.ayahs[2].span_ms, starts[1])
    for k in (0, 2):
        assert _decide(sura.ayahs[k], AYAHS[k][2]).outcome == "passed"


# ---------- второй проход (PHASE_3 §11.8k) ----------
async def test_model_is_not_run_again_until_rehear_is_called(model: Model) -> None:
    lp, _ = _speak([t for _, _, t in AYAHS])
    await _listen(model, lp)
    assert len(model.calls) == 1  # запись короче 180 с — один вызов, второго прохода нет


async def test_rehear_runs_the_model_on_the_cut_out_ayah_only(model: Model) -> None:
    """Второй проход: модель слушает только вырезанный аят (по найденным границам, с запасом
    до 0,3 с), а не всю запись; его баллы — на вырезанном звуке, верное чтение засчитано."""
    lp, starts = _speak([t for _, _, t in AYAHS])
    sura = await _listen(model, lp)
    before = len(model.calls)
    again = await sura.ayahs[1].rehear()
    assert len(model.calls) == before + 1
    first, count = model.calls[-1]
    assert starts[1] - 15 <= first <= starts[1]
    # конец куска — не позже начала следующего аята: его первый звук исказил бы последний слог
    assert first + count <= starts[2] + 1
    assert again.score_many is not None
    assert _decide(again, AYAHS[1][2]).outcome == "passed"


# ---------- длинная запись: окна с перекрытием (ADR-0088, §11.8k) ----------
async def test_recording_up_to_180_s_is_heard_in_one_call(model: Model) -> None:
    frames = 180 * 1000 // FRAME_MS
    lp, _ = _speak([t for _, _, t in AYAHS], at=[LEAD, 3000, 8000], total=frames)
    await _listen(model, lp)
    assert model.calls == [(0, frames)]


async def test_longer_recording_is_heard_in_overlapping_windows(model: Model) -> None:
    """> 180 с: окна 30 с с перекрытием 4 с; склейка без дублей — аят в конце записи найден
    там же, где прочитан (лишние кадры сдвинули бы его)."""
    frames = 200 * 1000 // FRAME_MS
    at = [LEAD, 4000, 9600]  # третий аят — на 192-й секунде, после многих окон
    lp, starts = _speak([t for _, _, t in AYAHS], at=at, total=frames)
    sura = await _listen(model, lp)
    window, overlap = 30 * 1000 // FRAME_MS, 4 * 1000 // FRAME_MS
    assert len(model.calls) > 1
    assert all(count <= window + 1 for _, count in model.calls)
    for (a, n), (b, _) in zip(model.calls, model.calls[1:], strict=False):
        assert a < b < a + n  # следующее окно начинается внутри предыдущего
        assert a + n - b == pytest.approx(overlap, abs=2)
    assert model.calls[0][0] == 0
    last_first, last_count = model.calls[-1]
    assert last_first + last_count >= frames - 1  # вся запись услышана
    for ayah, start in zip(sura.ayahs, starts, strict=True):
        _near_ms(ayah.span_ms, start)
    assert sura.audio_duration_ms == frames * FRAME_MS


# ---------- скорость (порог автора: 30 с на 2 мин записи, предел 60 с) ----------
# 7 аятов, 1500 кадров (30 с записи) без модели: ~2,5 с на M1 с батч-CTC; запас большой —
# тест ловит возврат к поштучному подсчёту (в десятки раз медленнее), а не колебания машины CI
BUDGET_S = 30.0


async def test_seven_ayahs_on_1500_frames_align_and_decide_within_budget(model: Model) -> None:
    """Выравнивание + ``decide`` по каждому аяту — батчем (``score_many``); поштучный подсчёт
    вариантов не уложился бы в бюджет. Логиты случайные: важна скорость, а не исходы."""
    rng = np.random.default_rng(7)
    p = rng.random((1500, len(VOCAB))) + 1e-3
    lp = np.log(p / p.sum(axis=1, keepdims=True))
    ayahs = [(c, k + 1, CARDS[c]["text"]) for k, c in enumerate(LONG)]
    started = time.perf_counter()
    sura = await _listen(model, lp, ayahs)
    for ayah in sura.ayahs:
        if ayah.span_ms is not None:
            assert ayah.score_many is not None
            _decide(ayah)
    assert time.perf_counter() - started < BUDGET_S


# ---------- сбои ----------
async def test_model_failure_is_a_recognition_error(
    model: Model, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(wave: Any) -> Any:
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(maroof, "_load", lambda *a, **k: (crash, VOCAB))
    lp, _ = _speak([t for _, _, t in AYAHS])
    model.lp = lp
    with pytest.raises(RecognitionError) as error:
        await MaroofListener().listen_sura(b"ogg", AYAHS, OPENING, PREAMBLE, long_is_short=False)
    assert error.value.stage == "model"


def test_window_constants_are_in_the_adapter() -> None:
    assert (maroof.WHOLE_MAX_S, maroof.WINDOW_S, maroof.OVERLAP_S) == (180, 30, 4)
