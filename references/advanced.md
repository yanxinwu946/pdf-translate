# Advanced reference — pdf-translate

Main workflow: `SKILL.md`. Agent folders: `references/install.md`.

## Engines

### grok / claude (CLI proxy)

`translate.sh` starts `scripts/cli_openai_proxy.py` on `127.0.0.1:<ephemeral>` and points pdf2zh `--openai` at it.

- **grok**: `grok -p` with a unique `--leader-socket`. Uses Grok login quota, not `api.x.ai`.
- **claude**: `claude -p --safe-mode --tools ""`. Prompt goes on stdin (Windows argument-length safe). Uses Claude Code login, not `--bare` (that flag skips OAuth).

The proxy classifies BabelDOC IL prompts (`## Structure Rules` / `layout_label`) and returns a clean JSON array. Simple-translator segments may batch (~12, wait 1.0s, 2 parallel processes). IL stays n=1 because BabelDOC already packs several paragraphs into one JSON.

Env: `PDF_TRANSLATE_ENGINE`, `PDF_TRANSLATE_MODEL`, `PDF_TRANSLATE_EFFORT`, `PDF_TRANSLATE_TIMEOUT`, `PDF_TRANSLATE_BATCH_SIZE`, `PDF_TRANSLATE_BATCH_WAIT`, `PDF_TRANSLATE_BATCH_PARALLEL`.

After changing the proxy or a glossary, pass `--fresh` (or `-- --ignore-cache`). Cache file: `~/.cache/pdf2zh_next/cache.v1.db`.

### claudecode

pdf2zh native path: one `claude -p` per segment. Slower. Use when you want pdf2zh to drive Claude itself.

### openai

`/v1/chat/completions` on an OpenAI-compatible gateway.

- base_url: `--base-url` > `OPENAI_BASE_URL` > `~/.codex/config.toml`
- key: `--api-key` > `OPENAI_API_KEY`
- model: `--model` > Codex config > `gpt-4o-mini`

Passthrough examples: `-- --zhipu --zhipu-api-key "$ZHIPU_KEY"`, `-- --deepseek`.

### siliconflowfree

Free GLM-4-9B. No key. Content is forwarded through the pdf2zh maintainer's server.

## Languages

Default `en` → `zh-CN`. Common codes: `zh-TW`, `ja`, `ko`, `fr`, `de`, `es`, `ru`.

Full list: https://pdf2zh-next.com/advanced/Language-Codes.html

## Glossaries

CSV columns `source,target,tgt_lng`. Auto-loaded:

1. `$SKILL_DIR/glossaries/academic-en-zh.csv`
2. `<pdf-dir>/pdf-translate-glossary.csv`
3. `<pdf>.glossary.csv`

The proxy uses the same CSV to split glued names (`YangXiang` → `Yang Xiang`, `姓名`+`大学`). Put paper-specific names in the PDF-side CSV, not in the skill.

## Speed

CLI engines: start at `--qps 8 --pool-max-workers 12`. OpenAI HTTP: `--qps 10 --pool-max-workers 30`. Back off on 429s.

Official rule of thumb: RPM-limited `qps = floor(rpm/60)`, `pool = qps * 10`.

## Partial / scanned / offline

- Pages: `--pages "1-3,10,25-"`
- Scanned: `-- --ocr-workaround` or `-- --auto-enable-ocr-workaround`
- Offline assets: `pdf2zh_next dummy.pdf --generate-offline-assets /bundle` then `-- --restore-offline-assets /bundle`
- Large PDFs: `--pages` or `-- --max-pages-per-part 50`

## Troubleshooting

- `pdf2zh_next` not found — run `setup.sh`; add `~/.local/bin` and uv tool shims to PATH.
- First run slow — one-time DocLayout-YOLO + fonts download.
- 429 — lower `--qps` and `--pool-max-workers`.
- OpenAI 404/400 — gateway may lack `/chat/completions`.
- Nested `grok -p` inside Grok — the proxy already sets a unique `--leader-socket`.
- Stale wording after a proxy/glossary change — `--fresh`.
- Windows — Git Bash for `.sh` scripts.
