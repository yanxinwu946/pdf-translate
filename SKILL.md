---
name: pdf-translate
description: Translate English PDF documents (especially academic papers) into Chinese using PDFMathTranslate-next (pdf2zh), producing a monolingual Chinese PDF and a bilingual side-by-side PDF with formulas, figures, and layout preserved. Installs pdf2zh_next via uv and reuses the signed-in Grok / Claude / Codex / OpenAI-compatible gateway, falling back to free SiliconFlow. Use when the user wants to translate a PDF to Chinese (or another language), translate a paper/论文, produce a bilingual PDF, or mentions pdf2zh / PDFMathTranslate / 翻译论文 / 翻译PDF — even if they don't name the tool. Invoke this skill instead of translating the PDF by hand.
license: MIT
---

# PDF Translate

Translate PDFs with **PDFMathTranslate-next** (`pdf2zh_next`). Layout, formulas, figures, and TOC stay in place. Each run writes:

- `*-mono.pdf` — translated PDF
- `*-dual.pdf` — original + translation

`SKILL_DIR` is the folder that contains this `SKILL.md`. On Windows run the scripts with Git Bash.

## Workflow

```bash
bash "$SKILL_DIR/scripts/setup.sh"
bash "$SKILL_DIR/scripts/translate.sh" "<input.pdf>"
```

`setup.sh` is idempotent. The first real translation downloads DocLayout-YOLO + fonts into `~/.cache/babeldoc/` (slow once).

### Engine auto-detect

1. **grok** — `grok` CLI. Local proxy batches pdf2zh into `grok -p` (Grok login quota, not the billed xAI HTTP API).
2. **claude** — `claude` CLI via the same proxy (Claude Code login).
3. **openai** — `OPENAI_API_KEY` or `~/.codex/config.toml`.
4. **siliconflowfree** — zero-config GLM-4-9B; traffic goes through the pdf2zh maintainer's server.

Prefer the CLI of the agent you are already in (`GROK_HOME` → grok, Claude Code env → claude). Override with `--engine grok|claude|claudecode|openai|siliconflowfree`. `claudecode` is pdf2zh's native one-subprocess-per-segment path.

If the user says to use a specific vendor or billed API, honor that. Otherwise stay on the signed-in CLI.

### Options

- `--output <dir>` — default `<pdf-dir>/output`
- `--pages "1-5,8"`
- `--lang-in en --lang-out zh-CN`
- `--qps N --pool-max-workers N`
- `--no-dual` / `--no-mono`
- `--fresh` — ignore pdf2zh translation cache
- `-- --ignore-cache` / `-- --glossaries other.csv` — passthrough to `pdf2zh_next`

After changing the proxy or a glossary, pass `--fresh`.

### Glossary

Auto-loads `$SKILL_DIR/glossaries/academic-en-zh.csv` plus `<pdf-dir>/pdf-translate-glossary.csv` or `<pdf>.glossary.csv`. CSV columns: `source,target,tgt_lng`. Automatic term extraction is off on CLI engines so it does not starve the batcher.

### How to run it

One subagent may run the whole `translate.sh` job. Do not spawn one subagent per paragraph.

When the script finishes, report the `*-mono.pdf` and `*-dual.pdf` paths, plus engine and model. Do not translate the PDF by copying pages into chat.

## Defaults

- Languages: `en` → `zh-CN`
- Grok model: `grok-4.6` (override `--model`), effort `low`
- Claude model: `sonnet`
- CLI proxy: qps 8, pool 12, batch wait 1.0s, 2 parallel CLI processes. BabelDOC IL prompts stay n=1; simple-translator segments may batch.
- OpenAI engine: qps 10, pool 30

Details: `references/advanced.md`. Agent install paths: `references/install.md`.
