"""Mouse multiplataforma: geometria validada, clique temporal e emissão isolados."""

from dataclasses import dataclass, replace
import math
from queue import Empty, Full, Queue
from threading import Event, Thread
import time
from typing import Protocol

MOVE_INTERVAL = 1 / 15
TRACKING_TIMEOUT = 0.500
FIST_CONFIRM = 0.250
RELEASE_CONFIRM = 0.200

from .gestures import GestureEvent


@dataclass(frozen=True, slots=True)
class HandTracking:
    index: tuple[float, float]


def extract_tracking(result, aspect: float) -> HandTracking | None:
    """Usa só a primeira mão; valida geometria após os limiares do MediaPipe.

    Mantém a validação geométrica da 0.4; o clique não calcula mais pinças.
    """
    if not result.hand_landmarks:
        return None
    hand = result.hand_landmarks[0]
    if len(hand) != 21 or not math.isfinite(aspect) or aspect <= 0:
        return None
    if any(not math.isfinite(p.x) or not math.isfinite(p.y)
           or not 0 <= p.x <= 1 or not 0 <= p.y <= 1 for p in hand):
        return None
    palm = math.hypot((hand[0].x - hand[9].x) * aspect, hand[0].y - hand[9].y)
    if palm < 0.03:
        return None
    return HandTracking((hand[8].x, hand[8].y))


class CoordinateMapper:
    def __init__(self, size, *, margin=0.12, smoothing=0.25, mirrored_input=True):
        if min(size) < 2 or not 0 <= margin < 0.5 or not 0 < smoothing <= 1:
            raise ValueError("Tela, margem ou suavizacao invalida")
        self.size, self.margin, self.alpha = size, margin, smoothing
        self.mirrored_input = mirrored_input
        self.previous = None

    def reset(self):
        self.previous = None

    def map(self, point):
        x, y = point
        # app.py já espelha antes da inferência: não inverter novamente nesse caso.
        if not self.mirrored_input:
            x = 1 - x
        span = 1 - 2 * self.margin
        target = tuple(max(0.0, min(1.0, (v - self.margin) / span)) * (size - 1)
                       for v, size in zip((x, y), self.size))
        if self.previous is None:
            self.previous = target
        else:
            self.previous = tuple(old + self.alpha * (new - old)
                                  for old, new in zip(self.previous, target))
        return tuple(max(0, min(size - 1, round(v))) for v, size in zip(self.previous, self.size))


