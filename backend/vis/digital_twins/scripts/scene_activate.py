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


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate a predefined sunroom scene.")
    parser.add_argument("--scene", required=True, help="scene id, e.g. presentation")
    parser.add_argument("--source", default="skill.sunroom-digital-twin-core")
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--trace-id", default=None)
    args = parser.parse_args()

    client = TwinHttpClient()
    result = client.activate_scene(args.scene, source=args.source, task_id=args.task_id, trace_id=args.trace_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

