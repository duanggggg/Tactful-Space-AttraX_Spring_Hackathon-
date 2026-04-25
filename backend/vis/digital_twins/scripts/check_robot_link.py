#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


CURRENT = Path(__file__).resolve()
SCRIPTS_DIR = CURRENT.parent
SHARED_DIR = SCRIPTS_DIR / "_shared"
BACKEND_DIR = CURRENT.parents[3]

sys.path.insert(0, SHARED_DIR.as_posix())
sys.path.insert(0, BACKEND_DIR.as_posix())

from twin_http import TwinHttpClient, TwinHttpError  # noqa: E402
from agent.twin_bridge import TwinEventBridge  # noqa: E402


DEFAULT_AGENT_BASE_URL = "http://127.0.0.1:8003"


def agent_get_json(base_url: str, path: str) -> Any:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url=url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach {url}: {exc}") from exc
    return json.loads(raw) if raw else None


def wait_until(check: Callable[[], bool], *, timeout_s: float = 5.0, interval_s: float = 0.25) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if check():
            return True
        time.sleep(interval_s)
    return False


def find_agent_status(items: list[dict[str, Any]], agent_id: int) -> str | None:
    for item in items:
        if int(item.get("id", -1)) == int(agent_id):
            return str(item.get("status"))
    return None


def print_step(title: str, payload: Any) -> None:
    print(f"[{title}]")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the agent backend is linked to the digital twin backend.")
    parser.add_argument("--agent-base-url", default=os.getenv("SUNROOM_AGENT_BASE_URL", DEFAULT_AGENT_BASE_URL), help="agent backend base url")
    parser.add_argument("--twin-base-url", default=os.getenv("SUNROOM_TWIN_BASE_URL", "http://127.0.0.1:8787"), help="digital twin base url")
    parser.add_argument("--check-agent-id", type=int, default=1, help="which visualized agent id to toggle during the check")
    parser.add_argument("--timeout", type=float, default=6.0, help="wait timeout in seconds for event/state propagation")
    args = parser.parse_args()

    os.environ["SUNROOM_TWIN_BASE_URL"] = args.twin_base_url
    os.environ["DIGITAL_TWIN_BRIDGE_BASE_URL"] = args.twin_base_url

    twin = TwinHttpClient()
    bridge = TwinEventBridge()
    marker = f"robot-link-check-{int(time.time())}"

    try:
        agent_health = agent_get_json(args.agent_base_url, "/api/agent/health")
        print_step("agent_health", agent_health)

        twin_health = twin.health()
        print_step("twin_health", twin_health)

        before_statuses = twin.agent_statuses()
        print_step("agent_status_before", before_statuses)

        publish_ok = bridge.publish(
            event_type="robot.link_check",
            status="running",
            message=marker,
            task_id=marker,
            trace_id=marker,
            payload={"source": "check_robot_link"},
        )
        if not publish_ok:
            raise RuntimeError("TwinEventBridge.publish returned False")

        seen_event = wait_until(
            lambda: any(
                event.get("message") == marker
                for event in (twin.recent_events().get("items") or [])
            ),
            timeout_s=args.timeout,
        )
        if not seen_event:
            raise RuntimeError("bridge publish succeeded locally, but the marker event did not appear in recent events")

        assign_ok = bridge.assign_agents(
            agent_ids=[args.check_agent_id],
            status="work",
            duration_seconds=0,
            source="robot_link_check",
            task_id=marker,
            trace_id=marker,
        )
        if not assign_ok:
            raise RuntimeError("TwinEventBridge.assign_agents returned False")

        status_changed = wait_until(
            lambda: find_agent_status(twin.agent_statuses(), args.check_agent_id) == "work",
            timeout_s=args.timeout,
        )
        if not status_changed:
            raise RuntimeError(f"agent {args.check_agent_id} did not switch to work after bridge assignment")

        after_assign = twin.agent_statuses()
        print_step("agent_status_after_assign", after_assign)

        reset_payload = twin.assign_agents(
            [args.check_agent_id],
            "rest",
            duration_seconds=0,
            source="robot_link_check_reset",
            task_id=marker,
            trace_id=marker,
        )
        print_step("reset_result", reset_payload)

        reset_ok = wait_until(
            lambda: find_agent_status(twin.agent_statuses(), args.check_agent_id) == "rest",
            timeout_s=args.timeout,
        )
        if not reset_ok:
            raise RuntimeError(f"agent {args.check_agent_id} did not switch back to rest during cleanup")

        final_statuses = twin.agent_statuses()
        print_step(
            "summary",
            {
                "ok": True,
                "bridge_enabled": bridge.enabled,
                "bridge_base_url": bridge.base_url,
                "agent_backend": args.agent_base_url,
                "twin_backend": args.twin_base_url,
                "checked_agent_id": args.check_agent_id,
                "final_statuses": final_statuses,
                "note": "If agent_health.config.has_api_key is false, the bridge is connected but the real LLM reply path is still not fully available.",
            },
        )
        return 0
    except (RuntimeError, TwinHttpError) as exc:
        print_step(
            "summary",
            {
                "ok": False,
                "bridge_enabled": bridge.enabled,
                "bridge_base_url": bridge.base_url,
                "agent_backend": args.agent_base_url,
                "twin_backend": args.twin_base_url,
                "checked_agent_id": args.check_agent_id,
                "error": str(exc),
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
