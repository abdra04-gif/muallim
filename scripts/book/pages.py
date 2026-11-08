"""Картинки страниц книги для «📄 Страница книги»: curriculum/book_pages/NNN.jpg (вне git).

    python scripts/book/pages.py [скан.pdf] [папка]   # с. 10–85; нужен pdftoppm (brew install poppler)

PDF-страница = страница книги + 1 (book/README.md)."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRST, LAST = 10, 85
DPI = 110  # читаемо в Telegram, файл ~150–300 КБ


def main() -> None:
    tool = shutil.which("pdftoppm")
    if tool is None:
        sys.exit("нет pdftoppm: brew install poppler")
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else next((ROOT / "book").glob("*.pdf"))
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "curriculum" / "book_pages"
    out.mkdir(parents=True, exist_ok=True)
    for page in range(FIRST, LAST + 1):
        target = out / f"{page:03d}"
        pdf_page = str(page + 1)
        subprocess.run(
            [tool, "-jpeg", "-jpegopt", "quality=80", "-r", str(DPI), "-singlefile", "-f", pdf_page, "-l", pdf_page,
             str(pdf), str(target)],
            check=True,
        )  # fmt: skip
    print(f"{LAST - FIRST + 1} страниц → {out}")


if __name__ == "__main__":
    main()
