---
name: pdf-translate
description: Translate academic PDFs into Chinese or another language with PDFMathTranslate-next, preserving layout, formulas, and figures and producing translated and bilingual PDFs. Supports Codex, Claude Code, Grok, custom harness command adapters, and explicitly selected OpenAI-compatible APIs. Use for translating papers, bilingual PDFs, 翻译论文, or 翻译PDF.
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
bash "$SKILL_DIR/scripts/translate.sh" "<input.pdf>" --engine codex
```

`setup.sh` is idempotent. The first real translation downloads DocLayout-YOLO + fonts into `~/.cache/babeldoc/` (slow once).

The command above is for Codex; use the matching engine below in other agents.

### Engine selection

Use the agent running this skill: **Codex must use `--engine codex`**, Claude Code uses `--engine claude`, and Grok uses `--engine grok`. Pass the engine explicitly when invoking the script; do not rely solely on environment detection. Codex uses `codex exec` with its existing login, provider, and configured model, not Claude/Grok or a separately billed API. Do not choose another vendor just because its CLI is installed.

If the selected CLI is unavailable, unauthenticated, or times out, stop and report the problem. Ask before switching vendors or using the free relay. An explicit user-requested vendor or API overrides host matching.

For other harnesses (Cursor, Gemini CLI, OpenCode, Copilot, etc.), skill installation and translation authentication are separate. Do not claim native backend support merely because the skill installs. Choose one of these explicit routes:

1. **command** — harness-specific noninteractive argv adapter, prompt on stdin and answer-only stdout. See `references/harnesses.md`. Do not invent vendor flags.
2. **openai** — a user-selected compatible gateway and API key, not automatically inferred permission to bill an API.
3. **codex / claude / grok** — another installed CLI only when the user explicitly chooses it.
4. **siliconflowfree** — only with user consent; sends content through the maintainer's server.

The launcher recognizes host session variables; unknown hosts stop with an actionable error instead of selecting an unrelated installed CLI. Override with `--engine codex|grok|claude|command|claudecode|openai|siliconflowfree`. `claudecode` is a slower legacy per-segment route.

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

Inspect rendered samples from the first page, formulas, figures and dense text before delivery. Report cache use separately from elapsed time: a warm-cache run is not a cold translation benchmark. Never promise a fixed completion time. Preserve source PDFs and previous outputs. Name remaining defects rather than declaring success from HTTP response counts alone.

## Defaults

- Languages: `en` → `zh-CN`
- Grok model: `grok-4.6` (override `--model`), effort `low`
- Claude model: `sonnet`
- Codex model: inherited from the user's Codex configuration; `--model` only when requested
- CLI proxy: qps 8, pool 12, batch wait 1.0s. IL and plain translation requests both batch; utility prompts remain independent. Codex defaults to 4 parallel processes and 48000 characters per batch.
- Optional network proxy: `PDF_TRANSLATE_CLI_PROXY=http://127.0.0.1:7897`. Local layout traffic bypasses it; system proxy settings remain unchanged.
- OpenAI engine: qps 10, pool 30

Details: `references/advanced.md`. Agent install paths: `references/install.md`.
