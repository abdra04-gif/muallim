# Вертикальные ролики 720×1280 (проба, ADR-0074 — решения автора 2026-10-31)

По образцу автора: камера у места звука, буква в цветном кружке с пульсом, тёмный фон.
Только macOS: арабский текст с огласовками рисует CoreText (`artext.swift`), в Pillow нет raqm.

```bash
swiftc -O scripts/video/vertical/artext.swift -o /tmp/artext
# буква (звук ар-Раи из curriculum/audio/library, SRC-144)
uv run --group video python -I scripts/video/vertical/letters.py /tmp/artext /tmp/let ب
# басмала (звук аль-Афаси, SRC-145: https://everyayah.com/data/Alafasy_128kbps/001001.mp3)
uv run --group video python -I scripts/video/vertical/basmala.py 001001.mp3 /tmp/artext /tmp/bas/basmala.mp4
# время звуков записи по кадрам CTC модели Muaalem (вход — s16le 16 кГц моно)
uv run --extra ml python -I scripts/video/vertical/align.py a.raw
```

Запускать из корня репозитория. Готовый mp4 → `curriculum/video/<sha256[:16]>.mp4` + строка в
`videos.yaml` со `status: unchecked`. Сборка ≈ 1 с на кадр (18 с ролика ≈ 9 мин).

Черновик, не утверждено автором: подписи и «Твоя очередь» в ролике басмалы, места ت ث ج на рисунке,
выбор 4 букв басмалы (ب ل ر ح — как в образце).
