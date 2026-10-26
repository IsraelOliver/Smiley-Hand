"""Win32 documentado via ctypes, carregado apenas no Windows/ativação."""

import ctypes as C
import sys

LONG, DWORD, WORD, ULONG_PTR = C.c_int32, C.c_uint32, C.c_uint16, C.c_size_t


class POINT(C.Structure):
    _fields_ = [('x', LONG), ('y', LONG)]


class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', LONG), ('dy', LONG), ('mouseData', DWORD),
                ('dwFlags', DWORD), ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk', WORD), ('wScan', WORD), ('dwFlags', DWORD),
                ('time', DWORD), ('dwExtraInfo', ULONG_PTR)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [('uMsg', DWORD), ('wParamL', WORD), ('wParamH', WORD)]


class INPUTUNION(C.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(C.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', DWORD), ('data', INPUTUNION)]


def load_user32():
    if sys.platform != 'win32':
        raise RuntimeError('Win32 indisponivel neste sistema')
    user = C.WinDLL('user32', use_last_error=True)
    signatures = {
        'SetCursorPos': ([C.c_int, C.c_int], C.c_int),
        'GetCursorPos': ([C.POINTER(POINT)], C.c_int),
        'GetSystemMetrics': ([C.c_int], C.c_int),
        'GetAsyncKeyState': ([C.c_int], C.c_int16),
        'SendInput': ([C.c_uint, C.POINTER(INPUT), C.c_int], C.c_uint),
        'SetProcessDpiAwarenessContext': ([C.c_void_p], C.c_int),
        'GetThreadDpiAwarenessContext': ([], C.c_void_p),
        'GetAwarenessFromDpiAwarenessContext': ([C.c_void_p], C.c_int),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(user, name)
        fn.argtypes, fn.restype = args, result
    return user


def prepare_dpi(user=None):
    """Chamar antes do OpenCV; não altera configuração global ou escala do sistema."""
    user = user or load_user32()
    if not user.SetProcessDpiAwarenessContext(C.c_void_p(-4)):
        context = user.GetThreadDpiAwarenessContext()
        if user.GetAwarenessFromDpiAwarenessContext(context) != 2:
            raise RuntimeError('Nao foi possivel ativar DPI por monitor; reinicie fora de outro host grafico')


class WindowsMouseBackend:
    def __init__(self, user=None):
        self.user = user or load_user32()
        prepare_dpi(self.user)
        self.origin = (self.user.GetSystemMetrics(76), self.user.GetSystemMetrics(77))
        self.size = (self.user.GetSystemMetrics(78), self.user.GetSystemMetrics(79))
        if min(self.size) < 2:
            raise RuntimeError('Area virtual de monitores invalida')

    def _position(self):
        point = POINT()
        if not self.user.GetCursorPos(C.byref(point)):
            raise RuntimeError('GetCursorPos falhou')
        return point.x, point.y

    def apply(self, x, y, click, allowed):
        if self.user.GetAsyncKeyState(0x1B) & 0x8000:
            raise RuntimeError('ESC: mouse desativado; reative com M')
        current = self._position()
        left, top = self.origin
        w, h = self.size
        if current[0] in (left, left + w - 1) and current[1] in (top, top + h - 1):
            raise RuntimeError('Seguranca: cursor no canto; mova-o e reative com M')
        if not allowed():
            return None
        if click:
            # Clique no cursor parado, nunca na posição do indicador recolhido.
            inputs = (INPUT * 2)()
            inputs[0].type = inputs[1].type = 0
            inputs[0].mi.dwFlags, inputs[1].mi.dwFlags = 0x0002, 0x0004
            if not allowed():
                return None
            sent = self.user.SendInput(2, inputs, C.sizeof(INPUT))
            if sent != 2:
                # Se só a pressão foi entregue, tenta liberar sem outra pressão.
                if sent == 1:
                    self.user.SendInput(1, C.pointer(inputs[1]), C.sizeof(INPUT))
                raise RuntimeError('SendInput falhou (sessao/permissao UIPI); nao eleve privilegios')
        else:
            x, y = left + max(0, min(w - 1, x)), top + max(0, min(h - 1, y))
            if not self.user.SetCursorPos(x, y):
                raise RuntimeError('SetCursorPos falhou')
        return self._position()

    def close(self):
        pass
