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
    parser = argparse.ArgumentParser(description="Fetch the latest telemetry and recent events.")
    parser.add_argument("--events", action="store_true", help="also include recent events")
    args = parser.parse_args()

    client = TwinHttpClient()
    payload = {"telemetry": client.telemetry()}
    if args.events:
        payload["recent_events"] = client.recent_events()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

