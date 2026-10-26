"""MediaPipe Tasks GestureRecognizer, sem APIs legacy."""

from pathlib import Path


class HandDetector:
    def __init__(self, model_path: Path):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        self._mp = mp
        options = vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(
                model_asset_path=str(model_path),
                delegate=python.BaseOptions.Delegate.CPU,
            ),
            # Uma chamada por quadro, sem fila, resultados alinhados à imagem.
            # VIDEO também usa tracking em quadros sucessivos da webcam.
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._recognizer = vision.GestureRecognizer.create_from_options(options)
        self._last_timestamp = -1

    def recognize(self, rgb_frame, timestamp_ms: int):
        timestamp_ms = max(timestamp_ms, self._last_timestamp + 1)
        self._last_timestamp = timestamp_ms
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb_frame)
        return self._recognizer.recognize_for_video(image, timestamp_ms)

    def close(self) -> None:
        self._recognizer.close()
