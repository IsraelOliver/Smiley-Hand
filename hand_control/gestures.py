"""Eventos independentes da câmera, prontos para futuros adaptadores seriais."""

from dataclasses import dataclass
from typing import Protocol

SUPPORTED_GESTURES = frozenset({"Open_Palm", "Closed_Fist", "Thumb_Up", "Thumb_Down"})
KNOWN_GESTURES = SUPPORTED_GESTURES | {
    "Pointing_Up", "Thumb_Down", "Thumb_Up", "Victory", "ILoveYou",
}


@dataclass(frozen=True, slots=True)
class GestureDiagnostic:
    state: str
    raw_name: str | None
    raw_confidence: float | None
    threshold: float


def diagnose(result, threshold: float) -> GestureDiagnostic:
    """Descreve o resultado bruto sem aplicar filtros ou alterar eventos."""
    category = result.gestures[0][0] if result.gestures and result.gestures[0] else None
    name = category.category_name if category is not None else None
    confidence = float(category.score) if category is not None else None
    if not result.hand_landmarks:
        state = "no_hand"
    elif name not in KNOWN_GESTURES:
        state = "unknown"
    elif name not in SUPPORTED_GESTURES:
        state = "unsupported"
    elif confidence < threshold:
        state = "below_threshold"
    else:
        state = "recognized"
    return GestureDiagnostic(state, name, confidence, threshold)


@dataclass(frozen=True, slots=True)
class GestureEvent:
    name: str | None
    confidence: float
    timestamp_ms: int


class GestureSink(Protocol):
    def handle(self, event: GestureEvent) -> None:
        """Recebe cada observação, incluindo perda da mão (name=None)."""
        ...


def to_event(result, timestamp_ms: int, threshold: float) -> GestureEvent:
    if result.gestures and result.gestures[0]:
        category = result.gestures[0][0]
        if category.category_name in SUPPORTED_GESTURES and category.score >= threshold:
            return GestureEvent(category.category_name, float(category.score), timestamp_ms)
    return GestureEvent(None, 0.0, timestamp_ms)
