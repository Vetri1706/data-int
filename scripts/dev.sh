#!/usr/bin/env bash
# Shared POSIX entry point. Invoke with bash; executable bits are optional.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for candidate in "$ROOT/.venv/bin/python" python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    exec "$candidate" "$ROOT/scripts/dev.py" "$@"
  fi
done
echo 'Python 3.11+ is required. Install it, then rerun this command.' >&2
exit 1
