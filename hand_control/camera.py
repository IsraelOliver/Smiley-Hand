"""Captura V4L2 com buffer curto."""


def open_camera(index: int, width: int, height: int, fps: int):
    import cv2

    capture = cv2.VideoCapture(index, cv2.CAP_V4L2)
    try:
        if not capture.isOpened():
            raise RuntimeError(
                f"Não foi possível abrir /dev/video{index}. Verifique conexão, "
                "permissões e se outro programa usa a câmera. "
                "Liste os dispositivos com v4l2-ctl --list-devices e tente --camera N."
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
