#!/usr/bin/env python3
"""No-network checks for proxy helpers. Run: python scripts/selftest.py"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli_openai_proxy import (  # noqa: E402
    Polisher,
    cjk_latin_space,
    classify,
    parse_json_array,
)


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"ok: {msg}")


def main() -> int:
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
