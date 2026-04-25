#!/usr/bin/env python3
"""Export a flat per-agent operation list from the fusion catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.catalog import load_agent_catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export flattened per-agent operations from the fusion catalog.")
    parser.add_argument("--catalog", default=str(PROJECT_ROOT / "metadata" / "fusion_agent_catalog.json"))
    parser.add_argument("--output-json", default=str(PROJECT_ROOT / "metadata" / "fusion_agent_operation_list.json"))
    parser.add_argument("--output-md", default=str(PROJECT_ROOT / "reports" / "fusion_agent_operation_list.md"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = load_agent_catalog(mode="fusion", catalog_path=Path(args.catalog))
    payload = {
        "mode": catalog.mode,
        "operations": catalog.operation_listing(),
        "metadata": catalog.metadata,
    }

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Fusion Agent Operation List", ""]
    for agent_name, operations in payload["operations"].items():
        lines.append(f"## {agent_name}")
        lines.append("")
        for operation in operations:
            lines.append(f"- `{operation}`")
        lines.append("")
    output_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[fusion-ops] wrote {output_json}")
    print(f"[fusion-ops] wrote {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
