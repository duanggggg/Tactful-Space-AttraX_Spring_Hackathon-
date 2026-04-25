"""
Trace-first agent orchestrator.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import AgentChatRequest, AgentChatResponse, OneTurnAfterRunAgent, TraceSummary
from .services import MemoryAssembler, MemoryManager
from .agent_workspace_manager import AgentWorkspaceManager
from .prompt_builder import PromptBuilder
from .trace_writer import TraceWriter
from .tools.registry import tool_registry
from .skills.skill_manager import SkillManager
from .twin_bridge import twin_event_bridge
from executor.runner import get_runner

logger = logging.getLogger(__name__)
AGENT_ASSIGNMENT_LINE_PATTERN = re.compile(r'^\s*AGENTS:\s*(.+?)\s*$', re.IGNORECASE | re.MULTILINE)
AGENT_ASSIGNMENT_ID_PATTERN = re.compile(r'"([123])"')


class AgentOrchestrator:
    def __init__(self, data_loader=None, *, agent_id: str = "default", session_id: str = "default", enable_skills: Optional[bool] = None):
        self.data_loader = data_loader
        self.agent_id = agent_id or "default"
        self.session_id = session_id
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.xiaomimimo.com/v1/chat/completions")
        self.model = os.getenv("OPENAI_MODEL", "mimo-v2-pro")
        self.max_steps = int(os.getenv("MAX_AGENT_STEPS", "30"))
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "4096"))
        self.enable_skills = bool(enable_skills)
        self.backend_root = Path(__file__).resolve().parent.parent
        self.workspace_manager = AgentWorkspaceManager(self.backend_root, self.agent_id)
        self.workspace_dir = self.workspace_manager.workspace_root
        self.trace_writer = TraceWriter(self.workspace_manager.trace_root, self.agent_id, self.workspace_manager.plan_path)
        self.memory_manager = MemoryManager(self.workspace_dir)
        self.memory_assembler = MemoryAssembler(self.workspace_dir)
        self.prompt_builder = PromptBuilder(self.workspace_dir)
        self.skill_manager = SkillManager(self.backend_root / "agent" / "skills") if self.enable_skills else None
        get_runner().set_active_agent(self.agent_id)
        self._init_tools()

    def _init_tools(self) -> None:
        from .tools.workspace_tools import WorkspaceTools
        WorkspaceTools(self.session_id)

    def _build_history_block(self, trace_messages: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for item in trace_messages[-12:]:
            role = str(item.get("role", "")).lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines)

    def _build_user_context(self, request: AgentChatRequest, trace_payload: Dict[str, Any]) -> str:
        parts: List[str] = []
        if request.ui_context:
            parts.append("## UI Context")
            if request.ui_context.date:
                parts.append(f"- date: {request.ui_context.date}")
            if request.ui_context.selected:
                parts.append(f"- selected: {request.ui_context.selected.get('type')} {request.ui_context.selected.get('id')}")
        history = self._build_history_block(trace_payload.get("messages", []))
        if history:
            parts.append("\n## Trace History")
            parts.append(history)
        parts.append("\n## Current User Request")
        parts.append(request.message)
        return "\n".join(parts).strip()

    def _safe_parse_args(self, raw_args: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(raw_args) if raw_args else {}
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def _publish_twin_event(
        self,
        *,
        event_type: str,
        status: str,
        message: str,
        request: Optional[AgentChatRequest] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        event_payload: Dict[str, Any] = {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
        }
        if request and request.ui_context:
            event_payload["ui_context"] = request.ui_context.model_dump(exclude_none=True)
        if payload:
            event_payload.update(payload)
        twin_event_bridge.publish(
            event_type=event_type,
            status=status,
            message=message,
            zone="chat",
            task_id=self.session_id,
            trace_id=self.session_id,
            payload=event_payload,
        )

    def _normalize_message_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
            return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
        return ""

    def _extract_assigned_agent_ids(self, message: str) -> List[int]:
        match = AGENT_ASSIGNMENT_LINE_PATTERN.search(message or "")
        if not match:
            return []
        assignment_text = match.group(1).strip()
        if assignment_text.lower() == "none":
            return []
        matches = AGENT_ASSIGNMENT_ID_PATTERN.findall(assignment_text)
        return sorted({int(item) for item in matches})

    def _create_chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: float,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        if tools_schema:
            payload["tools"] = tools_schema
        if tool_choice:
            payload["tool_choice"] = tool_choice

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        request = urllib.request.Request(self.api_base, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"请求模型服务失败: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"模型返回了非 JSON 响应: {raw[:500]}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError("模型返回格式无效，顶层不是 JSON object")
        return parsed

    def _tool_loop_stream(self, system_prompt: str, user_context: str, request: Optional[AgentChatRequest] = None):
        if not self.api_key:
            message = "Agent 服务未配置 OPENAI_API_KEY，当前无法执行真实推理。"
            self.trace_writer.append_message(self.session_id, role="assistant", content=message)
            self._publish_twin_event(event_type="chat.assistant_reply", status="error", message=message, request=request)
            yield {"event": "assistant_message", "data": {"content": message, "timestamp": datetime.now().isoformat(), "final": True}}
            return message, "error"

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_context}]
        tools_schema = tool_registry.openai_tools_schema()

        try:
            for _ in range(self.max_steps):
                response = self._create_chat_completion(
                    messages=messages,
                    tools_schema=tools_schema,
                    tool_choice="auto",
                    temperature=0.0,
                )
                choices = response.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise RuntimeError(f"模型返回缺少 choices: {json.dumps(response, ensure_ascii=False)[:1000]}")
                choice = choices[0] or {}
                message = choice.get("message") or {}
                finish_reason = choice.get("finish_reason")
                tool_calls = message.get("tool_calls") or []
                content = self._normalize_message_content(message.get("content"))
                response_trace = response

                if finish_reason == "tool_calls" and not tool_calls:
                    logger.warning("Model returned finish_reason=tool_calls without tool_calls; retrying without tools")
                    fallback_response = self._create_chat_completion(messages=messages, temperature=0.0)
                    fallback_choices = fallback_response.get("choices")
                    if not isinstance(fallback_choices, list) or not fallback_choices:
                        raise RuntimeError(f"模型回退响应缺少 choices: {json.dumps(fallback_response, ensure_ascii=False)[:1000]}")
                    fallback_choice = fallback_choices[0] or {}
                    response = fallback_response
                    message = fallback_choice.get("message") or {}
                    finish_reason = fallback_choice.get("finish_reason")
                    tool_calls = message.get("tool_calls") or []
                    content = self._normalize_message_content(message.get("content"))
                    response_trace = response

                if content:
                    yield {
                        "event": "assistant_message",
                        "data": {
                            "content": content,
                            "timestamp": datetime.now().isoformat(),
                            "final": not bool(tool_calls),
                        },
                    }

                if not tool_calls:
                    final_text = content
                    if not final_text and finish_reason == "tool_calls":
                        final_text = "模型声明要调用工具，但没有返回 tool_calls；请检查当前模型网关是否兼容 OpenAI function calling。"
                    if not final_text:
                        final_text = "模型没有返回可展示内容。"
                    assigned_agent_ids = self._extract_assigned_agent_ids(final_text)
                    if assigned_agent_ids:
                        twin_event_bridge.assign_agents(
                            agent_ids=assigned_agent_ids,
                            duration_seconds=0,
                            status="work",
                            source="main_chat",
                            task_id=self.session_id,
                            trace_id=self.session_id,
                        )
                    self.trace_writer.append_message(self.session_id, role="assistant", content=final_text)
                    self._publish_twin_event(
                        event_type="chat.assistant_reply",
                        status="completed",
                        message=final_text,
                        request=request,
                        payload={"final": True, "assigned_agent_ids": assigned_agent_ids},
                    )
                    if not content or final_text != content:
                        yield {
                            "event": "assistant_message",
                            "data": {
                                "content": final_text,
                                "timestamp": datetime.now().isoformat(),
                                "final": True,
                            },
                        }
                    return final_text, "completed"

                assistant_tool_calls = [
                    {
                        "id": call.get("id"),
                        "type": "function",
                        "function": {
                            "name": (call.get("function") or {}).get("name"),
                            "arguments": (call.get("function") or {}).get("arguments", ""),
                        },
                    }
                    for call in tool_calls
                ]
                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": assistant_tool_calls,
                    }
                )

                for call in tool_calls:
                    function_payload = call.get("function") or {}
                    call_id = str(call.get("id") or "")
                    function_name = str(function_payload.get("name") or "")
                    raw_arguments = str(function_payload.get("arguments") or "")
                    args = self._safe_parse_args(raw_arguments)
                    tool_input: Dict[str, Any] = args if args is not None else {"_raw_arguments": raw_arguments}
                    yield {
                        "event": "tool_start",
                        "data": {
                            "tool_call_id": call_id,
                            "tool": function_name,
                            "input": tool_input,
                            "timestamp": datetime.now().isoformat(),
                        },
                    }

                    if args is None:
                        result = {
                            "success": False,
                            "error": "Invalid JSON arguments",
                            "tool": function_name,
                            "raw_arguments": raw_arguments,
                        }
                    else:
                        try:
                            result = tool_registry.execute(function_name, session_id=self.session_id, agent_id=self.agent_id, **args)
                        except Exception as exc:
                            result = {"success": False, "error": str(exc), "tool": function_name, "params": args}

                    result_summary = json.dumps(result, ensure_ascii=False)[:4000]
                    trace_extra = {"tool_call_id": call_id}
                    if isinstance(result, dict) and result.get("error"):
                        trace_extra["failure_context"] = {
                            "finish_reason": finish_reason,
                            "assistant_message": {
                                "content": content,
                                "tool_calls": assistant_tool_calls,
                            },
                            "llm_response": response_trace,
                        }
                    self.trace_writer.append_tool_call(
                        self.session_id,
                        function_name,
                        args or {},
                        result_summary,
                        extra=trace_extra,
                    )
                    yield {
                        "event": "tool_end",
                        "data": {
                            "tool_call_id": call_id,
                            "tool": function_name,
                            "output": result_summary,
                            "timestamp": datetime.now().isoformat(),
                            "success": not isinstance(result, dict) or not bool(result.get("error")),
                        },
                    }
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False)})
        except Exception as exc:
            error_message = f"LLM 调用失败：{exc}"
            logger.exception("LLM tool loop failed")
            self.trace_writer.append_message(self.session_id, role="assistant", content=error_message)
            self._publish_twin_event(event_type="chat.assistant_reply", status="error", message=error_message, request=request)
            yield {"event": "error", "data": {"message": error_message, "timestamp": datetime.now().isoformat()}}
            return error_message, "error"

        timeout_message = "工具调用达到上限，流程被中止。"
        self.trace_writer.append_message(self.session_id, role="assistant", content=timeout_message)
        self._publish_twin_event(event_type="chat.assistant_reply", status="timeout", message=timeout_message, request=request)
        yield {
            "event": "assistant_message",
            "data": {
                "content": timeout_message,
                "timestamp": datetime.now().isoformat(),
                "final": True,
            },
        }
        return timeout_message, "timeout"

    def run_agent(self, request: AgentChatRequest) -> OneTurnAfterRunAgent:
        stream = self.run_agent_stream(request)
        while True:
            try:
                next(stream)
            except StopIteration as stop:
                if stop.value is None:
                    raise RuntimeError("run_agent_stream did not return a result")
                return stop.value

    def run_agent_stream(self, request: AgentChatRequest):
        self.trace_writer.reset_turn()
        self.trace_writer.ensure_trace(self.session_id)
        self.trace_writer.set_status(self.session_id, "running")
        self.trace_writer.append_message(self.session_id, role="user", content=request.message)
        self._publish_twin_event(
            event_type="chat.user_message",
            status="received",
            message=request.message,
            request=request,
        )
        self._publish_twin_event(
            event_type="chat.processing",
            status="running",
            message=f"正在处理来自第一个窗口的提问：{request.message}",
            request=request,
        )
        yield {
            "event": "session_created",
            "data": {
                "agent_id": self.agent_id,
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

        trace_payload = self.trace_writer.load_trace(self.session_id)
        memory_payload = self.memory_assembler.build(self.session_id)
        self.trace_writer.set_context_injection(
            self.session_id,
            {
                "control_files": [item["name"] for item in memory_payload.get("control_files", [])],
                "memory_files": [item["name"] for item in memory_payload.get("memory_content_blocks", [])],
                "assets": [item["path"] for item in memory_payload.get("assets", [])],
                "notes": "full memory concatenation",
            },
        )
        skills_section = self.skill_manager.render_skills_section() if self.skill_manager else ""
        system_prompt = self.prompt_builder.build(memory_payload=memory_payload, skills_section=skills_section)
        user_context = self._build_user_context(request, trace_payload)
        assistant_message, final_status = yield from self._tool_loop_stream(system_prompt, user_context, request)
        memory_commit = self.memory_manager.commit_turn(session_id=self.session_id, user_message=request.message, assistant_message=assistant_message)
        memory_updates = [memory_commit["memory_commit_path"]]
        self.trace_writer.extend_memory_commits(self.session_id, memory_updates)
        self.trace_writer.append_decision(self.session_id, summary=assistant_message[:500], artifact_paths=[])
        self.trace_writer.set_status(self.session_id, final_status)
        trace_summary = TraceSummary(**self.trace_writer.summarize(self.session_id))
        result = OneTurnAfterRunAgent(return_message=assistant_message, memory_updates=memory_updates, generated_artifacts=[], trace_summary=trace_summary)
        yield {
            "event": "done",
            "data": AgentChatResponse(
                agent_id=self.agent_id,
                session_id=self.session_id,
                message_markdown=result.return_message,
                trace_summary=result.trace_summary,
                memory_updates=result.memory_updates,
                generated_artifacts=result.generated_artifacts,
            ).model_dump(),
        }
        return result


orchestrator: Optional[AgentOrchestrator] = None


def init_orchestrator(data_loader, session_id: str = "default", enable_skills: Optional[bool] = None, agent_id: str = "default"):
    global orchestrator
    orchestrator = AgentOrchestrator(data_loader, agent_id=agent_id, session_id=session_id, enable_skills=enable_skills)
    return orchestrator
