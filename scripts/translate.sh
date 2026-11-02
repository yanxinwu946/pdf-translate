#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  tool_dir="$(uv tool dir)"
  export PATH="$(dirname "$tool_dir")/shims:$PATH"
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python}" "$script_dir/session.py" "$@"
