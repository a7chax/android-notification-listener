#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  setup|doctor|listen|snapshot|demo) ;;
  *) set -- listen "$@" ;;
esac

if command -v uv >/dev/null 2>&1; then
  exec uv run "$SCRIPT_DIR/listener.py" "$@"
fi
exec python3 "$SCRIPT_DIR/listener.py" "$@"
