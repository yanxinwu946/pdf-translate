#!/usr/bin/env bash
# setup.sh — ensure pdf2zh_next is installed and on PATH.
set -euo pipefail

add_path() {
  local d="$1"
  [[ -n "$d" && -d "$d" ]] || return 0
  case ":$PATH:" in
    *":$d:"*) ;;
    *) export PATH="$d:$PATH" ;;
  esac
}

add_path "$HOME/.local/bin"
if command -v uv >/dev/null 2>&1; then
  add_path "$(dirname "$(command -v uv)")"
  UV_TOOL_DIR="$(uv tool dir 2>/dev/null || true)"
  if [[ -n "$UV_TOOL_DIR" ]]; then
    add_path "$(dirname "$UV_TOOL_DIR")/shims"
  fi
fi

command -v uv >/dev/null 2>&1 || {
  echo "ERROR: 'uv' is not installed. Install it first:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "  powershell -ExecutionPolicy Bypass -c \"irm https://astral.sh/uv/install.ps1 | iex\"" >&2
  exit 1
}

BABELDOC_CACHE="$HOME/.cache/babeldoc"
models_cached() {
  [[ -d "$BABELDOC_CACHE/models" ]] && [[ -n "$(ls -A "$BABELDOC_CACHE/models" 2>/dev/null)" ]]
}

if command -v pdf2zh_next >/dev/null 2>&1; then
  if models_cached; then
    echo "[setup] ready — pdf2zh_next installed and models cached."
  else
    echo "[setup] ready — pdf2zh_next installed at $(command -v pdf2zh_next)."
    echo "[setup] NOTE: first translation will download model assets (~hundreds of MB, one-time)."
  fi
  exit 0
fi

echo "[setup] installing pdf2zh_next via uv (python 3.12)..."
uv tool install --python 3.12 --with "bitstring>=4.3,<5" pdf2zh-next

if command -v pdf2zh_next >/dev/null 2>&1; then
  echo "[setup] installed — $(command -v pdf2zh_next)"
  echo "[setup] NOTE: first translation will download model assets (~hundreds of MB, one-time)."
else
  echo "ERROR: pdf2zh_next still not on PATH after install." >&2
  echo "Add $HOME/.local/bin (and uv tool shims) to PATH, then re-run." >&2
  exit 1
fi
