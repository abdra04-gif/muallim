# ruff: noqa: E501
"""Listening page for the model comparison on whole ayahs (compare_models.py).

For each chosen ayah: the recording (compressed to Opus), the Uthmani text, and for each model the
error variant that came closest to the correct reading and the decision with three answers
(passed / say it again / error). The recordings are correct, so every "error" is a false alarm.

Usage (from the project root):
    python docs/research/phase3/listen_models.py COMPARE_JSON WAV_DIR OUT_HTML
"""

import argparse
import base64
import html
import json
import subprocess
from pathlib import Path

RULE_RU = {
    "vowel": "другая огласовка", "vowel_on_sukun": "лишняя гласная на сукуне", "no_shadda": "нет шадды",
    "short_madd": "короткий мадд", "added_length": "лишняя длина", "lookalike": "похожая буква", "": "—",
}  # fmt: skip
SAY_AGAIN = -4.0  # between this and 0 — "say it again"; below — "error"


def verdict(margin: float) -> tuple[str, str]:
    if margin >= 0:
        return "ok", "«засчитано»"
    if margin >= SAY_AGAIN:
        return "mid", "«скажи ещё раз»"
    return "no", "«ошибка»"


def opus_b64(path: Path) -> str:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        "-f",
        "ogg",
        "-",
    ]
    return base64.b64encode(subprocess.run(cmd, capture_output=True, check=True).stdout).decode()  # noqa: S603


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("compare", type=Path)
    parser.add_argument("wavs", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    data = json.loads(args.compare.read_text(encoding="utf-8"))
    s = data["summary"]
    ayahs = data["ayahs"]

    disagree = [a for a in ayahs if verdict(a["maroof"][0])[0] != verdict(a["muaalem"][0])[0]]
    agree_ok = [
        a
        for a in ayahs
        if verdict(a["maroof"][0])[0] == "ok" and verdict(a["muaalem"][0])[0] == "ok"
    ]
    both_bad = [
        a
        for a in ayahs
        if verdict(a["maroof"][0])[0] != "ok" and verdict(a["muaalem"][0])[0] != "ok"
    ]
    groups = [
        ("Модели решили по-разному", disagree[:12]),
        ("Обе модели засчитали", agree_ok[:4]),
        ("Обе модели не засчитали (ложная тревога у обеих)", both_bad[:4]),
    ]

    blocks = []
    for title, items in groups:
        if not items:
            continue
        blocks.append(f"<h2>{title}</h2>")
        for a in items:
            rows = ""
            for key, name in (("maroof", "MostafaMaroof"), ("muaalem", "Muaalem (модель бота)")):
                m, rule = a[key]
                cls, word = verdict(m)
                why = (
                    "верное чтение победило все варианты-ошибки"
                    if m >= 0
                    else f"ближе всего к верному оказался вариант «{RULE_RU.get(rule, rule)}» (разница {m:+.1f})"
                )
                rows += f'<tr><td>{name}</td><td>{why}</td><td class="{cls}">{word}</td></tr>'
            blocks.append(f"""<div class="clip"><div class="top"><span class="meta">сура:аят {a["where"]}</span><audio controls src="data:audio/ogg;base64,{opus_b64(args.wavs / (a["id"] + ".wav"))}"></audio></div>
<p class="ar">{html.escape(a["text"])}</p>
<table><tr><th>Модель</th><th>Что решила</th><th>Ответ ученику</th></tr>{rows}</table>
<p class="ask">Запись правильная (чтец). Если модель сказала «ошибка» или «скажи ещё раз» — это ложная тревога. Послушайте: слышно ли что-то, что могло её сбить?</p></div>""")

    def table(name: str) -> str:
        pa = s["pair_accuracy"][name]
        return "".join(
            f"<tr><td>{RULE_RU[r]}</td><td>{v['pairs']}</td><td>{v['correct_wins']}</td></tr>"
            for r, v in pa.items()
        )

    fa = s["false_alarm_ayahs"]
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Сравнение моделей на аятах</title>
<style>
:root{{--ink:#17221D;--muted:#56635C;--bg:#F6F5F0;--card:#FFFFFF;--ok:#1F6F55;--no:#C9622F;--mid:#C9822F}}
body{{background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Segoe UI,Arial,sans-serif;margin:0 auto;padding:24px 16px;max-width:1000px}}
h1{{font-size:26px}} h2{{font-size:20px;margin-top:32px;border-bottom:2px solid #DDE3DD;padding-bottom:6px}}
.box,.clip{{background:var(--card);padding:14px 18px;border-radius:8px;margin:12px 0}} .top{{display:flex;gap:14px;align-items:center;flex-wrap:wrap}}
.meta{{color:var(--muted)}} .ar{{font-family:'Noto Naskh Arabic','Geeza Pro',serif;font-size:26px;direction:rtl;text-align:right;line-height:1.9}}
table{{border-collapse:collapse;width:100%}} td,th{{text-align:left;padding:6px 8px;border-bottom:1px solid #E6EAE6;font-size:15px}}
.ok{{color:var(--ok);font-weight:700}} .no{{color:var(--no);font-weight:700}} .mid{{color:var(--mid);font-weight:700}}
.ask{{color:#8A4E12;background:#FFF6E8;padding:8px 12px;margin-top:10px}} .cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media (max-width:700px){{.cols{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>MostafaMaroof или Muaalem: сравнение на аятах Корана</h1>
<div class="box"><p><b>На чём.</b> {s["ayahs"]} аятов, прочитанных чтецами <b>правильно</b> (открытый набор IqraEval Iqra_train dev, CC BY-NC 4.0). Каждый аят — целиком, текст мусхафа известен.</p>
<p><b>Как.</b> Для каждого аята делаем варианты с типичными ошибками (другая огласовка, гласная на сукуне, нет шадды, короткий мадд, лишняя длина, похожая буква) и смотрим, выберет ли модель правильное чтение. Запись правильная — значит, хорошая модель всегда должна выбирать правильное.</p>
<p><b>Три ответа ученику:</b> правильное чтение победило — «засчитано»; ошибка близко (до 4) — «скажи ещё раз»; ошибка явно сильнее — «ошибка».</p>
<div class="cols"><div><h3>MostafaMaroof — правильное выбрано, %</h3><table><tr><th>Ошибка</th><th>Пар</th><th>%</th></tr>{table("maroof")}</table></div>
<div><h3>Muaalem — правильное выбрано, %</h3><table><tr><th>Ошибка</th><th>Пар</th><th>%</th></tr>{table("muaalem")}</table></div></div>
<p><b>Сколько правильных аятов модель бы поругала</b> (хотя бы одна ошибка сильнее правильного): MostafaMaroof — {fa["maroof"]["0.0"]}% строго, {fa["maroof"]["-4.0"]}% с допуском 4; Muaalem — {fa["muaalem"]["0.0"]}% строго, {fa["muaalem"]["-4.0"]}% с допуском 4.</p></div>
{"".join(blocks)}
</body></html>
"""
    args.out.write_text(page, encoding="utf-8")
    print(f"{sum(len(i) for _, i in groups)} ayahs → {args.out}")  # noqa: T201


if __name__ == "__main__":
    main()
