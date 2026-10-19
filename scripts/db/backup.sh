#!/bin/sh
# Резервная копия: БД (pg_dump -Fc) + голосовые записи → data/backups/<дата>/ и SHA256SUMS.
# Копия проверяется (pg_restore --list читает архив целиком); при любом сбое папка получает
# суффикс -FAILED и скрипт выходит с ошибкой — неудачная копия не выдаётся за успешную.
# Копии содержат голоса и псевдонимы: хранить зашифрованными и вне ноутбука (TD-SEC-17, TD-FN-14).
# --db-only — только БД (перед миграцией: она не трогает записи — секунды, а не минуты).
# Журнал удалений (data/erasures/) копируется рядом, но при восстановлении не перезаписывается.
set -eu
umask 077  # голоса и псевдонимы: читать может только владелец
cd "$(dirname "$0")/../.."

d="data/backups/$(date +%Y-%m-%d_%H%M%S)"
[ ! -e "$d" ] || d="${d}_$$"  # две копии в одну секунду (копия перед восстановлением)
mkdir -p "$d"

fail() {
  mv "$d" "$d-FAILED"
  echo "ОШИБКА: $1. Копия НЕ сделана: $d-FAILED" >&2
  exit 1
}

docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
  > "$d/db.dump" || fail "pg_dump завершился с ошибкой (запущен ли make db-up?)"
[ -s "$d/db.dump" ] || fail "дамп пустой"
docker compose exec -T postgres pg_restore --list < "$d/db.dump" > /dev/null \
  || fail "дамп не читается (pg_restore --list)"

if [ "${1:-}" != "--db-only" ] && [ -d data/audio ]; then
  tar -czf "$d/audio.tar.gz" -C data audio || fail "не удалось упаковать записи"
fi
if [ -f data/erasures/erasures.jsonl ]; then
  cp data/erasures/erasures.jsonl "$d/erasures.jsonl" || fail "не удалось скопировать журнал удалений"
fi

if command -v sha256sum > /dev/null; then sum="sha256sum"; else sum="shasum -a 256"; fi
files=$(cd "$d" && for f in db.dump audio.tar.gz erasures.jsonl; do [ ! -f "$f" ] || echo "$f"; done)
(cd "$d" && $sum $files > SHA256SUMS) || fail "не удалось посчитать SHA-256"

ls -la "$d"
echo "Копия: $d (хранить вне ноутбука, зашифрованной — docs/data/browsing.md)"
