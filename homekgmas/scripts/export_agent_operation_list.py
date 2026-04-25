#!/usr/bin/env python3
"""Export a flat per-agent operation list from any runtime catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.catalog import load_agent_catalog
from app.core.config import default_agent_catalog_path_for_mode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export flattened per-agent operations from one agent catalog.")
    parser.add_argument("--mode", default="fusion", choices=["fusion", "web", "generic"])
    parser.add_argument("--catalog", default="", help="Optional explicit catalog path. Defaults to the mode-specific catalog path.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path.")
    parser.add_argument("--output-md", default="", help="Optional output Markdown path.")
    return parser.parse_args()


def _default_output_json(mode: str) -> Path:
    return PROJECT_ROOT / "metadata" / f"{mode}_agent_operation_list.json"


def _default_output_md(mode: str) -> Path:
    return PROJECT_ROOT / "reports" / f"{mode}_agent_operation_list.md"


def main() -> int:
    args = parse_args()
    catalog_path = Path(args.catalog) if args.catalog else default_agent_catalog_path_for_mode(args.mode)
    catalog = load_agent_catalog(mode=args.mode, catalog_path=catalog_path)
    payload = {
        "mode": catalog.mode,
        "catalog_path": str(catalog_path) if catalog_path is not None else None,
        "operations": catalog.operation_listing(),
        "metadata": catalog.metadata,
    }

    output_json = Path(args.output_json) if args.output_json else _default_output_json(args.mode)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    output_md = Path(args.output_md) if args.output_md else _default_output_md(args.mode)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {args.mode.title()} Agent Operation List", ""]
    for agent_name, operations in payload["operations"].items():
        lines.append(f"## {agent_name}")
        lines.append("")
        for operation in operations:
            lines.append(f"- `{operation}`")
        lines.append("")
    output_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[agent-ops] wrote {output_json}")
    print(f"[agent-ops] wrote {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
