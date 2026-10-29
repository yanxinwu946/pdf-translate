#!/usr/bin/env bash
# Install this skill into every coding-agent skill folder on this machine.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HOME:-}"
[[ -n "$HOME_DIR" ]] || { echo "HOME is not set" >&2; exit 1; }

user_roots=(
  "$HOME_DIR/.claude/skills"
  "$HOME_DIR/.grok/skills"
  "$HOME_DIR/.agents/skills"
  "$HOME_DIR/.codex/skills"
  "$HOME_DIR/.cursor/skills"
  "$HOME_DIR/.copilot/skills"
  "$HOME_DIR/.gemini/skills"
  "$HOME_DIR/.config/opencode/skills"
  "$HOME_DIR/.factory/skills"
  "$HOME_DIR/.codeium/windsurf/skills"
  "$HOME_DIR/.pi/agent/skills"
  "$HOME_DIR/.openclaw/skills"
  "$HOME_DIR/.agent/skills"
  "$HOME_DIR/.hermes/skills"
  "$HOME_DIR/.windsurf/skills"
  "$HOME_DIR/.continue/skills"
  "$HOME_DIR/.qwen/skills"
  "$HOME_DIR/.trae/skills"
  "$HOME_DIR/.lingma/skills"
  "$HOME_DIR/.opencode/skills"
)

link_one() {
  local dest="$1/pdf-translate"
  mkdir -p "$1"
  if [[ -e "$dest" || -L "$dest" ]]; then
    local resolved
    resolved="$(cd "$dest" 2>/dev/null && pwd -P || true)"
    if [[ "$resolved" == "$SRC" ]]; then
      echo "[skip] already linked  $dest"
      return 0
    fi
    echo "[replace] $dest"
    rm -rf "$dest"
  fi
  if ln -sfn "$SRC" "$dest" 2>/dev/null; then
    echo "[link] $dest -> $SRC"
  else
    mkdir -p "$dest"
    cp -R "$SRC/." "$dest/"
    echo "[copy] $dest"
  fi
}

echo "Installing pdf-translate from $SRC"
for root in "${user_roots[@]}"; do
  parent="$(dirname "$root")"
  if [[ -d "$parent" || "$root" == *".agents/skills" || "$root" == *".claude/skills" || "$root" == *".grok/skills" ]]; then
    mkdir -p "$root"
    link_one "$root"
  fi
done

# Always ensure the universal interop path exists.
mkdir -p "$HOME_DIR/.agents/skills"
link_one "$HOME_DIR/.agents/skills"

echo
echo "Done. In your agent, say: 翻译这篇论文"
echo "Or: bash \"$SRC/scripts/setup.sh\" && bash \"$SRC/scripts/translate.sh\" paper.pdf"
