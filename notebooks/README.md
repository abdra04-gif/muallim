# Ноутбуки — запросы, таблицы и графики в VS Code

Для автора исследования. Библиотеки — группа `notebook` в `pyproject.toml` (ставится обычным `uv sync`).

## Как открыть
1. `make db-up` — база запущена.
2. Откройте `notebooks/start.ipynb` в VS Code.
3. Справа вверху «Выбрать ядро» → **Python Environments** → `.venv` (Python 3.12 проекта).
4. Запуск ячейки — **Shift+Enter**; все ячейки — «Выполнить все» вверху.

## Как писать свой запрос
```python
df = await sql(
    "SELECT page, COUNT(*) AS n FROM v_attempts WHERE model_version <> 'stub' GROUP BY page"
)
df  # таблица
df.plot.bar(x="page")  # график
```
Как писать сам SQL — `docs/data/sql-guide.md`.

## Правила
- Ноутбуки (`*.ipynb`) **не попадают в git**: в их результатах — данные учеников (псевдонимы,
  тексты попыток). В git — только `db.py` и этот файл.
- Цифра или рисунок для диссертации → запрос в `analytics/sql/` (воспроизводимо через `make report`,
  ADR-0036); ноутбук — черновик, где цифру ищут.
- Рисунки сохранять в `thesis/` вручную (`plt.savefig(...)`), а не оставлять только в ноутбуке.
