# -*- coding: utf-8 -*-
"""
设备场景识别 LLM 后端服务。

职责：
1. 接收 MCP 侧转发的文本。
2. 只要对话涉及房屋内电脑、灯光、空调功能，就进入 MCP + LLM 判定链路。
3. 输出完整的设备执行方案，并把方案同步到 digital twins 的设备状态和 agent 状态。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("DeviceLLMServer")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "d6ebb6fabb7e111df8b7f7325ce9f522226e5d2c50f2a26a2153de5f02f1b9f8")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://127.0.0.1:48760/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
DEVICE_LLM_SERVER_HOST = os.getenv("DEVICE_LLM_SERVER_HOST", "127.0.0.1")
DEVICE_LLM_SERVER_PORT = int(os.getenv("DEVICE_LLM_SERVER_PORT", "12345"))

DIGITAL_TWIN_BASE_URL = os.getenv("DIGITAL_TWIN_BASE_URL", "http://127.0.0.1:8787").rstrip("/")
DIGITAL_TWIN_TIMEOUT = float(os.getenv("DIGITAL_TWIN_TIMEOUT", "2.5"))
DIGITAL_TWIN_SYNC_ENABLED = os.getenv("DIGITAL_TWIN_SYNC_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

DEVICE_ORDER = ["computer", "light", "ac"]

DEVICE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "computer": {
        "label": "电脑",
        "agent_id": 3,
        "digital_twin_devices": ["screen.main"],
        "keywords": [
            "电脑",
            "计算机",
            "主机",
            "屏幕",
            "显示器",
            "显示屏",
            "投屏",
            "投到屏幕",
            "演示",
            "汇报",
            "会议屏",
            "桌面",
            "monitor",
            "screen",
            "display",
            "computer",
            "pc",
            "laptop",
        ],
    },
    "light": {
        "label": "灯光",
        "agent_id": 2,
        "digital_twin_devices": ["light.perimeter", "light.entry"],
        "keywords": [
            "灯",
            "灯光",
            "照明",
            "开灯",
            "关灯",
            "亮度",
            "调亮",
            "调暗",
            "太暗",
            "明亮",
            "柔光",
            "night light",
            "light",
            "lamp",
            "lighting",
            "bright",
        ],
    },
    "ac": {
        "label": "空调",
        "agent_id": 1,
        "digital_twin_devices": ["ac.main"],
        "keywords": [
            "空调",
            "冷气",
            "制冷",
            "制热",
            "降温",
            "升温",
            "调温",
            "温度",
            "太热",
            "太冷",
            "凉快",
            "暖和",
            "air conditioner",
            "ac",
            "cooling",
            "heating",
            "temperature",
        ],
    },
}

ON_WORDS = ["打开", "开启", "启动", "唤醒", "使用", "打开一下", "开一下"]
OFF_WORDS = ["关闭", "关掉", "关上", "停止", "断开", "关机", "息屏", "熄屏"]
STATUS_WORDS = ["状态", "看看", "查看", "查询", "有没有", "是否", "在不在", "多少度"]

app = FastAPI(title="设备场景识别服务", version="1.2.0")


class ClassificationRequest(BaseModel):
    input: str


class AppliancePlanModel(BaseModel):
    appliance: str
    label: str
    mentioned: bool
    execute: bool
    intent: str
    summary: str
    device_targets: List[str] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    agent_update: Optional[Dict[str, Any]] = None


class ClassificationResponse(BaseModel):
    success: bool
    devices: List[str]
    analysis: Optional[str] = None
    keyword_match: Optional[List[str]] = None
    plans: List[AppliancePlanModel] = Field(default_factory=list)
    digital_twin: Dict[str, Any] = Field(default_factory=dict)


class DeepHealthResponse(BaseModel):
    status: str
    service: str
    port: int
    llm_api: str
    model: str
    digital_twin_base_url: str
    digital_twin_sync_enabled: bool
    checks: Dict[str, Any]


def contains_any(text: str, keywords: List[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def extract_temperature(text: str) -> Optional[int]:
    match = re.search(r"(\d{2})(?:\s*[度℃])", text)
    if not match:
        return None
    value = int(match.group(1))
    return max(16, min(30, value))


def extract_brightness(text: str) -> Optional[int]:
    match = re.search(r"(\d{1,3})\s*%", text)
    if not match:
        return None
    value = int(match.group(1))
    return max(0, min(100, value))


def normalize_intent(appliance: str, intent: Optional[str]) -> str:
    if not intent:
        return "none"

    value = str(intent).strip().lower()

    mapping: Dict[str, Dict[str, str]] = {
        "computer": {
            "on": "power_on",
            "open": "power_on",
            "turn_on": "power_on",
            "poweron": "power_on",
            "wake": "power_on",
            "off": "power_off",
            "turn_off": "power_off",
            "shutdown": "power_off",
            "presentation": "presentation",
            "meeting": "presentation",
            "display": "presentation",
            "screen": "presentation",
            "focus": "focus",
            "status": "status",
            "query": "status",
        },
        "light": {
            "on": "on",
            "open": "on",
            "turn_on": "on",
            "bright": "brighten",
            "brighter": "brighten",
            "brighten": "brighten",
            "dim": "dim",
            "dark": "dim",
            "off": "off",
            "turn_off": "off",
            "status": "status",
            "query": "status",
        },
        "ac": {
            "on": "power_on",
            "open": "power_on",
            "turn_on": "power_on",
            "off": "power_off",
            "turn_off": "power_off",
            "shutdown": "power_off",
            "cool": "cool",
            "cooling": "cool",
            "cold": "cool",
            "heat": "heat",
            "heating": "heat",
            "warm": "heat",
            "set_temp": "set_temp",
            "temperature": "set_temp",
            "status": "status",
            "query": "status",
        },
    }

    return mapping.get(appliance, {}).get(value, value if value != appliance else "none")


def normalize_llm_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload or {}
    reason = str(payload.get("reason", "") or "").strip()
    should_trigger_mcp = bool(payload.get("should_trigger_mcp", False))
    appliances = payload.get("appliances")

    if not isinstance(appliances, dict):
        appliances = {}

    legacy_mapping = {
        "computer": bool(payload.get("computer_active") or payload.get("screen_active") or payload.get("display_active")),
        "light": bool(payload.get("light_active")),
        "ac": bool(payload.get("ac_active")),
    }

    normalized: Dict[str, Dict[str, Any]] = {}
    for appliance in DEVICE_ORDER:
        raw = appliances.get(appliance, {})
        if not isinstance(raw, dict):
            raw = {}

        mentioned = bool(raw.get("mentioned", raw.get("active", False))) or legacy_mapping[appliance]
        execute = raw.get("execute")
        if execute is None:
            execute = mentioned

        normalized[appliance] = {
            "mentioned": bool(mentioned),
            "execute": bool(execute),
            "intent": normalize_intent(appliance, raw.get("intent")),
            "summary": str(raw.get("summary", "") or "").strip(),
        }

    if not should_trigger_mcp:
        should_trigger_mcp = any(item["mentioned"] for item in normalized.values())

    return {
        "should_trigger_mcp": should_trigger_mcp,
        "reason": reason,
        "appliances": normalized,
    }


def keyword_plan_for_computer(text: str) -> Optional[Dict[str, Any]]:
    if not contains_any(text, DEVICE_DEFINITIONS["computer"]["keywords"]):
        return None

    if contains_any(text, STATUS_WORDS):
        intent = "status"
        execute = False
        summary = "用户在询问房屋内电脑/屏幕的状态。"
    elif contains_any(text, OFF_WORDS):
        intent = "power_off"
        execute = True
        summary = "用户要求关闭房屋内电脑或显示屏。"
    elif contains_any(text, ["汇报", "演示", "展示", "投屏", "ppt", "会议", "开会"]):
        intent = "presentation"
        execute = True
        summary = "用户要求让房屋内电脑进入汇报/展示模式。"
    elif contains_any(text, ["专注", "工作", "办公", "focus"]):
        intent = "focus"
        execute = True
        summary = "用户要求让房屋内电脑进入专注工作模式。"
    else:
        intent = "power_on"
        execute = True
        summary = "用户要求打开或启用房屋内电脑。"

    return {"appliance": "computer", "mentioned": True, "execute": execute, "intent": intent, "summary": summary}


def keyword_plan_for_light(text: str) -> Optional[Dict[str, Any]]:
    if not contains_any(text, DEVICE_DEFINITIONS["light"]["keywords"]):
        return None

    brightness = extract_brightness(text)
    if contains_any(text, STATUS_WORDS):
        intent = "status"
        execute = False
        summary = "用户在询问房屋内灯光状态。"
    elif contains_any(text, OFF_WORDS):
        intent = "off"
        execute = True
        summary = "用户要求关闭房屋内灯光。"
    elif contains_any(text, ["调暗", "暗一点", "柔和", "夜灯", "低亮度"]) or (brightness is not None and brightness <= 35):
        intent = "dim"
        execute = True
        summary = "用户要求降低房屋内灯光亮度。"
    elif contains_any(text, ["调亮", "亮一点", "更亮", "太暗", "照亮"]) or brightness is not None:
        intent = "brighten"
        execute = True
        summary = "用户要求提高房屋内灯光亮度。"
    else:
        intent = "on"
        execute = True
        summary = "用户要求打开房屋内灯光。"

    return {"appliance": "light", "mentioned": True, "execute": execute, "intent": intent, "summary": summary}


def keyword_plan_for_ac(text: str) -> Optional[Dict[str, Any]]:
    if not contains_any(text, DEVICE_DEFINITIONS["ac"]["keywords"]):
        return None

    temperature = extract_temperature(text)
    if contains_any(text, STATUS_WORDS):
        intent = "status"
        execute = False
        summary = "用户在询问房屋内空调状态。"
    elif contains_any(text, OFF_WORDS):
        intent = "power_off"
        execute = True
        summary = "用户要求关闭房屋内空调。"
    elif contains_any(text, ["制热", "升温", "太冷", "暖和", "热风"]):
        intent = "heat"
        execute = True
        summary = "用户要求让房屋内空调进入制热模式。"
    elif contains_any(text, ["制冷", "降温", "太热", "凉快", "冷风", "冷气"]):
        intent = "cool"
        execute = True
        summary = "用户要求让房屋内空调进入制冷模式。"
    elif temperature is not None or contains_any(text, ["温度", "调温", "几度"]):
        intent = "set_temp"
        execute = True
        summary = "用户要求调整房屋内空调温度。"
    else:
        intent = "power_on"
        execute = True
        summary = "用户要求打开房屋内空调。"

    return {"appliance": "ac", "mentioned": True, "execute": execute, "intent": intent, "summary": summary}


def keyword_plans(text: str) -> Dict[str, Dict[str, Any]]:
    plans = [
        keyword_plan_for_computer(text),
        keyword_plan_for_light(text),
        keyword_plan_for_ac(text),
    ]
    return {plan["appliance"]: plan for plan in plans if plan}


def build_actions_for_computer(intent: str, text: str) -> List[Dict[str, Any]]:
    if intent == "power_off":
        return [{"device_id": "screen.main", "action": "power", "params": {"on": False}}]
    if intent == "presentation":
        return [
            {"device_id": "screen.main", "action": "set_mode", "params": {"mode": "presentation"}},
            {"device_id": "screen.main", "action": "set_message", "params": {"message": "房屋电脑已切换到汇报模式"}},
        ]
    if intent == "focus":
        return [
            {"device_id": "screen.main", "action": "set_mode", "params": {"mode": "focus"}},
            {"device_id": "screen.main", "action": "set_message", "params": {"message": "房屋电脑已切换到专注模式"}},
        ]
    if intent == "power_on":
        return [
            {"device_id": "screen.main", "action": "power", "params": {"on": True}},
            {"device_id": "screen.main", "action": "set_mode", "params": {"mode": "dashboard"}},
            {"device_id": "screen.main", "action": "set_message", "params": {"message": "房屋电脑已唤醒，等待操作"}},
        ]
    return []


def build_actions_for_light(intent: str, text: str) -> List[Dict[str, Any]]:
    brightness = extract_brightness(text)
    if intent == "off":
        return [
            {"device_id": "light.perimeter", "action": "set_on", "params": {"on": False}},
            {"device_id": "light.entry", "action": "set_on", "params": {"on": False}},
        ]
    if intent == "dim":
        return [
            {"device_id": "light.perimeter", "action": "set_brightness", "params": {"brightness": brightness or 28}},
            {"device_id": "light.entry", "action": "set_brightness", "params": {"brightness": 18}},
        ]
    if intent in {"brighten", "on"}:
        target = brightness or (88 if intent == "brighten" else 72)
        return [
            {"device_id": "light.perimeter", "action": "set_brightness", "params": {"brightness": target}},
            {"device_id": "light.entry", "action": "set_brightness", "params": {"brightness": max(40, min(80, target - 10))}},
        ]
    return []


def build_actions_for_ac(intent: str, text: str) -> List[Dict[str, Any]]:
    temp = extract_temperature(text)
    if intent == "power_off":
        return [{"device_id": "ac.main", "action": "power", "params": {"on": False}}]
    if intent == "heat":
        return [
            {"device_id": "ac.main", "action": "set_mode", "params": {"mode": "heat"}},
            {"device_id": "ac.main", "action": "set_temp", "params": {"temp": temp or 26}},
        ]
    if intent == "cool":
        return [
            {"device_id": "ac.main", "action": "set_mode", "params": {"mode": "cool"}},
            {"device_id": "ac.main", "action": "set_temp", "params": {"temp": temp or 24}},
        ]
    if intent == "set_temp":
        return [{"device_id": "ac.main", "action": "set_temp", "params": {"temp": temp or 24}}]
    if intent == "power_on":
        return [
            {"device_id": "ac.main", "action": "power", "params": {"on": True}},
            {"device_id": "ac.main", "action": "set_temp", "params": {"temp": temp or 24}},
        ]
    return []


def build_actions(appliance: str, intent: str, text: str) -> List[Dict[str, Any]]:
    if appliance == "computer":
        return build_actions_for_computer(intent, text)
    if appliance == "light":
        return build_actions_for_light(intent, text)
    if appliance == "ac":
        return build_actions_for_ac(intent, text)
    return []


def build_agent_update(appliance: str, execute: bool, intent: str) -> Optional[Dict[str, Any]]:
    if not execute:
        return None
    if intent in {"status", "none"}:
        return None

    status = "rest" if intent in {"power_off", "off"} else "work"
    return {
        "agent_id": DEVICE_DEFINITIONS[appliance]["agent_id"],
        "status": status,
    }


class LLMClient:
    def __init__(
        self,
        api_key: str = OPENAI_API_KEY,
        api_base: str = OPENAI_API_BASE,
        model: str = OPENAI_MODEL,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    @staticmethod
    def _parse_json_result(content: str) -> Dict[str, Any]:
        stripped = (content or "").strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = stripped[start : end + 1]
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("LLM响应中未找到有效 JSON")

    async def analyze(self, text: str) -> Dict[str, Any]:
        prompt = (
            "请判断用户是否在操作房屋内设备功能。只分析三类对象：电脑、灯光、空调。\n\n"
            f"输入文本：{text}\n\n"
            "要求：\n"
            "1. 只基于用户当前这句话判断，不要猜测未提到的设备。\n"
            "2. 只要话题涉及房屋内电脑、灯光、空调的功能控制，就 should_trigger_mcp=true。\n"
            "3. 电脑类包括：电脑、显示器、显示屏、屏幕、会议屏、投屏、汇报、演示、专注工作。\n"
            "4. 灯光类包括：灯、灯光、照明、亮度、调亮、调暗、开灯、关灯。\n"
            "5. 空调类包括：空调、冷气、制冷、制热、温度、降温、升温、太热、太冷。\n"
            "6. status/query 类型表示在问状态，不应直接执行设备动作。\n"
            "7. intent 必须使用以下枚举：\n"
            "   电脑: none, power_on, power_off, presentation, focus, status\n"
            "   灯光: none, on, off, brighten, dim, status\n"
            "   空调: none, power_on, power_off, cool, heat, set_temp, status\n"
            "8. 必须输出严格 JSON，不要 Markdown，不要解释性文字。\n\n"
            "输出格式：\n"
            "{\n"
            '  "should_trigger_mcp": true,\n'
            '  "reason": "一句中文总结",\n'
            '  "appliances": {\n'
            '    "computer": {"mentioned": true, "execute": true, "intent": "presentation", "summary": "房屋内电脑进入汇报模式"},\n'
            '    "light": {"mentioned": false, "execute": false, "intent": "none", "summary": ""},\n'
            '    "ac": {"mentioned": true, "execute": true, "intent": "cool", "summary": "房屋内空调需要制冷"}\n'
            "  }\n"
            "}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是房屋设备路由与执行规划助手。"
                        "你的任务是为房屋内电脑、灯光、空调生成保守、准确的 MCP 触发判断。"
                        "禁止猜测，禁止补充用户未提到的设备。"
                        "只允许输出合法 JSON 对象。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
        }

        try:
            session = await self._get_session()
            async with session.post(
                self.api_base,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error("LLM error: %s - %s", resp.status, error_text)
                    raise RuntimeError(f"LLM错误: {resp.status}")

                data = await resp.json()
                choices = data.get("choices") or []
                if not choices:
                    logger.warning("LLM response missing choices: %s", data)
                    raise ValueError("LLM响应缺少 choices")

                content = choices[0].get("message", {}).get("content", "")
                logger.info("LLM response: %s", content[:240])
                normalized = normalize_llm_payload(self._parse_json_result(content))
                normalized["raw"] = content
                return normalized
        except asyncio.TimeoutError:
            logger.error("LLM request timeout")
            raise RuntimeError("LLM请求超时")
        except Exception as exc:
            logger.error("LLM analyze failed: %s", exc, exc_info=True)
            raise RuntimeError(str(exc)) from exc

    async def health_check(self) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            "temperature": 0.0,
            "max_tokens": 5,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
        }
        start = time.time()
        try:
            session = await self._get_session()
            async with session.post(
                self.api_base,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=min(self.timeout, 10)),
            ) as resp:
                latency_ms = int((time.time() - start) * 1000)
                return {
                    "ok": resp.status == 200,
                    "status_code": resp.status,
                    "latency_ms": latency_ms,
                }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "latency_ms": int((time.time() - start) * 1000),
            }


class DigitalTwinClient:
    """Best-effort client for syncing recognized device plans to digital twin."""

    def __init__(
        self,
        base_url: str = DIGITAL_TWIN_BASE_URL,
        timeout: float = DIGITAL_TWIN_TIMEOUT,
        enabled: bool = DIGITAL_TWIN_SYNC_ENABLED,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.enabled = enabled
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def assign_agents(self, agent_ids: List[int], status: str, duration_seconds: int = 0) -> bool:
        if not self.enabled or not agent_ids:
            return False

        payload = {
            "agent_ids": agent_ids,
            "status": status,
            "duration_seconds": duration_seconds,
            "source": "mcp.device_classifier",
        }

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/v1/agents/assign",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status == 200:
                    logger.info("Digital twin agents %s -> %s (%ss)", agent_ids, status, duration_seconds)
                    return True

                error_text = await resp.text()
                logger.warning("Digital twin assign failed [%s]: %s", resp.status, error_text)
                return False
        except Exception as exc:
            logger.warning("Digital twin assign skipped: %s", exc)
            return False

    async def command_device(self, device_id: str, action: str, params: Dict[str, Any], *, source: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "device_id": device_id, "action": action, "skipped": True}

        payload = {
            "action": action,
            "params": params,
            "source": source,
        }

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/v1/devices/{device_id}/commands",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                body = await resp.text()
                ok = resp.status == 200
                if not ok:
                    logger.warning("Digital twin device command failed [%s] %s %s: %s", resp.status, device_id, action, body)
                return {
                    "ok": ok,
                    "device_id": device_id,
                    "action": action,
                    "status_code": resp.status,
                    "response": body[:400],
                }
        except Exception as exc:
            logger.warning("Digital twin command skipped: %s", exc)
            return {
                "ok": False,
                "device_id": device_id,
                "action": action,
                "error": str(exc),
            }

    async def apply_plan_bundle(self, plans: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "device_commands": [], "agent_updates": []}

        device_commands: List[Dict[str, Any]] = []
        agent_updates: List[Dict[str, Any]] = []

        for plan in plans:
            if plan.get("execute"):
                for action in plan.get("actions", []):
                    device_commands.append(
                        await self.command_device(
                            action["device_id"],
                            action["action"],
                            action.get("params", {}),
                            source="mcp.device_classifier",
                        )
                    )

            update = plan.get("agent_update")
            if update:
                ok = await self.assign_agents([int(update["agent_id"])], str(update["status"]))
                agent_updates.append({**update, "ok": ok})

        return {
            "enabled": True,
            "device_commands": device_commands,
            "agent_updates": agent_updates,
        }


class DeviceClassifier:
    def __init__(self) -> None:
        self.llm_client = LLMClient()
        self.digital_twin_client = DigitalTwinClient()
        self.request_times: Dict[str, List[float]] = defaultdict(list)
        self.max_requests_per_minute = 60

    def _check_rate_limit(self, client_id: str = "default") -> bool:
        now = time.time()
        recent = [ts for ts in self.request_times[client_id] if now - ts < 60]
        self.request_times[client_id] = recent
        if len(recent) >= self.max_requests_per_minute:
            return False
        self.request_times[client_id].append(now)
        return True

    def _merge_plans(
        self,
        text: str,
        llm_payload: Dict[str, Any],
        keyword_based: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        appliances = llm_payload.get("appliances", {})

        for appliance in DEVICE_ORDER:
            definition = DEVICE_DEFINITIONS[appliance]
            llm_plan = appliances.get(appliance, {})
            keyword_plan = keyword_based.get(appliance)

            mentioned = bool(llm_plan.get("mentioned")) or keyword_plan is not None
            if not mentioned:
                continue

            execute = bool(llm_plan.get("execute")) if llm_plan else bool(keyword_plan and keyword_plan.get("execute"))
            intent = normalize_intent(appliance, llm_plan.get("intent")) if llm_plan else "none"
            if intent == "none" and keyword_plan:
                intent = normalize_intent(appliance, keyword_plan.get("intent"))

            summary = str(llm_plan.get("summary", "") or "").strip()
            if not summary and keyword_plan:
                summary = str(keyword_plan.get("summary", "") or "").strip()
            if not summary:
                summary = f"识别到房屋内{definition['label']}相关意图。"

            actions = build_actions(appliance, intent, text) if execute else []
            agent_update = build_agent_update(appliance, execute, intent)

            merged.append(
                {
                    "appliance": appliance,
                    "label": definition["label"],
                    "mentioned": True,
                    "execute": execute,
                    "intent": intent,
                    "summary": summary,
                    "device_targets": list(definition["digital_twin_devices"]),
                    "actions": actions,
                    "agent_update": agent_update,
                }
            )

        return merged

    async def classify(self, text: str, client_id: str = "default") -> Dict[str, object]:
        if not self._check_rate_limit(client_id):
            return {
                "success": False,
                "error": "请求过于频繁，请稍后再试",
                "devices": [],
                "plans": [],
            }

        logger.info("Classifying input: %s", text[:120])

        keyword_based = keyword_plans(text)
        keyword_labels = [DEVICE_DEFINITIONS[key]["label"] for key in DEVICE_ORDER if key in keyword_based]
        logger.info("Keyword match result: %s", keyword_labels)

        analysis_result = "暂无LLM分析"
        llm_payload = {"appliances": {}, "reason": "", "should_trigger_mcp": bool(keyword_based)}

        try:
            llm_payload = await self.llm_client.analyze(text)
            analysis_result = str(llm_payload.get("reason") or "").strip() or str(llm_payload.get("raw") or "")
        except Exception as exc:
            logger.warning("LLM classify fallback to keyword plan: %s", exc)
            analysis_result = f"LLM不可用，已回退关键词判定: {exc}"

        plans = self._merge_plans(text, llm_payload, keyword_based)
        devices = [plan["label"] for plan in plans]
        digital_twin_result = await self.digital_twin_client.apply_plan_bundle(plans)

        return {
            "success": True,
            "devices": devices,
            "analysis": analysis_result,
            "keyword_match": keyword_labels,
            "plans": plans,
            "digital_twin": digital_twin_result,
        }

    async def close(self) -> None:
        await self.llm_client.close()
        await self.digital_twin_client.close()


classifier = DeviceClassifier()


@app.get("/")
async def root() -> Dict[str, object]:
    return {
        "name": "设备场景识别服务",
        "version": "1.2.0",
        "description": "通过 MCP 接收指令，识别房屋内电脑、灯光、空调意图，并同步 digital twins 的设备与 agent 状态",
        "architecture": f"MCP -> {DEVICE_LLM_SERVER_PORT}(device_llm_server) -> LLM API -> digital twin",
        "supported_appliances": ["电脑", "灯光", "空调"],
        "endpoints": {
            "classify": "/api/classify",
            "analyze": "/api/analyze",
            "health": "/health",
            "deep_health": "/health/deep",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health_check() -> Dict[str, object]:
    return {
        "status": "ok",
        "service": "device_llm_server",
        "port": DEVICE_LLM_SERVER_PORT,
        "llm_api": OPENAI_API_BASE,
        "model": OPENAI_MODEL,
        "digital_twin_base_url": DIGITAL_TWIN_BASE_URL,
        "digital_twin_sync_enabled": DIGITAL_TWIN_SYNC_ENABLED,
        "supported_appliances": ["电脑", "灯光", "空调"],
    }


@app.get("/health/deep", response_model=DeepHealthResponse)
async def deep_health_check() -> DeepHealthResponse:
    llm_check = await classifier.llm_client.health_check()

    twin_check: Dict[str, Any] = {
        "enabled": DIGITAL_TWIN_SYNC_ENABLED,
        "ok": False,
    }
    if DIGITAL_TWIN_SYNC_ENABLED:
        start = time.time()
        try:
            session = await classifier.digital_twin_client._get_session()
            async with session.get(
                f"{DIGITAL_TWIN_BASE_URL}/api/v1/health",
                timeout=aiohttp.ClientTimeout(total=DIGITAL_TWIN_TIMEOUT),
            ) as resp:
                twin_check = {
                    "enabled": True,
                    "ok": resp.status == 200,
                    "status_code": resp.status,
                    "latency_ms": int((time.time() - start) * 1000),
                }
        except Exception as exc:
            twin_check = {
                "enabled": True,
                "ok": False,
                "error": str(exc),
                "latency_ms": int((time.time() - start) * 1000),
            }

    overall_ok = bool(llm_check.get("ok")) and (not DIGITAL_TWIN_SYNC_ENABLED or bool(twin_check.get("ok")))
    return DeepHealthResponse(
        status="ok" if overall_ok else "degraded",
        service="device_llm_server",
        port=DEVICE_LLM_SERVER_PORT,
        llm_api=OPENAI_API_BASE,
        model=OPENAI_MODEL,
        digital_twin_base_url=DIGITAL_TWIN_BASE_URL,
        digital_twin_sync_enabled=DIGITAL_TWIN_SYNC_ENABLED,
        checks={
            "llm_api": llm_check,
            "digital_twin": twin_check,
        },
    )


@app.post("/api/classify", response_model=ClassificationResponse)
async def classify_devices(request: ClassificationRequest) -> ClassificationResponse:
    if not request.input or not request.input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    try:
        result = await classifier.classify(request.input)
        return ClassificationResponse(**result)
    except Exception as exc:
        logger.error("Classification failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"分类失败: {exc}") from exc


@app.post("/api/analyze")
async def analyze(request: ClassificationRequest) -> Dict[str, object]:
    if not request.input or not request.input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    try:
        analysis = await classifier.llm_client.analyze(request.input)
        return {
            "success": True,
            "input": request.input,
            "analysis": analysis,
        }
    except Exception as exc:
        logger.error("Analyze failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}") from exc


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await classifier.close()
    logger.info("Device classification service stopped")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Device LLM server starting")
    logger.info("Bind: %s:%s", DEVICE_LLM_SERVER_HOST, DEVICE_LLM_SERVER_PORT)
    logger.info("LLM API: %s", OPENAI_API_BASE)
    logger.info("Model: %s", OPENAI_MODEL)
    logger.info("Digital twin sync: %s (%s)", DIGITAL_TWIN_SYNC_ENABLED, DIGITAL_TWIN_BASE_URL)
    logger.info("Supported appliances: 电脑 / 灯光 / 空调")
    logger.info("=" * 60)
    uvicorn.run(app, host=DEVICE_LLM_SERVER_HOST, port=DEVICE_LLM_SERVER_PORT, log_level="info")
