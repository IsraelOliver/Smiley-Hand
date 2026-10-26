"""Backend X11 validado no Arch; imports Xlib somente ao ativar."""

import os

class X11MouseBackend:
    """Somente o worker acessa esta conexão X11; nunca captura/grava a tela."""

    def __init__(self):
        if os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
            raise RuntimeError("Mouse requer uma sessao X11")
        from Xlib import X, XK, display
        from Xlib.ext import xtest

        self.X, self.xtest = X, xtest
        self.display = display.Display()
        try:
            if not self.display.has_extension("XTEST"):
                raise RuntimeError("Extensao XTEST indisponivel")
            self.root = self.display.screen().root
            geometry = self.root.get_geometry()
            self.size = geometry.width, geometry.height
            self.escape = self.display.keysym_to_keycode(XK.string_to_keysym("Escape"))
        except Exception:
            self.display.close()
            raise

    def apply(self, x, y, click, allowed):
        keymap = self.display.query_keymap()
        if self.escape and keymap[self.escape // 8] & (1 << (self.escape % 8)):
            raise RuntimeError("ESC: mouse desativado; reative com M")
        # python-xlib não possui failsafe próprio: cantos físicos interrompem o modo.
        pointer = self.root.query_pointer()
        w, h = self.size
        if pointer.root_x in (0, w - 1) and pointer.root_y in (0, h - 1):
            raise RuntimeError("Seguranca: cursor em um canto; mova-o e reative com M")
        if not allowed():
            return None
        x, y = max(0, min(w - 1, x)), max(0, min(h - 1, y))
        if not click:
            self.xtest.fake_input(self.display, self.X.MotionNotify, x=x, y=y)
            self.display.flush()
        if click and allowed():
            try:
                self.xtest.fake_input(self.display, self.X.ButtonPress, 1)
            finally:
                self.xtest.fake_input(self.display, self.X.ButtonRelease, 1)
                self.display.flush()
        return (pointer.root_x, pointer.root_y) if click else (x, y)

    def close(self):
        self.display.close()
