"""Win32/Core Audio simulados; nenhum acesso ao hardware em qualquer sistema."""

import ctypes as C
import importlib
from pathlib import Path
import subprocess
import sys
from threading import get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hand_control import backends
from hand_control.backends.windows_mouse import WindowsMouseBackend, INPUT, POINT, prepare_dpi
from hand_control.backends.windows_audio import WindowsAudioBackend
from hand_control.volume_control import VolumeController
from hand_control.gestures import GestureEvent
from hand_control.camera import open_camera


class WindowsMouseTests(unittest.TestCase):
    def make_user(self):
        user = Mock()
        user.SetProcessDpiAwarenessContext.return_value = 1
        user.GetAsyncKeyState.return_value = 0
        user.GetSystemMetrics.side_effect = {76: -1920, 77: -200, 78: 3840, 79: 1280}.get
        position = [100, 100]

        def get_position(pointer):
            p = C.cast(pointer, C.POINTER(POINT)).contents
            p.x, p.y = position
            return 1

        def set_position(x, y):
            position[:] = [x, y]
            return 1

        user.GetCursorPos.side_effect = get_position
        user.SetCursorPos.side_effect = set_position
        user.SendInput.return_value = 2
        return user

    def test_input_structure_has_windows_abi_on_both_test_systems(self):
        self.assertEqual(C.sizeof(INPUT), 40 if C.sizeof(C.c_void_p) == 8 else 28)

    def test_virtual_desktop_mapping_negative_origin_and_bounds(self):
        for local, expected in (((0, 0), (-1920, -200)), ((99999, -10), (1919, -200))):
            user = self.make_user()
            backend = WindowsMouseBackend(user)
            self.assertEqual(backend.size, (3840, 1280))
            self.assertEqual(backend.apply(*local, False, lambda: True), expected)
            user.SetCursorPos.assert_called_once_with(*expected)

    def test_click_does_not_move_and_sends_only_left_button_pair(self):
        user = self.make_user()
        backend = WindowsMouseBackend(user)
        self.assertEqual(backend.apply(900, 900, True, lambda: True), (100, 100))
        user.SetCursorPos.assert_not_called()
        count, inputs, size = user.SendInput.call_args.args
        self.assertEqual((count, size), (2, C.sizeof(INPUT)))
        self.assertEqual((inputs[0].mi.dwFlags, inputs[1].mi.dwFlags), (2, 4))

    def test_cancelled_output_neither_moves_nor_clicks(self):
        user = self.make_user()
        self.assertIsNone(WindowsMouseBackend(user).apply(1, 1, True, lambda: False))
        user.SetCursorPos.assert_not_called()
        user.SendInput.assert_not_called()

    def test_esc_and_sendinput_failure_are_reported(self):
        user = self.make_user()
        backend = WindowsMouseBackend(user)
        user.GetAsyncKeyState.return_value = 0x8000
        with self.assertRaisesRegex(RuntimeError, 'ESC'):
            backend.apply(1, 1, True, lambda: True)
        user.SendInput.assert_not_called()
        user.GetAsyncKeyState.return_value = 0
        user.SendInput.side_effect = [1, 1]
        with self.assertRaisesRegex(RuntimeError, 'SendInput'):
            backend.apply(1, 1, True, lambda: True)
        self.assertEqual(user.SendInput.call_count, 2)
        self.assertEqual(user.SendInput.call_args.args[0], 1)

    def test_invalid_dpi_state_is_not_silently_used(self):
        user = self.make_user()
        user.SetProcessDpiAwarenessContext.return_value = 0
        user.GetAwarenessFromDpiAwarenessContext.return_value = 2
        prepare_dpi(user)
        user.GetAwarenessFromDpiAwarenessContext.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'DPI'):
            prepare_dpi(user)

    def test_failed_cursor_operation_reports_error(self):
        user = self.make_user()
        user.SetCursorPos.side_effect = None
        user.SetCursorPos.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'SetCursorPos'):
            WindowsMouseBackend(user).apply(1, 1, False, lambda: True)


