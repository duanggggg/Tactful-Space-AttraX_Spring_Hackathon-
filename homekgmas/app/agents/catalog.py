"""Dataset-driven agent catalogs for fusion and web execution modes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# 中文关键词映射，让中文用户输入也能直接唤醒对应 agent。
# wakeup_manager 用 substring 匹配，所以这里的词直接出现在用户原话里即可。
# 包含两类：
#   1) 设备词（"空调"、"灯"、"音乐" 等）
#   2) 场景词（"睡觉"、"观影"、"专注" 等）—— 投到逻辑相关的 agent 上
_ZH_KEYWORDS: dict[str, list[str]] = {
    "cooling_agent": [
        "空调", "冷气", "制冷", "制热", "温度", "凉", "冷", "热",
        "调温", "降温", "升温", "暖气", "太热", "太冷", "闷", "闷热",
        # 场景含义（睡觉时调温、晚间舒适等）
        "睡觉", "入睡", "晚间", "晚上", "下班", "回家", "到家",
        # 业务/社交场景：希望环境舒适
        "客户", "客人", "来宾", "迎接", "招待", "会客", "会议", "开会",
        "演示", "汇报", "报告", "展示", "demo",
    ],
    "lighting_agent": [
        "灯", "灯光", "照明", "亮度", "灯泡", "台灯", "主灯", "吊灯",
        "调亮", "调暗", "开灯", "关灯", "刺眼",
        # 场景含义
        "放松", "慵懒", "舒缓", "晚间", "晚上", "睡觉", "早晨", "早上",
        "起床", "观影", "看电影", "看片", "专注", "工作", "学习", "写邮件",
        "看书", "阅读", "下班", "回家", "到家", "刚到", "累", "疲惫",
        # 业务/社交场景：通常需要明亮整洁
        "客户", "客人", "来宾", "朋友来了", "迎接", "招待", "会客",
        "会议", "开会", "演示", "汇报", "报告", "展示", "demo", "presentation",
        "准备", "整理", "收拾", "布置",
    ],
    "music_agent": [
        "音乐", "音量", "歌", "电视", "影音", "媒体", "静音",
        "声音", "播放", "播放列表", "歌单", "音响", "喇叭", "无聊",
        # 场景含义
        "放松", "慵懒", "晚间", "观影", "看电影", "下班", "回家",
        # 业务/社交场景：可能需要背景音/静音
        "客户", "客人", "来宾", "朋友来了", "招待", "会客",
        "会议", "开会", "演示", "汇报", "demo",
    ],
    "fan_agent": [
        "风扇", "电扇", "风", "通风", "凉风", "摇头", "风量",
        "闷", "闷热", "空气流通",
    ],
    "cover_agent": [
        "窗帘", "卷帘", "百叶", "遮阳", "拉开", "拉上", "遮光",
        # 场景含义
        "睡觉", "入睡", "早晨", "起床", "观影", "看电影",
        # 业务/社交：演示/会客时调遮阳避免反光
        "演示", "汇报", "demo", "会议", "刺眼", "强光",
    ],
    "lock_agent": [
        "锁", "门锁", "上锁", "解锁", "安防", "警报", "门",
        "出门", "回家", "布防", "撤防", "客户来了",
    ],
    "switch_agent": [
        "净化器", "加湿器", "除湿", "湿度", "空气净化", "干燥", "新风",
        # 业务/社交：会议前希望空气清新
        "客户", "会议", "演示", "demo", "招待",
    ],
    "appliance_agent": [
        "扫地机", "扫地机器人", "吸尘器", "清洁", "扫地", "拖地",
        # 业务/社交：客户来访前打扫
        "整理", "收拾", "打扫", "干净", "客户", "客人", "来宾", "迎接",
    ],
}


def _with_zh(agent_name: str, english_keywords: list[str]) -> list[str]:
    """Combine the existing English keyword hints with the Chinese keyword set for that agent."""
    return [*english_keywords, *_ZH_KEYWORDS.get(agent_name, [])]


class AgentActionProfile(BaseModel):
    """One runtime action-space profile for a domain agent."""

    agent_name: str
    mode: str = "fusion"
    description: str = ""
    source_datasets: list[str] = Field(default_factory=list)
    task_sources: list[str] = Field(default_factory=list)
    device_domains: list[str] = Field(default_factory=list)
    service_names: list[str] = Field(default_factory=list)
    argument_keys: list[str] = Field(default_factory=list)
    keyword_hints: list[str] = Field(default_factory=list)
    slot_hints: list[str] = Field(default_factory=list)
    allowed_devices: dict[str, list[str]] = Field(default_factory=dict)
    examples: list[str] = Field(default_factory=list)

    def action_targets(self) -> dict[str, set[str]]:
        """Return the allowed device/attribute pairs as sets."""

        return {
            device_id: {str(attribute) for attribute in attributes}
            for device_id, attributes in self.allowed_devices.items()
        }

    def allowed_operations(self) -> list[str]:
        """Return a stable flattened list of allowed device.attribute operations."""

        operations: list[str] = []
        for device_id, attributes in sorted(self.allowed_devices.items()):
            for attribute in sorted({str(attribute) for attribute in attributes}):
                operations.append(f"{device_id}.{attribute}")
        return operations

    def prompt_payload(self) -> dict[str, Any]:
        """Return a compact prompt-visible catalog payload."""

        return {
            "mode": self.mode,
            "description": self.description,
            "source_datasets": self.source_datasets,
            "task_sources": self.task_sources,
            "device_domains": self.device_domains,
            "service_names": self.service_names,
            "argument_keys": self.argument_keys,
            "keyword_hints": self.keyword_hints,
            "slot_hints": self.slot_hints,
            "allowed_devices": self.allowed_devices,
            "examples": self.examples[:3],
        }


class AgentCatalog(BaseModel):
    """Runtime catalog for one agent mode."""

    mode: str = "fusion"
    profiles: dict[str, AgentActionProfile] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def profile_for(self, agent_name: str) -> AgentActionProfile | None:
        """Return one agent profile if available."""

        return self.profiles.get(agent_name)

    def operation_listing(self) -> dict[str, list[str]]:
        """Return the flattened operation list for every agent."""

        return {
            agent_name: profile.allowed_operations()
            for agent_name, profile in self.profiles.items()
        }


def _default_fusion_profiles() -> dict[str, AgentActionProfile]:
    return {
        "cooling_agent": AgentActionProfile(
            agent_name="cooling_agent",
            description="Fusion-data climate controller for AC temperature, mode, and fan settings.",
            source_datasets=["smartsense", "edgewisepersona", "home_assistant_datasets"],
            task_sources=["user_nl", "routine", "automation", "inferred"],
            device_domains=["climate"],
            service_names=["turn_on", "turn_off", "set_temperature", "custom"],
            argument_keys=["temperature", "fan_speed", "mode", "state", "target_temperature"],
            keyword_hints=_with_zh("cooling_agent", ["cool", "cooling", "ac", "air conditioner", "temperature", "warm", "hot", "climate"]),
            slot_hints=["climate", "temperature", "target_temperature", "fan_speed", "mode"],
            allowed_devices={
                "living_room_ac_1": ["power", "target_temperature", "fan_speed", "mode"],
                "bedroom_ac_1": ["power", "target_temperature", "fan_speed", "mode"],
            },
            examples=["set AC to 22 C", "turn on bedroom AC", "change climate mode to cool"],
        ),
        "lighting_agent": AgentActionProfile(
            agent_name="lighting_agent",
            description="Fusion-data light controller for power, brightness, and scene attributes.",
            source_datasets=["smartsense", "edgewisepersona", "home_assistant_datasets"],
            task_sources=["user_nl", "routine", "automation"],
            device_domains=["light"],
            service_names=["turn_on", "turn_off", "set_brightness", "custom"],
            argument_keys=["brightness", "color", "mode", "state"],
            keyword_hints=_with_zh("lighting_agent", ["light", "lamp", "brightness", "bright", "dim", "scene", "reading", "color"]),
            slot_hints=["light", "brightness", "color", "mode"],
            allowed_devices={
                "living_room_main": ["power", "brightness", "color", "mode"],
                "bedroom_lamp": ["power", "brightness", "color", "mode"],
            },
            examples=["turn off the kitchen light", "set bedroom lamp brightness to 30", "make the lights neutral"],
        ),
        "music_agent": AgentActionProfile(
            agent_name="music_agent",
            description="Fusion-data media controller for shared speakers, TV-like media intent, and volume/input changes.",
            source_datasets=["smartsense", "edgewisepersona", "home_assistant_datasets"],
            task_sources=["user_nl", "routine", "inferred"],
            device_domains=["media_player"],
            service_names=["play", "pause", "stop", "custom", "turn_on", "turn_off"],
            argument_keys=["playlist", "volume", "volume_level", "input_source", "equalizer", "media_track", "state"],
            keyword_hints=_with_zh("music_agent", [
                "music",
                "playlist",
                "speaker",
                "volume",
                "television",
                "tv",
                "settop",
                "media",
                "movie",
                "netflix",
                "mute",
                "playback",
                "channel",
            ]),
            slot_hints=["media_player", "playlist", "volume", "input_source", "equalizer", "media_track"],
            allowed_devices={
                "music_player": ["power", "playlist", "volume", "input_source", "brightness", "equalizer", "media_track"],
            },
            examples=["turn the volume down to 50", "switch TV input to Netflix", "play calm music"],
        ),
        "fan_agent": AgentActionProfile(
            agent_name="fan_agent",
            description="Fusion-data fan controller for speed and oscillation decisions.",
            source_datasets=["smartsense", "edgewisepersona", "home_assistant_datasets"],
            task_sources=["user_nl", "routine", "inferred"],
            device_domains=["fan"],
            service_names=["turn_on", "turn_off", "custom"],
            argument_keys=["speed", "oscillate", "state"],
            keyword_hints=_with_zh("fan_agent", ["fan", "breeze", "circulation", "ventilation", "stuffy", "oscillate", "airflow"]),
            slot_hints=["fan", "speed", "oscillate"],
            allowed_devices={
                "living_room_fan_1": ["power", "speed", "oscillate"],
                "bedroom_fan_1": ["power", "speed", "oscillate"],
            },
            examples=["turn on the bedroom fan", "set fan speed to low", "enable oscillation"],
        ),
        "cover_agent": AgentActionProfile(
            agent_name="cover_agent",
            description="Fusion-data cover controller for curtains and blinds.",
            source_datasets=["smartsense", "home_assistant_datasets"],
            task_sources=["user_nl", "automation", "routine"],
            device_domains=["cover"],
            service_names=["open", "close", "custom"],
            argument_keys=["position", "current_position", "state"],
            keyword_hints=_with_zh("cover_agent", ["curtain", "blind", "shade", "privacy", "glare", "sunlight", "open", "close"]),
            slot_hints=["cover", "position", "current_position"],
            allowed_devices={
                "living_room_curtain": ["position"],
                "bedroom_blinds": ["position"],
            },
            examples=["close the blinds", "open the curtain halfway", "reduce glare in the living room"],
        ),
        "lock_agent": AgentActionProfile(
            agent_name="lock_agent",
            description="Fusion-data security controller for locks and alarm-like settings.",
            source_datasets=["edgewisepersona", "home_assistant_datasets"],
            task_sources=["user_nl", "routine", "automation"],
            device_domains=["lock"],
            service_names=["lock", "unlock", "custom"],
            argument_keys=["locked", "armed", "alarm_volume", "state"],
            keyword_hints=_with_zh("lock_agent", ["lock", "unlock", "door", "entry", "security", "secure", "alarm", "armed", "disarm"]),
            slot_hints=["lock", "armed", "alarm_volume", "security"],
            allowed_devices={
                "front_door_lock": ["locked", "armed", "alarm_volume"],
            },
            examples=["lock the front door", "arm the home security", "reduce alarm volume"],
        ),
        "switch_agent": AgentActionProfile(
            agent_name="switch_agent",
            description="Fusion-data auxiliary-device controller for purifier, humidifier, and humidity-like parameters.",
            source_datasets=["smartsense", "zh_commands"],
            task_sources=["user_nl", "routine", "inferred"],
            device_domains=["switch", "other"],
            service_names=["turn_on", "turn_off", "set_humidity", "custom"],
            argument_keys=["mode", "humidity", "value", "attribute", "state"],
            keyword_hints=_with_zh("switch_agent", ["purifier", "humidifier", "humidity", "air quality", "fresh", "dry", "mist", "switch"]),
            slot_hints=["switch", "humidifier", "purifier", "humidity", "attribute", "value"],
            allowed_devices={
                "air_purifier": ["power", "mode", "humidity"],
                "bedroom_humidifier": ["power", "mode", "humidity"],
            },
            examples=["increase humidifier humidity", "turn on the air purifier", "set purifier mode to boost"],
        ),
        "appliance_agent": AgentActionProfile(
            agent_name="appliance_agent",
            description="Fusion-data appliance controller for robot vacuum-like helpers.",
            source_datasets=["smartsense", "home_assistant_datasets"],
            task_sources=["user_nl", "routine", "automation", "inferred"],
            device_domains=["appliance", "vacuum"],
            service_names=["start", "stop", "custom", "turn_on", "turn_off"],
            argument_keys=["mode", "status", "state"],
            keyword_hints=_with_zh("appliance_agent", ["vacuum", "clean", "robot", "appliance", "floor", "dock"]),
            slot_hints=["appliance", "vacuum", "mode", "status"],
            allowed_devices={
                "robot_vacuum_1": ["power", "mode", "status"],
            },
            examples=["start the robot vacuum", "dock the vacuum", "clean the floor"],
        ),
    }


def _default_web_profiles() -> dict[str, AgentActionProfile]:
    return {
        "cooling_agent": AgentActionProfile(
            agent_name="cooling_agent",
            mode="web",
            description="Web-environment climate controller with explicit thermostat actions only.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "automation", "routine"],
            device_domains=["climate"],
            service_names=["turn_on", "turn_off", "set_temperature"],
            argument_keys=["state", "target_temperature", "temperature", "mode"],
            keyword_hints=_with_zh("cooling_agent", ["ac", "air conditioner", "climate", "temperature", "cool", "heat"]),
            slot_hints=["climate", "temperature", "target_temperature", "mode"],
            allowed_devices={
                "living_room_ac_1": ["power", "target_temperature", "mode"],
                "bedroom_ac_1": ["power", "target_temperature", "mode"],
            },
            examples=["Turn on the AC", "Set the living room temperature to 24 C"],
        ),
        "lighting_agent": AgentActionProfile(
            agent_name="lighting_agent",
            mode="web",
            description="Web-environment lighting controller limited to explicit power and brightness changes.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "automation", "routine"],
            device_domains=["light"],
            service_names=["turn_on", "turn_off", "set_brightness"],
            argument_keys=["state", "brightness"],
            keyword_hints=_with_zh("lighting_agent", ["light", "lamp", "brightness", "dim", "bright"]),
            slot_hints=["light", "brightness"],
            allowed_devices={
                "living_room_main": ["power", "brightness"],
                "bedroom_lamp": ["power", "brightness"],
            },
            examples=["Turn off the bedroom lamp", "Set light brightness to 40"],
        ),
        "music_agent": AgentActionProfile(
            agent_name="music_agent",
            mode="web",
            description="Web-environment media controller for playback, source switching, and volume.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "routine"],
            device_domains=["media_player"],
            service_names=["turn_on", "turn_off", "play", "pause", "stop"],
            argument_keys=["state", "playlist", "volume", "input_source"],
            keyword_hints=_with_zh("music_agent", ["music", "speaker", "media", "tv", "volume", "playlist"]),
            slot_hints=["media_player", "volume", "playlist", "input_source"],
            allowed_devices={
                "music_player": ["power", "playlist", "volume", "input_source"],
            },
            examples=["Play jazz music", "Lower the speaker volume"],
        ),
        "fan_agent": AgentActionProfile(
            agent_name="fan_agent",
            mode="web",
            description="Web-environment fan controller for simple power and speed changes.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "routine"],
            device_domains=["fan"],
            service_names=["turn_on", "turn_off", "custom"],
            argument_keys=["state", "speed"],
            keyword_hints=_with_zh("fan_agent", ["fan", "airflow", "breeze"]),
            slot_hints=["fan", "speed"],
            allowed_devices={
                "living_room_fan_1": ["power", "speed"],
                "bedroom_fan_1": ["power", "speed"],
            },
            examples=["Turn on the fan", "Set the fan to low speed"],
        ),
        "cover_agent": AgentActionProfile(
            agent_name="cover_agent",
            mode="web",
            description="Web-environment curtain and blind controller with explicit position changes.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "automation", "routine"],
            device_domains=["cover"],
            service_names=["open", "close", "custom"],
            argument_keys=["position", "state"],
            keyword_hints=_with_zh("cover_agent", ["curtain", "blind", "shade", "open", "close"]),
            slot_hints=["cover", "position"],
            allowed_devices={
                "living_room_curtain": ["position"],
                "bedroom_blinds": ["position"],
            },
            examples=["Open the curtain", "Close the bedroom blinds"],
        ),
        "lock_agent": AgentActionProfile(
            agent_name="lock_agent",
            mode="web",
            description="Web-environment security controller for lock and unlock operations.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "automation", "routine"],
            device_domains=["lock"],
            service_names=["lock", "unlock"],
            argument_keys=["locked", "state"],
            keyword_hints=_with_zh("lock_agent", ["lock", "unlock", "door", "security"]),
            slot_hints=["lock", "security"],
            allowed_devices={
                "front_door_lock": ["locked"],
            },
            examples=["Lock the front door", "Unlock the door"],
        ),
        "switch_agent": AgentActionProfile(
            agent_name="switch_agent",
            mode="web",
            description="Web-environment helper-device controller for purifier and humidifier toggles or modes.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "routine"],
            device_domains=["switch"],
            service_names=["turn_on", "turn_off", "custom"],
            argument_keys=["state", "mode"],
            keyword_hints=_with_zh("switch_agent", ["purifier", "humidifier", "switch", "air purifier"]),
            slot_hints=["switch", "purifier", "humidifier", "mode"],
            allowed_devices={
                "air_purifier": ["power", "mode"],
                "bedroom_humidifier": ["power", "mode"],
            },
            examples=["Turn on the purifier", "Set the humidifier mode to sleep"],
        ),
        "appliance_agent": AgentActionProfile(
            agent_name="appliance_agent",
            mode="web",
            description="Web-environment appliance controller for robot vacuum start and stop behavior.",
            source_datasets=["web_ui", "web_collected"],
            task_sources=["user_nl", "automation", "routine"],
            device_domains=["appliance", "vacuum"],
            service_names=["start", "stop", "turn_on", "turn_off"],
            argument_keys=["state", "status"],
            keyword_hints=_with_zh("appliance_agent", ["vacuum", "robot", "clean", "dock"]),
            slot_hints=["vacuum", "appliance", "status"],
            allowed_devices={
                "robot_vacuum_1": ["power", "status"],
            },
            examples=["Start the robot vacuum", "Stop the vacuum"],
        ),
    }


def default_agent_catalog(mode: str = "fusion") -> AgentCatalog:
    """Return the built-in catalog for the requested mode."""

    if mode == "fusion":
        return AgentCatalog(
            mode="fusion",
            profiles=_default_fusion_profiles(),
            metadata={"fallback": True, "notes": "Built-in fusion catalog used because no generated catalog was found."},
        )
    if mode == "web":
        return AgentCatalog(
            mode="web",
            profiles=_default_web_profiles(),
            metadata={"fallback": True, "notes": "Built-in web catalog used because no generated catalog was found."},
        )
    return AgentCatalog(mode=mode, profiles={})


def _inject_zh_keywords(profiles: dict[str, AgentActionProfile]) -> dict[str, AgentActionProfile]:
    """Merge Chinese keyword hints into each loaded profile so wakeup matches Chinese input.

    Idempotent: only adds keywords that aren't already present.
    """
    for agent_name, profile in profiles.items():
        zh = _ZH_KEYWORDS.get(agent_name) or []
        if not zh:
            continue
        existing = set(profile.keyword_hints)
        merged = list(profile.keyword_hints)
        for word in zh:
            if word not in existing:
                merged.append(word)
                existing.add(word)
        profile.keyword_hints = merged
    return profiles


def load_agent_catalog(*, mode: str, catalog_path: Path | None) -> AgentCatalog:
    """Load one agent catalog from disk, falling back to built-ins when needed."""

    if catalog_path is None or not catalog_path.exists():
        return default_agent_catalog(mode=mode)

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return default_agent_catalog(mode=mode)

    profiles_payload = payload.get("profiles", {})
    profiles = {
        agent_name: AgentActionProfile.model_validate(profile_payload)
        for agent_name, profile_payload in profiles_payload.items()
        if isinstance(profile_payload, dict)
    }
    if not profiles:
        return default_agent_catalog(mode=mode)

    profiles = _inject_zh_keywords(profiles)

    return AgentCatalog(
        mode=str(payload.get("mode") or mode),
        profiles=profiles,
        metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
    )
