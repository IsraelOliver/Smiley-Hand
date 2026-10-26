"""Core Audio/pycaw; cada operação inteira permanece no worker de áudio."""

import math


class WindowsAudioBackend:
    def __init__(self, utilities=None, com=None):
        if utilities is None:
            import comtypes
            from pycaw.pycaw import AudioUtilities
            utilities, com = AudioUtilities, comtypes
        self.utilities, self.com = utilities, com
        self._closed = False
        if com is not None:
            com.CoInitialize()

    def _device(self):
        device = self.utilities.GetSpeakers()
        if device is None:
            raise RuntimeError('Nenhuma saida de audio padrao no Windows')
        return device

    def read(self):
        value = float(self._device().volume_percent)
        if not math.isfinite(value):
            raise RuntimeError('Core Audio retornou volume invalido')
        return max(0, min(100, value))

    def adjust(self, delta):
        if delta not in (-5, 5):
            raise ValueError('Passo deve ser +5 ou -5')
        device = self._device()
        current = float(device.volume_percent)
        if not math.isfinite(current):
            raise RuntimeError('Core Audio retornou volume invalido')
        target = max(0, min(100, current + delta))
        if abs(current - target) < 1e-6:
            return target, None
        device.volume_percent = target
        actual = float(device.volume_percent)
        return actual, f"Volume {'+5%' if delta > 0 else '-5%'} -> {actual:.0f}%"

    def close(self):
        if not self._closed and self.com is not None:
            self.com.CoUninitialize()
        self._closed = True
