"""Нарезка «как правильно» для букв, слогов и строк книги из учебного чтения Хусари (ADR-0032).

    uv run --extra ml python scripts/audio/husary_cuts.py [--sections letter] [--per-token 6]

Для каждого слова/слога карточки (текст через пробел) ищем в Коране место, где он стоит в начале
слова, лучше всего в начале аята (там Хусари вступает после паузы и звук не «слипается» с
предыдущим). Аят скачиваем с EveryAyah (SRC-042), моделью Muaalem (SRC-002) находим время каждого
звука (кадр 40 мс), вырезаем нужный кусок и **проверяем его той же моделью**: если в куске она не
слышит ровно нужные звуки — кусок отбрасываем и пробуем следующий аят. Карточку собираем, только
если нашлись все её части; между частями — пауза.

Результат: curriculum/audio/husary/<хэш>.ogg и cuts.yaml (откуда каждый кусок). Человек слушает
review.html и ставит status: ok или bad (bad бот не даёт). Повторный запуск сохраняет статусы.
"""

import argparse
import difflib
import hashlib
import html
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import yaml
from quran_muaalem import Muaalem
from quran_transcript import Aya, MoshafAttributes, quran_phonetizer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "curriculum" / "audio" / "husary"
CACHE = Path.home() / ".cache" / "muallim" / "husary"
RECITER = "Husary_Muallim_128kbps"
URL = "https://everyayah.com/data/{reciter}/{sura:03d}{aya:03d}.mp3"
SR = 16000
MOSHAF = MoshafAttributes(
    rewaya="hafs", madd_monfasel_len=4, madd_mottasel_len=4, madd_mottasel_waqf=4, madd_aared_len=4
)  # как MOSHAF_PARAMS в infrastructure/asr/muaalem.py
VOWELS = set("َُِ")
MADD = set("اۦۥ")
GAP = 0.6  # пауза между частями карточки, с — новичку нужно время различить слоги
LEAD = 0.25  # тишина в начале и в конце файла, с
HEAD = 6.0  # для слова в начале аята хватает первых секунд записи — модель работает в разы быстрее


def phonemes(token: str) -> str | None:
    """Фонемы слова при слитном чтении (как в recognizer: слог «مَ» после и без него)."""
    text = token
    if text[:1] == "ا" and text[1:2] in VOWELS:  # хамза аль-васль в начале: اِرْمِ читается إِرْمِ
        text = "ء" + text[1:]
    try:
        return str(quran_phonetizer(text + " مَ", MOSHAF, remove_spaces=True).phonemes[:-1])
    except Exception:
        return None


@dataclass(frozen=True)
class Candidate:
    sura: int
    aya: int
    offset: int  # позиция в фонемах аята (без пробелов)
    ayah_start: bool


def index_ayat() -> list[tuple[int, int, str, list[int]]]:
    """(сура, аят, фонемы без пробелов, начала слов); считается один раз и хранится в кэше."""
    cached = CACHE / "index.json"
    if cached.is_file():
        return [tuple(row) for row in json.loads(cached.read_text("utf-8"))]  # type: ignore[misc]
    out = []
    for aya in Aya(1, 1).get_ayat_after():
        info = aya.get()
        spaced = str(quran_phonetizer(info.uthmani, MOSHAF, remove_spaces=False).phonemes)
        starts, pos = [], 0
        for word in spaced.split(" "):
            starts.append(pos)
            pos += len(word)
        out.append((info.sura_idx, info.aya_idx, spaced.replace(" ", ""), starts))
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    return out


def candidates(target: str, ayat: list[tuple[int, int, str, list[int]]]) -> list[Candidate]:
    """Места, где слово стоит в начале слова и за ним не продолжается гласный/удвоение."""
    found, size = [], {}
    for sura, aya, ph, starts in ayat:
        size[(sura, aya)] = len(ph)
        for start in starts:
            end = start + len(target)
            if ph[start:end] != target or end >= len(ph):
                continue
            nxt = ph[end]
            if nxt in VOWELS or nxt in MADD or nxt == ph[end - 1]:
                continue  # «قَا» вместо «قَ», удвоение — кусок вышел бы длиннее нужного
            found.append(Candidate(sura, aya, start, start == 0))
    found.sort(key=lambda c: (not c.ayah_start, size[(c.sura, c.aya)], c.sura, c.aya))
    return found