class FistClickDetector:
    """250 ms contínuos para clicar; saída aceita por 200 ms para rearmar.

    Oscilações curtas após o clique não rearmam. Antes dele, qualquer perda de
    validade reinicia os 250 ms. Ausência de tracking exige nova mão aberta.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.armed = self.ever_armed = self.freeze = False
        self.since = self.exit_since = None
        self.status = "AGUARDANDO ABERTURA"
        self.progress = 0.0

    def update(self, name, now):
        self.progress = 0.0
        if name == "Closed_Fist":
            self.exit_since = None
            self.freeze = True
            if self.armed:
                if self.since is None:
                    self.since = now
                self.progress = min(1, max(0, (now - self.since) / FIST_CONFIRM))
                self.status = "CONFIRMANDO"
                if now - self.since + 1e-9 >= FIST_CONFIRM:
                    self.armed = False
                    self.since = None
                    self.status = "CLIQUE"
                    return True
            else:
                self.status = "AGUARDANDO ABERTURA"
            return False
        self.since = None
        # 'None'/baixa confiança não é abertura, nem prova de que o punho saiu.
        accepted_exit = name in ("Open_Palm", "Thumb_Up", "Thumb_Down")
        if accepted_exit and (self.ever_armed or name == "Open_Palm"):
            if self.exit_since is None:
                self.exit_since = now
            if now - self.exit_since + 1e-9 >= RELEASE_CONFIRM:
                self.armed = self.ever_armed = True
                self.freeze = False
        else:
            self.exit_since = None
        self.status = "PRONTO" if self.armed and not self.freeze else "AGUARDANDO ABERTURA"
        return False


class MouseBackend(Protocol):
    size: tuple[int, int] | None
    error: str | None

    def activate(self): ...
    def poll(self): ...
    def submit(self, x: int, y: int, click: bool) -> bool: ...
    def suspend(self): ...
    def close(self): ...


from .backends.x11_mouse import X11MouseBackend  # compatibilidade de importação
from .backends import create_mouse_backend


class AsyncMouseBackend:
    """Worker único e no máximo um pedido; descarta pedidos cancelados/antigos."""

    def __init__(self, factory=None):
        self.factory = factory or create_mouse_backend
        self.size = self.error = self.position = None
        self._jobs, self._results = Queue(maxsize=1), Queue(maxsize=1)
        self._allowed, self._stop = Event(), Event()
        self._generation = 0
        self._thread = None
        self._busy = False

    def activate(self):
        self._allowed.set()
        if self._thread is None:
            self._thread = Thread(target=self._worker, name="mouse-output", daemon=True)
            self._busy = True
            self._thread.start()

    def _worker(self):
        backend = None
        try:
            backend = self.factory()
            self._results.put((backend.size, None, None))
            while not self._stop.is_set():
                job = self._jobs.get()
                if job is None:
                    break
                x, y, click, generation, submitted = job
                allowed = lambda: (self._allowed.is_set() and not self._stop.is_set()
                                   and generation == self._generation
                                   and time.monotonic() - submitted < 0.150)
                position = backend.apply(x, y, click, allowed) if allowed() else None
                self._results.put((backend.size, position, None))
        except Exception as exc:
            self._allowed.clear()
            self._results.put((None, None, str(exc)))
        finally:
            if backend is not None:
                backend.close()

    def poll(self):
        try:
            self.size, position, self.error = self._results.get_nowait()
            if position is not None:
                self.position = position
            self._busy = False
        except Empty:
            pass

    def submit(self, x, y, click):
        if self._busy or self.size is None or self.error or self._stop.is_set():
            return False
        self._allowed.set()
        try:
            self._jobs.put_nowait((x, y, click, self._generation, time.monotonic()))
        except Full:
            return False
        self._busy = True
        return True

    def suspend(self):
        self._allowed.clear()
        self._generation += 1

    def close(self):
        self.suspend()
        self._stop.set()
        try:
            self._jobs.put_nowait(None)
        except Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=0.25)
        # Se o servidor travar, daemon e autorização revogada impedem bloquear a saída.


@dataclass(frozen=True, slots=True)
class MouseState:
    permitted: bool = True
    active: bool = False
    status: str = "DESATIVADO"
    position: tuple[int, int] | None = None
    screen_size: tuple[int, int] | None = None
    click_status: str = "AGUARDANDO ABERTURA"
    click_progress: float = 0.0
    margin: float = 0.12
    error: str | None = None


class MouseController:
    def __init__(self, *, permitted=True, backend=None, margin=0.12, smoothing=0.25):
        self.state = MouseState(permitted=permitted, margin=margin)
        self.backend = backend
        self.margin, self.smoothing = margin, smoothing
        self.mapper = None
        self.click = FistClickDetector()
        self._click_due = False
        self.last_seen = self.last_move = self.last_frame = None

    def disable(self):
        self.state = replace(self.state, active=False, status="DESATIVADO", click_progress=0, click_status="AGUARDANDO ABERTURA")
        self.click.reset()
        self._click_due = False
        if self.mapper:
            self.mapper.reset()
        if self.backend:
            self.backend.suspend()

    def handle_key(self, key):
        if key == 27:
            self.disable()
        elif key in (ord("m"), ord("M")) and self.state.permitted:
            if self.state.active:
                self.disable()
            else:
                if self.backend is not None and self.backend.error:
                    self.backend.close()
                    self.backend = None
                if self.backend is None:
                    self.backend = AsyncMouseBackend()
                if self.backend.error:
                    self.state = replace(self.state, error=self.backend.error)
                    return
                self.backend.activate()
                self.click.reset()
                self._click_due = False
                self.last_seen = self.last_move = self.last_frame = None
                self.state = replace(self.state, active=True, status="INICIANDO", error=None)

    def update(self, tracking: HandTracking | None, event: GestureEvent | None = None, *, now=None):
        now = time.monotonic() if now is None else now
        if not self.state.permitted or self.backend is None:
            return
        self.backend.poll()
        self.state = replace(self.state, position=getattr(self.backend, "position", None) or self.state.position)
        if self.backend.error:
            self.disable()
            self.state = replace(self.state, error=self.backend.error)
            return
        if not self.state.active:
            return
        if self.last_frame is not None and now - self.last_frame > TRACKING_TIMEOUT:
            self.click.reset()
            self._click_due = False
            if self.mapper:
                self.mapper.reset()
            self.backend.suspend()
        self.last_frame = now
        if tracking is None:
            self.click.reset()
            self._click_due = False
            self.backend.suspend()
            if self.last_seen is not None and now - self.last_seen > TRACKING_TIMEOUT and self.mapper:
                self.mapper.reset()
            self.state = replace(self.state, status="SEM MAO", click_status="AGUARDANDO ABERTURA", click_progress=0)
            return
        self.last_seen = now
        if self.backend.size is None:
            return
        if self.mapper is None or self.mapper.size != self.backend.size:
            self.mapper = CoordinateMapper(self.backend.size, margin=self.margin, smoothing=self.smoothing)
        name = event.name if event is not None else None
        if name != "Closed_Fist" and self._click_due:
            self._click_due = False
            self.backend.suspend()
        if self.click.update(name, now):
            self._click_due = True
        # Invalida movimentos antigos ao começar a fechar a mão.
        if self.click.freeze and self.state.status == "MOVENDO":
            self.backend.suspend()
        status = "PARADO" if self.click.freeze else "MOVENDO"
        if self.last_move is None or now - self.last_move + 1e-9 >= MOVE_INTERVAL:
            if self._click_due or not self.click.freeze:
                point = self.state.position or (0, 0)
                if not self._click_due:
                    point = self.mapper.map(tracking.index)
                if self.backend.submit(*point, self._click_due):
                    self.last_move = now
                    if self._click_due:
                        self._click_due = False
                        status = "CLIQUE"
        self.state = replace(self.state, status=status, screen_size=self.backend.size,
                             click_status=self.click.status, click_progress=self.click.progress)

    def close(self):
        self.disable()
        if self.backend:
            self.backend.close()
