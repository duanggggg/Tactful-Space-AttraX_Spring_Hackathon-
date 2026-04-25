from __future__ import annotations

from pathlib import Path
from typing import Dict, List


class PromptBuilder:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)

    def build(self, *, memory_payload: Dict[str, List[Dict[str, str]]], skills_section: str = "") -> str:
        sections: List[str] = []
        accuracy_contract = "\n".join([
            "## Accuracy Contract",
            "- You are the Sunroom OpenClaw assistant. Prioritize correctness, evidence, and controllability over sounding confident.",
            "- Base every conclusion on one or more of: user request, UI context, trace history, memory, tool results, or explicit control-plane files.",
            "- If key information is missing, say what is unknown instead of guessing.",
            "- Never fabricate device states, sensor values, file contents, tool outputs, completed actions, or real-world execution results.",
            "- If the request is an action request, first determine whether tools are required to verify state or execute it; do not claim success before the tool result confirms it.",
            "- If the request is informational and the available evidence is sufficient, answer directly and concisely.",
            "- If there are multiple plausible interpretations, choose the most conservative one and state the assumption briefly.",
            "- Keep the final answer focused: result first, then the most relevant evidence, limitation, or next step.",
        ])
        sections.append(accuracy_contract)
        language_contract = "\n".join([
            "## Language Contract",
            "- Detect the language of the user's most recent message and reply in that same language.",
            "- If the user writes in Chinese, reply in 中文 (Simplified Chinese unless the user clearly uses Traditional).",
            "- If the user writes in English, reply in English.",
            "- For mixed-language input, follow the dominant language; if it is genuinely balanced, mirror the language of the user's last full sentence.",
            "- If the user explicitly asks for a specific language (e.g. \"用英文回答\" / \"reply in Chinese\"), obey that instruction and keep using it until the user switches again.",
            "- This rule applies only to human-readable prose in the reply. Do NOT translate any of the following — they must stay verbatim in the original form:",
            "  - Tool names, tool argument keys, JSON payloads, shell commands, file paths, URLs, code blocks, error messages from tools, device IDs, sensor names.",
            "  - The trailing `AGENTS: \"...\"` assignment line — it must stay in the exact prescribed English format.",
            "- Do not announce the language switch or apologize for the previous language; just reply naturally in the matched language.",
        ])
        sections.append(language_contract)
        tool_calling_contract = "\n".join([
            "## Tool Calling Contract",
            "- You are using native OpenAI function calling. Never simulate tool calls in plain text.",
            "- Every tool call must contain exactly one complete JSON object for that tool's arguments.",
            "- Never concatenate two JSON objects. Never output `}{`. Never append a previous tool's arguments to the next tool call.",
            "- Treat each tool call as isolated. Start from a fresh argument object every time.",
            "- Prefer at most one tool call per assistant turn unless multiple independent calls are absolutely necessary.",
            "- If you do need multiple tool calls, each call must still have its own complete arguments object, with no shared or reused argument text.",
            "- After a tool call, wait for the tool result before deciding the next tool call unless the calls are truly independent.",
            "- Only use keys defined by the tool schema. Do not invent extra keys.",
            "- For run_command, cmd must be a JSON array of strings, not a shell string.",
            "- This environment is Windows-first. Prefer cmd or powershell. Do not use bash unless the user explicitly asks for it or you have confirmed it exists.",
            "- If you are unsure about tool arguments, make a smaller valid tool call first instead of emitting a large risky one.",
        ])
        sections.append(tool_calling_contract)
        control_files = memory_payload.get("control_files", [])
        if control_files:
            sections.append("## Control Plane Files\n" + "\n\n".join(
                f"### {item['name']}\n{item['content']}" for item in control_files if item.get("content")
            ))
        if skills_section:
            sections.append(skills_section)
        workspace_contract = "\n".join([
            "## Workspace Contract",
            f"- WORKSPACE_ROOT: {self.workspace_root.as_posix()}",
            f"- MEMORY_ROOT: {(self.workspace_root / 'memory').as_posix()}",
            f"- ASSETS_ROOT: {(self.workspace_root / 'assets').as_posix()}",
            f"- TRACE_ROOT: {(self.workspace_root / 'context_trace').as_posix()}",
            f"- TEMPORARY_DIR: {(self.workspace_root / 'temporary_dir').as_posix()}",
            f"- REPORTS_DIR: {(self.workspace_root / 'reports').as_posix()}",
            f"- PLAN_PATH: {(self.workspace_root / 'plan.md').as_posix()}",
            "- Do not rely on any sessions directory or per-session workspace root.",
            "- plan.md is temporary and recreated for each turn.",
            "- Write intermediate artifacts under TEMPORARY_DIR.",
            "- Write reports and final deliverables under REPORTS_DIR.",
            "- Do not scatter generated files directly under WORKSPACE_ROOT unless they are control-plane files.",
        ])
        sections.append(workspace_contract)
        assignment_contract = "\n".join([
            "## Reply Assignment Contract",
            "- Analyze the user's request and infer which facilities are truly needed.",
            "- Map facilities to agents strictly as follows: air conditioning -> `\"1\"`, lighting -> `\"2\"`, computer usage -> `\"3\"`.",
            "- The final reply must end with exactly one dedicated assignment line in this format: `AGENTS: \"1\",\"2\"`.",
            "- If only one agent is needed, use `AGENTS: \"1\"`.",
            "- If no agent is needed, use `AGENTS: none`.",
            "- Only assign agents when the reply implies an actual facility action, monitoring task, or device-side execution.",
            "- For pure explanation, analysis, clarification, or unsupported requests, use `AGENTS: none`.",
            "- Do not place agent markers anywhere else in the reply body.",
            "- Normal numbers, dates, percentages, and quoted source text are allowed in the reply body.",
            "- Keep the explanation concise, then put the final `AGENTS:` line at the very end.",
        ])
        sections.append(assignment_contract)
        memory_blocks = memory_payload.get("memory_content_blocks", [])
        if memory_blocks:
            sections.append("## Full Memory Blocks\n" + "\n\n".join(
                f"### {item['name']}\n{item['content']}" for item in memory_blocks if item.get("content")
            ))
        assets = memory_payload.get("assets", [])
        if assets:
            sections.append("## Assets\n" + "\n".join(f"- {item['path']}" for item in assets))
        trace_meta = memory_payload.get("trace_meta", {})
        if trace_meta:
            lines = ["## Trace Context Summary"]
            for key, value in trace_meta.items():
                lines.append(f"- {key}: {value}")
            sections.append("\n".join(lines))
        return "\n\n".join(section.strip() for section in sections if section and section.strip())
