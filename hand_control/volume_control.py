"""Áudio: backend limitado, regras temporais e uma única operação assíncrona."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import math
import os
import re
import shutil
import subprocess
import time

from .gestures import GestureEvent

CONFIRM_SECONDS = 0.400
REPEAT_SECONDS = 0.700
COMMAND_TIMEOUT = 1.0
POLL_SECONDS = 2.0


class AudioError(RuntimeError):
    pass


class AudioBackend:
    """Chamadas síncronas, usadas somente pelo worker; nunca usa shell/sudo."""

    def __init__(self, executable: str, kind: str):
        self.executable = executable
        self.kind = kind
        self.sink = "@DEFAULT_AUDIO_SINK@" if kind == "wpctl" else "@DEFAULT_SINK@"

    @classmethod
    def detect(cls):
        for kind in ("wpctl", "pactl"):
            executable = shutil.which(kind)
            if executable:
                return cls(executable, kind)
        raise AudioError("wpctl e pactl nao encontrados")

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                [self.executable, *args], shell=False, check=True,
                capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
                env={**os.environ, "LC_ALL": "C"},
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioError(f"{self.kind}: timeout de {COMMAND_TIMEOUT:g}s") from exc
        except subprocess.CalledProcessError as exc:
            detail = ((exc.stderr or "").strip() or "saida de audio indisponivel").splitlines()[-1]
            raise AudioError(f"{self.kind}: {detail[:160]}") from exc
        except OSError as exc:
            raise AudioError(f"{self.kind}: {exc}") from exc
        return result.stdout

    def read(self) -> float:
        if self.kind == "wpctl":
            output = self._run("get-volume", self.sink)
            match = re.search(r"Volume:\s*([0-9]+(?:\.[0-9]+)?)", output)
            values = [float(match[1]) * 100] if match else []
        else:
            output = self._run("get-sink-volume", self.sink)
            # Usa o maior canal; o ajuste absoluto mantém todos <= 100%.
            values = [float(value) for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)%", output)]
        if not values or not all(math.isfinite(value) for value in values):
            raise AudioError(f"{self.kind}: resposta de volume invalida")
        return max(values)

    def adjust(self, delta: int) -> tuple[float, str | None]:
        if delta not in (-5, 5):
            raise ValueError("O passo de volume deve ser +5 ou -5")
        current = self.read()
        target = max(0.0, min(100.0, current + delta))
        if abs(target - current) < 1e-6:
            return current, None
        percent = f"{target:g}%"
        if self.kind == "wpctl":
            self._run("set-volume", "-l", "1.0", self.sink, percent)
        else:
            self._run("set-sink-volume", self.sink, percent)
        actual = self.read()
        return actual, f"Volume {'+5%' if delta > 0 else '-5%'} -> {actual:.0f}%"


class VolumeGestureGate:
    """Regra temporal pura; recebe eventos já aceitos por to_event."""

    def __init__(self):
        self.gesture = None
        self.since = None
        self.last_issue = None
        self.progress = 0.0

    def update(self, event: GestureEvent, now: float, *, ready: bool = True) -> int | None:
        if event.name not in ("Thumb_Up", "Thumb_Down"):
            self.gesture = self.since = None
            self.progress = 0.0
            return None
        if self.gesture != event.name:
            self.gesture, self.since = event.name, now
        elapsed = max(0.0, now - self.since)
        self.progress = min(1.0, elapsed / CONFIRM_SECONDS)
        if not ready or elapsed + 1e-9 < CONFIRM_SECONDS:
            return None
        if self.last_issue is not None and now - self.last_issue + 1e-9 < REPEAT_SECONDS:
            return None
        self.last_issue = now
        return 5 if self.gesture == "Thumb_Up" else -5


@dataclass(frozen=True, slots=True)
class VolumeState:
    enabled: bool = True
    available: bool = False
    percent: float | None = None
    error: str | None = "Conectando ao audio"
    last_command: str | None = None
    pending_gesture: str | None = None
    progress: float = 0.0
    busy: bool = False


class VolumeController:
    """Uma thread, um Future no máximo, nenhuma fila de ajustes.

    update/poll nunca esperam por subprocessos. Desativado: nem detecta backend,
    nem cria thread, nem executa leituras/comandos.
    """

    def __init__(self, *, enabled=True, backend_factory=None):
        self.state = VolumeState(enabled=enabled,
                                 error="Conectando ao audio" if enabled else None)
        self.gate = VolumeGestureGate()
        self._factory = backend_factory or AudioBackend.detect
        self._backend = None
        self._future = None
        self._delta = None
        self._next_read = 0.0
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="volume") if enabled else None

    def _perform(self, delta):
        backend = self._backend or self._factory()
        percent, command = (backend.read(), None) if delta is None else backend.adjust(delta)
        return backend, percent, command

    def _submit(self, delta):
        self._delta = delta
        self._future = self._executor.submit(self._perform, delta)

    def update(self, event: GestureEvent, *, now=None):
        if not self.state.enabled or self._closed:
            return
        now = time.monotonic() if now is None else now
        if self._future is not None and self._future.done():
            try:
                self._backend, percent, command = self._future.result()
                self.state = replace(self.state, available=True, percent=percent, error=None,
                                     last_command=command or self.state.last_command)
            except Exception as exc:
                self.state = replace(self.state, available=False, percent=None, error=str(exc))
                self._backend = None
            if self._delta is not None:
                # Mede também desde a conclusão: subprocessos lentos não causam rajadas.
                self.gate.last_issue = now
            self._future = None
            self._next_read = now + POLL_SECONDS
        delta = self.gate.update(event, now,
                                 ready=self.state.available and self._future is None)
        if delta is not None:
            self._submit(delta)
        elif self._future is None and now >= self._next_read:
            self._submit(None)
        self.state = replace(self.state, pending_gesture=self.gate.gesture,
                             progress=self.gate.progress, busy=self._future is not None)

    def close(self):
        self._closed = True
        if self._executor is not None:
            # Apenas na saída; cada chamada é limitada por COMMAND_TIMEOUT.
            self._executor.shutdown(wait=True, cancel_futures=True)
