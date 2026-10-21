#!/bin/zsh
set -euo pipefail
project_dir="${0:A:h:h}"
cd "$project_dir"
if [[ ! -f frontend/dist/index.html ]]; then
  pnpm --dir frontend build
fi
exec .venv/bin/observatory serve --port "${OBSERVATORY_PORT:-8776}"
