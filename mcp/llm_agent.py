"""
MCP LLM Agent - 与本地大模型接口通信
集成本地LLM (localhost:12345) 处理复杂任务

支持功能：
- 文本生成和对话
- 代码补全
- 指令解析和执行
"""

import asyncio
import os
import aiohttp
import logging
import json
from typing import Optional, Dict, Any
from fastmcp import FastMCP

logger = logging.getLogger('LLM_AGENT')

# 本地LLM API配置
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions",
    "completion": "/v1/completions",
    "generate": "/api/generate"
}

class LLMClient:
    """本地LLM客户端"""

    def __init__(self, base_url: str = LLM_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def health_check(self) -> bool:
        """检查LLM服务健康状态"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            return False

    async def chat(self, messages: list, model: str = "default", temperature: float = 0.7) -> str:
        """
        调用LLM的chat接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}, ...]
            model: 模型名称
            temperature: 温度参数

        Returns:
            模型的回复内容
        """
        try:
            session = await self._get_session()
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "stream": False
            }

            logger.info(f"Sending chat request to {self.base_url}{LLM_ENDPOINTS['chat']}")
            logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

            async with session.post(
                f"{self.base_url}{LLM_ENDPOINTS['chat']}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # 处理不同格式的响应
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    logger.info(f"LLM response received: {content[:100]}...")
                    return content
                else:
                    error_text = await resp.text()
                    logger.error(f"LLM error: {resp.status} - {error_text}")
                    return f"LLM错误: {resp.status}"

        except asyncio.TimeoutError:
            logger.error("LLM request timeout")
            return "错误: LLM请求超时"
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            return f"错误: {str(e)}"

    async def completion(self, prompt: str, max_tokens: int = 1000) -> str:
        """
        调用LLM的completion接口

        Args:
            prompt: 输入提示词
            max_tokens: 最大生成令牌数

        Returns:
            生成的文本
        """
        try:
            session = await self._get_session()
            payload = {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "stream": False
            }

            logger.info(f"Sending completion request to {self.base_url}")

            async with session.post(
                f"{self.base_url}{LLM_ENDPOINTS['completion']}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get('choices', [{}])[0].get('text', '')
                    return text
                else:
                    return f"错误: {resp.status}"

        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            return f"错误: {str(e)}"

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        调用通用的generate接口（适配更多模型）

        Args:
            prompt: 输入提示词
            **kwargs: 其他参数

        Returns:
            生成的文本
        """
        try:
            session = await self._get_session()
            payload = {"prompt": prompt, **kwargs}

            async with session.post(
                f"{self.base_url}{LLM_ENDPOINTS['generate']}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # 处理多种响应格式
                    if isinstance(data, dict):
                        return data.get('result', data.get('text', str(data)))
                    else:
                        return str(data)
                else:
                    return f"错误: {resp.status}"

        except Exception as e:
            logger.error(f"LLM generate failed: {e}")
            return f"错误: {str(e)}"


# 全局LLM客户端实例
_llm_client: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    """获取全局LLM客户端"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


# 创建MCP服务器
mcp = FastMCP("LLMAgent")


@mcp.tool()
async def ask_llm(question: str, chat_mode: str = "chat") -> dict:
    """
    询问本地大模型

    Args:
        question: 用户问题或提示词
        chat_mode: 模式选择 - "chat"(聊天) / "completion"(补全) / "generate"(生成)

    Returns:
        包含模型回复的字典
    """
    client = get_llm_client()

    try:
        # 检查服务健康状态
        is_healthy = await client.health_check()
        if not is_healthy:
            logger.warning("LLM service may be unavailable")

        if chat_mode == "chat":
            response = await client.chat([{"role": "user", "content": question}])
        elif chat_mode == "completion":
            response = await client.completion(question)
        else:  # generate
            response = await client.generate(question)

        return {
            "success": True,
            "mode": chat_mode,
            "question": question,
            "response": response
        }

    except Exception as e:
        logger.error(f"ask_llm error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def ask_llm_with_context(question: str, context: str = "", chat_mode: str = "chat") -> dict:
    """
    带上下文的LLM查询（适用于需要背景信息的场景）

    Args:
        question: 用户问题
        context: 上下文信息
        chat_mode: 模式选择

    Returns:
        包含模型回复的字典
    """
    client = get_llm_client()

    try:
        if chat_mode == "chat":
            messages = [
                {"role": "system", "content": f"背景信息: {context}" if context else ""},
                {"role": "user", "content": question}
            ]
            # 过滤掉空的system消息
            messages = [m for m in messages if m.get("content")]
            response = await client.chat(messages)
        else:
            full_prompt = f"背景: {context}\n\n问题: {question}" if context else question
            if chat_mode == "completion":
                response = await client.completion(full_prompt)
            else:
                response = await client.generate(full_prompt)

        return {
            "success": True,
            "mode": chat_mode,
            "question": question,
            "context": context,
            "response": response
        }

    except Exception as e:
        logger.error(f"ask_llm_with_context error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def llm_code_completion(code_prefix: str) -> dict:
    """
    LLM代码补全工具

    Args:
        code_prefix: 代码片段前缀

    Returns:
        包含补全后的代码
    """
    client = get_llm_client()

    try:
        prompt = f"请补全以下代码:\n{code_prefix}"
        response = await client.completion(prompt, max_tokens=500)

        return {
            "success": True,
            "prefix": code_prefix,
            "completion": response
        }

    except Exception as e:
        logger.error(f"code completion error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def llm_analyze_instruction(instruction: str) -> dict:
    """
    分析和执行MCP指令（通过LLM理解和处理）

    Args:
        instruction: 需要分析的指令

    Returns:
        分析结果
    """
    client = get_llm_client()

    try:
        analysis_prompt = f"""
请分析以下MCP指令，并提供执行建议:
指令: {instruction}

请包含:
1. 指令的目的
2. 所需的参数
3. 可能的风险
4. 建议的执行步骤
"""
        response = await client.chat([{"role": "user", "content": analysis_prompt}])

        return {
            "success": True,
            "instruction": instruction,
            "analysis": response
        }

    except Exception as e:
        logger.error(f"instruction analysis error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def classify_devices(input_text: str) -> dict:
    """
    设备场景识别工具

    调用device_llm_server的分类API，识别房屋内电脑、灯光、空调相关功能，
    并生成完整的设备执行方案与 digital twin 联动结果。

    【架构说明】
    本工具通过调用localhost:12345上的device_llm_server：
      - 12345 = device_llm_server (网关)
      - 用户配置的外部API: http://127.0.0.1:48760/v1/chat/completions
      - digital twin backend: http://127.0.0.1:8787

    【触发规则】
    只要对话涉及房屋内以下功能，就应该调用本工具：
      - 电脑/显示器/显示屏/投屏/汇报
      - 灯/灯光/照明/亮度
      - 空调/冷气/温度/制冷/制热

    Args:
        input_text: 用户输入文本，包含设备相关信息

    Returns:
        {
            "success": bool,
            "devices": ["电脑", "灯光", "空调"],  # 涉及到的设备列表
            "analysis": "分析结果",
            "plans": [...],  # 每个家电的动作方案
            "digital_twin": {...}  # 前后端联动执行结果
        }

    示例:
        >>> result = await classify_devices("打开电脑，调亮灯光，把空调调到24度")
        >>> print(result['devices'])
        ['电脑', '灯光', '空调']
    """

    try:
        session = aiohttp.ClientSession()
        device_service_url = "http://localhost:12345/api/classify"

        logger.info(f"调用设备分类服务: {device_service_url}")
        logger.info(f"输入文本: {input_text}")

        async with session.post(
            device_service_url,
            json={"input": input_text},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                logger.info(f"设备识别成功: {result}")
                # 同步把这次设备命令也送进 homekgmas 多 agent 讨论流，
                # 让 dashboard 也能看到设备型对话的气泡（不阻塞失败）
                try:
                    await _relay_device_intent_to_dashboard(input_text, result)
                except Exception as e:
                    logger.warning(f"设备命令同步到 dashboard 失败（不影响主流程）: {e}")
                # 添加 voice_reply 字段，供云端 LLM 忠实口播
                result["voice_reply"] = _summarize_devices_for_voice(result)
                return result
            else:
                error_text = await resp.text()
                logger.error(f"设备识别失败 [{resp.status}]: {error_text}")
                return {
                    "success": False,
                    "error": f"HTTP {resp.status}: {error_text}",
                    "devices": []
                }

    except asyncio.TimeoutError:
        logger.error("设备识别超时 (30秒)")
        return {
            "success": False,
            "error": "请求超时 (30秒)",
            "devices": []
        }

    except Exception as e:
        logger.error(f"设备识别异常: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "devices": []
        }

    finally:
        try:
            await session.close()
        except:
            pass


# ---- Chinese voice-reply synthesis (gives the cloud LLM a faithful sentence to speak) ----

_DEVICE_ZH: dict[str, str] = {
    "living_room_main": "客厅主灯",
    "bedroom_lamp": "卧室台灯",
    "living_room_ac_1": "客厅空调",
    "bedroom_ac_1": "卧室空调",
    "music_player": "音乐",
    "living_room_curtain": "客厅窗帘",
    "bedroom_blinds": "卧室百叶",
    "front_door_lock": "大门",
    "air_purifier": "空气净化器",
    "bedroom_humidifier": "卧室加湿器",
    "robot_vacuum_1": "扫地机器人",
    "living_room_fan_1": "客厅风扇",
    "bedroom_fan_1": "卧室风扇",
    # device_llm 用的简写
    "ac.main": "空调",
    "light.perimeter": "环境灯",
    "light.entry": "入口灯",
    "screen.main": "电脑",
}

_SCENE_ZH: dict[str, str] = {
    "Morning scene": "早晨场景",
    "Evening scene": "晚间场景",
    "Movie scene": "观影场景",
    "Night mode": "夜间模式",
    "Focus mode": "专注场景",
    "Bedtime": "睡眠场景",
    "Welcome": "迎接场景",
}

_MODE_ZH: dict[str, str] = {
    "cool": "制冷", "heat": "制热", "auto": "自动", "sleep": "睡眠",
    "boost": "增强", "presentation": "汇报", "focus": "专注",
    "static": "静态", "ambient": "氛围",
}


def _device_label(device_id: str) -> str:
    if device_id in _DEVICE_ZH:
        return _DEVICE_ZH[device_id]
    # 按下划线段做轻量映射
    if "ac" in device_id:
        return "空调"
    if "light" in device_id or "lamp" in device_id or "main" in device_id:
        return "灯"
    if "curtain" in device_id or "blind" in device_id or "cover" in device_id:
        return "窗帘"
    if "music" in device_id or "media" in device_id:
        return "音乐"
    if "fan" in device_id:
        return "风扇"
    if "lock" in device_id or "door" in device_id:
        return "门锁"
    if "vacuum" in device_id:
        return "扫地机器人"
    if "purifier" in device_id:
        return "空气净化器"
    if "humidifier" in device_id:
        return "加湿器"
    return device_id


def _action_to_zh(action: dict) -> str:
    """把 homekgmas plan.selected_actions 里的一条动作翻成中文人话。"""
    dev = _device_label(str(action.get("device_id", "")))
    attr = str(action.get("attribute", "")).lower()
    val = action.get("value")
    if attr == "power":
        return f"打开{dev}" if val else f"关闭{dev}"
    if attr == "brightness":
        try:
            return f"{dev}亮度 {int(val)}%"
        except Exception:
            return f"{dev}亮度 {val}"
    if attr in ("target_temperature", "temperature"):
        return f"{dev}调到 {val} 度"
    if attr == "fan_speed":
        return f"{dev}风速 {val}"
    if attr == "mode":
        return f"{dev}切到{_MODE_ZH.get(str(val), str(val))}模式"
    if attr == "volume":
        return f"{dev}音量 {val}"
    if attr == "playlist":
        return f"{dev}换成 {val} 歌单"
    if attr == "position":
        pos = {"open": "拉开", "closed": "关上", "half": "半开"}
        return f"{dev}{pos.get(str(val), str(val))}"
    if attr == "locked":
        return f"{dev}上锁" if val else f"{dev}解锁"
    if attr == "humidity":
        return f"{dev}湿度 {val}%"
    if attr == "input_source":
        return f"{dev}切到 {val}"
    if attr == "color":
        return f"{dev}调成{val}色调"
    return f"{dev}.{attr}={val}"


def _coalesce_actions(actions: list) -> list[str]:
    """同一设备的 power=true + brightness/温度/音量 合并成一句更自然的中文。"""
    by_device: dict[str, list[dict]] = {}
    order: list[str] = []
    for a in actions:
        dev = str(a.get("device_id") or "")
        if dev not in by_device:
            order.append(dev)
            by_device[dev] = []
        by_device[dev].append(a)

    phrases: list[str] = []
    for dev in order:
        acts = by_device[dev]
        attr_to_val = {str(a.get("attribute", "")).lower(): a.get("value") for a in acts}
        label = _device_label(dev)

        # 关闭：power=false 单独表述
        if attr_to_val.get("power") is False:
            phrases.append(f"关闭{label}")
            continue

        # 收集主调整词 (亮度/温度/音量/歌单/位置/锁)
        primary_bits: list[str] = []
        if "brightness" in attr_to_val:
            try:
                primary_bits.append(f"亮度 {int(attr_to_val['brightness'])}%")
            except Exception:
                primary_bits.append(f"亮度 {attr_to_val['brightness']}")
        if "target_temperature" in attr_to_val:
            primary_bits.append(f"{attr_to_val['target_temperature']} 度")
        elif "temperature" in attr_to_val:
            primary_bits.append(f"{attr_to_val['temperature']} 度")
        if "fan_speed" in attr_to_val:
            primary_bits.append(f"风速 {attr_to_val['fan_speed']}")
        if "volume" in attr_to_val:
            primary_bits.append(f"音量 {attr_to_val['volume']}")
        if "playlist" in attr_to_val:
            primary_bits.append(f"切到 {attr_to_val['playlist']} 歌单")
        if "mode" in attr_to_val:
            m = str(attr_to_val["mode"])
            primary_bits.append(f"{_MODE_ZH.get(m, m)}模式")
        if "position" in attr_to_val:
            pos = {"open": "拉开", "closed": "关上", "half": "半开"}.get(str(attr_to_val["position"]), str(attr_to_val["position"]))
            primary_bits.append(pos)
        if "humidity" in attr_to_val:
            primary_bits.append(f"湿度 {attr_to_val['humidity']}%")
        if "color" in attr_to_val:
            primary_bits.append(f"色调 {attr_to_val['color']}")

        if attr_to_val.get("locked") is True:
            phrases.append(f"{label}上锁"); continue
        if attr_to_val.get("locked") is False:
            phrases.append(f"{label}解锁"); continue

        if primary_bits:
            # power=true 有主调整时直接省略"打开"，更口语
            phrases.append(f"{label} {'，'.join(primary_bits)}")
        elif attr_to_val.get("power") is True:
            phrases.append(f"打开{label}")
        else:
            # 兜底：用第一条原始 action
            phrases.append(_action_to_zh(acts[0]))
    return phrases


def _summarize_for_voice(result: dict) -> str:
    """从 homekgmas OrchestrationResult 构造一条 Chloe 可直接口播的中文句。"""
    if not isinstance(result, dict):
        return "好的，我处理一下。"
    plan = result.get("plan") or {}
    actions = plan.get("selected_actions") or []
    user_view = result.get("user_view") or {}
    scene_en = user_view.get("scene_label") or ""
    scene_zh = _SCENE_ZH.get(scene_en, "")

    if not actions:
        return "我和家里的几位智能体讨论了一下，目前没有需要立刻调整的，你想怎么调直接告诉我就好。"

    phrases = _coalesce_actions(actions)
    head = phrases[:5]
    rest = max(0, len(phrases) - 5)
    listing = "、".join(head)
    if rest:
        listing += f"，还有 {rest} 项也一起做了"

    if scene_zh and len(phrases) >= 3:
        return f"按{scene_zh}给你准备好啦：{listing}。"
    if len(phrases) >= 2:
        return f"调好啦：{listing}。"
    return f"好，{listing}。"


def _summarize_devices_for_voice(device_result: dict) -> str:
    """从 device_llm classify 返回（含 plans）构造中文口播句。"""
    plans = (device_result or {}).get("plans") or []
    if not plans:
        return "没有识别到需要调整的设备。"
    appliance_zh = {"ac": "空调", "light": "灯", "computer": "电脑", "screen": "电脑"}
    phrases: list[str] = []
    for p in plans:
        if not p.get("execute") or not p.get("mentioned"):
            continue
        label = appliance_zh.get(str(p.get("appliance", "")).lower(), str(p.get("label", "")))
        for a in p.get("actions") or []:
            params = a.get("params") or {}
            action = str(a.get("action", "")).lower()
            if action == "set_temp":
                phrases.append(f"{label}调到 {params.get('temp', 24)} 度")
            elif action == "set_mode":
                m = params.get("mode", "")
                phrases.append(f"{label}切到{_MODE_ZH.get(m, m)}模式")
            elif action == "set_brightness":
                phrases.append(f"{label}亮度 {params.get('brightness', 80)}%")
            elif action == "power":
                phrases.append(f"打开{label}" if params.get("on", True) else f"关闭{label}")
            elif action == "set_fan":
                phrases.append(f"{label}风速 {params.get('fan', 'auto')}")
            elif action == "dim":
                phrases.append(f"{label}调暗")
            elif action == "brighten":
                phrases.append(f"{label}调亮")
            else:
                phrases.append(f"{label} {action}")
    if not phrases:
        return "已经按你的命令处理好了。"
    return "、".join(phrases) + "，搞定。"


def _synthesize_english_intent(plans: list) -> str:
    """把 device_llm 返回的 plans 翻成英文意图描述，用来唤醒 homekgmas 的 agents。"""
    if not plans:
        return ""
    parts: list[str] = []
    for p in plans:
        if not p.get("execute") or not p.get("mentioned"):
            continue
        appliance = (p.get("appliance") or "").lower()
        for a in p.get("actions") or []:
            params = a.get("params") or {}
            action = (a.get("action") or "").lower()
            if appliance == "ac":
                if action == "set_temp":
                    parts.append(f"Set the air conditioner to {params.get('temp', 24)} degrees Celsius")
                elif action == "set_mode":
                    mode = params.get("mode", "cool")
                    if mode == "cool":
                        parts.append("Switch the air conditioner to cooling mode")
                    elif mode == "heat":
                        parts.append("Switch the air conditioner to heating mode")
                    else:
                        parts.append(f"Switch the air conditioner to {mode} mode")
                elif action == "power":
                    on = params.get("on", True)
                    parts.append("Turn on the air conditioner" if on else "Turn off the air conditioner")
                elif action == "set_fan":
                    parts.append(f"Set the air conditioner fan speed to {params.get('fan', 'auto')}")
            elif appliance == "light":
                if action == "set_brightness":
                    b = params.get("brightness", 80)
                    parts.append(f"Adjust the lighting brightness to {b} percent")
                elif action == "power":
                    on = params.get("on", True)
                    parts.append("Turn on the lights" if on else "Turn off the lights")
                elif action == "dim":
                    parts.append("Dim the lights")
                elif action == "brighten":
                    parts.append("Brighten the lights")
            elif appliance in ("computer", "screen", "display"):
                if action == "power":
                    on = params.get("on", True)
                    parts.append("Turn on the computer" if on else "Turn off the computer")
                elif action == "set_mode":
                    mode = params.get("mode", "")
                    parts.append(f"Set the computer to {mode} mode" if mode else "Adjust the computer")
    return "; ".join(parts)


async def _relay_device_intent_to_dashboard(input_text: str, device_result: dict) -> None:
    """把设备命令以多 agent 讨论的形式送进 homekgmas，让 dashboard 也能看到。

    description = "<原话> (intent: <英文摘要>)"
      - 原话保留在用户气泡里，符合"我说话进 dashboard"的体验
      - 英文摘要让 homekgmas 的 wakeup keyword 能匹配到对应 agent
    """
    if not device_result or not device_result.get("success"):
        return
    plans = device_result.get("plans") or []
    english_intent = _synthesize_english_intent(plans)
    if not english_intent:
        return  # 没有可执行设备动作，不发空气泡

    description = f"{input_text} (intent: {english_intent})"
    base = os.getenv("HOMEKGMAS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    endpoint = f"{base}/api/v1/tasks/external"

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(
            endpoint,
            json={"description": description, "source": "xiaozhi"},
        ) as resp:
            if resp.status != 200:
                err = await resp.text()
                logger.warning(f"relay -> homekgmas failed [{resp.status}]: {err}")
            else:
                logger.info(f"relay -> homekgmas ok: {english_intent}")


@mcp.tool()
async def discuss_in_dashboard(input_text: str) -> dict:
    """
    把用户原话送进 homekgmas 多智能体讨论流，触发 dashboard 实时显示讨论 + 决策气泡。

    【何时调用】
    用户用自然语言描述"想要的家居氛围/场景/状态"，希望多个 agent 协商决策时调用。例如：
      - "把客厅调成晚间放松的样子"
      - "进入观影模式"
      - "我要专注工作"
      - "早上好，开启早晨场景"
      - "和家里讨论一下要不要开空调"

    【何时不调用】
    单一明确的设备开关/调档命令应继续走 classify_devices，例如：
      - "打开空调" / "灯调到 30%" / "关闭电脑"

    【链路】
    本工具 → POST http://127.0.0.1:8000/api/v1/tasks/external
       → homekgmas 触发 OrchestrationResult
       → 同时通过 SSE 推到 dashboard，前端播气泡

    Args:
        input_text: 用户原话（中文或英文均可）

    Returns:
        {
            "success": bool,
            "summary": "决策摘要",
            "result": {...}  # 完整 OrchestrationResult
        }
    """
    base = os.getenv("HOMEKGMAS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    endpoint = f"{base}/api/v1/tasks/external"

    session = None
    try:
        session = aiohttp.ClientSession()
        logger.info(f"调用多智能体讨论: {endpoint} | 输入: {input_text}")

        async with session.post(
            endpoint,
            json={"description": input_text, "source": "xiaozhi"},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                err = await resp.text()
                logger.error(f"多智能体讨论失败 [{resp.status}]: {err}")
                return {"success": False, "error": f"HTTP {resp.status}: {err}"}

            data = await resp.json()
            user_view = (data.get("user_view") or {})
            actions = ((data.get("plan") or {}).get("selected_actions") or [])
            summary = user_view.get("summary") or f"已规划 {len(actions)} 个动作"
            voice_reply = _summarize_for_voice(data)
            logger.info(f"多智能体讨论成功: {summary}  voice='{voice_reply}'")
            return {
                "success": True,
                "voice_reply": voice_reply,
                "summary": summary,
                "result": data,
            }

    except asyncio.TimeoutError:
        logger.error("多智能体讨论超时 (120s)")
        return {"success": False, "error": "讨论超时 (120s)"}
    except Exception as e:
        logger.error(f"多智能体讨论异常: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass


if __name__ == "__main__":
    import sys

    # 设置日志
    if sys.platform == 'win32':
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 启动MCP服务器
    mcp.run(transport="stdio")
