#!/usr/bin/env bash
# Compatibility entry point. Run scripts/<os>/dev setup first.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$ROOT/scripts/dev.sh" start "$@"
