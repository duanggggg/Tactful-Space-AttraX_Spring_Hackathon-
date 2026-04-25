#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT = Path(__file__).resolve()
SHARED = CURRENT.parent / "_shared"
sys.path.insert(0, SHARED.as_posix())

from twin_http import TwinHttpClient  # noqa: E402


def parse_params(raw: str) -> dict:
    if not raw:
        return {}
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a command to a sunroom digital twin device.")
    parser.add_argument("--device", required=True, help="device id, e.g. light.perimeter")
    parser.add_argument("--action", required=True, help="action name, e.g. set_brightness")
    parser.add_argument("--params", default="{}", help='JSON params, e.g. {"brightness":70}')
    parser.add_argument("--source", default="skill.sunroom-digital-twin-core")
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--trace-id", default=None)
    args = parser.parse_args()

    client = TwinHttpClient()
    result = client.command(
        args.device,
        args.action,
        parse_params(args.params),
        source=args.source,
        task_id=args.task_id,
        trace_id=args.trace_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

