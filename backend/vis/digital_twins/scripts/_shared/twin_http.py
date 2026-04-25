#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = "http://127.0.0.1:8787"


class TwinHttpError(RuntimeError):
    pass


def _base_url() -> str:
    return os.getenv("SUNROOM_TWIN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = os.getenv("SUNROOM_TWIN_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = _base_url() + path
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers=_headers(), method=method.upper())
    context = None
    if url.startswith("https://"):
        context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=context, timeout=15) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise TwinHttpError(f"HTTP {exc.code} calling {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise TwinHttpError(f"Failed to reach {url}: {exc}") from exc


class TwinHttpClient:
    def health(self) -> Dict[str, Any]:
        return _request("GET", "/api/v1/health")

    def layout(self) -> Dict[str, Any]:
        return _request("GET", "/api/v1/layout")

    def devices(self) -> Dict[str, Any]:
        return _request("GET", "/api/v1/devices")

    def device(self, device_id: str) -> Dict[str, Any]:
        device_id = urllib.parse.quote(device_id, safe="")
        return _request("GET", f"/api/v1/devices/{device_id}")

    def command(
        self,
        device_id: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        source: str = "skill",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        device_id = urllib.parse.quote(device_id, safe="")
        payload: Dict[str, Any] = {"action": action, "params": params or {}, "source": source}
        if task_id:
            payload["task_id"] = task_id
        if trace_id:
            payload["trace_id"] = trace_id
        return _request("POST", f"/api/v1/devices/{device_id}/commands", payload)

    def scenes(self) -> Dict[str, Any]:
        return _request("GET", "/api/v1/scenes")

    def activate_scene(
        self,
        scene: str,
        *,
        source: str = "skill",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"scene": scene, "source": source}
        if task_id:
            payload["task_id"] = task_id
        if trace_id:
            payload["trace_id"] = trace_id
        return _request("POST", "/api/v1/scenes/activate", payload)

    def telemetry(self) -> Dict[str, Any]:
        return _request("GET", "/api/v1/telemetry")

    def agent_statuses(self) -> Any:
        return _request("GET", "/api/v1/agents/status")

    def assign_agents(
        self,
        agent_ids: list[int],
        status: str,
        *,
        duration_seconds: int = 0,
        source: str = "skill",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "agent_ids": agent_ids,
            "status": status,
            "duration_seconds": duration_seconds,
            "source": source,
        }
        if task_id:
            payload["task_id"] = task_id
        if trace_id:
            payload["trace_id"] = trace_id
        return _request("POST", "/api/v1/agents/assign", payload)

    def recent_events(self) -> Dict[str, Any]:
        return _request("GET", "/api/v1/events/recent")

    def office_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _request("POST", "/api/v1/office-ui/events", payload)
