#!/bin/sh
# Рендер схем docs/architecture/diagrams/*.mmd → .svg (для Markdown) и .png (для диплома).
# Нужны node и Google Chrome; puppeteer не скачивает свой браузер.
set -eu
cd "$(dirname "$0")/../docs/architecture/diagrams"
export PUPPETEER_SKIP_DOWNLOAD=1
for f in *.mmd; do
  name="${f%.mmd}"
  npx -y @mermaid-js/mermaid-cli@11.4.2 -p puppeteer.json -i "$f" -o "$name.svg" -b white -q
  npx -y @mermaid-js/mermaid-cli@11.4.2 -p puppeteer.json -i "$f" -o "$name.png" -b white -s 2 -q
  echo "ok: $name"
done
