"""Правила проекта для проверки «варианты карточки» (FR-70 п. 8; ADR-0088 п. 2, 7).

- Ревизия MostafaMaroof закреплена: каждая загрузка с Hugging Face — с ``revision=MODEL_REVISION``,
  а это — коммит (40 hex) (QAS-09: пересчёт попытки по записи и той же модели).
- «Засчитано ли» — только по вердикту (``is_mastered_verdict``): «не failed» считает «ещё раз»
  засчитанным (бот, отчёты, повторение, разметка). Ловится любое сравнение с ``Verdict.FAILED``
  (и под другим именем, и ``.value``, и ``in (…)``, и ``case``), со строкой ``"failed"`` и
  ``'failed'`` в тексте SQL.
- Освоение карточки в сценариях — по вердикту, не по баллу (``GradingPolicy.is_mastered``):
  «ошибка» с баллом 85 иначе засчитала бы карточку.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "muallim"
MAROOF = SRC / "infrastructure" / "asr" / "maroof.py"
_HUB_CALLS = frozenset({"from_pretrained", "hf_hub_download", "snapshot_download"})
_SQL_FAILED = re.compile(r"(!=|<>|=)\s*'failed'|\bIN\s*\([^)]*'failed'", re.IGNORECASE)
# Законные сравнения с failed в src/ — «файл:строка» с причиной. Сейчас нет ни одного: миграция
# 0015 (откат again → failed) лежит в migrations/, не в src/, и сюда не попадает.
ALLOWED: frozenset[str] = frozenset()


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _maroof_tree() -> ast.Module:
    return ast.parse(MAROOF.read_text(encoding="utf-8"))


def test_maroof_model_is_loaded_at_the_pinned_revision() -> None:
    hub = [c for c in _calls(_maroof_tree()) if _name(c) in _HUB_CALLS]
    assert any(_name(c) == "from_pretrained" for c in hub), "модель грузится from_pretrained"
    unpinned = [
        c.lineno
        for c in hub
        if not any(
            k.arg == "revision" and isinstance(k.value, ast.Name) and k.value.id == "MODEL_REVISION"
            for k in c.keywords
        )
    ]
    assert not unpinned, f"maroof.py: загрузка без revision=MODEL_REVISION в строках {unpinned}"


def test_pinned_revision_is_a_commit_hash() -> None:
    values = [
        node.value.value
        for node in _maroof_tree().body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and any(
            isinstance(t, ast.Name) and t.id == "MODEL_REVISION"
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        and isinstance(node.value, ast.Constant)
    ]
    assert len(values) == 1, "MODEL_REVISION — одна строковая константа модуля"
    assert isinstance(values[0], str) and re.fullmatch(r"[0-9a-f]{40}", values[0])


def _verdict_names(tree: ast.AST) -> set[str]:
    """Имена, под которыми в файле ходит Verdict (в том числе ``import … as V``)."""
    names = {"Verdict"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {a.asname for a in node.names if a.name == "Verdict" and a.asname}
    return names


def _is_failed(node: ast.AST, names: set[str]) -> bool:
    """``Verdict.FAILED``, ``V.FAILED``, ``policy.Verdict.FAILED``, ``Verdict.FAILED.value``."""
    if isinstance(node, ast.Attribute) and node.attr == "value":
        node = node.value
    if not (isinstance(node, ast.Attribute) and node.attr == "FAILED"):
        return False
    owner = node.value
    return (isinstance(owner, ast.Name) and owner.id in names) or (
        isinstance(owner, ast.Attribute) and owner.attr == "Verdict"
    )


def _offences(tree: ast.AST) -> list[int]:
    names = _verdict_names(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            inner = [n for op in operands for n in ast.walk(op)]
            if any(_is_failed(n, names) for n in inner) or any(
                isinstance(n, ast.Constant) and n.value == "failed" for n in inner
            ):
                found.append(node.lineno)
        elif isinstance(node, ast.match_case):
            if any(
                isinstance(p, ast.MatchValue) and _is_failed(p.value, names)
                for p in ast.walk(node.pattern)
            ):
                found.append(node.pattern.lineno)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _SQL_FAILED.search(node.value)
        ):
            found.append(node.lineno)
    return found


def test_passed_is_never_told_by_comparing_with_failed() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        for line in _offences(ast.parse(path.read_text(encoding="utf-8")))
    ]
    found = [f for f in found if f not in ALLOWED]
    assert not found, "«засчитано» — через is_mastered_verdict:\n" + "\n".join(found)


@pytest.mark.parametrize(
    "code",
    [
        "ok = v != Verdict.FAILED",
        "ok = v is not Verdict.FAILED",
        "ok = 'нет' if v == Verdict.FAILED else 'да'",
        "ok = v.value != Verdict.FAILED.value",
        "ok = v not in (Verdict.FAILED,)",
        "from muallim.domain.policy import Verdict as V\nok = v != V.FAILED",
        "ok = v != policy.Verdict.FAILED",
        "ok = row.verdict != 'failed'",
        "ok = row.verdict in ('failed', 'again')",
        "match v:\n    case Verdict.FAILED:\n        ok = False",
        "q = \"SELECT count(*) FROM attempts WHERE verdict != 'failed'\"",
        "q = \"... WHERE verdict = 'failed'\"",
        "q = \"... WHERE verdict IN ('failed', 'again')\"",
    ],
)
def test_rule_catches_every_way_to_compare_with_failed(code: str) -> None:
    assert _offences(ast.parse(code)), code


@pytest.mark.parametrize(
    "code",
    [
        "ok = is_mastered_verdict(v)",
        "return Verdict.FAILED",
        "ok = event == 'recognition_failed'",
        "key = 'passed' if passed else 'failed'",
    ],
)
def test_rule_leaves_other_code_alone(code: str) -> None:
    assert not _offences(_fn(code)), code


def _fn(code: str) -> ast.Module:
    return ast.parse("def f():\n    " + code)


def test_use_cases_do_not_master_cards_by_score() -> None:
    found = []
    for path in sorted((SRC / "application").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found += [
            f"{path.relative_to(ROOT)}:{c.lineno}"
            for c in _calls(tree)
            if _name(c) == "is_mastered"
        ]
    assert not found, "освоение — по вердикту (ADR-0088 п. 7):\n" + "\n".join(found)
