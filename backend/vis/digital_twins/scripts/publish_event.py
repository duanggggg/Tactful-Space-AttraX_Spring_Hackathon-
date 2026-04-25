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
    parser = argparse.ArgumentParser(description="Publish an office_ui event through the digital twin bridge.")
    parser.add_argument("--type", required=True, help="event type, e.g. avatar.say")
    parser.add_argument("--zone", required=True, help="zone id, e.g. execution")
    parser.add_argument("--status", required=True, help="status, e.g. executing")
    parser.add_argument("--message", required=True, help="speech bubble or event text")
    parser.add_argument("--agent-id", default="openclaw-main")
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--payload", default="{}", help="extra JSON payload")
    args = parser.parse_args()

    payload = json.loads(args.payload)
    payload.update(
        {
            "type": args.type,
            "zone": args.zone,
            "status": args.status,
            "message": args.message,
            "agent_id": args.agent_id,
        }
    )
    if args.task_id:
        payload["task_id"] = args.task_id
    if args.trace_id:
        payload["trace_id"] = args.trace_id

    client = TwinHttpClient()
    result = client.office_event(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

