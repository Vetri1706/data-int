#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
action="${1:-start}"
if (($#)); then shift; fi
case "$action" in
  start) set -- up -d --build --wait --wait-timeout 240 "$@" ;;
  stop) set -- stop "$@" ;;
  status) set -- ps "$@" ;;
  logs) set -- logs --tail 100 -f "$@" ;;
  build) set -- build "$@" ;;
  *) echo 'Usage: docker.sh {start|stop|status|logs|build} [service...]' >&2; exit 2 ;;
esac
exec docker compose --project-directory "$root" --env-file "$root/.env" -f "$root/compose.yml" "$@"
