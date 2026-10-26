"""LED com confirmação temporal; independente de OpenCV e MediaPipe."""

from dataclasses import dataclass
from enum import Enum
import time
from typing import Protocol

from .gestures import GestureEvent

CONFIRMATION_SECONDS = 0.300


class LedCommand(Enum):
    ON = "ON"
    OFF = "OFF"


class LedOutput(Protocol):
    def send(self, command: LedCommand) -> None:
        """Envia uma mudança confirmada (futuro adaptador Arduino/ESP32)."""
        ...


@dataclass(frozen=True, slots=True)
class LedState:
    on: bool = False
    pending_gesture: str | None = None
    progress: float = 0.0


class VirtualLedController:
    """Recebe somente eventos já filtrados por to_event/confiança da aplicação.

    update não espera: usa monotonic por padrão, ou `now` em segundos para testes.
    O estado permanece retido após perda da mão ou classificação inválida.
    """

    def __init__(self, output: LedOutput | None = None):
        self.state = LedState()
        self._pending_since: float | None = None
        self._output = output

    def update(self, event: GestureEvent, *, now: float | None = None) -> LedCommand | None:
        now = time.monotonic() if now is None else now
        target = {"Open_Palm": True, "Closed_Fist": False}.get(event.name)
        if target is None or target == self.state.on:
            self._reset_confirmation()
            return None
        if self.state.pending_gesture != event.name:
            self._pending_since = now
        elapsed = max(0.0, now - self._pending_since)
        # Tolerância de 1 ns apenas para arredondamento da subtração de floats.
        if elapsed + 1e-9 < CONFIRMATION_SECONDS:
            self.state = LedState(self.state.on, event.name,
                                  min(1.0, elapsed / CONFIRMATION_SECONDS))
            return None
        command = LedCommand.ON if target else LedCommand.OFF
        if self._output is not None:
            self._output.send(command)
        self.state = LedState(on=target)
        self._pending_since = None
        return command

    def _reset_confirmation(self) -> None:
        self.state = LedState(on=self.state.on)
        self._pending_since = None
