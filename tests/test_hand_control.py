"""Testes de lógica e falhas; usam doubles, não validam inferência real."""

from contextlib import redirect_stderr
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError
import zipfile

from hand_control import app
from hand_control.__main__ import main, parse_args
from hand_control.camera import open_camera
from hand_control.detector import HandDetector
from hand_control.gestures import diagnose, to_event
from hand_control.model import download_model, validate_model


def result_for(name=None, score=0.9):
    return SimpleNamespace(
        gestures=[[SimpleNamespace(category_name=name, score=score)]] if name else [],
        hand_landmarks=[],
    )


class GestureTests(unittest.TestCase):
    def test_supported_gestures_preserve_confidence(self):
        for name in ("Open_Palm", "Closed_Fist", "Thumb_Up", "Thumb_Down"):
            with self.subTest(name=name):
                event = to_event(result_for(name), 123, 0.6)
                self.assertEqual((event.name, event.confidence, event.timestamp_ms), (name, 0.9, 123))

    def test_other_gestures_and_low_confidence_do_not_emit_commands(self):
        for name, score in (("Victory", 0.99), ("None", 0.95), ("Open_Palm", 0.59),
                            ("Thumb_Up", 0.59), ("Thumb_Down", 0.59)):
            with self.subTest(name=name, score=score):
                event = to_event(result_for(name, score), 123, 0.6)
                self.assertIsNone(event.name)
                self.assertEqual(event.confidence, 0)

    def test_missing_hand_clears_previous_gesture(self):
        self.assertIsNone(to_event(result_for(), 124, 0.6).name)


class DiagnosticTests(unittest.TestCase):
    def test_no_hand_is_distinct_from_unknown_gesture(self):
        result = result_for()
        self.assertEqual(diagnose(result, 0.6).state, "no_hand")
        result.hand_landmarks = [object()]
        diagnostic = diagnose(result, 0.6)
        self.assertEqual(diagnostic.state, "unknown")
        self.assertIsNone(diagnostic.raw_name)
        self.assertIsNone(diagnostic.raw_confidence)

    def test_none_and_unknown_categories_keep_raw_score(self):
        for name in ("None", "Unknown", "New_Category", "", None):
            with self.subTest(name=name):
                result = SimpleNamespace(
                    gestures=[[SimpleNamespace(category_name=name, score=0.91)]],
                    hand_landmarks=[object()],
                )
                diagnostic = diagnose(result, 0.6)
                self.assertEqual(diagnostic.state, "unknown")
                self.assertEqual(diagnostic.raw_name, name)
                self.assertEqual(diagnostic.raw_confidence, 0.91)

    def test_low_confidence_preserves_raw_gesture_without_accepting_event(self):
        for name in ("Open_Palm", "Closed_Fist"):
            with self.subTest(name=name):
                result = result_for(name, 0.43)
                result.hand_landmarks = [object()]
                diagnostic = diagnose(result, 0.6)
                self.assertEqual(diagnostic.state, "below_threshold")
                self.assertEqual(diagnostic.raw_name, name)
                self.assertEqual(diagnostic.raw_confidence, 0.43)
                self.assertEqual(diagnostic.threshold, 0.6)
                self.assertIsNone(to_event(result, 123, 0.6).name)

    def test_threshold_boundary_and_custom_limit(self):
        result = result_for("Open_Palm", 0.6)
        result.hand_landmarks = [object()]
        self.assertEqual(diagnose(result, 0.6).state, "recognized")
        self.assertEqual(diagnose(result, 0.61).state, "below_threshold")
        result.gestures[0][0].score = 0.0
        self.assertEqual(diagnose(result, 0).state, "recognized")
        result.gestures[0][0].score = 1.0
        self.assertEqual(diagnose(result, 1).state, "recognized")

    def test_other_model_gestures_are_not_misreported_as_unknown(self):
        result = result_for("Victory", 0.95)
        result.hand_landmarks = [object()]
        diagnostic = diagnose(result, 0.6)
        self.assertEqual(diagnostic.state, "unsupported")
        self.assertEqual(diagnostic.raw_name, "Victory")
        self.assertIsNone(to_event(result, 123, 0.6).name)

    def test_empty_category_list_does_not_crash(self):
        result = SimpleNamespace(gestures=[[]], hand_landmarks=[object()])
        self.assertEqual(diagnose(result, 0.6).state, "unknown")


