#!/usr/bin/env bash
# translate.sh — translate a PDF with pdf2zh_next.
#
# Engine selection (unless --engine is given):
#   1. grok     — `grok` CLI. Local OpenAI-compatible proxy → `grok -p`
#                 (Grok login quota, not the billed xAI HTTP API).
#   2. claude   — `claude` CLI via the same proxy (Claude Code login).
#   3. openai   — OPENAI_API_KEY or ~/.codex/config.toml.
#   4. siliconflowfree — zero-config GLM-4-9B fallback.
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
  [[ -n "$UV_TOOL_DIR" ]] && add_path "$(dirname "$UV_TOOL_DIR")/shims"
fi

INPUT=""
ENGINE=""
MODEL=""
BASE_URL=""
API_KEY=""
OUTPUT=""
PAGES=""
LANG_IN="en"
LANG_OUT="zh-CN"
QPS=""
POOL=""
NO_DUAL=0
NO_MONO=0
FRESH=0
PASSTHROUGH=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine)        ENGINE="$2"; shift 2 ;;
    --model)         MODEL="$2"; shift 2 ;;
    --base-url)      BASE_URL="$2"; shift 2 ;;
    --api-key)       API_KEY="$2"; shift 2 ;;
    --output)        OUTPUT="$2"; shift 2 ;;
    --pages)         PAGES="$2"; shift 2 ;;
    --lang-in)       LANG_IN="$2"; shift 2 ;;
    --lang-out)      LANG_OUT="$2"; shift 2 ;;
    --qps)           QPS="$2"; shift 2 ;;
    --pool-max-workers) POOL="$2"; shift 2 ;;
    --no-dual)       NO_DUAL=1; shift ;;
    --no-mono)       NO_MONO=1; shift ;;
    --fresh)         FRESH=1; shift ;;
    --)              shift; while [[ $# -gt 0 ]]; do PASSTHROUGH+=("$1"); shift; done ;;
    -h|--help)      sed -n '2,20p' "$0"; exit 0 ;;
    -*)             echo "Unknown option: $1" >&2; exit 2 ;;
    *)              if [[ -z "$INPUT" ]]; then INPUT="$1"; else echo "Unexpected arg: $1" >&2; exit 2; fi; shift ;;
  esac
done

if [[ -z "$INPUT" ]]; then
  echo "ERROR: no input PDF given." >&2
  echo "Usage: translate.sh <input.pdf> [options]" >&2
  exit 2
fi

INPUT="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
if [[ ! -f "$INPUT" ]]; then
  echo "ERROR: input file not found: $INPUT" >&2
  exit 1
fi

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="$(dirname "$INPUT")/output"
fi
mkdir -p "$OUTPUT"

command -v pdf2zh_next >/dev/null 2>&1 || {
  echo "pdf2zh_next not found. Run setup.sh first." >&2
  exit 1
}

pick_python() {
  if command -v python >/dev/null 2>&1; then command -v python; return 0; fi
  if command -v python3 >/dev/null 2>&1; then command -v python3; return 0; fi
  echo python
}

read_codex_config() {
  local cfg="$HOME/.codex/config.toml"
  local py
  py="$(pick_python)"
  [[ -f "$cfg" ]] || return 0
  "$py" - "$cfg" <<'PY'
import sys, tomllib
try:
    with open(sys.argv[1], "rb") as f:
        cfg = tomllib.load(f)
except Exception:
    sys.exit(0)
model = cfg.get("model", "")
provider = cfg.get("model_provider", "")
base_url = ""
provs = cfg.get("model_providers", {})
if provider and provider in provs:
    base_url = provs[provider].get("base_url", "")
if base_url or model:
    print(f"{base_url}\t{model}")
PY
}

if [[ -z "$ENGINE" ]]; then
  ENGINE="${PDF_TRANSLATE_ENGINE:-}"
fi
if [[ -z "$ENGINE" ]]; then
  if [[ -n "${GROK_HOME:-}" ]] && command -v grok >/dev/null 2>&1; then
    ENGINE="grok"
  elif [[ -n "${CLAUDECODE:-}${CLAUDE_CODE:-}${CLAUDE_CODE_ENTRYPOINT:-}" ]] && command -v claude >/dev/null 2>&1; then
    ENGINE="claude"
  elif command -v grok >/dev/null 2>&1; then
    ENGINE="grok"
  elif command -v claude >/dev/null 2>&1; then
    ENGINE="claude"
  elif [[ -n "${OPENAI_API_KEY:-}" || -n "$API_KEY" ]]; then
    ENGINE="openai"
  else
    ENGINE="siliconflowfree"
  fi
