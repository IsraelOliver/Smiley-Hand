"""Geometria e renderização sem abrir webcam ou janela gráfica."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hand_control.gestures import GestureEvent
from hand_control.render import display_layout, draw_overlay, get_display_size
from hand_control.virtual_led import LedState
from hand_control.volume_control import VolumeState

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None


class LayoutTests(unittest.TestCase):
    def test_camera_fits_wide_tall_and_small_windows_without_distortion(self):
        for size in ((960, 720), (1280, 720), (400, 900), (160, 120), (1, 1)):
            for source in ((320, 240), (640, 480), (640, 360)):
                with self.subTest(size=size, source=source):
                    (x, y, width, height), header, footer = display_layout(source, size)
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, header)
                    self.assertLessEqual(x + width, size[0])
                    self.assertLessEqual(y + height, size[1] - footer)
                    # Tolerância de um pixel por dimensão devido ao arredondamento.
                    self.assertLessEqual(abs(width - height * source[0] / source[1]),
                                         1 + source[0] / source[1])


@unittest.skipIf(cv2 is None, "OpenCV/NumPy indisponíveis")
class RenderTests(unittest.TestCase):
    def test_display_size_and_landmarks_preserve_inference_image(self):
        source = np.full((240, 320, 3), 60, dtype=np.uint8)
        hand = [SimpleNamespace(x=0.5, y=0.5) for _ in range(21)]
        result = SimpleNamespace(hand_landmarks=[hand], gestures=[[
            SimpleNamespace(category_name="Open_Palm", score=0.934)
        ]])
        event = GestureEvent("Open_Palm", 0.934, 100)
        for size in ((960, 720), (1200, 600), (360, 800), (1, 1)):
            with self.subTest(size=size):
                display = draw_overlay(source, result, event, display_size=size)
                self.assertEqual(display.shape, (size[1], size[0], 3))
                self.assertTrue(np.all(source == 60))
                if size != (1, 1):
                    (x, y, width, height), _, _ = display_layout((320, 240), size)
                    point = display[y + height // 2, x + width // 2]
                    np.testing.assert_array_equal(point, (0, 180, 255))

    def test_absence_and_unknown_gesture_render_without_landmark_errors(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for hands in ([], [[SimpleNamespace(x=0, y=0) for _ in range(21)]]):
            with self.subTest(hands=bool(hands)):
                display = draw_overlay(frame, SimpleNamespace(hand_landmarks=hands, gestures=[]),
                                       GestureEvent(None, 0, 101))
                self.assertEqual(display.shape, (720, 960, 3))

    def test_overlay_shows_raw_score_and_limit_for_each_diagnostic_state(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        hand = [SimpleNamespace(x=0.5, y=0.5) for _ in range(21)]
        cases = (
            ([], [], "Nenhuma mao detectada", "sem classificacao", "--"),
            ([hand], [], "Mao detectada: gesto None ou desconhecido", "sem classificacao", "--"),
            ([hand], [("None", 0.91)], "Mao detectada: gesto None ou desconhecido", "None", "91.0%"),
            ([hand], [("Open_Palm", 0.43)], "Gesto conhecido: confianca abaixo do limite", "Open_Palm", "43.0%"),
            ([hand], [("Closed_Fist", 0.9)], "Gesto aceito: Closed_Fist", "Closed_Fist", "90.0%"),
            ([hand], [("Victory", 0.9)], "Gesto conhecido: fora dos habilitados", "Victory", "90.0%"),
        )
        for hands, categories, status, raw_name, score in cases:
            with self.subTest(status=status, raw=raw_name):
                result = SimpleNamespace(hand_landmarks=hands, gestures=[[
                    SimpleNamespace(category_name=name, score=value) for name, value in categories
                ]])
                event = GestureEvent("Closed_Fist" if raw_name == "Closed_Fist" else None, 0, 100)
                with patch("hand_control.render._put_text") as text:
                    draw_overlay(frame, result, event, threshold=0.65)
                labels = [call.args[1] for call in text.call_args_list]
                self.assertEqual(labels[0], status)
                self.assertEqual(labels[1], f"Bruto: {raw_name}  |  Confianca: {score}")
                self.assertEqual(labels[2], "Limite: 65.0% (--threshold 0.65)")

    def test_minimized_and_unsupported_window_keep_previous_size(self):
        for rect in ((10, 10, 1200, 700), (0, 0, 0, 0)):
            with patch.object(cv2, "getWindowImageRect", return_value=rect):
                expected = rect[2:] if rect[2] else (960, 720)
                self.assertEqual(get_display_size("test"), expected)
        with patch.object(cv2, "getWindowImageRect", side_effect=cv2.error("unsupported")):
            self.assertEqual(get_display_size("test", (800, 600)), (800, 600))

    def test_volume_feedback_and_bar(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        result = SimpleNamespace(hand_landmarks=[], gestures=[])
        cases = (
            VolumeState(available=True, percent=55, error=None,
                        last_command="Volume +5% -> 55%", pending_gesture="Thumb_Up", progress=1),
            VolumeState(available=True, percent=0, error=None, pending_gesture="Thumb_Down", progress=0.5),
            VolumeState(error="wpctl: saida nao encontrada"),
            VolumeState(enabled=False, error=None),
        )
        for state in cases:
            for size in ((960, 720), (320, 240), (400, 900)):
                with self.subTest(state=state, size=size):
                    with patch("hand_control.render._put_text") as text:
                        display = draw_overlay(frame, result, GestureEvent(None, 0, 0),
                                               volume_state=state, display_size=size)
                    labels = [call.args[1] for call in text.call_args_list]
                    self.assertTrue(any(label.startswith("VOLUME:") for label in labels))
                    if state.error:
                        self.assertIn(f"Audio indisponivel: {state.error}", labels)
                    if state.pending_gesture:
                        self.assertTrue(any(state.pending_gesture in label for label in labels))
                    if not state.enabled:
                        self.assertTrue(any("nenhum acesso" in label for label in labels))
                    if state.percent == 55:
                        _, _, footer = display_layout((320, 240), size)
                        y = round(size[1] - footer + footer * 0.28)
                        np.testing.assert_array_equal(display[y, size[0] // 4], (255, 185, 75))
                        np.testing.assert_array_equal(display[y, size[0] * 3 // 4], (55, 60, 65))

    def test_led_states_are_visible_in_resized_windows(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        result = SimpleNamespace(hand_landmarks=[], gestures=[])
        event = GestureEvent(None, 0, 0)
        for size in ((960, 720), (1280, 720), (360, 800), (320, 240)):
            for on in (False, True):
                with self.subTest(size=size, on=on):
                    with patch("hand_control.render._put_text") as text:
                        display = draw_overlay(frame, result, event, display_size=size,
                                               led_state=LedState(on=on))
                    labels = [call.args[1] for call in text.call_args_list]
                    self.assertIn("LED: LIGADO" if on else "LED: DESLIGADO", labels)
                    self.assertIn("Confirmando: --", labels)
                    _, header, _ = display_layout((320, 240), size)
                    scale = max(0.05, min(size[0] / 960, size[1] / 720))
                    radius = max(1, min(round(15 * scale), size[0] // 8, header // 12))
                    x, y = max(1, round(22 * scale)) + radius, round(header * 0.69)
                    pixel = display[y, x]
                    if on:
                        # O reflexo suavizado pode clarear o centro em tamanhos pequenos.
                        self.assertEqual(pixel[1], 255)
                        self.assertGreater(int(pixel[1]), int(pixel[0]))
                        self.assertGreater(int(pixel[1]), int(pixel[2]))
                    else:
                        np.testing.assert_array_equal(pixel, (55, 60, 65))

    def test_confirmation_name_and_progress_bar(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        result = SimpleNamespace(hand_landmarks=[], gestures=[])
        with patch("hand_control.render._put_text") as text:
            display = draw_overlay(frame, result, GestureEvent(None, 0, 0),
                                   led_state=LedState(False, "Open_Palm", 0.5))
        self.assertIn("Confirmando: Open_Palm (50%)",
                      [call.args[1] for call in text.call_args_list])
        _, header, _ = display_layout((320, 240), (960, 720))
        bar_y = round(header * 0.95)
        np.testing.assert_array_equal(display[bar_y, 100], (90, 230, 170))
        np.testing.assert_array_equal(display[bar_y, 800], (55, 60, 65))
