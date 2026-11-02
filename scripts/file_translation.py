"""Local, resumable translation handoff; never launches a model or calls an API."""

import hashlib
import json
import time
import uuid
from pathlib import Path


def exchange(directory, messages, language, timeout=600):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    request = {"language": language, "messages": messages}
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    pending = root / f"{key}.request.json"
    answer = root / f"{key}.response.json"
    if not pending.exists():
        temporary = root / f"{key}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(pending)
    deadline = time.monotonic() + timeout
    while True:
        if answer.exists():
            response = json.loads(answer.read_text(encoding="utf-8"))
            if not isinstance(response, dict) or not isinstance(response.get("text"), str) or not response["text"].strip():
                raise ValueError(f"Invalid translation response: {answer}")
            return response["text"]
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Awaiting current-agent translation: {pending}")
        time.sleep(0.25)
