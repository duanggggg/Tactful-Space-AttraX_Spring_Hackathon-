"""Home simulator facade that can use an embedded or remote dynamic environment."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import AppSettings
from app.core.utils import utc_timestamp
from app.environment.dynamic_environment import DynamicHomeEnvironment
from app.environment.home_state import HomeState
from app.planning.action import PlannedAction
from app.planning.plan import ExecutedAction, ExecutionPlan, ExecutionResult


class SimulatorBackend(Protocol):
    """Backend protocol used by the orchestration layer."""

    def get_home_state(self) -> HomeState:
        """Return the current full home state."""

    def apply_actions(self, actions: list[PlannedAction]) -> HomeState:
        """Apply actions and return the updated state."""


class EmbeddedSimulatorBackend:
    """In-process dynamic simulator backend."""

    def __init__(self, environment: DynamicHomeEnvironment) -> None:
        self.environment = environment

    def get_home_state(self) -> HomeState:
        return self.environment.get_home_state()

    def apply_actions(self, actions: list[PlannedAction]) -> HomeState:
        return self.environment.apply_actions(actions)

    def reset(self) -> HomeState:
        return self.environment.reset()


class RemoteSimulatorBackend:
    """HTTP client that talks to the standalone simulator service."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_home_state(self) -> HomeState:
        response = httpx.get(
            f"{self.base_url}/api/state",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return HomeState(
            sensors=payload["sensors"],
            devices=payload["devices"],
            outdoor=payload["outdoor"],
        )

    def apply_actions(self, actions: list[PlannedAction]) -> HomeState:
        response = httpx.post(
            f"{self.base_url}/api/actions",
            json={"actions": [action.model_dump(mode="json") for action in actions]},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return HomeState(
            sensors=payload["sensors"],
            devices=payload["devices"],
            outdoor=payload["outdoor"],
        )


class HomeSimulator:
    """Coordinates state reads and device updates for the local environment."""

    def __init__(self, backend: SimulatorBackend) -> None:
        self.backend = backend

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "HomeSimulator":
        if settings.simulator_mode == "remote":
            backend: SimulatorBackend = RemoteSimulatorBackend(
                base_url=settings.simulator_api_base,
                timeout_seconds=settings.simulator_request_timeout_seconds,
            )
        else:
            backend = EmbeddedSimulatorBackend(
                DynamicHomeEnvironment.from_config_paths(
                    sensors_config_path=settings.sensors_config_path,
                    devices_config_path=settings.devices_config_path,
                    simulator_config_path=settings.simulator_config_path,
                )
            )
        return cls(backend=backend)

    def get_home_state(self) -> HomeState:
        return self.backend.get_home_state()

    def reset(self) -> HomeState:
        reset_method = getattr(self.backend, "reset", None)
        if callable(reset_method):
            return reset_method()
        return self.get_home_state()

    def apply_overrides(
        self,
        sensors: dict | None = None,
        outdoor: dict | None = None,
        devices: dict | None = None,
    ) -> HomeState:
        """Forward override request to the backend if it supports it."""
        env = getattr(self.backend, "environment", None)
        target = env if env is not None else self.backend
        apply = getattr(target, "apply_overrides", None)
        if callable(apply):
            return apply(sensors=sensors, outdoor=outdoor, devices=devices)
        return self.get_home_state()

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        applied_at = utc_timestamp()
        try:
            updated_state = self.backend.apply_actions(plan.selected_actions)
            applied_actions = [
                ExecutedAction(
                    **action.model_dump(mode="json"),
                    status="applied",
                    applied_at=applied_at,
                )
                for action in plan.selected_actions
            ]
            return ExecutionResult(
                success=True,
                applied_actions=applied_actions,
                state_snapshot=updated_state.model_dump(mode="json"),
                notes=[
                    "Executed against the dynamic home simulator",
                    f"Simulator backend: {self.backend.__class__.__name__}",
                ],
            )
        except Exception as exc:
            failed_actions = [
                ExecutedAction(
                    **action.model_dump(mode="json"),
                    status="failed",
                    applied_at=applied_at,
                    failure_reason=str(exc),
                )
                for action in plan.selected_actions
            ]
            return ExecutionResult(
                success=False,
                applied_actions=failed_actions,
                state_snapshot={},
                notes=[
                    "Execution failed in the dynamic home simulator",
                    str(exc),
                ],
            )
