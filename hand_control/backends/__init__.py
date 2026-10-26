"""Seleção de backends sem importar bibliotecas nativas de outro sistema."""

import sys


def create_mouse_backend():
    if sys.platform == 'win32':
        from .windows_mouse import WindowsMouseBackend
        return WindowsMouseBackend()
    if sys.platform.startswith('linux'):
        from .x11_mouse import X11MouseBackend
        return X11MouseBackend()
    raise RuntimeError('Mouse suportado somente em Windows e Linux X11')


def create_audio_backend():
    if sys.platform == 'win32':
        from .windows_audio import WindowsAudioBackend
        return WindowsAudioBackend()
    if sys.platform.startswith('linux'):
        from ..volume_control import AudioBackend
        return AudioBackend.detect()
    raise RuntimeError('Audio suportado somente em Windows e Linux')
