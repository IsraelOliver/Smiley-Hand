"""Captura V4L2 no Linux e DirectShow no Windows, com buffer curto."""

import sys


def open_camera(index: int, width: int, height: int, fps: int):
    import cv2

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
    capture = cv2.VideoCapture(index, backend)
    try:
        if not capture.isOpened():
            raise RuntimeError(
                f"Não foi possível abrir a câmera {index} (/dev/video{index} no Linux). Verifique conexão, "
                "permissões e se outro programa usa a câmera. "
                "Tente --camera N; no Linux, liste com v4l2-ctl --list-devices."
            )
        # Alguns drivers ignoram estas propriedades; o loop também limita tamanho/FPS.
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture
    except Exception:
        capture.release()
        raise
