"""Build diverse user questions from current home context."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.api.schemas import TaskRequest
from app.environment.home_state import HomeState


@dataclass(frozen=True)
class QuestionBlueprint:
    """One question template family tied to a high-level intent."""

    category: str
    template: str


class ContextQuestionBuilder:
    """Generate non-redundant user questions from home context."""

    def __init__(self) -> None:
        self.blueprints = [
            QuestionBlueprint("calm_scene", "It's {time_phrase}. Please make the living room feel calm with cooler air, softer lighting, and gentle music."),
            QuestionBlueprint("cooling_focus", "The living room feels warm around {time_phrase}. Can you cool it down without making the atmosphere too intense?"),
            QuestionBlueprint("lighting_focus", "Around {time_phrase}, the room feels {light_phrase}. Help me set better lighting for {activity_phrase}."),
            QuestionBlueprint("music_focus", "For {time_phrase}, could you choose background music that matches a {mood_phrase} mood without being distracting?"),
            QuestionBlueprint("energy_aware", "At {time_phrase}, please keep the living room comfortable but avoid unnecessary energy use."),
            QuestionBlueprint("quiet_hours", "It's {time_phrase} and I want the space restful. Adjust devices so the room stays comfortable without breaking quiet hours."),
            QuestionBlueprint("weather_blend", "With the weather {weather_phrase} outside this {time_phrase}, can you tune the room for a more balanced indoor scene?"),
            QuestionBlueprint("occupancy", "Someone is in the {occupied_room_phrase} during {time_phrase}. Please prepare the environment so it fits that room's current use."),
            QuestionBlueprint("reading_scene", "I want to read during {time_phrase}. Please adjust the room so it is comfortable, clear, and not overly harsh."),
            QuestionBlueprint("winddown", "Help me wind down this {time_phrase} with a quieter, softer room setup."),
            QuestionBlueprint("brightness_balance", "The outside light is {outdoor_light_phrase} right now. Can you rebalance the indoor scene for comfort?"),
            QuestionBlueprint("humidity_comfort", "The room feels a bit {humidity_phrase} this {time_phrase}. Please make the overall environment feel better."),
        ]

    def build_tasks_from_state(
        self,
        state: HomeState,
        *,
        count: int = 8,
        existing_texts: set[str] | None = None,
    ) -> list[TaskRequest]:
        """Generate a deduplicated list of task requests from one context snapshot."""

        existing_texts = existing_texts or set()
        candidates: list[str] = []
        for blueprint in self.blueprints:
            text = blueprint.template.format(
                time_phrase=self._time_phrase(state),
                light_phrase=self._light_phrase(state),
                activity_phrase=self._activity_phrase(state),
                mood_phrase=self._mood_phrase(state),
                weather_phrase=self._weather_phrase(state),
                occupied_room_phrase=self._occupied_room_phrase(state),
                outdoor_light_phrase=self._outdoor_light_phrase(state),
                humidity_phrase=self._humidity_phrase(state),
            )
            candidates.append(self._normalize_question(text))

        unique_questions: list[str] = []
        seen_keys = set(existing_texts)
        for question in candidates:
            key = self._question_key(question)
            if key in seen_keys:
                continue
            unique_questions.append(question)
            seen_keys.add(key)
            if len(unique_questions) >= count:
                break

        return [TaskRequest(description=question) for question in unique_questions]

    def _time_phrase(self, state: HomeState) -> str:
        if state.sensors.quiet_hours:
            return "late night"
        mapping = {
            "dawn": "early morning",
            "morning": "morning",
            "afternoon": "afternoon",
            "evening": "evening",
            "night": "night",
        }
        return mapping.get(state.sensors.time_of_day, "this time")

    def _light_phrase(self, state: HomeState) -> str:
        level = state.sensors.ambient_light_level
        if level < 25:
            return "too dim"
        if level > 70:
            return "too bright"
        return "a little flat"

    def _activity_phrase(self, state: HomeState) -> str:
        if state.sensors.quiet_hours:
            return "winding down"
        if state.sensors.time_of_day in {"morning", "afternoon"}:
            return "reading or focused work"
        return "relaxing"

    def _mood_phrase(self, state: HomeState) -> str:
        if state.sensors.quiet_hours:
            return "restful"
        if state.outdoor.weather in {"rainy", "cloudy"}:
            return "cozy"
        return "calm"

    def _weather_phrase(self, state: HomeState) -> str:
        return state.outdoor.weather.replace("_", " ")

    def _occupied_room_phrase(self, state: HomeState) -> str:
        occupied = [room.replace("_", " ") for room, value in state.sensors.occupancy.items() if value]
        return occupied[0] if occupied else "living room"

    def _outdoor_light_phrase(self, state: HomeState) -> str:
        level = state.outdoor.outdoor_light_level
        if level < 20:
            return "very low"
        if level < 55:
            return "moderate"
        return "strong"

    def _humidity_phrase(self, state: HomeState) -> str:
        if state.sensors.room_humidity_pct >= 65:
            return "humid"
        if state.sensors.room_humidity_pct <= 38:
            return "dry"
        return "stuffy"

    def _normalize_question(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        return cleaned if cleaned.endswith("?") or cleaned.endswith(".") else f"{cleaned}."

    def _question_key(self, text: str) -> str:
        lowered = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        return lowered
