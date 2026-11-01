#!/usr/bin/env python3
"""No-network checks for proxy helpers. Run: python scripts/selftest.py"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_openai_proxy import (  # noqa: E402
    Polisher,
    Batcher,
    Item,
    cjk_latin_space,
    classify,
    codex_cmd,
    parse_json_array,
    run_cli,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"ok: {msg}")


def main() -> int:
    with patch.dict(os.environ, {"PDF_TRANSLATE_COMMAND_JSON": json.dumps([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"])}, clear=False):
        check(run_cli("command", "hello", "command-default", "low", 10, None) == "HELLO", "generic harness stdin/stdout integration")
    with patch.dict(os.environ, {"PDF_TRANSLATE_COMMAND_JSON": '"not an argv array"'}, clear=False):
        try:
            run_cli("command", "hello", "", "", 10, None)
        except RuntimeError:
            check(True, "malformed custom command rejected")
        else:
            check(False, "malformed custom command rejected")

    batcher = Batcher("codex", "codex-default", "low", "zh-CN", 12, 1, 48000, 180, 4)
    formula = Item("{v1} + 24 = 48", "translate")
    batcher.submit(formula)
    check(formula.event.is_set() and formula.output == formula.prompt and batcher.q.empty(), "formula bypasses model")
    prose = Item("Compute 24", "translate")
    batcher.submit(prose)
    check(not prose.event.is_set(), "English prose is not skipped")
    outputs = ['[{"id":1,"output":"第一段"}]', '[{"id":2,"output":"第二段"}]']
    with patch.object(batcher, "_once", return_value=json.dumps(outputs)) as call:
        result = batcher._call([Item('## Structure Rules first', 'il'), Item('## Structure Rules second', 'il')])
        check(len(result) == 2 and "第一段" in result[0] and "第二段" in result[1], "IL batching preserves independent JSON responses")
        check(call.call_count == 1 and call.call_args.args[1] is None, "Codex IL batch uses one call without unsupported array schema")

    with patch("cli_openai_proxy.which", return_value="codex"):
        cmd = codex_cmd("codex-default", "low", Path("result.txt"))
        check("--model" not in cmd, "Codex inherits configured model")
        check(cmd[-1] == "-" and "--ephemeral" in cmd, "Codex stdin and ephemeral session")
        check(cmd[cmd.index("--sandbox") + 1] == "read-only", "Codex read-only sandbox")
        cmd = codex_cmd("requested-model", "low", Path("result.txt"))
        check(cmd[cmd.index("--model") + 1] == "requested-model", "Codex explicit model")

        def fake_run(command, **kwargs):
            check(kwargs["input"] == "test prompt", "Codex prompt passed through stdin")
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text("translated text", encoding="utf-8")
            if "--output-schema" in command:
                schema_file = Path(command[command.index("--output-schema") + 1])
                check(schema_file.is_file(), "Codex schema passed as file")
            return SimpleNamespace(returncode=0, stdout="CLI logs", stderr="")

        with patch("cli_openai_proxy.subprocess.run", side_effect=fake_run):
            result = run_cli("codex", "test prompt", "codex-default", "low", 10, {"type": "object"})
            check(result == "translated text", "Codex returns final message, not logs")

    check("et al." in cjk_latin_space("etal."), "etal. spacing")
    check(cjk_latin_space("用VLM做") == "用 VLM 做", "CJK-Latin spacing")
    check(cjk_latin_space("{v1}VLM") == "{v1}VLM", "placeholder left alone")

    kind, payload = classify(
        "You are a machine translation engine.\n\nInput:\n\nHello"
    )
    check(kind == "translate" and payload.strip() == "Hello", "classify translate")
    kind, _ = classify('## Structure Rules\n[{"layout_label":"text","id":1}]')
    check(kind == "il", "classify il")
    kind, _ = classify("summarize this paragraph")
    check(kind == "other", "classify other")

    wrapped = '{"text": "[\\"alpha\\", \\"beta\\"]"}'
    parsed = parse_json_array(wrapped, 2)
    check(parsed == ["alpha", "beta"], f"coerce wrapped text JSON, got {parsed}")

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "g.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["source", "target", "tgt_lng"])
            w.writeheader()
            w.writerow(
                {"source": "Yang Xiang", "target": "Yang Xiang", "tgt_lng": "zh-CN"}
            )
            w.writerow({"source": "张三", "target": "张三", "tgt_lng": "zh-CN"})
            w.writerow(
                {"source": "Tsinghua University", "target": "清华大学", "tgt_lng": "zh-CN"}
            )
        p = Polisher([str(csv_path)])
        check(p.text("YangXiang") == "Yang Xiang", "Latin name unglue")
        check(p.text("张三清华大学") == "张三 清华大学", "CJK name + org unglue")
        il = p.il_json('[{"id":1,"output":"YangXiang at 张三清华大学"}]')
        check("Yang Xiang" in il and "张三 清华大学" in il, f"IL polish, got {il}")

    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
