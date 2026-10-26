"""Download explícito do modelo oficial, sem dependências externas."""

from pathlib import Path
import shutil
from urllib.error import URLError
from urllib.request import urlopen
import zipfile

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "gesture_recognizer.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/1/gesture_recognizer.task"
)


def validate_model(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as bundle:
            required = {"hand_landmarker.task", "hand_gesture_recognizer.task"}
            if not required.issubset(bundle.namelist()) or bundle.testzip() is not None:
                raise ValueError("bundle incompleto ou corrompido")
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise RuntimeError(
            f"Modelo inválido ou ausente: {path}. "
            "Execute .venv/bin/python -m hand_control --download-model. "
            "Se estiver corrompido, remova apenas esse arquivo e baixe novamente."
        ) from exc


def download_model(path: Path = DEFAULT_MODEL) -> None:
    if path.exists():
        validate_model(path)
        print(f"Modelo já disponível: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    try:
        print(f"Baixando modelo oficial para {path}...", flush=True)
        with urlopen(MODEL_URL, timeout=30) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=64 * 1024)
        validate_model(partial)
        partial.replace(path)
    except (OSError, URLError, RuntimeError) as exc:
        raise RuntimeError(
            f"Falha ao baixar o modelo: {exc}. "
            "Verifique internet/DNS e tente novamente; consulte o README para download manual."
        ) from exc
    finally:
        partial.unlink(missing_ok=True)
    print(f"Modelo pronto: {path}")
