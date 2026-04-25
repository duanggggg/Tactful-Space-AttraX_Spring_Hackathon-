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
    parser = argparse.ArgumentParser(description="Read digital twin layout, devices, or a single device.")
    parser.add_argument("--device", default=None, help="optional device id")
    parser.add_argument("--layout", action="store_true", help="include layout")
    args = parser.parse_args()

    client = TwinHttpClient()
    payload = {}
    if args.layout:
        payload["layout"] = client.layout()
    if args.device:
        payload["device"] = client.device(args.device)
    else:
        payload["devices"] = client.devices()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