def download(sura: int, aya: int) -> Path:
    path = CACHE / RECITER / f"{sura:03d}{aya:03d}.mp3"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = URL.format(reciter=RECITER, sura=sura, aya=aya)
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 — адрес фиксированный
            data = r.read()
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        time.sleep(0.3)  # не нагружать EveryAyah
    return path


def decode_file(path: Path, start: float | None = None, end: float | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "quiet"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"]
    cmd += ["-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    pcm = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.float32).copy()


class Model:
    def __init__(self) -> None:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.m = Muaalem(device=device, dtype=torch.float32)
        self.vocab = self.m.multi_level_tokenizer.id_to_vocab["phonemes"]
        self.device = device

    @torch.no_grad()
    def spikes(self, wave: np.ndarray) -> tuple[list[tuple[str, int, int]], float]:
        """Жадное CTC-декодирование: [(фонема, первый кадр, последний кадр)], длина кадра в с."""
        feats = self.m.processor([wave], sampling_rate=SR, return_tensors="pt")
        feats = {k: v.to(self.device, dtype=torch.float32) for k, v in feats.items()}
        logits = self.m.model(**feats, return_dict=False)[0]["phonemes"][0]
        ids = logits.argmax(-1).cpu().tolist()
        frame = len(wave) / SR / max(len(ids), 1)
        out: list[tuple[str, int, int]] = []
        prev = 0
        for i, t in enumerate(ids):
            if t != 0 and t == prev:
                ch, a, _ = out[-1]
                out[-1] = (ch, a, i)
            elif t != 0:
                out.append((self.vocab[t], i, i))
            prev = t
        return out, frame

    def text(self, wave: np.ndarray) -> str:
        return "".join(ch for ch, _, _ in self.spikes(wave)[0])


@dataclass
class Cut:
    token: str
    sura: int
    aya: int
    start: float
    end: float
    pause_before: float
    wave: np.ndarray
    check: str = (
        "model"  # model — кусок отдельно услышан моделью; alignment — только в контексте аята
    )


WINDOW = 5.0  # слово в середине аята: декодируем ±5 с вокруг него, а не минуту записи целиком
Heard = tuple[np.ndarray, list[tuple[str, int, int]], float]
_spikes: dict[tuple[int, int, float], Heard] = {}


def heard_in(model: Model, c: Candidate, ref: str) -> tuple[Heard, str, int, float]:
    """Звук окна аята, услышанные в нём фонемы со временем; кусок эталона и позиция цели в нём.

    Модель на длинной записи работает очень долго (внимание по всей записи), поэтому для слова
    из середины аята оцениваем его время по доле фонем и берём окно вокруг.
    """
    path = download(c.sura, c.aya)
    if c.ayah_start:
        lo, hi = 0.0, HEAD
    else:
        full = decode_file(path)
        dur = len(full) / SR
        t = c.offset / len(ref) * dur
        lo, hi = max(0.0, t - WINDOW), min(dur, t + WINDOW)
    key = (c.sura, c.aya, round(lo, 1))
    if key not in _spikes:
        wave = decode_file(path, lo, hi)
        _spikes[key] = (wave, *model.spikes(wave))
    heard = _spikes[key]
    n = len(heard[1])
    if c.ayah_start:  # услышано только начало аята — и сравниваем с началом
        return heard, ref[: n + 4], c.offset, lo
    a = max(0, c.offset - n)  # эталон с запасом: окно точно внутри
    return heard, ref[a : c.offset + n], c.offset - a, lo


def try_cut(model: Model, target: str, c: Candidate, ref: str) -> Cut | None:
    (wave, sp, frame), ref, offset, lo = heard_in(model, c, ref)
    heard = "".join(ch for ch, _, _ in sp)
    # сопоставить эталон аята с услышанным: позиция цели в эталоне -> позиция в услышанном
    sm = difflib.SequenceMatcher(None, ref, heard, autojunk=False)
    j = None
    for a, b, size in sm.get_matching_blocks():
        if a <= offset and offset + len(target) < a + size:  # цель и следующий звук внутри
            j = b + (offset - a)
            break
    if j is None or heard[j : j + len(target)] != target:
        return None
    first, nxt = sp[j], sp[j + len(target)]
    prev_end = sp[j - 1][2] if j > 0 else -100
    pause = (first[1] - prev_end) * frame
    if j > 0 and pause < 0.2:
        return None  # перед словом нет паузы — звук «слипнется» с предыдущим
    start = max(0.0, (first[1] - 3) * frame, (prev_end + 1) * frame)
    for shift in (0.0, -0.04, -0.08, 0.04):
        end = nxt[1] * frame - 0.02 + shift
        if end <= start + 0.08:
            continue
        piece = wave[int(start * SR) : int(end * SR)]
        if model.text(_padded(_faded(piece))) == target:  # проверка тем же «ухом»
            return Cut("", c.sura, c.aya, lo + start, lo + end, pause, _faded(piece))
    if c.ayah_start and nxt[1] - sp[j + len(target) - 1][2] >= 2:
        # Короткое «ءِ», «ءُ» модель отдельно не слышит (нужен контекст), а в аяте услышала точно
        # и до следующего звука есть зазор: берём по разметке, человек проверит на слух.
        end = nxt[1] * frame - 0.02
        piece = wave[int(start * SR) : int(end * SR)]
        return Cut("", c.sura, c.aya, lo + start, lo + end, pause, _faded(piece), "alignment")
    return None


def _faded(piece: np.ndarray) -> np.ndarray:
    piece = piece.copy()
    n_in, n_out = int(0.01 * SR), int(0.04 * SR)
    piece[:n_in] *= np.linspace(0, 1, n_in, dtype=np.float32)
    piece[-n_out:] *= np.linspace(1, 0, n_out, dtype=np.float32)
    peak = float(np.abs(piece).max()) or 1.0
    return piece * (0.8 / peak)


def _padded(piece: np.ndarray, lead: float = LEAD) -> np.ndarray:
    pad = np.zeros(int(lead * SR), dtype=np.float32)
    return np.concatenate([pad, piece, pad])


def write_ogg(wave: np.ndarray, path: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".f32") as raw:
        raw.write(wave.astype(np.float32).tobytes())
        raw.flush()
        subprocess.run(
            ["ffmpeg", "-v", "quiet", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1",
             "-i", raw.name, "-c:a", "libopus", "-b:a", "32k", "-ac", "1", str(path)],
            check=True,
        )  # fmt: skip


def card_texts(sections: set[str]) -> list[str]:
    course = yaml.safe_load((ROOT / "curriculum" / "course.ru.yaml").read_text("utf-8"))
    out: list[str] = []
    for les in course["lessons"]:
        if les["section"] not in sections:
            continue
        for item in les["items"]:
            if item.get("quran") or item["kind"] == "alphabet":
                continue
            if item["kind"] == "rule" and not all(
                (ph := phonemes(t)) and set(ph) & (VOWELS | MADD) for t in item["text"].split()
            ):
                continue  # в правиле может стоять просто буква: без гласного её не озвучить
            if item["text"] not in out:
                out.append(item["text"])
    return out


def find_cuts(
    model: Model,
    tokens: list[str],
    found_in: dict[str, tuple[str, list[Candidate]]],
    refs: dict[tuple[int, int], str],
    per_token: int,
) -> dict[str, Cut]:
    """Для каждого слова — первая нарезка из кандидатов, которую подтвердила модель."""
    cuts: dict[str, Cut] = {}
    for n, token in enumerate(tokens, start=1):
        target, options = found_in[token]
        found = None
        for c in options[:per_token]:
            try:
                found = try_cut(model, target, c, refs[(c.sura, c.aya)])
            except Exception as error:
                print(f"    {c.sura}:{c.aya}: {error}", file=sys.stderr)
            if found:
                found.token = token
                break
        cuts[token] = found  # type: ignore[assignment]
        where = f"{found.sura}:{found.aya}" if found else "—"
        print(f"[{n}/{len(tokens)}] {token} ({target}): {where}", file=sys.stderr)
    return cuts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", default="letter")
    ap.add_argument("--per-token", type=int, default=6, help="сколько аятов пробовать на слово")
    args = ap.parse_args()

    texts = card_texts(set(args.sections.split(",")))
    ayat = index_ayat()
    refs = {(s, a): ph for s, a, ph, _ in ayat}
    found_in: dict[str, tuple[str, list[Candidate]]] = {}
    for token in {t for text in texts for t in text.split()}:
        target = phonemes(token)
        found_in[token] = (target or "", candidates(target, ayat) if target else [])
    # карточку собираем, только если нашлись все части — остальные слова не ищем зря
    possible = [t for t in texts if all(found_in[w][1] for w in t.split())]
    tokens = sorted({w for t in possible for w in t.split()})
    print(
        f"{len(texts)} карточек, по тексту Корана можно озвучить {len(possible)}; "
        f"слов/слогов для поиска: {len(tokens)}",
        file=sys.stderr,
    )
    cuts = find_cuts(Model(), tokens, found_in, refs, args.per_token)

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "cuts.yaml"
    old = (
        {r["text"]: r for r in yaml.safe_load(manifest.read_text("utf-8")) or []}
        if manifest.is_file()
        else {}
    )
    rows = []
    for text in texts:
        parts = [cuts.get(t) for t in text.split()]
        if not all(parts):
            continue
        gap = np.zeros(int(GAP * SR), dtype=np.float32)
        wave = _padded(np.concatenate([x for p in parts for x in (p.wave, gap)][:-1]))  # type: ignore[union-attr]
        name = hashlib.sha1(text.encode()).hexdigest()[:16] + ".ogg"  # noqa: S324 — имя, не защита
        write_ogg(wave, OUT / name)
        prev = old.get(text, {})
        source = [
            {"token": p.token, "aya": f"{p.sura}:{p.aya}", "start": round(p.start, 2),
             "end": round(p.end, 2), "pause_before": round(min(p.pause_before, 9.99), 2),
             "check": p.check}
            for p in parts if p
        ]  # fmt: skip
        same = prev.get("parts") == source
        status = prev.get("status", "unchecked") if same else "unchecked"
        rows.append({"text": text, "file": name, "status": status, "parts": source})
    for text, row in old.items():  # отклонённое человеком не теряем, даже если не нашлось заново
        if row.get("status") == "bad" and text not in {r["text"] for r in rows}:
            rows.append(row)
    head = (
        "# Нарезки «как правильно» из учебного чтения Хусари (EveryAyah, SRC-042), ADR-0032.\n"
        "# Генерирует scripts/audio/husary_cuts.py. status: unchecked → человек слушает\n"
        "# review.html и ставит ok или bad (bad бот не даёт). start/end — секунды в файле аята.\n"
    )
    manifest.write_text(
        head + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False, width=120), "utf-8"
    )
    write_review(rows)
    print(f"Готово: {len(rows)} из {len(texts)} карточек со звуком → {OUT}", file=sys.stderr)
    missing = [t for t in tokens if not cuts.get(t)]
    print(f"Не нашлось ({len(missing)}): {' '.join(missing)}", file=sys.stderr)


def write_review(rows: list[dict]) -> None:
    """Страница для прослушивания: открыть в браузере, отметить плохие в cuts.yaml."""
    items = "\n".join(
        f'<tr><td class="ar">{html.escape(r["text"])}</td><td><audio controls preload="none" '
        f'src="{r["file"]}"></audio></td><td>{html.escape(", ".join(p["aya"] for p in r["parts"]))}'
        f"</td><td>{r['status']}</td></tr>"
        for r in rows
    )
    page = (
        "<!doctype html><meta charset='utf-8'><title>Нарезки Хусари</title>"
        "<style>body{font:15px system-ui;margin:24px}"
        "td{padding:6px 12px;border-bottom:1px solid #ddd}"
        ".ar{font-size:28px;direction:rtl}</style>"
        "<h1>Нарезки Хусари — проверка</h1><p>Плохую нарезку отметьте в cuts.yaml: "
        "<code>status: bad</code>, хорошую — <code>status: ok</code>.</p>"
        f"<table><tr><th>Текст</th><th>Звук</th><th>Аяты</th><th>Статус</th></tr>{items}</table>"
    )
    (OUT / "review.html").write_text(page, "utf-8")


if __name__ == "__main__":
    main()
