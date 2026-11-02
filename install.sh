#!/usr/bin/env bash
set -euo pipefail
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="${1:-$HOME/.codex/skills}"
dest="$root/pdf-translate"
if [[ -e "$dest" || -L "$dest" ]]; then
  echo "Existing installation preserved: $dest"
  exit 0
fi
mkdir -p "$root"
ln -s "$src" "$dest"
echo "Installed: $dest"
