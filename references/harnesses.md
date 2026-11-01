# Harness adapters

Installing the skill lets a harness discover the workflow; it does not grant access to that harness's model account. Native CLI adapters exist for Codex, Claude Code and Grok. Other hosts use an explicitly configured command or gateway.

## Generic command contract

Set `PDF_TRANSLATE_COMMAND_JSON` to a JSON array of executable and arguments. The process must accept the whole UTF-8 prompt on stdin, return only the final answer on stdout, send diagnostics to stderr, exit nonzero on failure, and work noninteractively. Use the CLI's documented noninteractive mode. If it emits event streams or banners, supply a wrapper that extracts the final answer. Never paste credentials into the array.

```bash
export PDF_TRANSLATE_COMMAND_JSON='["/absolute/path/to/adapter", "--noninteractive"]'
bash scripts/translate.sh paper.pdf --engine command
```

This is a contract example, not a real vendor command. Model selection and authentication belong to the configured command. `--model` does not rewrite custom argv. Unknown harnesses never fall through to unrelated installed vendors or a free relay.

## Network and performance

```bash
export PDF_TRANSLATE_CLI_PROXY=http://127.0.0.1:7897
bash scripts/translate.sh paper.pdf --engine codex
```

Proxy configuration is optional and process-scoped. Loopback traffic bypasses it. Codex inherits its configured model; the log label `codex-default` is a routing alias, not the actual model name. Obtain the resolved model from a verified CLI report before claiming a model name.

Codex batches independent layout prompts up to 48000 characters, with four parallel CLI processes. Tune with `PDF_TRANSLATE_BATCH_MAX_CHARS`, `PDF_TRANSLATE_BATCH_PARALLEL`, `PDF_TRANSLATE_BATCH_SIZE`, `PDF_TRANSLATE_BATCH_WAIT`, and `PDF_TRANSLATE_TIMEOUT`. A CLI process is still started per batch; this is not a persistent model session. Reduce batch size if a model loses placeholders. Do not raise concurrency blindly when rate-limited.

For a cold benchmark use a separate output folder and `--fresh`; do not delete user caches. Record elapsed time, page count, backend, known model, cache policy and render defects. A cached 21-page run completed in 2m27s locally, but this does not establish cold-run performance or a cross-harness speed guarantee.
