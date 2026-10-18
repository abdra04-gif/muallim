#!/bin/sh
# Восстановление из копии: scripts/db/restore.sh data/backups/<дата> [--yes]
# ПЕРЕЗАПИШЕТ текущую базу и записи. Порядок: сверка SHA256SUMS → проверка архива →
# подтверждение словом «да» → копия текущего состояния → pg_restore одной транзакцией
# (сбой посередине — база остаётся как была). Запускает человек; перед этим остановите бота.
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

echo "Копия текущего состояния перед восстановлением…"
sh scripts/db/backup.sh

docker compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' \
  < "$d/db.dump" || { echo "ОШИБКА: восстановление не удалось, база не изменена" >&2; exit 1; }
if [ -f "$d/audio.tar.gz" ]; then
  tar -xzf "$d/audio.tar.gz" -C data
fi
echo "Восстановлено из $d. Проверьте: uv run muallim-research verify"
echo "ВНИМАНИЕ: копия вернула учеников, которые удалили данные или отозвали согласие ПОСЛЕ неё —"
echo "удалите их снова (TD-DB-05, docs/security/privacy.md)."
