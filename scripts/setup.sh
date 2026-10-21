#!/bin/zsh
set -euo pipefail
project_dir="${0:A:h:h}"
cd "$project_dir"
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
if ! command -v pnpm >/dev/null 2>&1; then
  print 'pnpm is required. Install Node.js and enable pnpm, then rerun this script.' >&2
  exit 1
fi
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
.venv/bin/observatory init
.venv/bin/python -m alembic upgrade head
.venv/bin/observatory geography
.venv/bin/python scripts/fetch_city_labels.py
.venv/bin/observatory atlas --core
print 'Setup complete. Start with ./scripts/start.sh; collect with ./scripts/collect.sh.'
