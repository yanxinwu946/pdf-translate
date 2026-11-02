"""Original layout engine, translated by the current session through local files."""

import argparse
from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from file_translation import exchange


class TranslationServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, directory, language, timeout):
        self.directory = Path(directory)
        self.language = language
        self.timeout_seconds = timeout
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        self.send_json(200 if self.path == "/health" else 404, {"mode": "current-session"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": "Unknown route"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_000_000:
                raise ValueError("Request size out of bounds")
            request = json.loads(self.rfile.read(length))
            messages = request.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError("messages must be a nonempty list")
            output = exchange(self.server.directory, messages, self.server.language, self.server.timeout_seconds)
            self.send_json(200, {
                "id": f"local-{uuid.uuid4().hex}", "object": "chat.completion",
                "model": "current-session",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": output}, "finish_reason": "stop"}],
            })
        except TimeoutError as error:
            self.send_json(504, {"error": {"message": str(error)}})
        except (ValueError, AttributeError, OSError) as error:
            self.send_json(422, {"error": {"message": str(error)}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--job-dir", type=Path)
    parser.add_argument("--pages")
    parser.add_argument("--lang-in", default="en")
    parser.add_argument("--lang-out", default="zh-CN")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--no-dual", action="store_true")
    parser.add_argument("--no-mono", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=900)
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error("Input PDF does not exist")
    if args.wait_seconds <= 0:
        parser.error("--wait-seconds must be positive")
    executable = shutil.which("pdf2zh_next")
    if not executable:
        parser.error("pdf2zh_next not installed; run scripts/setup.sh")
    output = (args.output or args.input.parent / "output").resolve()
    output.mkdir(parents=True, exist_ok=True)
    directory = (args.job_dir or output / ".translation-job").resolve()
    if args.fresh:
        directory = directory / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / 'run-state.json'
    state = {'state': 'starting', 'pid': os.getpid(),
             'started_at': datetime.now(timezone.utc).isoformat(),
             'input': str(args.input.resolve()), 'scope': args.pages or 'full',
             'requested_outputs': [kind for kind, disabled in [('mono', args.no_mono), ('dual', args.no_dual)] if not disabled]}

    def write_state():
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(state_path)

    before = {str(p.resolve()): (p.stat().st_mtime_ns, p.stat().st_size) for p in output.glob('*.pdf')}
    write_state()
    server = TranslationServer(directory, args.lang_out, args.wait_seconds)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_address[1]
    command = [executable, str(args.input.resolve()), "--output", str(output),
               "--lang-in", args.lang_in, "--lang-out", args.lang_out,
               "--watermark-output-mode", "no_watermark", "--openai",
               "--openai-base-url", f"http://127.0.0.1:{port}/v1",
               "--openai-api-key", "local-session", "--openai-model", "current-session-v1",
               "--openai-timeout", str(args.wait_seconds + 30),
               "--no-auto-extract-glossary", "--pool-max-workers", "12"]
    if args.pages:
        command.extend(["--pages", args.pages])
    for enabled, flag in [(args.fresh, "--ignore-cache"), (args.no_dual, "--no-dual"), (args.no_mono, "--no-mono")]:
        if enabled:
            command.append(flag)
    environment = os.environ.copy()
    bypass = "localhost,127.0.0.1,::1"
    environment["NO_PROXY"] = environment["no_proxy"] = bypass + "," + environment.get("NO_PROXY", environment.get("no_proxy", ""))
    print(f"[session] queue: {directory}", flush=True)
    print("[session] Current chat must fill the queue while layout runs. No model process is launched.", flush=True)
    try:
        state['state'] = 'running'
        write_state()
        result = subprocess.call(command, env=environment)
        state.update(state='engine_succeeded' if result == 0 else 'engine_failed', engine_exit_code=result)
        return result
    except BaseException as error:
        state.update(state='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error))
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        state['new_or_modified_pdfs'] = [str(p.resolve()) for p in output.glob('*.pdf')
                                       if before.get(str(p.resolve())) != (p.stat().st_mtime_ns, p.stat().st_size)]
        write_state()


if __name__ == "__main__":
    raise SystemExit(main())
