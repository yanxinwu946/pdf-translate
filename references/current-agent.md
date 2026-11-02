# Local translation handoff

The engine writes `HASH.request.json` files containing `language` and `messages` into its printed queue directory. The hash covers messages and target language. Files contain document text, not credentials. Keep them private.

For each unanswered request, write `HASH.response.json` as `{"text":"the required translation response"}`. Write a temporary file then rename it so the engine cannot read half-written JSON. For plain requests, `text` is the translation only. For structured IL requests, `text` is the serialized JSON specified by the request, retaining IDs, formula placeholders and structure. Never mix ID namespaces between requests.

Read only unanswered requests in bounded groups. Read shared instructions once, not on every poll. Answer initial readiness probes promptly. Keep checking for new requests: validation and fallback may introduce additional ones. A successful response alone does not prove the PDF is valid.

## Service loop

1. Inspect `queue_status.py QUEUE --summary` and the live engine handle.
2. Read `queue_status.py QUEUE --limit 3` (lower the limit for large units). Translate these requests, write responses atomically, then immediately take the next batch. Process oldest requests first to reduce timeouts. Do not read all pending requests or repeat shared prompts on every poll.
3. If pending is zero but the engine is alive, wait briefly and inspect again. Parsing, validation, and PDF generation can all produce quiet periods. Continue until the engine exits; a response timeout is an error to diagnose and resume, not permission to shrink the scope.
4. On exit, check its status and requested outputs, inspect late-page coverage and rendered samples, then deliver. `run-state.json` identifies new/modified PDFs from this invocation; older outputs do not establish success.

Bibliography entries are copied unchanged by default, including titles and publication details; do not translate or summarize them. Still return a response with the required JSON IDs and output fields. For a batch mixing references and prose, preserve only the bibliography entries and translate the prose. Fallback may ask for the unchanged entry again; respond again. Translate bibliography only on explicit user request.

Preserve tags and placeholders within their original units. Do not add translator notes or duplicate words already supplied by neighboring styled spans. Formula-only or identifier-only inputs can legitimately be unchanged.

Responses persist for resume. Revised source, prompt or language gets a different hash. Correct only affected responses. `--fresh` creates a new namespace and disables engine cache without deleting previous work. Missing responses time out; there is no CLI or remote translator fallback.
