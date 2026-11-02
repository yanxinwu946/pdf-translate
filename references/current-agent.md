# Local translation handoff

The engine writes `HASH.request.json` files containing `language` and `messages` into its printed queue directory. The hash covers messages and target language. Files contain document text, not credentials. Keep them private.

For each unanswered request, write `HASH.response.json` as `{"text":"the required translation response"}`. Write a temporary file then rename it so the engine cannot read half-written JSON. For plain requests, `text` is the translation only. For structured IL requests, `text` is the serialized JSON specified by the request, retaining IDs, formula placeholders and structure. Never mix ID namespaces between requests.

Read only unanswered requests in bounded groups. Read shared instructions once, not on every poll. Answer initial readiness probes promptly. Keep checking for new requests: validation and fallback may introduce additional ones. A successful response alone does not prove the PDF is valid.

Responses persist for resume. Revised source, prompt or language gets a different hash. Correct only affected responses. `--fresh` creates a new namespace and disables engine cache without deleting previous work. Missing responses time out; there is no CLI or remote translator fallback.
