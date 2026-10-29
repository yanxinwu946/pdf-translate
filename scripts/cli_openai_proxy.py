#!/usr/bin/env python3
"""OpenAI-compatible proxy that batches pdf2zh calls into a local coding-agent CLI.

pdf2zh talks HTTP; this process fans requests into grok/claude CLI calls using
the user's existing login, not a separately billed HTTP API.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PLACEHOLDER_RE = re.compile(
    r"\{v\d+\}|\{\{\d+\}\}|<style\s+id='[^']+'>|</style>",
    re.I,
)
CJK = r"\u4e00-\u9fff"
LATIN_PERSON = re.compile(r"^[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+$")
CJK_PERSON = re.compile(rf"^[{CJK}]{{2,4}}$")
ORG_MARKERS = ("大学", "学院", "研究所", "研究院", "实验室", "University", "Institute")

GROK_DISALLOWED = ",".join(
    [
        "Agent",
        "run_terminal_cmd",
        "web_search",
        "web_fetch",
        "write",
        "search_replace",
        "read_file",
        "grep",
        "list_dir",
        "spawn_subagent",
        "image_gen",
        "image_edit",
        "use_tool",
        "search_tool",
        "workflow",
        "monitor",
    ]
)

IL_EXTRA_RULES = """

## Extra academic typesetting rules
- Keep a space between a person name and an affiliation.
- Keep Latin given-name and family-name spacing (e.g. Yang Xiang).
- Keep "et al." as "et al." with spaces.
- Keep model/system names, placeholders, formulas, URLs, and arXiv ids unchanged.
- Return ONLY the JSON array. No markdown fences, no commentary.
"""


def log(msg: str) -> None:
    print(f"[pdf-translate-proxy] {msg}", file=sys.stderr, flush=True)


def which(name: str) -> str:
    found = shutil.which(name) or shutil.which(f"{name}.exe")
    if not found:
        raise RuntimeError(f"{name} CLI not found on PATH")
    return found


def cjk_latin_space(text: str) -> str:
    parts: list[str] = []
    last = 0
    for m in PLACEHOLDER_RE.finditer(text):
        parts.append(_space_chunk(text[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_space_chunk(text[last:]))
    return "".join(parts)


def _space_chunk(s: str) -> str:
    s = re.sub(rf"([{CJK}])([A-Za-z])", r"\1 \2", s)
    s = re.sub(rf"([A-Za-z])([{CJK}])", r"\1 \2", s)
    s = re.sub(r"\betal\.", "et al.", s, flags=re.I)
    s = re.sub(r"\bet al\b", "et al.", s, flags=re.I)
    return s


def load_glossary_fixes(paths: list[str]) -> list[tuple[str, str]]:
    fixes: list[tuple[str, str]] = [
        ("etal.", "et al."),
        ("et al.", "et al."),
    ]
    people_cjk: list[str] = []
    orgs: list[str] = []
    seen: set[tuple[str, str]] = set(fixes)
    for raw in paths:
        path = Path(raw.strip())
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                source = (row.get("source") or "").strip()
                target = (row.get("target") or source).strip()
                if not source:
                    continue
                if LATIN_PERSON.match(source) or LATIN_PERSON.match(target):
                    compact = re.sub(r"[\s-]+", "", source)
                    pair = (compact, source if " " in source else target)
                    if pair[0] != pair[1] and pair not in seen:
                        fixes.append(pair)
                        seen.add(pair)
                if CJK_PERSON.match(target):
                    people_cjk.append(target)
                if any(m in target for m in ORG_MARKERS):
                    orgs.append(target)
    for person in people_cjk:
        for org in orgs:
            glued, spaced = person + org, f"{person} {org}"
            if (glued, spaced) not in seen:
                fixes.append((glued, spaced))
                seen.add((glued, spaced))
    fixes.sort(key=lambda x: len(x[0]), reverse=True)
    return fixes


class Polisher:
    def __init__(self, glossary_paths: list[str]):
        self.fixes = load_glossary_fixes(glossary_paths)

    def text(self, text: str) -> str:
        s = cjk_latin_space(text)
        for src, dst in self.fixes:
            s = s.replace(src, dst)
        return s

    def il_json(self, raw: str) -> str:
        data = _loads_json(raw)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("output"), str):
                    item["output"] = self.text(item["output"])
            return json.dumps(data, ensure_ascii=False)
        if isinstance(data, dict):
            if isinstance(data.get("output"), str):
                data["output"] = self.text(data["output"])
                return json.dumps(data, ensure_ascii=False)
            if isinstance(data.get("text"), str):
                inner = self.il_json(data["text"])
                if inner.strip()[:1] in "[{":
                    return inner
        return raw.strip()


POLISHER = Polisher([])


def classify(content: str) -> tuple[str, str]:
    lower = content.lower()
    if "machine translation engine" in lower or "translate it into" in lower:
        for marker in ("Input:\n\n", "Input:\r\n\r\n"):
            if marker in content:
                return "translate", content.split(marker, 1)[1]
        return "translate", content
    if "## Structure Rules" in content or '"layout_label"' in content:
        return "il", content
    return "other", content


def _loads_json(s: str) -> Any:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start_arr, end_arr = s.find("["), s.rfind("]")
        start_obj, end_obj = s.find("{"), s.rfind("}")
        candidates = []
        if start_arr != -1 and end_arr > start_arr:
            candidates.append(s[start_arr : end_arr + 1])
        if start_obj != -1 and end_obj > start_obj:
            candidates.append(s[start_obj : end_obj + 1])
        for c in candidates:
            try:
                return json.loads(c)
            except json.JSONDecodeError:
                continue
    return None


def _item_text(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for k in ("output", "translation", "text", "content"):
            v = item.get(k)
            if isinstance(v, str):
                return v.strip()
        return json.dumps(item, ensure_ascii=False)
    return str(item).strip()


def coerce_list(data: Any, n: int) -> list[str] | None:
    if data is None:
        return None
    if isinstance(data, dict):
        if "text" in data:
            inner = data["text"]
            if isinstance(inner, str):
                parsed = _loads_json(inner)
                if parsed is not None:
                    return coerce_list(parsed, n)
                if n == 1:
                    return [inner.strip()]
            else:
                return coerce_list(inner, n)
        if n == 1:
            t = _item_text(data)
            return [t] if t else None
        return None
    if isinstance(data, list):
        if len(data) == n:
            return [_item_text(x) for x in data]
        if len(data) == 1 and n != 1:
            return coerce_list(data[0], n)
        if (
            len(data) == 1
            and isinstance(data[0], str)
            and data[0].strip()[:1] in "[{"
        ):
            return coerce_list(_loads_json(data[0]), n)
    if isinstance(data, str):
        return coerce_list(_loads_json(data), n)
    return None


def parse_json_array(raw: str, n: int) -> list[str] | None:
    return coerce_list(_loads_json(raw), n) or coerce_list(raw, n)


def job_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "pdf-translate-cli"
    d.mkdir(parents=True, exist_ok=True)
    (d / "cwd").mkdir(parents=True, exist_ok=True)
    return d


def grok_cmd(prompt_path: Path, model: str, effort: str) -> list[str]:
    d = job_dir()
    return [
        which("grok"),
        "--prompt-file",
        str(prompt_path),
        "--verbatim",
        "--max-turns",
        "1",
        "--no-subagents",
        "--no-plan",
        "--no-alt-screen",
        "--no-auto-update",
        "--disable-web-search",
        "--output-format",
        "plain",
        "--permission-mode",
        "dontAsk",
        "--reasoning-effort",
        effort,
        "-m",
        model,
        "--cwd",
        str(d / "cwd"),
        "--leader-socket",
        str(d / f"leader-{uuid.uuid4().hex}.sock"),
        "--session-id",
        str(uuid.uuid4()),
        "--disallowed-tools",
        GROK_DISALLOWED,
    ]


def claude_cmd(model: str, effort: str) -> list[str]:
    # Do not use --bare: it ignores Claude Code OAuth and requires ANTHROPIC_API_KEY.
    cmd = [
        which("claude"),
        "-p",
        "--output-format",
        "text",
        "--input-format",
        "text",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--tools",
        "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--safe-mode",
        "--session-id",
        str(uuid.uuid4()),
    ]
    if effort:
        cmd.extend(["--effort", effort])
    if model:
        cmd.extend(["--model", model])
    return cmd


def run_cli(
    backend: str,
    prompt: str,
    model: str,
    effort: str,
    timeout: int,
    schema: dict | None,
) -> str:
    d = job_dir()
    env = os.environ.copy()
    env.pop("XAI_API_KEY", None)
    env.pop("GROK_CODE_XAI_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    prompt_path: Path | None = None
    stdin_data: str | None = None
    try:
        if backend == "grok":
            prompt_path = d / f"prompt-{uuid.uuid4().hex}.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            cmd = grok_cmd(prompt_path, model, effort)
        elif backend == "claude":
            # stdin avoids Windows CreateProcess argument-length limits on IL JSON.
            cmd = claude_cmd(model, effort)
            stdin_data = prompt
        else:
            raise RuntimeError(f"unknown backend {backend}")
        if schema is not None:
            cmd.extend(["--json-schema", json.dumps(schema, ensure_ascii=False)])
        result = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            cwd=str(d / "cwd"),
        )
    finally:
        if prompt_path is not None:
            prompt_path.unlink(missing_ok=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{backend} CLI failed ({result.returncode}): {err[:800]}")
    out = (result.stdout or "").strip()
    if not out:
        raise RuntimeError(f"{backend} CLI empty stdout: {(result.stderr or '')[:400]}")
    return out


def translate_prompt(lang_out: str, items: list[str]) -> str:
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
    return (
        "You are a professional academic translator (English → "
        f"{lang_out}).\n\n"
        f"Translate each numbered item. Return ONLY a JSON array of {len(items)} "
        'strings, same order, same length. Example: ["译文1","译文2"]. '
        "Do not return objects, keys, or markdown.\n"
        "Rules:\n"
        "- Translation only inside the JSON strings. No markdown, no notes.\n"
        "- Keep placeholders like {v1}, {{1}}, <style id='N'> unchanged.\n"
        '- Keep "et al." as "et al." with spaces.\n'
        "- Keep a space between a person name and an affiliation.\n"
        "- Keep Latin given-name + family-name spacing.\n"
        "- Keep model/system names, formula fragments, URLs, and arXiv ids unchanged.\n"
        "- If translation is unnecessary (proper nouns, codes), return the original.\n\n"
        "Items:\n"
        f"{numbered}\n"
    )


def other_prompt(items: list[str]) -> str:
    numbered = "\n\n".join(f"--- {i+1} ---\n{t}" for i, t in enumerate(items))
    return (
        f"Answer each independent prompt. Return ONLY a JSON array of {len(items)} "
        "strings (the answers), same order.\n\n"
        f"{numbered}\n"
    )


class Item:
    def __init__(self, prompt: str, kind: str):
        self.prompt = prompt
        self.kind = kind
        self.event = threading.Event()
        self.output: str | None = None
        self.error: str | None = None


class Batcher:
    def __init__(
        self,
        backend: str,
        model: str,
        effort: str,
        lang_out: str,
        batch_size: int,
        wait_s: float,
        max_chars: int,
        timeout: int,
        parallel: int,
    ):
        self.backend = backend
        self.model = model
        self.effort = effort
        self.lang_out = lang_out
        self.batch_size = batch_size
        self.wait_s = wait_s
        self.max_chars = max_chars
        self.timeout = timeout
        self.sema = threading.Semaphore(parallel)
        self.q: queue.Queue[Item | None] = queue.Queue()
        self.stop = threading.Event()
        self.stats = {"batches": 0, "items": 0, "fallbacks": 0}
        self.lock = threading.Lock()

    def submit(self, item: Item) -> None:
        self.q.put(item)

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                first = self.q.get(timeout=0.3)
            except queue.Empty:
                continue
            if first is None:
                return
            batch = [first]
            deadline = time.time() + self.wait_s
            while len(batch) < self.batch_size:
                timeout = deadline - time.time()
                if timeout <= 0:
                    break
                try:
                    nxt = self.q.get(timeout=timeout)
                except queue.Empty:
                    break
                if nxt is None:
                    self.q.put(None)
                    break
                batch.append(nxt)
            for kind in ("translate", "other", "il"):
                group = [it for it in batch if it.kind == kind]
                if kind != "translate":
                    for it in group:
                        threading.Thread(
                            target=self._run_chunk, args=([it],), daemon=True
                        ).start()
                else:
                    for chunk in self._chunks(group):
                        threading.Thread(
                            target=self._run_chunk, args=(chunk,), daemon=True
                        ).start()

    def _chunks(self, items: list[Item]) -> list[list[Item]]:
        out: list[list[Item]] = []
        cur: list[Item] = []
        chars = 0
        for it in items:
            n = len(it.prompt)
            if cur and (len(cur) >= self.batch_size or chars + n > self.max_chars):
                out.append(cur)
                cur, chars = [], 0
            cur.append(it)
            chars += n
        if cur:
            out.append(cur)
        return out

    def _run_chunk(self, items: list[Item]) -> None:
        with self.sema:
            try:
                texts = self._call(items)
                for it, text in zip(items, texts):
                    it.output = text
                    it.event.set()
            except Exception as e:
                log(f"batch failed ({len(items)} items): {e}")
                if len(items) == 1:
                    items[0].error = str(e)
                    items[0].event.set()
                    return
                with self.lock:
                    self.stats["fallbacks"] += len(items)
                for it in items:
                    try:
                        one = self._call([it])
                        it.output = one[0]
                    except Exception as e2:
                        it.error = str(e2)
                    it.event.set()

    def _call(self, items: list[Item]) -> list[str]:
        kind = items[0].kind
        payloads = [it.prompt for it in items]
        if len(items) == 1:
            if kind == "translate":
                prompt = (
                    "You are a professional academic translator (English → "
                    f"{self.lang_out}). Output the translation ONLY.\n"
                    'Keep "et al." with spaces. Keep a space between a person name '
                    "and an affiliation. Keep placeholders like {v1} unchanged.\n"
                    "Keep model and system names unchanged.\n\n"
                    f"{payloads[0]}"
                )
            elif kind == "il":
                prompt = payloads[0] + IL_EXTRA_RULES
            else:
                prompt = payloads[0]
            raw = self._once(prompt)
            if kind == "il":
                parsed = [POLISHER.il_json(raw)]
            elif kind == "translate":
                parsed = [POLISHER.text(raw.strip())]
            else:
                parsed = [raw.strip()]
            with self.lock:
                self.stats["batches"] += 1
                self.stats["items"] += 1
            log(f"batch kind={kind} n=1 chars={len(payloads[0])}")
            return parsed

        prompt = (
            translate_prompt(self.lang_out, payloads)
            if kind == "translate"
            else other_prompt(payloads)
        )
        schema = {
            "type": "array",
            "items": {"type": "string"},
            "minItems": len(items),
            "maxItems": len(items),
        }
        raw = self._once(prompt, schema)
        parsed = parse_json_array(raw, len(items))
        if parsed is None:
            log("schema parse failed, retry plain")
            try:
                raw = self._once(prompt)
                parsed = parse_json_array(raw, len(items))
            except RuntimeError as e:
                log(f"plain retry failed: {e}")
        if parsed is None:
            raise RuntimeError(
                f"could not parse JSON array of {len(items)}: {raw[:400]}"
            )
        if kind == "translate":
            parsed = [POLISHER.text(x) for x in parsed]
        with self.lock:
            self.stats["batches"] += 1
            self.stats["items"] += len(items)
        log(f"batch kind={kind} n={len(items)} chars={sum(len(p) for p in payloads)}")
        return parsed

    def _once(self, prompt: str, schema: dict | None = None) -> str:
        try:
            return run_cli(
                self.backend, prompt, self.model, self.effort, self.timeout, schema
            )
        except RuntimeError as e:
            if "max turns" not in str(e).lower():
                raise
            log("max turns reached, retrying once")
            return run_cli(
                self.backend, prompt, self.model, self.effort, self.timeout, schema
            )


class ProxyState:
    batcher: Batcher
    model: str
    backend: str


STATE = ProxyState()


def completion_payload(text: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        log(fmt % args)

    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/v1/health"):
            self._send(
                200,
                {
                    "ok": True,
                    "backend": f"{STATE.backend}-cli",
                    "stats": STATE.batcher.stats,
                },
            )
            return
        if path in ("/v1/models", "/models"):
            self._send(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": STATE.model,
                            "object": "model",
                            "owned_by": f"{STATE.backend}-cli",
                        }
                    ],
                },
            )
            return
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ("/v1/chat/completions", "/chat/completions"):
            self._send(404, {"error": {"message": f"no such route {path}"}})
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send(400, {"error": {"message": "invalid json"}})
            return
        messages = req.get("messages") or []
        content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                c = msg.get("content")
                if isinstance(c, str):
                    content = c
                elif isinstance(c, list):
                    content = "".join(
                        p.get("text", "") if isinstance(p, dict) else str(p) for p in c
                    )
                break
        if not content.strip():
            self._send(200, completion_payload("", STATE.model))
            return
        kind, payload = classify(content)
        item = Item(payload, kind)
        STATE.batcher.submit(item)
        if not item.event.wait(timeout=STATE.batcher.timeout + 30):
            self._send(504, {"error": {"message": "cli batch timed out"}})
            return
        if item.error:
            self._send(500, {"error": {"message": item.error}})
            return
        self._send(200, completion_payload(item.output or "", STATE.model))


def _split_csv(value: str) -> list[str]:
    return [p for p in (value or "").split(",") if p.strip()]


def main() -> int:
    global POLISHER
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument(
        "--port", type=int, default=int(os.environ.get("PDF_TRANSLATE_PROXY_PORT", "0"))
    )
    ap.add_argument(
        "--backend",
        default=os.environ.get("PDF_TRANSLATE_BACKEND", "grok"),
        choices=("grok", "claude"),
    )
    ap.add_argument("--model", default=os.environ.get("PDF_TRANSLATE_MODEL", ""))
    ap.add_argument(
        "--effort", default=os.environ.get("PDF_TRANSLATE_EFFORT", "low")
    )
    ap.add_argument(
        "--lang-out", default=os.environ.get("PDF_TRANSLATE_LANG_OUT", "zh-CN")
    )
    ap.add_argument(
        "--glossary",
        default=os.environ.get("PDF_TRANSLATE_GLOSSARIES", ""),
        help="comma-separated glossary CSV paths",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("PDF_TRANSLATE_BATCH_SIZE", "12")),
    )
    ap.add_argument(
        "--batch-wait",
        type=float,
        default=float(os.environ.get("PDF_TRANSLATE_BATCH_WAIT", "1.0")),
    )
    ap.add_argument(
        "--max-chars",
        type=int,
        default=int(os.environ.get("PDF_TRANSLATE_BATCH_MAX_CHARS", "12000")),
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("PDF_TRANSLATE_TIMEOUT", "180")),
    )
    ap.add_argument(
        "--parallel",
        type=int,
        default=int(os.environ.get("PDF_TRANSLATE_BATCH_PARALLEL", "2")),
    )
    args = ap.parse_args()
    if not args.model:
        args.model = "grok-4.6" if args.backend == "grok" else "sonnet"
    if args.port <= 0:
        args.port = 0

    POLISHER = Polisher(_split_csv(args.glossary))
    STATE.model = args.model
    STATE.backend = args.backend
    STATE.batcher = Batcher(
        backend=args.backend,
        model=args.model,
        effort=args.effort,
        lang_out=args.lang_out,
        batch_size=max(1, args.batch_size),
        wait_s=max(0.05, args.batch_wait),
        max_chars=max(2000, args.max_chars),
        timeout=args.timeout,
        parallel=max(1, args.parallel),
    )
    threading.Thread(target=STATE.batcher.run, daemon=True).start()
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    port = httpd.server_address[1]
    print(f"PORT={port}", flush=True)
    log(
        f"listening on http://{args.host}:{port}/v1  backend={args.backend} "
        f"model={args.model} batch={args.batch_size}"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    STATE.batcher.stop.set()
    STATE.batcher.q.put(None)
    httpd.server_close()
    log(f"stopped stats={STATE.batcher.stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
