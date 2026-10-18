# Как смотреть данные: ответы, ошибки, отчёты, резервные копии

Всё ниже работает с PostgreSQL в Docker (`make db-up`). Telegram ID в представлениях и выгрузках
нет — только псевдоним `L-xxxx`. Попытки-заглушки (`model_version = 'stub'`) в отчётах не считаются.

## 1. Быстро — командами
| Что | Команда |
|---|---|
| Сводный отчёт (10 разделов) | `make report` → `analytics/reports/report_<дата>.md` |
| Ошибки на букве ص | `make errors a="--letter ص"` |
| Что путают с ص (слышится س) | `make errors a="--letter ص --heard س"` |
| Ошибки урока / строки книги | `make errors a="--lesson L18"` · `make errors a="--page 18 --line 8"` |
| Только пары «Обратите внимание» | `make errors a="--pairs"` |
| Ошибки одного ученика | `make errors a="--learner L-7f3a9c"` |
| За период | `make errors a="--since 2026-11-01 --until 2026-12-01"` |
| Ещё не размечены / оспорены / с записью | `--unannotated` · `--disputed` · `--with-audio` |
| Все фильтры | `uv run muallim-research errors --help` |

Каждый вызов сохраняет CSV в `data/errors/errors_<дата>.csv` (открывается в Excel/LibreOffice).
Колонка `audio_path` — путь к записи: открыть и прослушать.

## 2. Удобно — в DBeaver (бесплатно, с фильтрами и сортировкой как в Excel)
1. Установить: <https://dbeaver.io/download/> (Community).
2. «Новое подключение» → PostgreSQL:
   - Host `localhost`, Port `5432`, Database `muallim`, User `muallim`;
   - пароль — строка `POSTGRES_PASSWORD` в файле `.env` (открыть самому, агенту файл не читать).
3. Схема `public` → **Views**:
   - `v_errors` — каждая ошибка: ученик, урок, страница/строка книги, текст строки, что ожидалось,
     что услышано, балл, разметка;
   - `v_attempts` — каждая попытка: балл, вердикт, число ошибок, оспорена ли, есть ли запись.
4. Фильтр — поле над таблицей, например `expected = 'ص' AND page = 18`; сортировка — клик по колонке.
5. Таблицы (`attempts`, `detected_errors`, `annotations`, …) **не редактировать руками** — разметка
   идёт через `muallim-research annotation-export/import` (`docs/data/annotation-guide.md`).

Консоль без программ: `make db-shell`, потом например
`SELECT expected, heard, COUNT(*) FROM v_errors GROUP BY 1, 2 ORDER BY 3 DESC;` (выход — `\q`).

## 3. Какие отчёты есть (`analytics/sql/`)
| Файл | Отвечает на вопрос |
|---|---|
| `01_overview.sql` | сколько учеников, попыток, ошибок |
| `02_item_difficulty.sql` | какие карточки труднее |
| `03_error_kinds.sql` | какие типы ошибок и как часто |
| `04_letter_confusions.sql` | какую букву на какую путают (матрица путаниц) |
| `05_annotation_labels.sql` | итоги разметки: где модель права, где нет |
| `06_learner_activity.sql` | активность учеников (по псевдонимам) |
| `07_learner_disputes.sql` | где ученики нажимали «Бот ошибся» |
| `08_book_lines.sql` | **трудные строки книги** (страница, строка, текст) |
| `09_minimal_pairs.sql` | **пары «Обратите внимание»**: какие путают |
| `10_errors_by_letter.sql` | **ошибки по буквам**: сколько, у скольких, сколько размечено |

## 4. Путь данных до обучения модели
1. Бот пишет попытки и ошибки (`attempts`, `detected_errors`) — каждая со ссылкой на строку книги.
2. `muallim-research annotation-export` → CSV-очередь (оспоренные — первыми) → человек ставит метки →
   `annotation-import` (таблица `annotations`).
3. `make report` / `make errors` — частые ошибки, трудные строки, ошибки модели.
4. `muallim-research dataset-export` → `data/exports/<дата>/manifest.jsonl` + аудио — только ученики с
   согласием, только настоящая модель. Это вход для дообучения/оценки модели.

## 5. Резервные копии
- `make backup` → `data/backups/<дата>/db.dump` (вся БД) + `audio.tar.gz` (голосовые).
- Восстановить: `make restore d=data/backups/<дата>` — **перезапишет** текущие данные.
- Копии содержат голоса и псевдонимы: хранить на зашифрованном диске, не в облаке без шифрования,
  не в git (TD-SEC-17). Делать копию перед каждой миграцией и раз в неделю во время пилота.

## 6. Если что-то не так
- Бот не стартует с «Программа … изменилась без смены version» — правили `curriculum/course.ru.yaml`,
  но не увеличили `version`. Увеличьте — старые попытки останутся связаны со старым текстом.
- Пустые `page`/`line` в представлениях — попытки, сделанные до появления снимка программы (их нет).