class WindowsAudioTests(unittest.TestCase):
    def make_backend(self, value):
        device = SimpleNamespace(volume_percent=value)
        utilities, com = Mock(), Mock()
        utilities.GetSpeakers.return_value = device
        backend = WindowsAudioBackend(utilities, com)
        self.addCleanup(backend.close)
        return backend, device, com

    def test_increase_decrease_and_clamp(self):
        for initial, delta, expected in ((50, 5, 55), (50, -5, 45), (98, 5, 100), (2, -5, 0)):
            with self.subTest(initial=initial, delta=delta):
                backend, device, _ = self.make_backend(initial)
                value, command = backend.adjust(delta)
                self.assertEqual(value, expected)
                self.assertEqual(device.volume_percent, expected)
                self.assertIsNotNone(command)

    def test_boundaries_do_not_repeat_adjustments(self):
        for value, delta in ((100, 5), (0, -5)):
            backend, _, _ = self.make_backend(value)
            self.assertEqual(backend.adjust(delta), (value, None))

    def test_missing_device_and_invalid_value(self):
        backend, device, _ = self.make_backend(50)
        backend.utilities.GetSpeakers.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'saida'):
            backend.read()
        backend.utilities.GetSpeakers.return_value = device
        device.volume_percent = float('nan')
        with self.assertRaisesRegex(RuntimeError, 'invalido'):
            backend.adjust(5)

    def test_com_lifecycle_is_in_same_worker_even_on_exit_before_poll(self):
        calls = []
        com = SimpleNamespace(CoInitialize=lambda: calls.append(('init', get_ident())),
                              CoUninitialize=lambda: calls.append(('close', get_ident())))
        utilities = Mock()
        utilities.GetSpeakers.return_value = SimpleNamespace(volume_percent=50)
        controller = VolumeController(backend_factory=lambda: WindowsAudioBackend(utilities, com))
        controller.update(GestureEvent(None, 0, 0), now=0)
        controller._future.result(timeout=2)
        controller.close()
        controller.close()
        self.assertEqual([name for name, _ in calls], ['init', 'close'])
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertNotEqual(calls[0][1], get_ident())

    def test_com_closed_when_backend_read_fails(self):
        com, utilities = Mock(), Mock()
        utilities.GetSpeakers.side_effect = RuntimeError('audio perdido')
        controller = VolumeController(backend_factory=lambda: WindowsAudioBackend(utilities, com))
        self.addCleanup(controller.close)
        controller.update(GestureEvent(None, 0, 0), now=0)
        with self.assertRaises(RuntimeError):
            controller._future.result(timeout=2)
        com.CoUninitialize.assert_called_once()


class SelectionTests(unittest.TestCase):
    def test_mouse_factory_by_platform(self):
        for system, module, name in (('win32', 'windows_mouse', 'WindowsMouseBackend'),
                                     ('linux', 'x11_mouse', 'X11MouseBackend')):
            with patch.object(sys, 'platform', system), patch(f'hand_control.backends.{module}.{name}') as cls:
                self.assertIs(backends.create_mouse_backend(), cls.return_value)
                cls.assert_called_once()

    def test_audio_factory_by_platform(self):
        with patch.object(sys, 'platform', 'win32'), patch('hand_control.backends.windows_audio.WindowsAudioBackend') as cls:
            self.assertIs(backends.create_audio_backend(), cls.return_value)
        with patch.object(sys, 'platform', 'linux'), patch('hand_control.volume_control.AudioBackend.detect') as detect:
            self.assertIs(backends.create_audio_backend(), detect.return_value)

    def test_camera_backend_by_platform(self):
        cv2 = Mock()
        cv2.CAP_DSHOW, cv2.CAP_V4L2 = 700, 200
        for system, expected in (('win32', 700), ('linux', 200)):
            cv2.reset_mock()
            with patch.object(sys, 'platform', system), patch.dict('sys.modules', {'cv2': cv2}):
                capture = open_camera(0, 320, 240, 15)
                cv2.VideoCapture.assert_called_once_with(0, expected)
                capture.release()

    def test_foreign_libraries_are_not_imported_at_module_load(self):
        code = """
import sys
from hand_control import app, mouse_control, volume_control
from hand_control.backends import windows_mouse, windows_audio, x11_mouse
assert not any(name in sys.modules for name in ('Xlib', 'pycaw', 'comtypes'))
from hand_control.mouse_control import MouseController
mouse = MouseController(permitted=False)
mouse.handle_key(ord('m'))
mouse.close()
assert mouse.backend is None
"""
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_platform_requirement_markers(self):
        from packaging.requirements import Requirement
        requirements = [Requirement(line) for line in Path('requirements.txt').read_text().splitlines()
                        if line and not line.startswith('#')]
        selected = lambda platform: {r.name for r in requirements if not r.marker or r.marker.evaluate({'sys_platform': platform})}
        self.assertIn('python-xlib', selected('linux'))
        self.assertNotIn('pycaw', selected('linux'))
        self.assertIn('pycaw', selected('win32'))
        self.assertNotIn('python-xlib', selected('win32'))
