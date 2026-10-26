"""Importações de CI, sem abrir câmera, display ou dispositivo de áudio."""

import importlib
import pkgutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hand_control

for module in pkgutil.walk_packages(hand_control.__path__, 'hand_control.'):
    importlib.import_module(module.name)
for dependency in ('cv2', 'mediapipe', 'numpy'):
    importlib.import_module(dependency)
if sys.platform == 'win32':
    from pycaw.pycaw import AudioUtilities
    import comtypes
    assert 'Xlib' not in sys.modules
elif sys.platform.startswith('linux'):
    from Xlib.ext import xtest
    assert 'pycaw' not in sys.modules and 'comtypes' not in sys.modules
print(f'Importacoes OK: {sys.platform}, Python {sys.version.split()[0]}; nenhum backend instanciado.')
