from pathlib import Path

import pytest

from muallim.domain.curriculum import ItemKind
from muallim.infrastructure.curriculum.yaml_loader import load_curriculum, load_lexicon


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="словарь"):
        load_lexicon(path)


def test_item_kind_and_note_override_lesson(tmp_path: Path) -> None:
    course = tmp_path / "course.yaml"
    course.write_text(
        """\
id: c
version: "1"
title: t
lessons:
- id: L01
  number: 1
  title: t
  kind: line
  source: {source_id: SRC-040, page: 11}
  items:
  - {id: L01-01, kind: letter, text: "رَ رِ رُ", sound: ро, name: Ро}
  - {id: L01-02, text: "رَرْ", note: пары, source: {source_id: SRC-040, page: 11, line: 2}}
""",
        encoding="utf-8",
    )
    lexicon = Path(__file__).resolve().parents[2] / "curriculum" / "lexicon.ru.yaml"
    head, line = load_curriculum(course, lexicon).lessons[0].items
    assert (head.kind, line.kind) == (ItemKind.LETTER, ItemKind.LINE)
    assert (line.note, line.sound) == ("пары", "")
    assert head.source is not None and head.source.page == 11 and head.source.line is None
    assert line.source is not None and line.source.line == 2
