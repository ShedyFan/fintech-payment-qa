#!/usr/bin/env bash
# Сборка docs/qa-report.pdf из docs/qa-report.html.
#
# В окружении нет прав root и недоступны apt/pip/node, поэтому weasyprint /
# wkhtmltopdf поставить нельзя. Рендер идёт через headless Chrome (сборка для
# Windows, вызывается из WSL) + полифил CSS Paged Media paged.js: он считает
# постраничную вёрстку, колонтитулы и номера страниц в оглавлении.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
# Рабочая папка на стороне Windows без пробелов и кириллицы в пути —
# у Chrome, запущенного через WSL-interop, иначе ломается разбор аргументов.
WORK_WIN='C:\Users\Tester_QA\AppData\Local\Temp\qabuild'
WORK_NIX="$(wslpath -u "$WORK_WIN")"

rm -rf "$WORK_NIX"
mkdir -p "$WORK_NIX"
cp "$HERE/qa-report.html" "$HERE/paged.polyfill.js" "$WORK_NIX/"

"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --run-all-compositor-stages-before-draw --virtual-time-budget=180000 \
  --print-to-pdf="$WORK_WIN\\qa-report.pdf" \
  "$WORK_WIN\\qa-report.html"

cp "$WORK_NIX/qa-report.pdf" "$HERE/qa-report.pdf"
echo "OK: $HERE/qa-report.pdf"
