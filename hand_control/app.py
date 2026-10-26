"""Loop de captura e apresentação, com uso limitado de CPU/memória."""

import os
from contextlib import ExitStack
import sys
from pathlib import Path
import time

from .camera import open_camera
from .detector import HandDetector
from .gestures import GestureSink, to_event
from .model import validate_model
from .render import DEFAULT_DISPLAY_SIZE, draw_overlay, get_display_size
from .virtual_led import LedOutput, VirtualLedController
from .volume_control import VolumeController
from .mouse_control import MouseController, extract_tracking

WINDOW = "Smiley-Hand 0.5"


def run(*, model_path: Path, camera: int, width: int, height: int,
        fps: int, threshold: float, sink: GestureSink | None = None,
        led_output: LedOutput | None = None, volume_control: bool = True,
        mouse_control: bool = True, mouse_margin: float = 0.12,
        mouse_smoothing: float = 0.25, enable_virtual_led: bool = False) -> None:
    # Antes de importar NumPy/MediaPipe: evita pools extras de BLAS/OpenMP.
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(variable, "1")
    if sys.platform == "win32":
        from .backends.windows_mouse import prepare_dpi
        prepare_dpi()
    elif not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("Nenhuma sessão gráfica disponível. Execute no terminal do desktop.")

    import cv2

    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    capture = open_camera(camera, width, height, fps)
    detector = None
    volume = None
    mouse = None
    window_created = False
    try:
        validate_model(model_path)
        detector = HandDetector(model_path)
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO | cv2.WINDOW_GUI_NORMAL)
        window_created = True
        cv2.resizeWindow(WINDOW, *DEFAULT_DISPLAY_SIZE)
        display_size = DEFAULT_DISPLAY_SIZE
        led = VirtualLedController(output=led_output) if enable_virtual_led else None
        volume = VolumeController(enabled=volume_control)
        mouse = MouseController(permitted=mouse_control and not enable_virtual_led,
                                margin=mouse_margin, smoothing=mouse_smoothing)
        print("Smiley-Hand 0.5 iniciado. M: mouse, ESC: desativar, Q: sair.", flush=True)
        while True:
            start = time.monotonic()
            success, frame = capture.read()
            if not success or frame is None or frame.size == 0:
                raise RuntimeError("A webcam abriu, mas não entregou imagens. Verifique se foi desconectada ou está ocupada.")
            actual_height, actual_width = frame.shape[:2]
            scale = min(1.0, width / actual_width, height / actual_height)
            if scale < 1:
                frame = cv2.resize(frame, (max(1, int(actual_width * scale)),
                                          max(1, int(actual_height * scale))),
                                   interpolation=cv2.INTER_AREA)
            cv2.flip(frame, 1, dst=frame)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            timestamp = time.monotonic_ns() // 1_000_000
            result = detector.recognize(rgb, timestamp)
            event = to_event(result, timestamp, threshold)
            if led is not None:
                led.update(event)
            volume.update(event)
            mouse.update(extract_tracking(result, frame.shape[1] / frame.shape[0]), event)
            if sink is not None:
                sink.handle(event)
            # Amplia apenas a apresentação, depois de concluir a inferência.
            display = draw_overlay(frame, result, event, display_size=display_size,
                                   threshold=threshold, led_state=led.state if led else None,
                                   volume_state=volume.state, mouse_state=mouse.state)
            cv2.imshow(WINDOW, display)
            # waitKey processa eventos da janela e limita o ritmo sem busy waiting.
            delay_ms = max(1, round((1 / fps - (time.monotonic() - start)) * 1000))
            key = cv2.waitKey(delay_ms) & 0xFF
            mouse.handle_key(key)
            if key in (ord("q"), ord("Q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            display_size = get_display_size(WINDOW, display_size)
    finally:
        # Todos os recursos são liberados mesmo se um callback de limpeza falhar.
        with ExitStack() as cleanup:
            if volume is not None:
                cleanup.callback(volume.close)
            if window_created:
                cleanup.callback(cv2.destroyAllWindows)
            if detector is not None:
                cleanup.callback(detector.close)
            cleanup.callback(capture.release)
            if mouse is not None:
                cleanup.callback(mouse.close)
