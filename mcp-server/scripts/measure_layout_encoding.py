#!/usr/bin/env python3
"""Measure raw and compact layout JSON without imposing an acceptance ratio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def compact_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def metrics(value, encoder=None) -> dict:
    payload = compact_json(value)
    return {
        "characters": len(payload),
        "utf8_bytes": len(payload.encode("utf-8")),
        "tokens": len(encoder.encode(payload)) if encoder else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path, help="captured raw EasyEDA layout JSON")
    parser.add_argument("compact", type=Path, help="corresponding compact MCP JSON")
    parser.add_argument("--encoding", default="o200k_base")
    args = parser.parse_args()

    try:
        import tiktoken

        encoder = tiktoken.get_encoding(args.encoding)
        tokenizer = args.encoding
    except ImportError:
        encoder = None
        tokenizer = None

    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    compact = json.loads(args.compact.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "tokenizer": tokenizer,
                "raw": metrics(raw, encoder),
                "compact": metrics(compact, encoder),
                "ratio_gate": None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
