#!/usr/bin/env python3
"""Query a generic BoardSpec part database JSON file.

``search`` prints a JSON array of part summaries; ``get`` prints the detailed
record with ``part_id`` injected. Prints an ``UNKNOWN_PART`` diagnostic and
exits non-zero when a part is not found.
"""

from __future__ import annotations

import argparse
import json
import sys

from _bspec import PartDB


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query a BoardSpec part database JSON file.")
    ap.add_argument("command", choices=["search", "get"])
    ap.add_argument("query", help="search text, or a part id for get")
    ap.add_argument("--db", required=True, help="path to a part database JSON file")
    ap.add_argument("--limit", type=int, default=None, help="max results for search")
    args = ap.parse_args(argv)

    db = PartDB()
    try:
        db.load(args.db)
    except (OSError, ValueError) as exc:
        json.dump(
            {
                "ok": False,
                "errors": [
                    {
                        "code": "LIBRARY_LOAD_FAILED",
                        "path": args.db,
                        "message": str(exc),
                    }
                ],
                "warnings": [],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    if args.command == "search":
        results = db.search(args.query, args.limit)
        json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    detail = db.detail(args.query)
    if detail is None:
        json.dump(
            {
                "ok": False,
                "errors": [
                    {
                        "code": "UNKNOWN_PART",
                        "path": args.query,
                        "message": f"part '{args.query}' not found",
                    }
                ],
                "warnings": [],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    json.dump(detail, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
