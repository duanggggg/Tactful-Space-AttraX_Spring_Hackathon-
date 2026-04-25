"""
Best-effort bridge for forwarding main chat events to the digital twin backend.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TWIN_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_TWIN_AGENT_ID = "openclaw-main"


class TwinEventBridge:
    def __init__(self) -> None:
        self.enabled = os.getenv("DIGITAL_TWIN_BRIDGE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
        self.base_url = os.getenv("DIGITAL_TWIN_BRIDGE_BASE_URL", DEFAULT_TWIN_BASE_URL).rstrip("/")
        self.agent_id = os.getenv("DIGITAL_TWIN_BRIDGE_AGENT_ID", DEFAULT_TWIN_AGENT_ID).strip() or DEFAULT_TWIN_AGENT_ID
        self.timeout_s = float(os.getenv("DIGITAL_TWIN_BRIDGE_TIMEOUT", "2.5"))

    def publish(
        self,
        *,
        event_type: str,
        status: str,
        message: str,
        zone: str = "chat",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not self.enabled:
            return False

        body = {
            "type": event_type,
            "zone": zone,
            "status": status,
            "message": message,
            "agent_id": self.agent_id,
            "task_id": task_id,
            "trace_id": trace_id,
            "payload": payload or {},
        }
        url = f"{self.base_url}/api/v1/office-ui/events"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        context = ssl.create_default_context() if url.startswith("https://") else None

        try:
            with urllib.request.urlopen(request, context=context, timeout=self.timeout_s) as response:
                response.read()
            return True
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.warning("Digital twin bridge HTTP %s for %s: %s", exc.code, event_type, error_body)
        except urllib.error.URLError as exc:
            logger.info("Digital twin bridge skipped for %s: %s", event_type, exc.reason)
        except Exception as exc:
            logger.warning("Digital twin bridge failed for %s: %s", event_type, exc)
        return False

    def assign_agents(
        self,
        *,
        agent_ids: list[int],
        duration_seconds: int = 0,
        status: str = "work",
        source: str = "main_chat",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> bool:
        if not self.enabled or not agent_ids:
            return False

        body = {
            "agent_ids": agent_ids,
            "status": status,
            "duration_seconds": duration_seconds,
            "source": source,
            "task_id": task_id,
            "trace_id": trace_id,
        }
        url = f"{self.base_url}/api/v1/agents/assign"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        context = ssl.create_default_context() if url.startswith("https://") else None

        try:
            with urllib.request.urlopen(request, context=context, timeout=self.timeout_s) as response:
                response.read()
            return True
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.warning("Digital twin agent assignment HTTP %s: %s", exc.code, error_body)
        except urllib.error.URLError as exc:
            logger.info("Digital twin agent assignment skipped: %s", exc.reason)
        except Exception as exc:
            logger.warning("Digital twin agent assignment failed: %s", exc)
        return False


twin_event_bridge = TwinEventBridge()