fi

CMD=(pdf2zh_next "$INPUT" --lang-in "$LANG_IN" --lang-out "$LANG_OUT" --output "$OUTPUT" --watermark-output-mode no_watermark)
[[ -n "$PAGES" ]]        && CMD+=(--pages "$PAGES")
[[ -n "$QPS" ]]          && CMD+=(--qps "$QPS")
[[ -n "$POOL" ]]         && CMD+=(--pool-max-workers "$POOL")
(( NO_DUAL == 1 ))       && CMD+=(--no-dual)
(( NO_MONO == 1 ))       && CMD+=(--no-mono)
(( FRESH == 1 ))         && CMD+=(--ignore-cache)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

start_cli_proxy() {
  local backend="$1"
  local default_model="$2"
  local py_bin proxy gloss
  local paths
  paths="$("$(pick_python)" - "$SCRIPT_DIR" "$INPUT" <<'PY'
from pathlib import Path
import shutil, sys

def to_win(p: str) -> Path:
    p = p.replace("\\", "/")
    if len(p) >= 3 and p.startswith("/") and p[2] == "/":
        return Path(f"{p[1].upper()}:{p[2:]}")
    return Path(p)

script_dir = to_win(sys.argv[1])
pdf = to_win(sys.argv[2])
py = Path(shutil.which("python") or shutil.which("python3") or sys.executable).resolve()
proxy = (script_dir / "cli_openai_proxy.py").resolve()
print(py.as_posix())
print(proxy.as_posix())
cands = [
    script_dir.parent / "glossaries" / "academic-en-zh.csv",
    pdf.parent / "pdf-translate-glossary.csv",
    pdf.with_suffix(".glossary.csv"),
]
for p in cands:
    if p.is_file():
        print(p.resolve().as_posix())
PY
)"
  py_bin="$(printf '%s\n' "$paths" | sed -n '1p')"
  proxy="$(printf '%s\n' "$paths" | sed -n '2p')"
  gloss="$(printf '%s\n' "$paths" | sed -n '3,99p' | tr '\n' ',' | sed 's/,$//')"
  if [[ -z "$py_bin" || -z "$proxy" ]]; then
    echo "ERROR: could not resolve python / cli_openai_proxy.py" >&2
    exit 1
  fi
  local cli_model="${MODEL:-$default_model}"
  export PDF_TRANSLATE_LANG_OUT="$LANG_OUT"
  export PDF_TRANSLATE_MODEL="$cli_model"
  export PDF_TRANSLATE_EFFORT="${PDF_TRANSLATE_EFFORT:-low}"
  export PDF_TRANSLATE_TIMEOUT="${PDF_TRANSLATE_TIMEOUT:-180}"
  export PDF_TRANSLATE_BACKEND="$backend"
  export PDF_TRANSLATE_GLOSSARIES="$gloss"
  local port
  port="$("$py_bin" -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")"
  local proxy_log="${TMPDIR:-/tmp}/pdf-translate-cli-proxy.log"
  mkdir -p "$(dirname "$proxy_log")"
  : > "$proxy_log"
  "$py_bin" -u "$proxy" --host 127.0.0.1 --port "$port" --backend "$backend" --model "$cli_model" --lang-out "$LANG_OUT" --glossary "$gloss" >>"$proxy_log" 2>&1 &
  PROXY_PID=$!
  cleanup_proxy() { kill "$PROXY_PID" 2>/dev/null || true; }
  trap cleanup_proxy EXIT
  if ! "$py_bin" -c "import sys,time,urllib.request
port=sys.argv[1]
for _ in range(50):
    try:
        urllib.request.urlopen('http://127.0.0.1:%s/health'%port, timeout=1)
        raise SystemExit(0)
    except Exception:
        time.sleep(0.2)
