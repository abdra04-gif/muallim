# ruff: noqa: E501, E402
"""Listening page: for chosen recordings — the audio, where each expected sound was found, and
what the three methods decided (the bot today, the choice from 84 syllables, the per-sound check).

Usage (from the project root):
    python docs/research/phase3/listen_page.py ALIGN_DIR DEMO_JSON OUT_HTML
ALIGN_DIR is the output of align_check.py; DEMO_JSON is the output of demo_data.py.
"""

import argparse
import base64
import html
import io
import json
import math
import sys
import wave
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
mpl.rcParams["font.family"] = ["Arial Unicode MS", "DejaVu Sans"]
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from letters_test import RATE, decode

FRAME = 0.02  # seconds per model frame
PASS_AT = 0.0  # per-sound check: every sound must beat its best competitor on average
VERDICT_RU = {"failed": "«повтори»", "passed": "«засчитано»", "excellent": "«отлично»"}
CLS_RU = {"accept": "«засчитано»", "again": "«скажи ещё раз»", "error": "«ошибка»"}


def wav_b64(samples: np.ndarray) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return base64.b64encode(buf.getvalue()).decode()


def picture(samples: np.ndarray, lp: np.ndarray, row: dict, names: list[str]) -> str:
    li, vi = names.index(row["letter"]), names.index(row["vowel"])
    t = np.arange(len(samples)) / RATE
    tf = (np.arange(lp.shape[0]) + 0.5) * FRAME
    fig, (a1, a2) = plt.subplots(
        2, 1, figsize=(9, 3.6), sharex=True, gridspec_kw={"height_ratios": [1.2, 1]}
    )
    a1.plot(t, samples, color="#8A958F", lw=0.6)
    for (s, e), col, lab in zip(
        row["spans"], ("#1F6F55", "#2A6F9E"), (row["letter"], row["vowel"]), strict=True
    ):
        a1.axvspan(s * FRAME, e * FRAME, color=col, alpha=0.25)
        a1.text(
            (s + e) / 2 * FRAME,
            a1.get_ylim()[1] * 0.75,
            lab,
            ha="center",
            fontsize=18,
            color=col,
            fontname="Geeza Pro",
        )
    a1.set_yticks([])
    a1.set_title(
        "Где модель нашла звуки (зелёный — буква, синий — огласовка)", fontsize=10, loc="left"
    )
    p = np.exp(lp.astype(np.float32))
    a2.plot(tf, p[:, li], color="#1F6F55", lw=1.8, label=f"буква {row['letter']}")
    a2.plot(tf, p[:, vi], color="#2A6F9E", lw=1.8, label="огласовка")
    a2.plot(tf, p[:, -1], color="#C9D2CC", lw=1.2, label="пауза")
    a2.set_ylim(0, 1.05)
    a2.set_xlabel("секунды")
    a2.set_ylabel("уверенность")
    a2.legend(fontsize=8, loc="upper right", ncol=3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


ERR_RU = {
    "madd_too_long": "гласная слишком долгая",
    "letter_substitution": "другая буква",
    "vowel_substitution": "другая огласовка",
    "extra_sound": "лишний звук",
    "fragment_substitution": "заменено несколько звуков",
    "sound_missing": "пропущен звук",
    "vowel_missing": "нет огласовки",
    "shadda_missing": "нет удвоения",
    "madd_too_short": "гласная коротка",
    "sound_substitution": "другой звук",
}
VOWEL_RU = {"\u064e": "«а» (фатха)", "\u0650": "«и» (кясра)", "\u064f": "«у» (дамма)"}
FEATURE = {
    frozenset("زس"): "«з» звонкая, «с» глухая — отличаются только голосом",
    frozenset("دت"): "«д» звонкая, «т» глухая — отличаются только голосом",
    frozenset("صس"): "ص — твёрдое (эмфатическое) «с», س — простое",
    frozenset("ضد"): "ض — твёрдое (эмфатическое) «д», د — простое",
    frozenset("طت"): "ط — твёрдое (эмфатическое) «т», ت — простое",
    frozenset("ظز"): "ظ — твёрдое межзубное, ز — простое «з»",
    frozenset("ظذ"): "ظ — твёрдое межзубное, ذ — мягкое межзубное",
    frozenset("ثس"): "ث — межзубное (как англ. th), س — обычное «с»",
    frozenset("ذز"): "ذ — межзубное (как англ. th в «this»), ز — обычное «з»",
    frozenset("حه"): "ح — глубокое горловое «х», ه — лёгкий выдох",
    frozenset("عء"): "ع — горловой звук, ء — простая остановка голоса",
    frozenset("قك"): "ق — глубокое «к» из горла, ك — обычное «к»",
}


def top_unit(lp, span, rng):
    a, b = span
    if b <= a:
        return None, 0.0
    m = lp[a:b].astype("float32").mean(axis=0)
    best = max(rng, key=lambda i: m[i])
    return best, math.exp(float(m[best]))


def explain(r, d, lp, names, text):
    n_letters = 28
    bl, pl = top_unit(lp, r["spans"][0], range(n_letters))
    bv, pv = top_unit(lp, r["spans"][1], range(n_letters, n_letters + 3))
    lines = []
    letter_ok = r["gop_letter"] > 0
    vowel_ok = r["gop_vowel"] > 0
    if letter_ok and vowel_ok:
        lines.append(
            f"<b>Проверка каждого звука:</b> на месте буквы звучит {r['letter']}, на месте огласовки — {VOWEL_RU.get(r['vowel'], r['vowel'])}. Оба звука совпали с заданными."
        )
    else:
        parts = []
        if not letter_ok and bl is not None:
            heard = names[bl]
            why = FEATURE.get(frozenset(heard + r["letter"]), "")
            parts.append(
                f"на месте буквы {r['letter']} модель слышит <b>{heard}</b> (уверенность {pl:.2f})"
                + (f" — {why}" if why else "")
            )
        if not vowel_ok and bv is not None:
            parts.append(
                f"на месте огласовки {VOWEL_RU.get(r['vowel'])} модель слышит <b>{VOWEL_RU.get(names[bv], names[bv])}</b> (уверенность {pv:.2f})"
            )
        lines.append("<b>Проверка каждого звука:</b> " + "; ".join(parts) + ".")
    if d["bot"]["verdict"] == "failed":
        errs = ", ".join(ERR_RU.get(e, e) for e in d["bot"]["errors"]) or "—"
        held = (
            " «Долгая гласная» на отдельной букве обычно значит, что ученик просто протянул звук — это не ошибка."
            if "madd_too_long" in d["bot"]["errors"]
            else ""
        )
        lines.append(
            f"<b>Бот сейчас:</b> Muaalem записал «{d['out']['muaalem'] or '—'}», бот нашёл: {errs}; балл {d['bot']['score']} меньше 80.{held}"
        )
    else:
        lines.append(
            f"<b>Бот сейчас:</b> Muaalem записал «{d['out']['muaalem'] or '—'}», балл {d['bot']['score']} — засчитано."
        )
    if d["cls"]["decision"] == "accept":
        lines.append(
            f"<b>Выбор из 84:</b> самый похожий слог — {d['cls']['best']}, уверенность в заданном {d['cls']['p']:.2f} — засчитано."
        )
    else:
        lines.append(
            f"<b>Выбор из 84:</b> больше всего похоже на <b>{d['cls']['best']}</b>, а в заданном {text} уверенность лишь {d['cls']['p']:.2f}."
        )
    agree = sum(1 for k in ("maroof", "espeak", "tarteel", "muaalem") if not d["ok"].get(k))
    if not letter_ok and agree >= 3:
        lines.append(
            f"<b>Вывод:</b> {agree} модели из 4 независимо услышали не то, что задано, — скорее всего, ошибка ученика. Проверьте на слух."
        )
    elif not d["ok"]["maroof"] and letter_ok and vowel_ok:
        lines.append("<b>Вывод:</b> модели расходятся — решит только учитель.")
    return '<div class="why">' + "<br>".join(lines) + "</div>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("align", type=Path)
    parser.add_argument("demo", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    data = json.loads((args.align / "align.json").read_text(encoding="utf-8"))
    names = data["summary"]["names"]
    frames = np.load(args.align / "align_clips.npz")
    demo = {it["name"]: it for it in json.loads(args.demo.read_text(encoding="utf-8"))}
    rows = data["rows"]

    def ok(r: dict) -> bool:
        return min(r["gop_letter"], r["gop_vowel"]) > PASS_AT

    # A spread of cases: bot says repeat but per-sound check passes; both reject; disagreements.
    chosen, seen = [], set()
    for want in ("bot_fail_check_ok", "both_fail", "check_fail_cls_ok", "all_ok"):
        n = 0
        for r in rows:
            d = demo[r["item"]]["clips"][r["clip"] - 1]
            bot_ok = d["bot"]["verdict"] != "failed"
            cls_ok = d["cls"]["decision"] == "accept"
            case = {
                "bot_fail_check_ok": not bot_ok and ok(r),
                "both_fail": not bot_ok and not ok(r) and not cls_ok,
                "check_fail_cls_ok": not ok(r) and cls_ok,
                "all_ok": bot_ok and ok(r) and cls_ok,
            }[want]
            if case and r["item"].split("_")[0] not in seen and n < 6:
                chosen.append((want, r))
                seen.add(r["item"].split("_")[0])
                n += 1

    titles = {
        "bot_fail_check_ok": "Бот говорит «повтори», проверка каждого звука — «засчитано»",
        "both_fail": "Все способы против — похоже на настоящую ошибку",
        "check_fail_cls_ok": "Проверка звуков против, выбор из 84 — «засчитано»",
        "all_ok": "Все три способа согласны: «засчитано»",
    }
    blocks, last = [], None
    for want, r in chosen:
        if want != last:
            blocks.append(f"<h2>{titles[want]}</h2>")
            last = want
        d = demo[r["item"]]["clips"][r["clip"] - 1]
        samples = decode(Path(r["file"]))
        lp = frames[f"{r['item']}-{r['clip']}"]
        img = picture(samples, lp, r, names)
        check_ok = ok(r)
        blocks.append(f"""<div class="clip">
<div class="top"><span class="ar">{html.escape(demo[r["item"]]["text"])}</span><span class="meta">{html.escape(r["item"])}, ученик {r["clip"]}</span>
<audio controls src="data:audio/wav;base64,{wav_b64(samples)}"></audio></div>
<img src="data:image/png;base64,{img}" alt="нарезка">
<table><tr><th>Способ</th><th>Что услышал / как оценил</th><th>Решение</th></tr>
<tr><td>1 · Бот сейчас (Muaalem + сравнение строк)</td><td class="ar2">{html.escape(d["out"]["muaalem"] or "—")} · балл {d["bot"]["score"]}</td><td class="{"ok" if d["bot"]["verdict"] != "failed" else "no"}">{VERDICT_RU[d["bot"]["verdict"]]}</td></tr>
<tr><td>2 · Выбор из 84 слогов</td><td>уверенность в заданном слоге {d["cls"]["p"]:.2f}</td><td class="{"ok" if d["cls"]["decision"] == "accept" else "no"}">{CLS_RU[d["cls"]["decision"]]}</td></tr>
<tr><td>3 · Проверка каждого звука</td><td>буква {r["gop_letter"]:+.2f} · огласовка {r["gop_vowel"]:+.2f}</td><td class="{"ok" if check_ok else "no"}">{"«засчитано»" if check_ok else "«ошибка»"}</td></tr></table>
{explain(r, d, lp, names, demo[r["item"]]["text"])}
<p class="ask">Послушайте: что на самом деле прочитано? Совпадает ли нарезка с тем, что слышно?</p>
</div>""")

    s = data["summary"]
    th = "".join(
        f"<tr><td>{k}</td><td>{v['correct_passed']}</td><td>{v['lookalike_passed']}</td><td>{v['other_vowel_passed']}</td></tr>"
        for k, v in s["thresholds"].items()
    )
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Прослушивание: три способа проверки</title>
<style>
:root{{--ink:#17221D;--muted:#56635C;--bg:#F6F5F0;--card:#FFFFFF;--ok:#1F6F55;--no:#C9622F}}
body{{background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Segoe UI,Arial,sans-serif;margin:0;padding:24px 16px;max-width:1000px;margin:auto}}
h1{{font-size:26px}} h2{{font-size:20px;margin-top:36px;border-bottom:2px solid #DDE3DD;padding-bottom:6px}}
.clip{{background:var(--card);padding:16px 18px;margin:14px 0;border-radius:8px}}
.top{{display:flex;gap:16px;align-items:center;flex-wrap:wrap}} .ar{{font-family:'Noto Naskh Arabic',serif;font-size:44px}} .ar2{{font-family:'Noto Naskh Arabic',serif;font-size:20px}}
.meta{{color:var(--muted)}} img{{max-width:100%;margin-top:8px}} table{{border-collapse:collapse;width:100%;margin-top:6px}}
td,th{{text-align:left;padding:6px 8px;border-bottom:1px solid #E6EAE6;font-size:15px}} .ok{{color:var(--ok);font-weight:700}} .no{{color:var(--no);font-weight:700}}
.why{{background:#EEF6F1;border-left:5px solid #1F6F55;padding:10px 14px;margin-top:10px;font-size:15px;line-height:1.5}} .ask{{color:#8A4E12;background:#FFF6E8;padding:8px 12px;margin-top:10px}} .box{{background:var(--card);padding:14px 18px;border-radius:8px}}
</style></head><body>
<h1>Прослушивание: как три способа проверяют одну и ту же запись</h1>
<div class="box"><p><b>Что здесь.</b> Настоящие записи открытого набора (индонезийские школьники, Pelafalan Huruf Hijaiyah, AFL-3.0). Для каждой: запись, картинка — где модель нашла букву и огласовку, — и решения трёх способов.</p>
<p><b>Способ 3 — проверка каждого звука.</b> Бот знает, что задано. Выравнивание находит в записи место каждого ожидаемого звука, затем сравнивает, насколько этот звук похож на ожидаемый по сравнению с самым похожим другим звуком того же вида. Число больше 0 — ожидаемый звук победил; засчитано, если победили и буква, и огласовка. Протяжная гласная здесь не считается ошибкой. Ничего не обучалось.</p>
<p><b>Итог на {s["clips"]} записях</b> (верные — запись проверена как то, что задано; подмены — та же запись проверена как похожая буква, {s["swap_letter_trials"]} проверок, или другая огласовка, {s["swap_vowel_trials"]}):</p>
<table><tr><th>Порог</th><th>Верных засчитано, %</th><th>Похожая буква пропущена, %</th><th>Другая огласовка пропущена, %</th></tr>{th}</table></div>
{"".join(blocks)}
</body></html>"""
    args.out.write_text(page, encoding="utf-8")
    sys.stdout.write(f"{len(chosen)} clips → {args.out}\n")


if __name__ == "__main__":
    main()
