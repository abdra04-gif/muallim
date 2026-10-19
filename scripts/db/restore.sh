#!/bin/sh
# Восстановление из копии: scripts/db/restore.sh data/backups/<дата> [--yes]
# ПЕРЕЗАПИШЕТ текущую базу и записи. Порядок: сверка SHA256SUMS → проверка архива →
# подтверждение словом «да» → копия текущего состояния → pg_restore одной транзакцией
# (сбой посередине — база остаётся как была) → повтор журнала удалений: копия не знает об
# удалениях после неё (TD-DB-05). Запускает человек; перед этим остановите бота.
set -eu
umask 077  # голоса и псевдонимы: читать может только владелец
cd "$(dirname "$0")/../.."

d="${1:-}"
[ -n "$d" ] && [ -f "$d/db.dump" ] || { echo "Укажите папку копии: $0 data/backups/<дата>" >&2; exit 1; }

if command -v sha256sum > /dev/null; then sum="sha256sum"; else sum="shasum -a 256"; fi
(cd "$d" && $sum -c SHA256SUMS > /dev/null 2>&1) \
  || { echo "ОШИБКА: копия повреждена — SHA256 не совпадает ($d/SHA256SUMS)" >&2; exit 1; }
docker compose exec -T postgres pg_restore --list < "$d/db.dump" > /dev/null \
  || { echo "ОШИБКА: архив БД не читается" >&2; exit 1; }

if [ "${2:-}" != "--yes" ]; then
  printf 'Текущие данные будут ЗАМЕНЕНЫ копией %s. Введите «да»: ' "$d"
  read -r answer || answer=""
  [ "$answer" = "да" ] || { echo "Отменено." >&2; exit 1; }
fi

# Роли — на весь сервер, в дампе их нет, а владелец таблиц в нём — muallim_owner (ADR-0054).
roles=$(docker compose exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM pg_roles WHERE rolname IN ('muallim_owner', 'muallim_app', 'muallim_reader')\"" \
  | tr -d '[:space:]')
[ "$roles" = "3" ] || { echo "ОШИБКА: на сервере нет ролей muallim_* — сначала make db-roles" >&2; exit 1; }

echo "Копия текущего состояния перед восстановлением…"
sh scripts/db/backup.sh

docker compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' \
  < "$d/db.dump" || { echo "ОШИБКА: восстановление не удалось, база не изменена" >&2; exit 1; }
if [ -f "$d/audio.tar.gz" ]; then
  tar -xzf "$d/audio.tar.gz" -C data || echo "ОШИБКА: записи не распакованы — БД уже восстановлена" >&2
fi

# Журналы удалений объединяем: в текущем — удаления новее копии, в копии — те, что могли
# пропасть (журнал пересоздан, новый компьютер). Строки начинаются со времени — сортировка по нему.
if [ -f "$d/erasures.jsonl" ]; then
  mkdir -p data/erasures
  cat "$d/erasures.jsonl" data/erasures/erasures.jsonl 2>/dev/null | sort -u > data/erasures/merged.tmp
  mv data/erasures/merged.tmp data/erasures/erasures.jsonl
fi
echo "Повторяю удаления из журнала: ученики, удалившие данные или отозвавшие согласие после копии…"
${MUALLIM_RESEARCH:-uv run muallim-research} reapply-erasures || {
  echo "ОШИБКА: журнал удалений не применён — запустите: uv run muallim-research reapply-erasures" >&2
  exit 1
}
echo "Восстановлено из $d. Проверьте: uv run muallim-research verify"