print('proxy did not become healthy', file=sys.stderr)
raise SystemExit(1)
" "$port"
  then
    echo "ERROR: $backend proxy failed to start. Log: $proxy_log" >&2
    tail -n 40 "$proxy_log" 2>/dev/null || true
    exit 1
  fi
  echo "[translate] started $backend proxy pid=$PROXY_PID  http://127.0.0.1:$port/v1"
  echo "[translate] proxy log: $proxy_log"
  [[ -z "$QPS" ]]  && CMD+=(--qps 8)
  [[ -z "$POOL" ]] && CMD+=(--pool-max-workers 12)
  CMD+=(--openai --openai-base-url "http://127.0.0.1:${port}/v1" --openai-api-key "${backend}-cli" --openai-model "$cli_model" --openai-timeout "${PDF_TRANSLATE_TIMEOUT}")
  CMD+=(--no-auto-extract-glossary)
  local skip_gloss=0
  for a in "${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}"; do
    [[ "$a" == --glossaries ]] && skip_gloss=1
  done
  if [[ "$skip_gloss" -eq 0 && -n "$gloss" ]]; then
    CMD+=(--glossaries "$gloss")
    echo "[translate] glossaries: $gloss"
  fi
  echo "[translate] engine=$backend  model=$cli_model  (batched $backend CLI via local proxy)"
}

case "$ENGINE" in
  grok)
    command -v grok >/dev/null 2>&1 || { echo "ERROR: grok CLI not found on PATH." >&2; exit 1; }
    start_cli_proxy grok grok-4.6
    ;;
  claude)
    command -v claude >/dev/null 2>&1 || { echo "ERROR: claude CLI not found on PATH." >&2; exit 1; }
    start_cli_proxy claude "${MODEL:-sonnet}"
    ;;
  claudecode)
    CC_MODEL="${MODEL:-sonnet}"
    [[ -z "$QPS" ]]  && CMD+=(--qps 4)
    [[ -z "$POOL" ]] && CMD+=(--pool-max-workers 8)
    CMD+=(--claudecode --claude-code-model "$CC_MODEL")
    echo "[translate] engine=claudecode  model=$CC_MODEL  (one subprocess per segment)"
    ;;
  openai)
    if [[ -z "$BASE_URL" ]]; then
      BASE_URL="${OPENAI_BASE_URL:-}"
    fi
    if [[ -z "$BASE_URL" ]]; then
      codex_row="$(read_codex_config || true)"
      if [[ -n "$codex_row" ]]; then
        BASE_URL="$(printf '%s' "$codex_row" | cut -f1)"
        [[ -z "$MODEL" ]] && MODEL="$(printf '%s' "$codex_row" | cut -f2)"
      fi
    fi
    [[ -z "$MODEL" ]] && MODEL="gpt-4o-mini"
    KEY="${API_KEY:-${OPENAI_API_KEY:-}}"
    if [[ -z "$KEY" ]]; then
      echo "ERROR: openai engine needs an API key. Set OPENAI_API_KEY or pass --api-key." >&2
      exit 1
    fi
    if [[ -z "$BASE_URL" ]]; then
      echo "ERROR: openai engine needs a base_url. Pass --base-url or configure ~/.codex/config.toml." >&2
      exit 1
    fi
    [[ -z "$QPS" ]]  && CMD+=(--qps 10)
    [[ -z "$POOL" ]] && CMD+=(--pool-max-workers 30)
    CMD+=(--openai --openai-base-url "$BASE_URL" --openai-api-key "$KEY" --openai-model "$MODEL")
    echo "[translate] engine=openai  base_url=$BASE_URL  model=$MODEL"
    ;;
  siliconflowfree)
    CMD+=(--siliconflowfree)
    echo "[translate] engine=siliconflowfree  (free, content routed via pdf2zh maintainer's server)"
    ;;
  *)
    echo "ERROR: unknown engine '$ENGINE'. Use grok | claude | claudecode | openai | siliconflowfree." >&2
    exit 2
    ;;
esac

[[ ${#PASSTHROUGH[@]} -gt 0 ]] && CMD+=("${PASSTHROUGH[@]}")

echo "[translate] output dir: $OUTPUT"
echo "[translate] running: ${CMD[*]}"
BABELDOC_CACHE="$HOME/.cache/babeldoc"
if [[ ! -d "$BABELDOC_CACHE/models" ]] || [[ -z "$(ls -A "$BABELDOC_CACHE/models" 2>/dev/null)" ]]; then
  echo "(first run downloads model assets and will be slow — subsequent runs use cache)"
fi
echo

set +e
"${CMD[@]}"
RC=$?
set -e

echo
if [[ $RC -ne 0 ]]; then
  echo "[translate] FAILED (exit $RC)." >&2
  exit $RC
fi

echo "[translate] done. Generated files:"
ls -1 "$OUTPUT"/*mono.pdf "$OUTPUT"/*dual.pdf 2>/dev/null | sed 's/^/  /' || true
