# SQL для своих данных — учебник за 20 минут

Для автора исследования: как самому спрашивать базу «сколько, где, у кого». Работает в VS Code
(расширение PostgreSQL, подключение «muallim (просмотр)» — `docs/data/browsing.md`) или в консоли
`make db-shell`. Вход только для чтения: испортить данные запросом нельзя.

## 0. Где писать и как запускать
1. Откройте `.vscode/queries.sql` (личный файл, в git не попадает) или любой новый файл `*.sql`.
2. Курсор в запрос → **Shift+Enter**. Первый раз VS Code спросит подключение — «muallim (просмотр)».
3. Результат — таблица внизу. Запрос заканчивается `;`. Строка после `--` — комментарий.

## 1. Две главные таблицы
| Представление | Одна строка — это | Самые нужные колонки |
|---|---|---|
| `v_attempts` | попытка (ученик прочитал строку) | `created_at`, `pseudonym`, `page`, `line`, `item_text`, `score`, `verdict`, `errors`, `disputed`, `annotations`, `model_version` |
| `v_errors` | ошибка, найденная ботом | `pseudonym`, `page`, `line`, `item_text`, `kind`, `expected`, `heard`, `syllable`, `message`, `label`, `model_version` |

Связь: у каждой ошибки есть `attempt_id` её попытки. Главные колонки — `docs/data/data-dictionary.md`,
все — `src/muallim/infrastructure/db/views.py`.

**Правило:** в исследовании всегда `WHERE model_version <> 'stub'` — иначе в цифры попадут проверки
без модели (тесты, `make run-stub`).

## 2. Пять слов, которых хватает почти на всё

**SELECT … FROM** — какие колонки из какой таблицы:
```sql
SELECT pseudonym, page, line, verdict FROM v_attempts;
```
`SELECT *` — все колонки. `LIMIT 20` в конце — только первые 20 строк.

**WHERE** — оставить нужные строки. Текст — в одинарных кавычках; условия соединяются `AND` / `OR`:
```sql
SELECT pseudonym, item_text, heard
FROM v_errors
WHERE expected = 'ص' AND page = 18 AND model_version <> 'stub';
```
Полезное: `<>` — «не равно»; `page BETWEEN 10 AND 20`; `verdict IN ('failed', 'passed')`;
`audio_sha256 IS NULL` — записи нет; `item_text LIKE '%صَ%'` — содержит.

**ORDER BY** — сортировка; `DESC` — по убыванию:
```sql
SELECT created_at, pseudonym, score FROM v_attempts ORDER BY score DESC LIMIT 10;
```

**GROUP BY + COUNT / AVG** — посчитать по группам. Всё, что в `SELECT` не посчитано, должно быть в
`GROUP BY`:
```sql
-- средний балл и число попыток по каждой странице книги
SELECT page, COUNT(*) AS попыток, ROUND(AVG(score)) AS средний_балл
FROM v_attempts
WHERE model_version <> 'stub'
GROUP BY page
ORDER BY page;
```
Ещё: `COUNT(DISTINCT pseudonym)` — сколько разных учеников; `MIN`, `MAX`, `SUM`.

**HAVING** — фильтр уже по посчитанному (WHERE работает до подсчёта, HAVING — после):
```sql
-- буквы, на которых ошиблись хотя бы 3 разных ученика
SELECT expected, COUNT(DISTINCT pseudonym) AS учеников
FROM v_errors
WHERE model_version <> 'stub'
GROUP BY expected
HAVING COUNT(DISTINCT pseudonym) >= 3
ORDER BY учеников DESC;
```

## 3. Готовые вопросы для диссертации
```sql
-- Доля засчитанных попыток у каждого ученика
SELECT pseudonym,
       COUNT(*) AS попыток,
       ROUND(100.0 * COUNT(*) FILTER (WHERE verdict <> 'failed') / COUNT(*)) AS процент_засчитано
FROM v_attempts
WHERE model_version <> 'stub'
GROUP BY pseudonym
ORDER BY попыток DESC;

-- Попытки по дням (как идёт сбор данных)
SELECT created_at::date AS день, COUNT(*) AS попыток, COUNT(DISTINCT pseudonym) AS учеников
FROM v_attempts
WHERE model_version <> 'stub'
GROUP BY день
ORDER BY день;

-- Самые трудные строки книги: где чаще всего не засчитано
SELECT page, line, item_text,
       COUNT(*) AS попыток,
       COUNT(*) FILTER (WHERE verdict = 'failed') AS не_засчитано
FROM v_attempts
WHERE model_version <> 'stub'
GROUP BY page, line, item_text
HAVING COUNT(*) >= 3
ORDER BY не_засчитано DESC;

-- Сколько попыток учителя подтвердили (agree) и исправили (fix) — по таблице меток;
-- label в v_errors — метка попытки, а не ошибки: там попытка считалась бы столько раз, сколько в ней ошибок
SELECT a.label, COUNT(DISTINCT a.attempt_id) AS попыток
FROM annotations a
JOIN v_attempts t ON t.attempt_id = a.attempt_id
WHERE t.model_version <> 'stub'
GROUP BY a.label;
```

## 4. Частые ошибки
| Сообщение | Что не так |
|---|---|
| `column "…" does not exist` | опечатка в имени колонки или текст в двойных кавычках — нужны одинарные `'ص'` |
| `must appear in the GROUP BY clause` | колонка в `SELECT` не посчитана и не перечислена в `GROUP BY` |
| `argument of WHERE must be type boolean` | условие неполное: `WHERE disputed` → `WHERE disputed > 0` |
| `permission denied` | скрытые данные: колонка Telegram ID или таблица `annotator_invites` — входу «просмотр» их не видно |
| `cannot execute … in a read-only transaction` | попытка изменить данные — вход только для чтения |

## 5. Когда запрос стоит сохранить
Разовый вопрос — в `.vscode/queries.sql`. Вопрос, ответ на который пойдёт в диссертацию, —
в `analytics/sql/NN_имя.sql`: он попадёт в git и в `make report`, и цифру в главе можно будет
воспроизвести (ADR-0036). Попросите агента оформить его туда.

## 6. Как учиться дальше
- Не знаете, как спросить, — напишите вопрос словами агенту в VS Code: он составит запрос, проверит
  его на базе и объяснит по строчкам.
- Справочник PostgreSQL на русском: <https://postgrespro.ru/docs/postgresql/16/tutorial-sql>
  (главы 2.5–2.7: запросы, соединения, агрегатные функции).
- Тренажёр в браузере: <https://sqlbolt.com> (англ., 20 коротких уроков).
