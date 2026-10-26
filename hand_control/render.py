"""Desenha diretamente com OpenCV; não depende de drawing_utils legacy."""

from .gestures import diagnose
from .virtual_led import LedState
from .volume_control import VolumeState
from .mouse_control import MouseState
import sys

DEFAULT_DISPLAY_SIZE = (960, 720)

CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)


def get_display_size(window, fallback=DEFAULT_DISPLAY_SIZE):
    """Dimensão da área de imagem; mantém a última se a janela for minimizada."""
    import cv2

    try:
        rect = cv2.getWindowImageRect(window)
        if len(rect) == 4 and rect[2] > 0 and rect[3] > 0:
            return int(rect[2]), int(rect[3])
    except cv2.error:
        # Alguns backends (por exemplo Wayland) não oferecem essa consulta.
        pass
    return fallback


def display_layout(source_size, display_size):
    """Calcula a região da câmera sem distorção, entre cabeçalho e rodapé."""
    width, height = display_size
    source_width, source_height = source_size
    header = min(height // 3, max(1, round(height * 0.30)))
    footer = min(height // 3, max(1, round(height * 0.32)))
    available_height = max(1, height - header - footer)
    scale = min(width / source_width, available_height / source_height)
    image_width = max(1, round(source_width * scale))
    image_height = max(1, round(source_height * scale))
    return ((width - image_width) // 2,
            header + (available_height - image_height) // 2,
            image_width, image_height), header, footer


def _put_text(frame, text, origin, scale, thickness, color, max_width):
    """Ajusta textos longos à largura, inclusive em janelas estreitas."""
    import cv2

    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, _), _ = cv2.getTextSize(text, font, scale, thickness)
    if text_width > max_width:
        scale *= max_width / text_width
    cv2.putText(frame, text, origin, font, scale, color, thickness, cv2.LINE_AA)


def draw_led_panel(canvas, state: LedState, header: int, ui_scale: float) -> None:
    """Indicador no cabeçalho: acompanha o tamanho da janela e não cobre a mão."""
    import cv2

    height, width = canvas.shape[:2]
    margin = max(1, round(22 * ui_scale))
    radius = max(1, min(round(15 * ui_scale), width // 8, header // 12))
    center = (min(width - 1, margin + radius), min(height - 1, round(header * 0.69)))
    color = (80, 255, 110) if state.on else (55, 60, 65)
    if state.on:
        cv2.circle(canvas, center, radius + max(1, round(4 * ui_scale)),
                   (35, 90, 45), -1, cv2.LINE_AA)
    cv2.circle(canvas, center, radius, color, -1, cv2.LINE_AA)
    if state.on:
        cv2.circle(canvas, (center[0] - radius // 3, center[1] - radius // 3),
                   max(1, radius // 4), (200, 255, 210), -1, cv2.LINE_AA)
    text_x = center[0] + radius + max(1, round(15 * ui_scale))
    text_width = max(1, width - text_x - margin)
    _put_text(canvas, "LED: LIGADO" if state.on else "LED: DESLIGADO",
              (text_x, min(height - 1, center[1] + round(7 * ui_scale))),
              0.8 * ui_scale, max(1, round(2 * ui_scale)),
              (90, 255, 150) if state.on else (185, 195, 205), text_width)
    pending = (f"Confirmando: {state.pending_gesture} ({state.progress:.0%})"
               if state.pending_gesture else "Confirmando: --")
    _put_text(canvas, pending, (margin, round(header * 0.89)),
              0.6 * ui_scale, max(1, round(ui_scale)), (200, 210, 220),
              max(1, width - 2 * margin))
    left, right = min(width - 1, margin), max(0, width - margin - 1)
    top, bottom = min(height - 1, round(header * 0.94)), min(height - 1, round(header * 0.97))
    if right > left:
        cv2.rectangle(canvas, (left, top), (right, bottom), (55, 60, 65), -1)
        if state.progress > 0:
            end = left + round((right - left) * min(1.0, max(0.0, state.progress)))
            cv2.rectangle(canvas, (left, top), (end, bottom), (90, 230, 170), -1)


def draw_volume_panel(canvas, state: VolumeState, footer: int, ui_scale: float):
    import cv2

    height, width = canvas.shape[:2]
    top = height - footer
    footer *= 0.57  # Reserva a parte inferior para o painel do mouse e as teclas.
    margin = max(1, round(22 * ui_scale))
    text_width = max(1, width - 2 * margin)
    percent = f"{state.percent:.0f}%" if state.percent is not None else "--"
    label = f"VOLUME: {percent}"
    if not state.enabled:
        label += "  (desativado)"
    _put_text(canvas, label, (margin, round(top + footer * 0.18)),
              0.7 * ui_scale, max(1, round(2 * ui_scale)), (245, 245, 245), text_width)
    right = max(0, width - margin - 1)
    bar_top, bar_bottom = round(top + footer * 0.26), round(top + footer * 0.30)
    if right > margin:
        cv2.rectangle(canvas, (margin, bar_top), (right, bar_bottom), (55, 60, 65), -1)
        if state.percent is not None and state.percent > 0:
            end = margin + round((right - margin) * min(100, max(0, state.percent)) / 100)
            cv2.rectangle(canvas, (margin, bar_top), (end, bar_bottom), (255, 185, 75), -1)
    feedback = "Audio: aguardando Thumb_Up / Thumb_Down"
    if state.pending_gesture:
        feedback = f"Audio: {state.pending_gesture} | confirmacao {state.progress:.0%}"
        if state.progress >= 1:
            feedback += " | " + ("operacao em curso" if state.busy else "intervalo 700 ms")
    if not state.enabled:
        feedback = "Audio desativado: --no-volume-control (nenhum acesso)"
    _put_text(canvas, feedback, (margin, round(top + footer * 0.49)),
              0.5 * ui_scale, max(1, round(ui_scale)), (200, 210, 220), text_width)
    detail = (f"Audio indisponivel: {state.error}" if state.error else
              f"Ultimo comando: {state.last_command or '--'}")
    _put_text(canvas, detail, (margin, round(top + footer * 0.70)),
              0.5 * ui_scale, max(1, round(ui_scale)),
              (90, 195, 255) if state.error else (185, 195, 205), text_width)


def draw_mouse_panel(canvas, state: MouseState, footer, ui_scale):
    height, width = canvas.shape[:2]
    top = height - footer
    margin = max(1, round(22 * ui_scale))
    text_width = max(1, width - 2 * margin)
    position = str(state.position) if state.position is not None else "--"
    label = f"MOUSE: {'ATIVADO' if state.active else 'DESATIVADO'} | Cursor: {position}"
    if not state.permitted:
        label = "MOUSE: DESATIVADO (--no-mouse-control)"
    _put_text(canvas, label, (margin, round(top + footer * 0.64)),
              0.6 * ui_scale, max(1, round(ui_scale)), (150, 230, 255), text_width)
    detail = f"Mouse: {state.error}" if state.error else f"Estado: {state.status}"
    if state.screen_size is not None:
        detail += f" | Tela: {state.screen_size[0]}x{state.screen_size[1]}"
    _put_text(canvas, detail, (margin, round(top + footer * 0.75)),
              0.5 * ui_scale, max(1, round(ui_scale)), (200, 210, 220), text_width)
    _put_text(canvas, f"Clique: {state.click_status} | {state.click_progress:.0%}",
              (margin, round(top + footer * 0.85)), 0.5 * ui_scale,
              max(1, round(ui_scale)), (185, 195, 205), text_width)


def draw_mouse_region(view, result, state):
    import cv2

    height, width = view.shape[:2]
    margin = state.margin
    color = (255, 200, 70) if state.active else (100, 110, 120)
    cv2.rectangle(view, (round((width - 1) * margin), round((height - 1) * margin)),
                  (round((width - 1) * (1 - margin)), round((height - 1) * (1 - margin))), color, 1)


def draw_overlay(frame, result, event, *, display_size=DEFAULT_DISPLAY_SIZE,
                 threshold=0.6, led_state: LedState | None = None,
                 volume_state: VolumeState = VolumeState(enabled=False, error=None),
                 mouse_state: MouseState = MouseState(permitted=False)):
    """Cria uma imagem de apresentação; não altera o quadro usado na inferência."""
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    display_width, display_height = display_size
    rect, header, footer = display_layout((width, height), display_size)
    left, top, image_width, image_height = rect
    canvas = np.full((display_height, display_width, 3), (18, 22, 28), dtype=np.uint8)
    view = canvas[top:top + image_height, left:left + image_width]
    # dst evita alocar outra imagem ampliada a cada quadro.
    cv2.resize(frame, (image_width, image_height), dst=view,
               interpolation=cv2.INTER_LINEAR if image_width >= width else cv2.INTER_AREA)
    ui_scale = max(0.05, min(display_width / 960, display_height / 720))
    line_width = max(1, round(2 * ui_scale))
    radius = max(1, round(4 * ui_scale))
    draw_mouse_region(view, result, mouse_state)
    for hand in result.hand_landmarks:
        points = [
            (max(0, min(image_width - 1, int(p.x * image_width))),
             max(0, min(image_height - 1, int(p.y * image_height))))
            for p in hand
        ]
        for start, end in CONNECTIONS:
            cv2.line(view, points[start], points[end], (70, 230, 110), line_width, cv2.LINE_AA)
        for point in points:
            cv2.circle(view, point, radius, (0, 180, 255), -1, cv2.LINE_AA)

    diagnostic = diagnose(result, threshold)
    labels = {
        "no_hand": "Nenhuma mao detectada",
        "unknown": "Mao detectada: gesto None ou desconhecido",
        "below_threshold": "Gesto conhecido: confianca abaixo do limite",
        "unsupported": "Gesto conhecido: fora dos habilitados",
        "recognized": f"Gesto aceito: {event.name}",
    }
    label = labels[diagnostic.state]
    raw_name = diagnostic.raw_name if diagnostic.raw_name is not None else "sem classificacao"
    raw_confidence = (f"{diagnostic.raw_confidence:.1%}"
                      if diagnostic.raw_confidence is not None else "--")
    raw_label = f"Bruto: {raw_name}  |  Confianca: {raw_confidence}"
    limit_label = f"Limite: {diagnostic.threshold:.1%} (--threshold {diagnostic.threshold:g})"
    status_color = ((90, 230, 170) if diagnostic.state == "recognized" else (90, 195, 255))
    # Fonte Hershey do OpenCV não renderiza acentos.
    margin = max(1, round(22 * ui_scale))
    text_width = max(1, display_width - 2 * margin)
    _put_text(canvas, label, (margin, round(header * (0.26 if led_state is not None else 0.36))),
              0.85 * ui_scale, max(1, round(2 * ui_scale)), status_color, text_width)
    _put_text(canvas, raw_label, (margin, round(header * (0.41 if led_state is not None else 0.60))),
              0.75 * ui_scale, line_width, (245, 245, 245), text_width)
    _put_text(canvas, limit_label, (margin, round(header * (0.55 if led_state is not None else 0.83))),
              0.65 * ui_scale, line_width, (185, 195, 205), text_width)
    system = "Windows" if sys.platform == "win32" else "Linux" if sys.platform.startswith("linux") else sys.platform
    _put_text(canvas, f"Smiley-Hand 0.5 | {system}", (margin, round(header * 0.12)),
              0.6 * ui_scale, line_width, (185, 195, 205), text_width)
    if led_state is not None:
        draw_led_panel(canvas, led_state, header, ui_scale)
    draw_volume_panel(canvas, volume_state, footer, ui_scale)
    draw_mouse_panel(canvas, mouse_state, footer, ui_scale)
    _put_text(canvas, "Q: sair | M: mouse | ESC: desativar mouse | Arraste a borda",
              (margin, display_height - max(1, round(footer * 0.08))),
              0.5 * ui_scale, max(1, round(ui_scale)), (185, 195, 205), text_width)
    return canvas
