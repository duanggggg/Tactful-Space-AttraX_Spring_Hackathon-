#!/usr/bin/env python3
"""Scan the unified warehouse and build a fusion-dataset agent/action catalog."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.catalog import default_agent_catalog


DOMAIN_TO_AGENT = {
    "climate": "cooling_agent",
    "light": "lighting_agent",
    "media_player": "music_agent",
    "fan": "fan_agent",
    "cover": "cover_agent",
    "lock": "lock_agent",
    "switch": "switch_agent",
    "other": "switch_agent",
    "appliance": "appliance_agent",
    "vacuum": "appliance_agent",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a fusion-dataset agent catalog from processed warehouse tables.")
    parser.add_argument("--action-items", default=str(PROJECT_ROOT / "data_processed" / "fact_action_item.parquet"))
    parser.add_argument("--tasks", default=str(PROJECT_ROOT / "data_processed" / "fact_task.parquet"))
    parser.add_argument("--output", default=str(PROJECT_ROOT / "metadata" / "fusion_agent_catalog.json"))
    return parser.parse_args()


def _parse_json_like(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def main() -> int:
    args = parse_args()
    action_items = pd.read_parquet(Path(args.action_items))
    tasks = pd.read_parquet(Path(args.tasks), columns=["source_dataset", "task_source"])

    catalog = default_agent_catalog(mode="fusion")
    profile_stats = {
        agent_name: {
            "source_datasets": Counter(),
            "task_sources": Counter(),
            "device_domains": Counter(),
            "service_names": Counter(),
            "argument_keys": Counter(),
        }
        for agent_name in catalog.profiles
    }
    unmapped_domains = Counter()

    for row in action_items.itertuples(index=False):
        device_domain = str(getattr(row, "device_domain", "") or "other")
        agent_name = DOMAIN_TO_AGENT.get(device_domain)
        if agent_name is None or agent_name not in profile_stats:
            unmapped_domains[device_domain] += 1
            continue

        stats = profile_stats[agent_name]
        stats["source_datasets"][str(getattr(row, "source_dataset", "") or "unknown")] += 1
        stats["device_domains"][device_domain] += 1
        stats["service_names"][str(getattr(row, "service_name_norm", "") or "custom")] += 1
        for key in _parse_json_like(getattr(row, "arguments_json", None)).keys():
            stats["argument_keys"][str(key)] += 1

    task_counts = tasks.groupby(["source_dataset", "task_source"]).size()
    for (source_dataset, task_source), count in task_counts.items():
        for profile in catalog.profiles.values():
            if source_dataset in profile.source_datasets or not profile.source_datasets:
                profile_stats[profile.agent_name]["task_sources"][str(task_source)] += int(count)

    output_profiles = {}
    for agent_name, profile in catalog.profiles.items():
        stats = profile_stats[agent_name]
        output_profiles[agent_name] = {
            **profile.model_dump(mode="json"),
            "source_datasets": [name for name, _ in stats["source_datasets"].most_common()][:8] or profile.source_datasets,
            "task_sources": [name for name, _ in stats["task_sources"].most_common()][:8] or profile.task_sources,
            "device_domains": [name for name, _ in stats["device_domains"].most_common()][:8] or profile.device_domains,
            "service_names": [name for name, _ in stats["service_names"].most_common()][:12] or profile.service_names,
            "argument_keys": [name for name, _ in stats["argument_keys"].most_common()][:16] or profile.argument_keys,
            "stats": {
                "source_datasets": dict(stats["source_datasets"].most_common()),
                "task_sources": dict(stats["task_sources"].most_common()),
                "device_domains": dict(stats["device_domains"].most_common()),
                "service_names": dict(stats["service_names"].most_common()),
                "argument_keys": dict(stats["argument_keys"].most_common()),
            },
        }

    payload = {
        "mode": "fusion",
        "profiles": output_profiles,
        "metadata": {
            "generated_from": {
                "action_items": str(Path(args.action_items)),
                "tasks": str(Path(args.tasks)),
            },
            "unmapped_domains": dict(unmapped_domains.most_common()),
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fusion-agent-catalog] wrote {output_path}")
    print(json.dumps(payload["metadata"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