class ConfigurationTests(unittest.TestCase):
    def test_no_volume_control_flag(self):
        self.assertFalse(parse_args([]).no_volume_control)
        self.assertTrue(parse_args(["--no-volume-control"]).no_volume_control)
        with patch.object(app, "run") as run:
            self.assertEqual(main(["--no-volume-control"]), 0)
            self.assertFalse(run.call_args.kwargs["volume_control"])

    def test_custom_threshold_from_cli(self):
        self.assertEqual(parse_args(["--threshold", "0.45"]).threshold, 0.45)

    def test_rejects_excessive_resolution_fps_and_invalid_threshold(self):
        for args in (["--width", "1280"], ["--height", "720"], ["--fps", "0"],
                     ["--fps", "60"], ["--threshold", "nan"], ["--camera", "-1"]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    parse_args(args)
                self.assertEqual(error.exception.code, 2)

    def test_inference_timestamps_strictly_increase(self):
        # Exercita a proteção contra timestamps iguais/regressivos sem carregar o modelo.
        detector = HandDetector.__new__(HandDetector)
        detector._mp = MagicMock()
        detector._recognizer = MagicMock()
        detector._last_timestamp = -1
        for timestamp in (10, 10, 9):
            detector.recognize(object(), timestamp)
        self.assertEqual(
            [call.args[1] for call in detector._recognizer.recognize_for_video.call_args_list],
            [10, 11, 12],
        )


class CameraTests(unittest.TestCase):
    def test_unavailable_camera_is_released(self):
        cv2 = MagicMock()
        capture = cv2.VideoCapture.return_value
        capture.isOpened.return_value = False
        with patch.dict("sys.modules", {"cv2": cv2}):
            with self.assertRaisesRegex(RuntimeError, "/dev/video3"):
                open_camera(3, 640, 480, 15)
        capture.release.assert_called_once()

    def run_fake_camera(self, read_result, key=ord("q"), threshold=0.6, volume_enabled=True):
        cv2 = MagicMock()
        cv2.waitKey.return_value = key
        cv2.getWindowProperty.return_value = 1
        capture = MagicMock()
        capture.read.return_value = read_result
        detector = MagicMock()
        detector.recognize.return_value = result_for("Open_Palm")
        sink = MagicMock()
        with patch.dict("sys.modules", {"cv2": cv2}), \
             patch.dict("os.environ", {"DISPLAY": ":0"}), \
             patch.object(app, "open_camera", return_value=capture), \
             patch.object(app, "validate_model"), \
             patch.object(app, "HandDetector", return_value=detector), \
             patch.object(app, "VolumeController") as volume, \
             patch.object(app, "draw_overlay") as overlay:
            try:
                app.run(model_path=Path("fake.task"), camera=0, width=640, height=480,
                        fps=15, threshold=threshold, sink=sink, volume_control=volume_enabled)
                self.assertEqual(overlay.call_args.kwargs["threshold"], threshold)
                volume.assert_called_once_with(enabled=volume_enabled)
                volume.return_value.close.assert_called_once()
            finally:
                capture.release.assert_called_once()
                detector.close.assert_called_once()
                cv2.destroyAllWindows.assert_called_once()
        return sink

    def test_disconnected_camera_releases_resources(self):
        with self.assertRaisesRegex(RuntimeError, "não entregou imagens"):
            self.run_fake_camera((False, None))

    def test_q_closes_and_publishes_event(self):
        for key in (ord("q"), ord("Q")):
            with self.subTest(key=key):
                frame = SimpleNamespace(shape=(480, 640, 3), size=640 * 480 * 3)
                sink = self.run_fake_camera((True, frame), key)
                self.assertEqual(sink.handle.call_args.args[0].name, "Open_Palm")

    def test_custom_threshold_is_forwarded_to_display(self):
        frame = SimpleNamespace(shape=(480, 640, 3), size=640 * 480 * 3)
        self.run_fake_camera((True, frame), threshold=0.85)

    def test_disabled_volume_is_forwarded_to_controller(self):
        frame = SimpleNamespace(shape=(480, 640, 3), size=640 * 480 * 3)
        self.run_fake_camera((True, frame), volume_enabled=False)


class ModelTests(unittest.TestCase):
    def test_corrupted_model_is_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "model.task"
            path.write_text("arquivo incompleto")
            with self.assertRaisesRegex(RuntimeError, "Modelo inválido"):
                validate_model(path)

    def test_valid_existing_bundle_does_not_download_again(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "model.task"
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("hand_landmarker.task", b"test double")
                bundle.writestr("hand_gesture_recognizer.task", b"test double")
            with patch("hand_control.model.urlopen") as request:
                download_model(path)
                request.assert_not_called()

    def test_failed_download_leaves_no_partial_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "model.task"
            with patch("hand_control.model.urlopen", side_effect=URLError("DNS")):
                with self.assertRaisesRegex(RuntimeError, "DNS"):
                    download_model(path)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix(".part").exists())


if __name__ == "__main__":
    unittest.main()
