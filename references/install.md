# Install this skill on every agent

The skill is one folder. Agents differ only in where they look for `SKILL.md`.

## One-command install

From the repo root:

```bash
bash install.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Or:

```bash
npx skills add yanxinwu946/pdf-translate
```

## Where it lands

| Agent | User (all projects) | This repo |
|---|---|---|
| Universal | `~/.agents/skills/pdf-translate/` | `.agents/skills/pdf-translate/` |
| Claude Code | `~/.claude/skills/pdf-translate/` | `.claude/skills/pdf-translate/` |
| Grok | `~/.grok/skills/pdf-translate/` | `.grok/skills/pdf-translate/` |
| Codex | `~/.codex/skills/pdf-translate/` | `.codex/skills/` or `.agents/skills/` |
| Cursor | `~/.cursor/skills/pdf-translate/` | `.cursor/skills/pdf-translate/` |
| GitHub Copilot | `~/.copilot/skills/pdf-translate/` | `.github/skills/` or `.agents/skills/` |
| Gemini CLI | `~/.gemini/skills/pdf-translate/` | `.gemini/skills/` |
| OpenCode | `~/.config/opencode/skills/pdf-translate/` | `.opencode/skills/` |
| Factory Droid | `~/.factory/skills/pdf-translate/` | |
| Windsurf | `~/.codeium/windsurf/skills/pdf-translate/` or `~/.windsurf/skills/` | `.windsurf/skills/` |
| Continue | `~/.continue/skills/pdf-translate/` | |
| Qwen | `~/.qwen/skills/pdf-translate/` | |
| Trae | `~/.trae/skills/pdf-translate/` | |
| 通义灵码 | `~/.lingma/skills/pdf-translate/` | |

`install.sh` / `install.ps1` junction or copy the repo into every user folder whose parent already exists, and always into `~/.claude`, `~/.grok`, and `~/.agents`.

## Then

```
翻译这篇论文
```

or

```bash
bash scripts/setup.sh
bash scripts/translate.sh "/path/to/paper.pdf"
```

Windows needs Git Bash for the `.sh` scripts.
